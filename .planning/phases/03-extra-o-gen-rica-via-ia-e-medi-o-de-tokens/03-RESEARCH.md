# Phase 3: Extração Genérica via IA e Medição de Tokens - Research

**Researched:** 2026-06-16
**Domain:** Integração de motor de extração via IA (OpenAI Responses API) com a fila/worker SQLite e a máquina de estados existentes (Fases 1–2)
**Confidence:** HIGH (integração com código existente — lido linha a linha; stack já travada no AI-SPEC e confirmada no PyPI)

> **Esta pesquisa é COMPLEMENTAR ao AI-SPEC.** O AI-SPEC (`03-AI-SPEC.md`) já travou framework (Responses API + Structured Outputs), schema genérico (`ExtractionResult` = `list[ExtractedField]` + `full_text` + `doc_type_guess`), caminho texto-nativo-vs-visão, `AsyncOpenAI`, tunables de `config.py` e estratégia de eval. **NÃO duplico nada disso.** Esta pesquisa resolve os **pontos de integração com o CÓDIGO EXISTENTE** e as **armadilhas específicas** que o planner precisa endereçar antes de planejar tarefas.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Extração da Fase 3 é **genérica** (IA lê e devolve o que encontrar, sem template). Fallback universal do motor.
- **D-02:** Saída **estruturada (JSON) com schema genérico**: pares `dado→valor` + texto integral + palpite de tipo com confiança.
- **D-03:** Extração fica **atrás de um roteador/interface** (seam). Nunca "sempre chama IA" cravado. Fases 4 (template casado) e 7 (determinístico→nativo→IA) plugam o atalho local aqui. **Ponto de costura arquitetural mais importante da fase.**
- **D-04:** Alavanca de custo: PDF com texto nativo → manda **TEXTO** à IA (barato); escaneado/imagem → **render página → IA por visão** (caro). A IA estrutura em ambos.
- **D-05:** Custo-zero por layout conhecido **não é desta fase** (Fase 4 + 7). A Fase 3 só não pode bloquear (D-03).
- **D-06:** Persistir o **texto nativo extraído E o resultado da extração** ligados ao documento (base para Fases 4/7 construírem layouts).
- **D-07:** Sucesso → `PROCESSANDO` com `last_completed_step="extraido"`. **NUNCA `CONCLUIDO`.**
- **D-08:** Falha (recusa ou esgotou retries) → fila faz retry/backoff (Fase 2); ao esgotar → **`FALHA`** (dead-letter, re-tentável; CAS preserva original).
- **D-09:** **Sem gate de qualidade.** Extração "fraca" persiste e segue para `extraido`. Score/revisão são Fase 5.
- **D-10:** Cada chamada registra `prompt_tokens + completion_tokens` de `response.usage` no modelo **`Usage`** (já existe), ligado ao `Document`, `step="extract"`.
- **D-11:** **PyMuPDF (fitz)** para texto nativo + render. Uso interno → AGPL sem ônus (premissa a confirmar — ver Open Questions).

### Claude's Discretion
- Estrutura concreta do **modelo `Extraction`** e formato exato do schema genérico (já guiado pelo AI-SPEC §4b.1).
- **Tipos de campo:** manter saída `dado→valor` flexível (sem tipagem por campo — isso é Fase 4).
- **Heurística "tem texto nativo suficiente"** (texto vs render por página).
- **Modelo OpenAI** vigente e parâmetros (expor em `config.py` como tunáveis).
- **Granularidade** de bloco multi-página (sugestão: 1 chamada por `Document`).
- **Enfileiramento e dispatch por `step`** e chave de idempotência da extração.
- Tratamento de **chave OpenAI ausente/inválida**.

### Deferred Ideas (OUT OF SCOPE)
- **EXT-04** (schema derivado de template + validações de campo) → **Fase 4**. NÃO planejar aqui.
- Identificação/classificação por presença de dados → Fase 4 (TPL-03).
- Extração local custo-zero + roteamento determinístico→nativo→IA (EXT-03, EXT-05) → Fase 7.
- Validações de domínio (DV CNPJ/Módulo 11, datas plausíveis) → Fase 4/5.
- Painel de consumo de tokens na UI (INT2-02) → v2. Fase 3 só persiste.
- Stack permissiva de PDF (pypdfium2 + pdfplumber) → fallback se uso virar distribuição.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXT-01 | Texto nativo local (PDF com texto extraível → input de texto barato) | PyMuPDF `page.get_text()` + heurística texto-vs-visão (§Pattern 2). Texto persistido em `Extraction.full_text` (D-06). |
| EXT-02 | Extração genérica via IA da OpenAI (schema `dado→valor` + texto + palpite de tipo) | Responses API + `text_format=ExtractionResult` (AI-SPEC §3/§4b.1). Despacho via job `step="extract"` (§Integration Point 1). |
| USE-02 / SC4 | Medição de tokens por documento | `response.usage` → modelo `Usage` existente, `step="extract"` (§Integration Point 4). |

⚠️ **EXT-04 RE-ESCOPADO → Fase 4.** NÃO planejar schema-derivado-de-template nem validações de campo nesta fase.
</phase_requirements>

## Summary

Esta fase adiciona o **núcleo do motor de extração** a um pipeline já maduro (Fases 1–2: CAS, fila SQLite durável, máquina de estados, worker async in-process). O trabalho de pesquisa NÃO é descobrir como chamar a OpenAI (já travado no AI-SPEC) — é **costurar a extração nos seams existentes sem violar as garantias de idempotência, atomicidade e integridade de arquivo** que as Fases 1–2 estabeleceram.

Três descobertas dominam o planejamento:

1. **Conflito async-vs-thread no worker (a maior armadilha).** O worker hoje despacha `_process_job_blocking` via `asyncio.to_thread` (porque o split de PDF é CPU-bound e síncrono). Mas o caminho de extração é **`async` (`AsyncOpenAI` + `await`)**. Chamar `await` dentro de uma thread (`to_thread`) quebra — não há event loop na thread. **O dispatch por `step` precisa bifurcar:** `ingest` continua em thread; `extract` roda como coroutine no event loop do worker (ou usa `asyncio.run` numa thread dedicada, o que o AI-SPEC §4b adverte contra). Esta é a decisão arquitetural nº 1 que o planner deve resolver.

2. **A chave de idempotência da fila é `(original_hash, step)`, mas a extração é por bloco (`Document.content_hash`).** Um original gera N blocos; cada bloco precisa de seu próprio job `extract`. A constraint `uq_jobs_hash_step` UNIQUE em `(original_hash, step)` **colidiria** se todos os blocos usassem o `original_hash`. A solução de menor risco: **usar o `Document.content_hash` do bloco como `original_hash` do job de extract** (o nome do campo é "original_hash" mas semanticamente é "a identidade de conteúdo deste trabalho"). Cada bloco vira `(content_hash_do_bloco, "extract")` — único e idempotente, sem alterar o schema da fila.

3. **Quem enfileira o extract?** Hoje `ingest_stage` deixa blocos em `aguardando_extracao` e **não enfileira nada**. Há duas opções limpas: (a) `ingest_stage` enfileira um job `extract` por bloco no mesmo commit que cria os Documents; ou (b) um sweep no startup/loop que pega Documents em `aguardando_extracao` sem job e os enfileira. Opção (a) é mais direta e atômica — recomendada.

**Primary recommendation:** Adicionar um `extract_stage` async espelhando `ingest_stage` (isolável, sem HTTP, commit atômico), enfileirado por bloco em `ingest_stage` com chave `(block.content_hash, "extract")`, e bifurcar `worker._run_once` por `step` para rodar `extract` como coroutine no loop (não em `to_thread`). Persistir `Extraction` (Alembic 0003) + `Usage(step="extract")` no mesmo commit que avança o estado para `extraido` ANTES de `mark_done` (idempotência = não cobrar duas vezes).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Detecção texto-nativo-vs-escaneado | Backend / pipeline local (PyMuPDF) | — | Decisão local sobre o bloco lido do CAS; não envolve IA. |
| Render página → imagem | Backend / pipeline local (PyMuPDF) | — | CPU-bound local; produz bytes para `input_image`. |
| Extração estruturada (dado→valor) | API externa (OpenAI Responses) | Backend (router/seam D-03) | A IA preenche o schema; o seam decide se chama IA (Fases 4/7 plugam atalho). |
| Roteamento de extração (D-03) | Backend / `extraction/router.py` | — | Interface que Fases 4/7 estendem. Default v1: "texto-vs-visão sempre IA". |
| Medição de tokens | Backend / DB (`Usage`) | — | Lê `response.usage`, persiste; sem tier externo além da leitura. |
| Persistência do resultado + texto nativo | Backend / DB (`Extraction`, Alembic) | — | Base D-06 para Fases 4/7. |
| Enfileiramento/dispatch por step | Backend / fila SQLite + worker | — | Reusa fila durável da Fase 2; bifurca por step. |
| Transição de estado pós-extração | Backend / `state_machine` | — | `PROCESSANDO` + `last_completed_step="extraido"` (D-07) / `FALHA` (D-08). |

## Standard Stack

> Stack **já travada no AI-SPEC §2/§3 e no CLAUDE.md**. Aqui apenas confirmo versões contra o PyPI (2026-06-16) e o que falta instalar.

### Core (a adicionar nesta fase)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| openai | `2.41.1` | Responses API + Structured Outputs (`AsyncOpenAI`) | NÃO instalado — adicionar `openai==2.41.*` |
| PyMuPDF | `1.27.2.3` | `page.get_text()` (texto nativo) + `page.get_pixmap().tobytes("png")` (render visão) | NÃO instalado — adicionar `PyMuPDF==1.27.*` |
| pydantic | `2.13.4` | `ExtractionResult` como `text_format` (JSON Schema strict) | JÁ instalado (pin `2.13.4` em pyproject) |

### Supporting (dev)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| respx | `0.23.1` | Mock de OpenAI nos testes (sem gastar token em CI) | NÃO instalado — adicionar ao grupo `dev` |

**Version verification (PyPI, 2026-06-16):**
- `openai` → última `2.41.1` (pin `2.41.*` resolve para ela). **[VERIFIED: PyPI]** ⚠️ *nome confirmado via CLAUDE.md/AI-SPEC (fonte autoritativa OpenAI) + PyPI.*
- `PyMuPDF` → última `1.27.2.3` (pin `1.27.*` resolve para ela; wheels para Python 3.12). **[VERIFIED: PyPI]**
- `respx` → última `0.23.1`. **[VERIFIED: PyPI]** ⚠️ *nome confirmado via CLAUDE.md (fonte do projeto) + PyPI.*

**Installation:**
```bash
# Backend (gerido por uv) — adicionar ao backend/pyproject.toml [project.dependencies]
uv add "openai==2.41.*" "PyMuPDF==1.27.*"
# Grupo dev
uv add --group dev respx
```
> ⚠️ `import` de PyMuPDF é `import fitz` (não `import pymupdf`), apesar do nome de pacote `PyMuPDF`. **[CITED: AI-SPEC §3 Core Imports]**

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Responses API | Chat Completions `chat.completions.parse` | Mesmo SDK/Pydantic; CLAUDE.md prescreve Responses para projeto novo. Fallback só se recurso da conta não migrou. |
| PyMuPDF (render+texto) | pypdfium2 (BSD) + pdfplumber | Só se uso virar distribuição/venda (AGPL). Deferido. |
| respx | unittest mock manual do SDK | respx é o padrão do projeto (CLAUDE.md "mockar OpenAI"). |

## Package Legitimacy Audit

> slopcheck não disponível neste ambiente (sem rede para `pip install slopcheck`). Os três pacotes são **estabelecidos, de fonte oficial autoritativa** (OpenAI SDK oficial; PyMuPDF mantido pela Artifex; respx é o mock padrão de httpx) e **já prescritos no CLAUDE.md** do projeto — não introduzidos por esta pesquisa. Confirmados no PyPI com as versões exatas dos pins. Marcados `[VERIFIED: PyPI]` por dupla confirmação (fonte autoritativa do projeto + registro correto).

| Package | Registry | Idade | Source Repo | Verificação | Disposition |
|---------|----------|-------|-------------|-------------|-------------|
| openai | PyPI | anos (SDK oficial) | github.com/openai/openai-python | PyPI 2.41.1 + CLAUDE.md | Approved |
| PyMuPDF | PyPI | anos | github.com/pymupdf/PyMuPDF (Artifex) | PyPI 1.27.2.3 + CLAUDE.md | Approved |
| respx | PyPI | anos | github.com/lundberg/respx | PyPI 0.23.1 + CLAUDE.md | Approved |

**Packages removidos (slopcheck SLOP):** nenhum.
**Packages flagged (SUS):** nenhum.

## Architecture Patterns

### System Architecture Diagram

```
                      [ Fase 2: ingest_stage cria Documents ]
                                     │
              (NOVO) enqueue job step="extract" por bloco
                  key = (block.content_hash, "extract")
                                     │
                                     ▼
                          ┌──────────────────┐
                          │  fila SQLite      │  (repo.claim_next — atômico, 1 writer)
                          │  (jobs table)     │
                          └────────┬─────────┘
                                   │ row.step
                  ┌────────────────┴─────────────────┐
                  │ step=="ingest"                    │ step=="extract"   (NOVO ramo)
                  ▼                                    ▼
        asyncio.to_thread                    await extract_stage(...)   ← coroutine no loop
        (_process_job_blocking)              (NÃO to_thread — é async)
        process_ingest (sync)                         │
                                                      ▼
                                    ┌─────────────────────────────────┐
                                    │ extract_stage(session, doc)     │
                                    │  1. cas.read_bytes(content_hash)│
                                    │  2. router.choose() ── D-03 seam│
                                    │  3. pdf_io: get_text/render PNG │
                                    │     heurística texto-vs-visão   │
                                    │  4. await openai_client.extract │──► OpenAI Responses API
                                    │  5. persist Extraction +        │◄── response.output_parsed
                                    │     full_text + Usage(extract)  │    response.usage
                                    │  6. state_machine.transition →  │
                                    │     PROCESSANDO/"extraido"      │
                                    └────────────────┬────────────────┘
                                                     │ (commit ANTES de mark_done)
                                                     ▼
                                          repo.mark_done(job)
                                  (recusa/erro → schedule_retry → FALHA, D-08)
```

### Recommended Project Structure
> Do AI-SPEC §3 (Recommended Project Structure) — copiado para referência; nenhuma re-pesquisa.
```
backend/app/
├── extraction/
│   ├── router.py        # D-03: seam de extração — Fases 4/7 plugam atalho local
│   ├── openai_client.py # AsyncOpenAI: responses.parse, _unwrap, leitura de usage
│   ├── schema.py        # ExtractionResult (Pydantic) — schema genérico (AI-SPEC §4b.1)
│   ├── pdf_io.py        # PyMuPDF: get_text + heurística "tem texto suficiente" + render PNG
│   └── stage.py         # extract_stage async, isolável, idempotente, commit atômico
├── models/
│   └── extraction.py    # NOVO modelo Extraction (Alembic 0003)
alembic/versions/0003_*.py  # cria tabela extractions
```

### Pattern 1: Dispatch por step no worker (bifurcação async-vs-thread)
**What:** `_run_once` lê `row.step` e roteia. `ingest` mantém o caminho `to_thread` atual; `extract` roda como coroutine `await`ada no event loop (o worker já está no loop).
**When to use:** Sempre — é o ponto de entrada do trabalho de extração.
**Why:** `AsyncOpenAI` exige um event loop ativo. `asyncio.to_thread` roda código **síncrono** numa thread sem loop — `await client.responses.parse(...)` lá dentro daria `RuntimeError`. O AI-SPEC §4b alerta explicitamente: "Dentro do worker, sempre `await`, nunca `asyncio.run()`."
**Example (esqueleto — o planner detalha):**
```python
# worker._run_once, após claim_next
if row.step == "ingest":
    await asyncio.to_thread(_process_job_blocking, engine, original_hash=..., payload=row.payload)
elif row.step == "extract":
    # extract_stage é async; roda no loop do worker (NÃO to_thread).
    # PyMuPDF (get_text/render) é CPU-bound — encapsular SÓ a parte fitz em to_thread
    # de DENTRO do extract_stage, mantendo a chamada OpenAI no loop.
    await extract_stage(engine, content_hash=row.original_hash, payload=row.payload)
```
> **Sub-armadilha (CPU-bound dentro do async):** `page.get_text()` e `get_pixmap()` são CPU/IO-bound síncronos. Para não bloquear o event loop durante render de muitas páginas, envolver **apenas a parte PyMuPDF** em `await asyncio.to_thread(...)` de dentro do `extract_stage`, deixando a chamada OpenAI como `await` direto. O worker hoje já faz `to_thread` para o split pela mesma razão (Pitfall 4 do worker.py).

### Pattern 2: Heurística texto-nativo-vs-visão (EXT-01 / D-04)
**What:** Para cada página, `page.get_text()` e medir o texto extraível. Se a soma (ou por-página) ultrapassa um limiar configurável → caminho texto; senão → render+visão.
**When to use:** No `router.choose()` / `pdf_io`, antes de decidir o content block da chamada.
**Example:**
```python
# pdf_io.py — esqueleto
import fitz
def extract_text_and_decide(pdf_bytes: bytes, min_chars_per_page: int) -> tuple[str, str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts = [page.get_text() for page in doc]
    total_chars = sum(len(t.strip()) for t in texts)
    full_text = "\n".join(texts)
    route = "native_text" if total_chars >= min_chars_per_page * doc.page_count else "vision"
    return full_text, route
```
> **Imagens (JPG/PNG):** a Fase 2 trata imagem como 1 bloco = bytes do arquivo (não PDF). `fitz.open(stream=..., filetype="pdf")` falha para esses. O `extract_stage` precisa detectar o tipo do blob (PDF vs imagem) e, para imagem, ir direto ao caminho visão (a imagem já é a página). **Decidir no planejamento como distinguir** (extensão não está no CAS — só o hash; talvez ler magic bytes, ou guardar o tipo no `Document`). É uma lacuna de integração concreta.

### Anti-Patterns to Avoid
- **`await` dentro de `asyncio.to_thread`:** não há loop na thread → `RuntimeError`. (Ver Pattern 1.)
- **`asyncio.run(extract_stage(...))` de dentro do worker:** o worker já está num loop → `RuntimeError: asyncio.run() cannot be called from a running event loop`. (AI-SPEC §4b.)
- **`mark_done` antes de persistir Extraction+Usage:** um crash entre `mark_done` e o commit faria reprocessar = **cobrança dupla**. Persistir TUDO no mesmo commit, ANTES de `mark_done`.
- **Setar `doc.state` direto:** sempre via `transition` (allowlist). O worker.py já documenta isto como Anti-Pattern.
- **Usar `original_hash` do original para o job de extract:** colidiria com `uq_jobs_hash_step` entre blocos do mesmo original. Usar o `content_hash` do bloco.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry/backoff/dead-letter da extração | Loop de retry no `extract_stage` | `repo.schedule_retry` da fila (Fase 2) | Já implementa backoff exponencial+jitter, dead-letter→FALHA. AI-SPEC §4b: "não reimplementar retry no request". |
| Claim atômico de job | SELECT+UPDATE manual | `repo.claim_next` (`UPDATE ... RETURNING`) | Atômico, resume-safe, já testado. |
| Geração de JSON Schema da IA | Schema dict à mão | `text_format=ExtractionResult` (Pydantic) | SDK gera schema strict, valida e devolve objeto tipado. |
| Validação de conformidade da saída | Checagem manual de campos | Structured Outputs (strict mode) | Garantido pela API; `output_parsed` já validado. |
| Idempotência de reprocessamento | Flag custom no Document | `(content_hash, step)` UNIQUE da fila + checar Extraction existente | A barreira já existe; só estender o uso. |
| Leitura de texto/render de PDF | Parser próprio | PyMuPDF `get_text`/`get_pixmap` | Maduro, rápido, já prescrito (D-11). |
| Persistência imutável do bloco | Reescrever | `cas.read_bytes(content_hash)` | CAS já guarda o bloco; só ler. |

**Key insight:** Quase toda a "infraestrutura difícil" desta fase (fila durável, retry, atomicidade, máquina de estados, CAS, schema-via-Alembic) **já existe e foi testada nas Fases 1–2**. O trabalho da Fase 3 é **estender padrões existentes**, não construir novos. O único componente genuinamente novo é o cliente OpenAH + o `extract_stage` + o modelo `Extraction`.

## Runtime State Inventory

> Esta fase é **greenfield aditiva** (adiciona código/schema), não rename/refactor/migração de dados. Mas verifiquei estado runtime relevante à integração:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Documents em `PROCESSANDO`/`aguardando_extracao` criados pela Fase 2 ainda **sem job de extract** (a Fase 2 não enfileira extract). | Decisão de planejamento: o sweep/enqueue inicial precisa pegar Documents pré-existentes nesse estado, OU aceitar que só novos ingests enfileiram extract. Recomendo um sweep no startup do worker (análogo a `requeue_running`) que enfileira `extract` para Documents em `aguardando_extracao` sem job. |
| Live service config | Nenhum serviço externo com estado embutido (OpenAI é stateless por chamada). | None — verificado: OpenAI não guarda estado entre chamadas; cada extração é independente. |
| OS-registered state | Nenhum. Worker/watcher sobem no `lifespan` do FastAPI (não há Task Scheduler/systemd). | None — verificado em main.py. |
| Secrets/env vars | `openai_api_key: SecretStr` já existe em `Settings`. Novos tunables `OPENAI_EXTRACT_*` (env). | Adicionar os tunables em config.py; chave já presente. |
| Build artifacts | `openai` e `PyMuPDF` ausentes do venv (não em pyproject). | `uv add` + reinstalar deps no ambiente de execução. |

**Nada encontrado em "Live service config" e "OS-registered state":** confirmado por leitura de `main.py` (lifespan) e `config.py`.

## Common Pitfalls

### Pitfall 1: Async (OpenAI) dentro de thread (to_thread)
**What goes wrong:** O caminho de extração é `await`. Despachar via `asyncio.to_thread` (como o ingest faz) roda código síncrono numa thread sem event loop → `await client.responses.parse(...)` levanta `RuntimeError`.
**Why it happens:** O worker foi desenhado para trabalho CPU-bound síncrono (split de PDF). A extração mistura CPU-bound (PyMuPDF) com async (OpenAI).
**How to avoid:** Bifurcar `_run_once` por `step`. `extract` roda como coroutine no loop; só a parte PyMuPDF vai a `to_thread` de dentro do `extract_stage`.
**Warning signs:** `RuntimeError: ... no running event loop` / `asyncio.run() cannot be called from a running event loop`.

### Pitfall 2: Colisão de idempotência entre blocos do mesmo original
**What goes wrong:** Se todos os N blocos de um original usarem `original_hash` na chave do job de extract, `uq_jobs_hash_step (original_hash, "extract")` aceita só **um** — os outros blocos nunca são extraídos.
**Why it happens:** O campo da fila chama-se `original_hash`, mas a extração é por **bloco** (`Document.content_hash`), não por original.
**How to avoid:** Usar o `content_hash` do bloco como `original_hash` do job de extract. Cada bloco → `(block.content_hash, "extract")`, único. (Semântica: "identidade de conteúdo deste trabalho".)
**Warning signs:** Originais multi-bloco com só o primeiro bloco extraído.

### Pitfall 3: Cobrança dupla por mark_done prematuro
**What goes wrong:** Crash entre `mark_done` e o commit de Extraction/Usage → resume reprocessa o bloco → nova chamada paga à IA (Failure Mode 3 do AI-SPEC).
**Why it happens:** Ordem errada de operações; `mark_done` e persistência em commits separados.
**How to avoid:** (1) Persistir `Extraction` + `Usage` + `transition` no **mesmo commit**, ANTES de `mark_done`. (2) No início do `extract_stage`, checar se já existe `Extraction` para o `content_hash` → se sim, no-op (não re-chamar IA). O `worker` hoje já chama `mark_done` num bloco separado após sucesso — manter, mas garantir que o trabalho já está comitado.
**Warning signs:** Duas linhas em `Usage` para o mesmo `document_id`/`step="extract"`.

### Pitfall 4: `output_parsed is None` (recusa) não é exceção
**What goes wrong:** O modelo recusa → `output_parsed` volta `None` (não levanta). Se o código assume objeto, dá `AttributeError`; se ignora, persiste lixo.
**Why it happens:** Comportamento do SDK em recusa (AI-SPEC §3 Pitfall 2).
**How to avoid:** Checar explicitamente `if parsed is None: raise ExtractionRefused(...)` → o worker captura, `schedule_retry`, e ao esgotar → `FALHA` (D-08). Logar o motivo do `refusal` + `document_id` — **nunca a chave nem o conteúdo** (Failure Mode 5).
**Warning signs:** Documents indo a FALHA com `last_error` de recusa; ou Extractions com campos vazios.

### Pitfall 5: Blob de imagem tratado como PDF
**What goes wrong:** `fitz.open(stream=blob, filetype="pdf")` falha quando o blob é JPG/PNG (a Fase 2 ingere imagem como 1 bloco = bytes do arquivo). O CAS guarda só o hash — não a extensão.
**Why it happens:** O `extract_stage` lê do CAS por hash e não sabe o tipo do conteúdo.
**How to avoid:** Detectar tipo (magic bytes: `%PDF` vs JPEG/PNG signatures) no `extract_stage`, ou persistir o tipo/extensão no `Document` ao ingerir. Imagem → caminho visão direto (a imagem já é a página). **Decisão de planejamento.**
**Warning signs:** Erros de PyMuPDF ao abrir blobs de imagem; Documents de imagem indo a FALHA.

### Pitfall 6: `max_output_tokens` ausente trunca/explode
**What goes wrong:** Sem teto, o `full_text` na saída pode inflar tokens; com teto baixo, documento longo é truncado no meio (Failure Mode 5 do domínio).
**Why it happens:** O schema inclui `full_text` que ocupa output tokens.
**How to avoid:** `openai_extract_max_output_tokens` tunável (AI-SPEC sugere 4096 default), ajustar por observação. Flag se `usage.output_tokens ≈ max_output_tokens` (sinal de truncamento, dim 6 do eval).
**Warning signs:** `full_text` cortado; `output_tokens` colado no teto.

## Code Examples

> A sintaxe da Responses API, o schema `ExtractionResult` e os fluxos de chamada estão **completos no AI-SPEC §3 e §4b.1** — não duplico. Aqui só os pontos de **integração com o código existente** que o AI-SPEC não cobre.

### Enfileirar extract por bloco (em ingest_stage, no commit que cria Documents)
```python
# DENTRO do loop de blocos de process_ingest, após criar cada Document:
# (esqueleto — o planner decide se enfileira aqui ou num sweep separado)
from app.queue import repo
payload = json.dumps({"content_hash": block_hash})
# Mesmo session/commit que cria os Documents (atomicidade CR-02).
# OBS: repo.enqueue faz seu PRÓPRIO commit hoje — o planner deve decidir se
# (a) adapta enqueue para não commitar, ou (b) enfileira após o commit dos Documents
# num passo separado idempotente. Ver Open Question 2.
repo.enqueue(session, original_hash=block_hash, step="extract", payload=payload)
```

### Gravar Usage no commit da extração (modelo existente)
```python
# Usage já existe: (document_id, step, prompt_tokens, completion_tokens, created_at)
from app.models.usage import Usage
session.add(Usage(
    document_id=doc.id,
    step="extract",
    prompt_tokens=response.usage.input_tokens,    # Responses API: input_tokens
    completion_tokens=response.usage.output_tokens, # Responses API: output_tokens
))
# OBS: o modelo Usage chama os campos prompt_tokens/completion_tokens (nomenclatura
# Chat Completions), mas a Responses API expõe input_tokens/output_tokens. Mapear
# input→prompt, output→completion na gravação. Documentar para não confundir.
```

### Avançar estado (state_machine existente)
```python
from app.pipeline.state_machine import transition
from app.models.enums import DocState
# Sucesso → PROCESSANDO continua, marcador "extraido" (D-07). NUNCA CONCLUIDO.
# PROCESSANDO→PROCESSANDO NÃO está na allowlist (auto-laço proibido) — então NÃO
# use transition() para "ficar em PROCESSANDO". Use mark_step() para só o marcador:
from app.pipeline.state_machine import mark_step
mark_step(session, doc, "extraido")   # mantém state=PROCESSANDO, atualiza marcador
```
> **Armadilha de integração concreta:** `transition(PROCESSANDO → PROCESSANDO)` **falha** (auto-laço não está na allowlist — ver `states.py` e o docstring de `transition`). Como o documento **permanece** em `PROCESSANDO` e só avança o marcador para `"extraido"`, o caminho de sucesso deve usar **`mark_step(session, doc, "extraido")`**, NÃO `transition`. O `transition` só entra no caminho de **FALHA** (`PROCESSANDO → FALHA`, que está na allowlist). O AI-SPEC §4 mostra `transition(... to_state=PROCESSANDO, completed_step="extraido")`, mas isso quebraria — **corrigir para `mark_step` no planejamento.** Esta é a discrepância mais importante entre o AI-SPEC e o código real.

### Modelo Extraction (novo — Alembic 0003)
```python
# backend/app/models/extraction.py — esqueleto (Claude's Discretion p/ campos exatos)
class Extraction(Base):
    __tablename__ = "extractions"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, unique=True, nullable=False
    )  # UNIQUE: 1 extração por bloco = idempotência (não re-extrair)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)   # list[ExtractedField] serializado
    full_text: Mapped[str] = mapped_column(Text, nullable=False)      # texto nativo (D-06)
    doc_type_guess: Mapped[str] = mapped_column(String, nullable=False)
    doc_type_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    route: Mapped[str] = mapped_column(String, nullable=False)        # "native_text"|"vision" (métrica D-04)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```
> **Lembrar de registrar em `app/models/__init__.py`** (autogenerate do Alembic depende disso — ver o `__init__.py` atual). E adicionar `relationship` recíproca em `Document` se desejado (opcional). Migração `0003` segue o padrão de `0002` (batch mode SQLite; cuidado com o trigger `trg_documents_updated_at` SÓ se tocar a tabela `documents`).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Chat Completions + JSON mode | Responses API + Structured Outputs | OpenAI mar/2025 | Schema garantido, `text_format=Pydantic`. Já travado no AI-SPEC. |
| `response.usage.prompt_tokens` | `response.usage.input_tokens`/`output_tokens` (Responses API) | Responses API | Mapear input→prompt, output→completion ao gravar em `Usage`. |
| watchdog/PyPDF2 | watchfiles/pikepdf+PyMuPDF | já no projeto | Sem mudança nesta fase. |

**Deprecated/outdated:** "JSON mode" (`response_format: json_object`) — não garante schema. Usar Structured Outputs (CLAUDE.md "What NOT to Use").

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Usar `content_hash` do bloco como `original_hash` do job de extract resolve a idempotência sem mudar o schema da fila. | Pitfall 2 / IP1 | Se o planner preferir alterar o schema (`document_id` no job), a migração 0003 cresce. Baixo risco — o approach proposto não mexe no schema. |
| A2 | `extract_stage` async rodando no loop do worker (com só PyMuPDF em `to_thread`) é a forma correta. | Pattern 1 | Alternativa (`asyncio.run` em thread dedicada) é desaconselhada pelo AI-SPEC mas possível; a escolhida é a recomendada. |
| A3 | Enfileirar extract dentro de `ingest_stage` é mais limpo que um sweep. | IP1 / OQ2 | Se `repo.enqueue` (que commita) quebrar a atomicidade do commit único do ingest, o sweep vira preferível. Ver OQ2. |
| A4 | Caminho de sucesso usa `mark_step("extraido")`, não `transition`, porque PROCESSANDO→PROCESSANDO não está na allowlist. | Code Examples | **Confirmado por leitura de states.py/state_machine.py** — não é assumido, é VERIFIED. Mantido aqui só para destacar a divergência com o AI-SPEC. |
| A5 | Blob de imagem precisa de detecção de tipo (magic bytes) no extract_stage. | Pitfall 5 | Se a Fase 2 já persistir o tipo no Document (não persiste hoje — verificado), seria trivial. Hoje exige magic bytes ou nova coluna. |
| A6 | "Uso interno" (D-11/AGPL) ainda não foi confirmado pelo dono do projeto; postura conservadora LGPD permanece. | User Constraints | Premissa meta, fora da Fase 3. Não bloqueia implementação; afeta postura de privacidade futura. |

## Open Questions

1. **Quem enfileira o extract: `ingest_stage` (inline) ou um sweep no worker?**
   - What we know: `ingest_stage` cria Documents num commit único atômico; `repo.enqueue` faz seu próprio commit (quebraria a atomicidade se chamado no meio).
   - What's unclear: Se enfileirar inline exige refatorar `enqueue` para não commitar, ou se um sweep idempotente pós-commit (pegar Documents `aguardando_extracao` sem job) é mais limpo e cobre também Documents legados.
   - Recommendation: **Sweep idempotente** no startup do worker (análogo a `requeue_running`) + opcionalmente enfileirar após o commit do ingest. Cobre Documents pré-existentes e mantém a atomicidade do ingest intacta. O planner decide.

2. **Como o `extract_stage` distingue PDF de imagem ao ler o blob do CAS?**
   - What we know: CAS guarda só `content_hash` → bytes. A Fase 2 ingere imagem como 1 bloco de bytes crus; PDF como blocos PDF.
   - What's unclear: Não há tipo/extensão persistido no `Document` nem no CAS.
   - Recommendation: Detectar por **magic bytes** no `extract_stage` (`%PDF-` → PDF; `\xFF\xD8` → JPEG; `\x89PNG` → PNG). Alternativa: adicionar coluna `content_type`/`source_ext` ao `Document` na migração 0003. Magic bytes é menos invasivo.

3. **Nomenclatura `Usage.prompt_tokens/completion_tokens` vs Responses `input_tokens/output_tokens`.**
   - What we know: O modelo `Usage` usa nomes da era Chat Completions; a Responses API expõe `input_tokens/output_tokens`.
   - What's unclear: Nada — é só mapeamento. Documentar para não confundir.
   - Recommendation: Mapear `input→prompt`, `output→completion` na gravação; comentar no código.

4. **Cached tokens do prompt caching contam onde?**
   - What we know: AI-SPEC §4b sugere `prompt_cache_key` para cachear o `instructions` fixo; `response.usage` pode trazer `input_tokens_details.cached_tokens`.
   - What's unclear: Se a cobrança por consumo deve descontar cached tokens (são mais baratos).
   - Recommendation: v1 — gravar `input_tokens`/`output_tokens` brutos em `Usage` (suficiente para SC4). Refinar custo com cached tokens é v2 (INT2-02, painel).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| openai SDK | EXT-02 (chamada à IA) | ✗ (não instalado) | alvo 2.41.* | nenhum — instalar |
| PyMuPDF (fitz) | EXT-01 (texto/render) | ✗ (não instalado) | alvo 1.27.* | pypdfium2 (deferido) |
| respx | testes/eval (CI sem token) | ✗ (não instalado) | alvo 0.23.* | mock manual |
| pydantic 2.13 | schema | ✓ | 2.13.4 (pin) | — |
| SQLite ≥ 3.35 | fila/migração | ✓ | 3.50.4 (confirmado no repo.py) | — |
| Chave OpenAI válida + internet | runtime da extração (não testes) | depende da instância | — | tratamento de chave ausente/inválida → FALHA + log (sem vazar chave) |

**Missing dependencies with no fallback:** `openai` e `PyMuPDF` — instalar via `uv add` (passo de tarefa).
**Chave OpenAI ausente/inválida:** não bloqueia testes (respx mocka); em runtime, a chamada falha → fila faz backoff → `FALHA`. Tratar `AuthenticationError` distintamente (não é retryável — chave inválida não melhora com retry; considerar dead-letter imediato ou alerta). **Decisão de planejamento.**

## Validation Architecture

> `workflow.nyquist_validation` não está explicitamente `false` (não há `.planning/config.json` com a chave) → seção incluída. Alinhada à §5 do AI-SPEC (evals offline, pytest, respx) — aqui mapeada aos critérios de sucesso da fase.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`asyncio_mode = "auto"`, já em pyproject) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| Quick run command | `cd backend && uv run pytest tests/ -x -q` |
| Full suite command | `cd backend && uv run pytest` |
| OpenAI mock | `respx` (a adicionar ao grupo dev) — CI sem gastar token |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXT-01 | Texto nativo extraído de PDF com texto (sem custo de IA p/ a leitura local) | unit | `uv run pytest tests/extraction/test_pdf_io.py -x` | ❌ Wave 0 |
| EXT-01 | Heurística escolhe `native_text` p/ PDF com texto, `vision` p/ escaneado | unit | `uv run pytest tests/extraction/test_router.py -x` | ❌ Wave 0 |
| EXT-02 | `extract_stage` produz `ExtractionResult` conforme schema (OpenAI mockado) | unit | `uv run pytest tests/extraction/test_stage.py -x` | ❌ Wave 0 |
| EXT-02 | Recusa (`output_parsed is None`) → FALHA via fila, sem corromper estado | unit | `uv run pytest tests/extraction/test_stage.py::test_refusal -x` | ❌ Wave 0 |
| EXT-02 | Persistência de `Extraction` (fields + full_text + type guess) | unit | `uv run pytest tests/extraction/test_persistence.py -x` | ❌ Wave 0 |
| USE-02/SC4 | `Usage(step="extract")` gravado com input/output tokens, 1 por extração (sem dupla) | unit | `uv run pytest tests/extraction/test_usage.py -x` | ❌ Wave 0 |
| Idempotência | Re-claim do mesmo bloco não re-chama IA nem duplica Usage | integration | `uv run pytest tests/extraction/test_idempotency.py -x` | ❌ Wave 0 |
| Dispatch | Worker roteia `step="extract"` p/ o caminho async (não to_thread) | integration | `uv run pytest tests/queue/test_dispatch.py -x` | ❌ Wave 0 |
| Estado | Sucesso → PROCESSANDO + `last_completed_step="extraido"` (via mark_step) | unit | `uv run pytest tests/extraction/test_state.py -x` | ❌ Wave 0 |
| Migração | Alembic 0003 cria `extractions` (upgrade/downgrade limpos) | integration | `uv run pytest tests/test_migrations.py -x` | ❌ verificar se existe padrão |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest tests/extraction -x -q`
- **Per wave merge:** `cd backend && uv run pytest` (suite completa)
- **Phase gate:** suite verde + evals Code (`uv run pytest tests/evals -m "not live"`) antes de `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `tests/extraction/` — diretório novo (não existe). Criar com fixtures.
- [ ] `tests/extraction/conftest.py` — fixture de `AsyncOpenAI` mockado via respx; fixture de PDF com texto e PDF escaneado (sintético).
- [ ] Fixtures de eval (AI-SPEC §5): `tests/evals/fixtures/<tipo>/<caso>.pdf` + `.golden.json` (rotulados pelo operador). **Dataset 10–20 exemplos** — depende do operador; v1 pode começar com sintéticos + 2-3 reais.
- [ ] Framework de eval: `tests/evals/test_extraction_evals.py` (dims Code 1,3,4,6,8) + `test_llm_judge.py` (dims 2,5, marker `@pytest.mark.live`).
- [ ] Install: `uv add --group dev respx`.

> **Nota sobre evals (AI-SPEC §5/§6):** a Fase 3 **não tem gate de qualidade** (D-09). Os evals são **offline/dev**, não bloqueiam runtime. As checagens Code (conformidade de schema, DV de identificadores sobre valor cru, formato BR, cobertura multi-página, tokens) rodam em CI com OpenAI mockada. O LLM judge (fidelidade/campos trocados) gasta token → nightly fora do CI. **A VALIDATION.md desta fase deve validar a INTEGRAÇÃO** (extração funciona end-to-end, schema estruturado, texto nativo sem custo de IA, tokens persistidos sem dupla), deixando a **qualidade de extração** para o flywheel/Fase 5.

## Security Domain

> `security_enforcement` não está `false` no config → seção incluída. Foco em LGPD (dados fiscais sensíveis) e proteção de segredo.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | parcial | Chave OpenAI por instância (`SecretStr`); não há auth de usuário no v1. |
| V5 Input Validation | yes | Structured Outputs (strict) valida a saída da IA. Entrada (blob do CAS) já validada na ingestão. |
| V6 Cryptography | parcial | Nada hand-rolled. Hash SHA-256 do CAS (já existe). Sem cripto nova nesta fase. |
| V7 Error Handling & Logging | yes | **Nunca logar `openai_api_key` nem conteúdo do documento.** Logar só `document_id`, caminho (texto/visão), `doc_type_guess`, motivo de recusa. |
| V9 Communications | yes | HTTPS para OpenAI (SDK default). |
| V8 Data Protection (LGPD) | yes | Minimizar/explicitar o que sai da máquina: caminho texto envia texto nativo; visão envia imagem da página. Decisão consciente; controle por-documento é v2 (INT2-03). |

### Known Threat Patterns for {OpenAI extraction + SQLite + Windows local}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Vazamento da chave OpenAI em logs | Information Disclosure | `SecretStr`; `.get_secret_value()` só no ponto de criação do `AsyncOpenAI`; teste que assere ausência da chave em logs (Failure Mode 5). |
| Vazamento de conteúdo sensível (CPF/CNPJ/salário) em logs | Information Disclosure | Logar só metadados (`document_id`, caminho, tipo). Nunca `full_text`/`fields` em log. |
| Envio excessivo à OpenAH (LGPD) | Information Disclosure | Enviar só o necessário (texto nativo quando possível, mais barato e menos cru que imagem). Explicitar/controlar é v2. |
| Cobrança dupla por reprocessamento | (não-STRIDE — custo) | Idempotência `(content_hash, "extract")` + Extraction UNIQUE por document. |
| Chave inválida não tratada → loop de retry caro | DoS (custo) | `AuthenticationError` não-retryável → dead-letter imediato/alerta, não backoff infinito. |
| Alucinação de campo passando como verdade | Tampering (do dado) | Sem gate na Fase 3 (D-09) — mitigado a jusante (Fase 5 + evals offline). Documentado, não resolvido aqui. |

## Sources

### Primary (HIGH confidence)
- **Código existente lido linha a linha** (autoritativo para integração):
  - `backend/app/queue/repo.py`, `worker.py`, `app/models/job.py` — fila, claim, dispatch, idempotência `(original_hash, step)`.
  - `backend/app/pipeline/ingest_stage.py`, `state_machine.py`, `states.py` — onde a Fase 3 começa, allowlist (PROCESSANDO→PROCESSANDO NÃO permitido).
  - `backend/app/models/usage.py`, `document.py`, `page.py`, `extraction`(ausente), `__init__.py` — schema existente e registro de modelos.
  - `backend/app/storage/cas.py` — `read_bytes(content_hash)`.
  - `backend/app/config.py`, `main.py` — `SecretStr`, tunables, lifespan worker/watcher.
  - `backend/alembic/versions/0002_ingestion.py` — padrão de migração (batch SQLite, trigger).
  - `backend/app/ingest/watcher.py` — como jobs `ingest` são enfileirados (payload, `repo.enqueue`).
- **`03-AI-SPEC.md`** — framework, sintaxe Responses API, schema `ExtractionResult`, eval strategy (NÃO re-pesquisado, reusado).
- **`03-CONTEXT.md`** — decisões D-01..D-11, escopo, re-escopo EXT-04.
- **PyPI** (2026-06-16) — versões: openai 2.41.1, PyMuPDF 1.27.2.3, respx 0.23.1.

### Secondary (MEDIUM confidence)
- `CLAUDE.md` — stack prescritiva (Responses API, PyMuPDF, versões).

### Tertiary (LOW confidence)
- Nenhuma — esta pesquisa é majoritariamente verificação de código existente (alta confiança).

## Metadata

**Confidence breakdown:**
- Integração com código existente: **HIGH** — todos os arquivos relevantes lidos diretamente; a divergência AI-SPEC/`transition` foi confirmada no código.
- Standard stack: **HIGH** — versões confirmadas no PyPI, pins exatos do AI-SPEC.
- Pitfalls: **HIGH** — derivados do código real (async-vs-thread, idempotência, allowlist) + AI-SPEC.
- Pontos em aberto (enqueue inline vs sweep; detecção PDF/imagem): **MEDIUM** — múltiplas soluções válidas; recomendação dada, decisão de planejamento.

**Research date:** 2026-06-16
**Valid until:** ~2026-07-16 (estável; reavaliar versões de openai/PyMuPDF se passar de 30 dias, pois giram rápido).

# Phase 4: Templates, Sub-templates e Classificação - Research

**Researched:** 2026-06-16
**Domain:** Modelagem de templates schema-first, classificação híbrida (regras→IA) e validação/normalização determinística sobre uma base de extração genérica já persistida (FastAPI + Pydantic 2 + SQLAlchemy 2 + OpenAI Responses API)
**Confidence:** HIGH (toda a fundação a reusar está no repositório e foi lida; stack travada em CLAUDE.md; única integração externa nova é uma 2ª chamada à mesma Responses API já em produção)

## Summary

Esta fase NÃO é greenfield: ela monta uma camada nova (templates + classificação + validação) **em cima** de uma fundação madura das Fases 1–3 que já está no repositório. A extração genérica (`Extraction` com `fields_json` list-of-pairs + `full_text` + `doc_type_guess`), a fila durável SQLite com despacho por `step`, a máquina de estados com a aresta `PROCESSANDO→QUARENTENA` já permitida, o cliente OpenAI Responses API + Structured Outputs com mapeamento de `usage`, e o padrão de stage atômico/idempotente (`extract_stage`) — tudo isso existe e deve ser **espelhado, não reinventado**. O trabalho real é: (1) três novos modelos via Alembic 0004 (template, campo de template, resultado preenchido por `(documento, template)`), (2) um `classify_stage` que espelha o `extract_stage` em forma/garantias e roda como novo `step="classify"` na fila, (3) um módulo de validação determinística reutilizável (Módulo 11 CNPJ/CPF próprio + parsers de data/moeda pt-BR), e (4) o construtor de template real no frontend substituindo o mock, mais visibilidade somente-leitura da classificação — tudo já contratado no `04-UI-SPEC.md` (design system TRAVADO).

O risco técnico mais alto é o **double-charge da IA** (chamada de desempate D-01 + chamada de campos faltantes D-06 são pagas): o `classify_stage` deve checar o registro existente ANTES de qualquer chamada paga, exatamente como `extract_stage` faz com `Extraction`, e gravar `Usage(step="classify")`. O segundo risco é o **Structured Outputs strict mode**, que rejeita dict aberto e exige `additionalProperties:false` + todos os campos `required` (confirmado: nesting até 5 níveis, campos opcionais viram `nullable`). A Fase 3 já resolveu isso com list-of-pairs; a Fase 4 deve manter o mesmo padrão e NÃO tentar gerar um JSON Schema dinâmico por template com chaves variáveis. O terceiro risco é o **parsing pt-BR** (datas dd/mm/aaaa, moeda "1.234,56") com ambiguidade real — tratável com `python-dateutil` (já instalado no ambiente, mas ausente do `pyproject.toml`; precisa ser adicionado) + parser de moeda próprio com `Decimal`.

**Primary recommendation:** Espelhar exatamente os padrões da Fase 3 (`classify_stage` ≈ `extract_stage`; novos schemas Pydantic list-of-pairs; novo `step="classify"` no worker; checagem de registro existente antes de chamada paga; `Usage(step="classify")`). Modelar template/campo/resultado como 3 tabelas via Alembic 0004. Implementar validação determinística como módulo próprio reutilizável (Fase 7 também usará). Construtor de template no frontend seguindo `useWatchedFolders` + `04-UI-SPEC.md` ao pé da letra.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Classificação (documento ↔ template) — TPL-03**
- **D-01:** Classificação **híbrida regras→IA**: casa por **regras locais primeiro** (custo 0, sobre os dados já extraídos pela Fase 3); se nada casa com confiança suficiente, a **IA desempata**. Aproveita `doc_type_guess` como atalho.
- **D-02:** Cada template declara **sinais identificadores explícitos** (ex.: "tem linha digitável + CNPJ + valor" = boleto). Alimentam o casamento por regras E servem de dica para a IA no desempate.
- **D-03:** **Nenhum template casa → `QUARENTENA`** (TPL-04). **Múltiplos casam → maior confiança vence.** Caso duvidoso → quarentena por padrão (nada classificado às cegas). Limiar/política de desempate a definir no planejamento.
- **D-04:** Documento que **casou** fica em `PROCESSANDO` com marcador `last_completed_step="classificado"`, **vinculado ao template** que casou. **Nunca `CONCLUIDO`** aqui (terminal só após a automação da Fase 6). Espelha o padrão `"extraido"` da Fase 3.

**Preenchimento dos campos do template (EXT-04)**
- **D-05:** Após classificar, preenche os campos do template **mapeando os pares dado→valor que a Fase 3 já extraiu** (`fields_json` + `full_text`). **Custo 0 por padrão.**
- **D-06:** Se faltarem **campos obrigatórios** após o mapeamento, faz **UMA chamada dirigida à IA só para os campos faltantes** (não re-extrai tudo).
- **D-07:** Resultado conforme o template guardado num **novo registro ligado a `(documento, template)`**, **preservando intacta** a `Extraction` genérica bruta. Schema via Alembic.

**Campos, tipos, validações e normalização (EXT-04)**
- **D-08:** Cada campo tem **tipo opcional** (padrão **texto/string**). Conjunto: **texto, número, data, moeda, CPF/CNPJ, booleano**. O tipo é etiqueta que destrava validação/comparação/normalização.
- **D-09:** Validações **configuráveis por campo**: **obrigatório** + **validação por tipo** (data parseável; número/moeda parseável; **DV de CPF/CNPJ via Módulo 11** determinístico próprio) + **regex opcional**.
- **D-10:** Validação que falha → **marca o campo válido/inválido** e persiste; documento **segue sem aplicar automação**. Campo obrigatório inválido/faltante **NÃO vai direto para quarentena** nesta fase — fica marcado; o consumo das marcas (score, limiar, fila de revisão) é da **Fase 5**.
- **D-11:** **Normalizar guardando bruto + normalizado**: valor como veio (auditável) + valor normalizado (data→ISO `YYYY-MM-DD`, moeda→decimal, CPF/CNPJ→só dígitos). O bruto original nunca é perdido.

### Claude's Discretion
- Estrutura concreta dos novos modelos (template, campo, registro de campos preenchidos por `(documento, template)`) e formato de persistência dos sinais identificadores (D-02) e das validações por campo (D-09) — via Alembic.
- **Formato dos sinais identificadores** (D-02): como o usuário declara "presença de X/Y/Z" na UI e como vira regra avaliável localmente + dica para a IA.
- **Limiar e política de desempate** da classificação (D-03): valor padrão do limiar; empates próximos (sugestão: duvidoso → quarentena). Limiar **por template** é v2; aqui, se houver, é **global**.
- **Como a classificação entra no pipeline:** novo `step="classify"` na fila durável (despacho por `step`); chave de idempotência por bloco (`Document.content_hash`). Confirmar no planejamento.
- **Prompt/schema** da chamada de desempate (D-01) e da chamada dirigida de campos faltantes (D-06): Pydantic → JSON Schema (Structured Outputs strict, list-of-pairs); ler `response.usage` e gravar `Usage(step="classify")`.
- **UI do construtor de template** (TemplatesPage hoje é mock): declarar campos + tipos + validações + sinais; criar/editar/remover. Seed de campos a partir de documento extraído fica a critério do planejamento.

### Deferred Ideas (OUT OF SCOPE)
- **Sub-templates / tratativas condicionais por cliente/emissor/valor (TPL-02)** → **Fase 6** (regras condicionais de automação).
- **Auto-identificar cliente/sub-template pelo CNPJ sem configuração (INT2-01)** → v2.
- **Limiar de confiança por template** (INT2-05) → v2 (Fase 4 usa limiar global se houver).
- **Score de confiança, limiar configurável, fila de revisão lado-a-lado, quarentena visível/resolúvel (REV-01..05)** → **Fase 5**. A Fase 4 só **marca** válido/inválido e **vincula** o template.
- **Automações de arquivo, dry-run, undo, anti-colisão (AUT-01..06)** + regras condicionais → **Fase 6**.
- **Extração local custo-zero por layout + roteamento determinístico (EXT-03, EXT-05)** → **Fase 7**.
- **Correções da revisão humana virando hints/few-shot por template (INT2-04)** → v2.
- **Seed de campos do template a partir de documento extraído** — considerar no planejamento/UI; não travado.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **TPL-01** | Usuário cria templates declarando campos (nome, tipo, validação, dica) — editor schema-first, sem zonas visuais | Modelo `Template`/`TemplateField` (3 tabelas, Alembic 0004) + API CRUD fina espelhando `watched_folders.py` + construtor de UI espelhando `useWatchedFolders`/`PastasTab` (ver `04-UI-SPEC.md` S1/S2/S3) |
| **TPL-03** | Sistema classifica automaticamente cada documento contra os templates (usando IA para contexto) | `classify_stage` híbrido: matcher local por sinais (D-02) sobre `Extraction.fields_json`/`full_text`/`doc_type_guess` → desempate por IA (Responses API + Structured Outputs) quando ambíguo; novo `step="classify"` na fila |
| **TPL-04** | Documento que não casa vai para quarentena (não some) | `transition(doc, QUARENTENA, ...)` — aresta `PROCESSANDO→QUARENTENA` **já na allowlist** (`states.py`); marca o motivo para a Fase 5 consumir |
| **EXT-04** | IA retorna dados em formato estruturado (JSON Schema derivado do template), com validações de campo configuráveis | Mapeamento local dos pares extraídos → campos do template (D-05); chamada IA dirigida só p/ campos obrigatórios faltantes (D-06) com schema list-of-pairs strict; módulo de validação determinística (Módulo 11 + parsers pt-BR) marcando válido/inválido + bruto/normalizado (D-09/D-10/D-11) |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Definir template (campos/tipos/validações/sinais) | API / Backend (CRUD) | Frontend (form schema-first) | Template é dado de domínio persistido; a UI só edita. Espelha o CRUD de `watched_folders` |
| Classificação documento↔template | Backend stage (`classify_stage`) | OpenAI (só no desempate D-01) | Decisão de negócio sobre dados persistidos; a IA é fallback de contexto, não o dono da decisão. Regras locais primeiro (custo 0) |
| Preenchimento de campos (mapeamento) | Backend stage (puro, local) | OpenAI (só campos faltantes D-06) | Mapeamento determinístico sobre `Extraction.fields_json` já persistido; IA só no que sobra |
| Validação + normalização de campos | Backend (módulo determinístico próprio) | — | Módulo 11 CNPJ/CPF + parsers pt-BR são puros, testáveis, reutilizáveis (Fase 7 também usa). NUNCA na IA nem no frontend |
| Quarentena (não-casou) | Backend (state machine) | — | `transition` é o único dono do estado de topo; aresta já existe |
| Medição de tokens das chamadas pagas | Backend (`Usage(step="classify")`) | — | Mesma base de cobrança da Fase 3; gravado no commit atômico do stage |
| Enfileirar classificação | Backend (fila/worker, `step="classify"`) | — | Idempotência por `content_hash`+step, igual ao `extract` |
| Visibilidade da classificação | Frontend (somente leitura) | Backend (endpoint de detalhe do doc) | UI reflete o DB por polling; sem edição/resolução nesta fase (Fase 5) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 (`>=3.12,<3.13`) | Runtime | Fixado em `pyproject.toml` [VERIFIED: pyproject.toml] |
| FastAPI | 0.137.1 | API CRUD de templates + endpoint de classificação | Já em uso (routers `documents`/`watched_folders`) [VERIFIED: pyproject.toml] |
| Pydantic | 2.13.4 | Modelos de schema da IA (desempate/faltantes) + API in/out de template | Mesmo padrão de `ExtractionResult` e dos `*In`/`*Out` de `watched_folders` [VERIFIED: pyproject.toml] |
| SQLAlchemy | 2.0.* | ORM dos 3 novos modelos | Padrão `Mapped`/`mapped_column` já em todos os modelos [VERIFIED: pyproject.toml] |
| Alembic | 1.18.4 | Migração 0004 (3 tabelas novas) | D-10: schema só via migração; 0003 é o predecessor [VERIFIED: pyproject.toml] |
| openai | 2.41.* | Chamada de desempate (D-01) + campos faltantes (D-06) via Responses API | `openai_client.py` já encapsula Responses API + Structured Outputs + usage [VERIFIED: pyproject.toml] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dateutil | 2.9.0.post0 | Parsing/normalização de datas heterogêneas → ISO `YYYY-MM-DD` (D-11) | **PRECISA SER ADICIONADO ao `pyproject.toml`** — recomendado em CLAUDE.md, instalado no ambiente, mas AUSENTE das `dependencies` [VERIFIED: pip index versions + pyproject.toml grep] |
| (stdlib) `decimal.Decimal` | — | Normalização de moeda pt-BR → decimal (D-11) | Parser de moeda pt-BR ("1.234,56") é próprio; usar `Decimal`, nunca `float` |
| (stdlib) `re` | — | Validação por regex opcional (D-09) | Compilar `re.compile` com timeout conceitual / `re.fullmatch` |
| respx | >=0.23.1 (dev) | Mockar as novas chamadas OpenAI nos testes (sem gastar token) | Fixtures `mock_openai`/`openai_success_payload` já existem e são reusáveis |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Módulo 11 CNPJ/CPF próprio | lib externa (`validate-docbr`, `python-stdnum`) | **PROIBIDO por CLAUDE.md** (Decisão Crítica 3): DV de CNPJ/CPF é algoritmo trivial de domínio público; não vale dependência externa. Validar próprio |
| python-dateutil | parser de data próprio | dateutil cobre os formatos heterogêneos do mundo real; próprio reinventaria mal. CLAUDE.md já o prescreve. **Mas** dateutil é ambíguo em pt-BR (ver Pitfall 3) — passar `dayfirst=True` |
| 1 chamada IA combinada (desempate + faltantes) | manter D-01 e D-06 separados | Combinar acopla classificação a preenchimento e estoura schema; manter separados (regras locais resolvem a maioria sem IA nenhuma) |
| JSON Schema dinâmico por template (chaves = nomes de campos) | list-of-pairs fixo (como Fase 3) | Schema dinâmico com chaves variáveis quebra strict mode (`additionalProperties:false` + todos required). Manter list-of-pairs (ver Pitfall 1) |

**Installation:**
```bash
# Adicionar ao pyproject.toml dependencies (uv):
uv add python-dateutil==2.9.0.post0
# (openai/pydantic/sqlalchemy/alembic/fastapi já presentes — nenhuma outra dep nova)
```

**Version verification:**
- `python-dateutil` 2.9.0.post0 — confirmado via `pip index versions python-dateutil` (instalado no ambiente; última release da série 2.9) [VERIFIED: pip index]
- Demais libs — versões fixadas em `pyproject.toml`, sem mudança nesta fase [VERIFIED: pyproject.toml]

## Package Legitimacy Audit

> Esta fase adiciona **um** pacote novo (`python-dateutil`). slopcheck não foi executável neste ambiente sem rede; verificação por registro + proveniência abaixo.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| python-dateutil | PyPI | ~20 anos | ~200M+/mês (top-10 PyPI) | github.com/dateutil/dateutil | n/a (indisponível) | **Approved** — pacote canônico, ubíquo, prescrito por CLAUDE.md; presente no ambiente |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

`python-dateutil` é um dos pacotes mais baixados do PyPI, mantido há ~20 anos, dependência transitiva implícita de inúmeras libs (pandas, etc.) e explicitamente recomendado em CLAUDE.md. O risco de slopsquatting é nulo. Mesmo assim, como slopcheck não rodou, o planner pode opcionalmente gatear o `uv add` atrás de um `checkpoint:human-verify` — porém isso é estritamente formalidade aqui.

## Architecture Patterns

### System Architecture Diagram

```
                        Frontend (React 19 + TanStack Query)
   ┌──────────────────────────────────────────────────────────────────┐
   │  TemplatesPage (S1 grid) ── Construtor (S2) ── Modal remover (S3)  │
   │  DocumentsPage + S4 (classificação somente-leitura)               │
   └───────────────┬─────────────────────────────────┬────────────────┘
                   │ TanStack Query (polling/invalidate)
                   ▼                                 ▼
   ┌──────────────────────────┐      ┌───────────────────────────────────┐
   │ API /templates (CRUD)    │      │ API /documents/{id} (+classificação)│
   │  espelha watched_folders │      │  somente leitura (S4)              │
   └──────────┬───────────────┘      └─────────────────┬─────────────────┘
              │ persiste                                 │ lê
              ▼                                          ▼
   ┌──────────────────────────────── SQLite (WAL) ───────────────────────────┐
   │  templates ── template_fields        classification_results              │
   │                                       (1 por documento×template casado)  │
   │  Extraction (Fase 3, INTACTA) ◀── fonte do matcher + mapeamento          │
   │  jobs (fila durável)   documents (state + last_completed_step)           │
   └─────────────────────────────────────────────────────────────────────────┘
              ▲                                          ▲
              │ enfileira step="classify"                │ persiste atômico
              │ após "extraido"                          │
   ┌──────────┴──────────────────────────────────────────┴──────────────────┐
   │ Worker in-process (asyncio) — dispatch por step                         │
   │   ingest → extract → CLASSIFY (novo)                                    │
   │                                                                          │
   │  classify_stage(content_hash):                                          │
   │   1. checa classification_result existente → no-op (não re-cobra)       │
   │   2. lê Extraction do bloco (fields_json + full_text + doc_type_guess)  │
   │   3. MATCHER LOCAL por sinais declarados (D-02) → confiança por template│
   │   4. desempate?  ──não──> maior confiança ≥ limiar → casa              │
   │                  ──sim──> [IA desempate D-01] (Responses API, pago)     │
   │   5. nenhum casa / ambíguo → transition(QUARENTENA) (TPL-04)            │
   │   6. casou → mapeia pares→campos (D-05, local custo 0)                  │
   │   7. faltam obrigatórios? → [IA campos faltantes D-06] (pago)           │
   │   8. valida+normaliza cada campo (Módulo 11 / dateutil / Decimal/regex) │
   │   9. COMMIT ATÔMICO: classification_result + filled_fields              │
   │      + Usage(step="classify") + marcador "classificado"                 │
   └──────────────────────────────────────────────────────────────────────────┘
                          │ chamadas pagas (passo 4 e 7)
                          ▼
                  OpenAI Responses API (openai_client.py reusado)
```

### Recommended Project Structure
```
backend/app/
├── models/
│   ├── template.py              # Template + TemplateField (novos)
│   └── classification.py        # ClassificationResult + FilledField (novos)
├── classification/              # NOVO pacote (espelha extraction/)
│   ├── schema.py                # Pydantic list-of-pairs p/ desempate (D-01) e faltantes (D-06)
│   ├── matcher.py               # regras locais por sinais (D-02), puro, sem IA/DB
│   ├── openai_client.py         # OU reuso direto de extraction.openai_client (ver nota)
│   ├── filler.py                # mapeia pares extraídos → campos do template (D-05)
│   └── stage.py                 # classify_stage (espelha extraction/stage.py)
├── validation/                  # NOVO pacote (reutilizável — Fase 7 também usa)
│   ├── doc_ids.py               # Módulo 11 CNPJ + CPF (próprio, CLAUDE.md)
│   ├── dates.py                 # dateutil dayfirst → ISO
│   ├── money.py                 # parser pt-BR → Decimal
│   └── fields.py                # orquestra validação por tipo de campo (D-09/D-11)
├── api/
│   └── templates.py             # CRUD (espelha watched_folders.py)
└── alembic/versions/0004_*.py   # 3 tabelas novas

frontend/src/
├── hooks/useTemplates.ts        # espelha useWatchedFolders.ts
├── pages/TemplatesPage.tsx      # substitui o mock
└── (DocumentsPage.tsx estendido com S4)
```

### Pattern 1: Stage atômico idempotente (espelhar `extract_stage`)
**What:** Função async isolável (sem HTTP), que checa registro existente ANTES de chamada paga, persiste tudo num ÚNICO `session.commit()`, e avança só o marcador interno (`last_completed_step="classificado"`) sem `transition` quando o estado de topo não muda.
**When to use:** O `classify_stage` inteiro.
**Example:**
```python
# Source: backend/app/extraction/stage.py (padrão a espelhar)
async def classify_stage(session, *, content_hash: str) -> ClassifyStageResult:
    doc = session.scalar(select(Document).where(Document.content_hash == content_hash))
    if doc is None:
        raise ValueError("Document inexistente")
    # IDEMPOTÊNCIA: registro de classificação já existe → no-op, NÃO re-cobra IA
    existing = session.scalar(
        select(ClassificationResult).where(ClassificationResult.document_id == doc.id)
    )
    if existing is not None:
        return ClassifyStageResult(matched=existing.template_id is not None, called_ai=False)
    extraction = session.scalar(select(Extraction).where(Extraction.document_id == doc.id))
    # ... matcher local → (talvez) IA desempate → mapeamento → (talvez) IA faltantes
    # ... validação/normalização
    # COMMIT ÚNICO: ClassificationResult + FilledFields + Usage(step="classify") + marcador
    session.commit()
```
**Garantias herdadas:** idempotência (não re-cobrar), atomicidade (rollback total se crashar antes do commit), erro propaga ao worker para retry/backoff.

### Pattern 2: Schema Structured Outputs list-of-pairs (NUNCA dict aberto)
**What:** Modelos Pydantic da chamada de desempate e de campos faltantes seguem o padrão `ExtractedField`/`ExtractionResult` — chaves variáveis viram DADOS (`key`/`value`), nunca forma do schema. Campos opcionais → `nullable`.
**When to use:** `classification/schema.py`.
**Example:**
```python
# Source: backend/app/extraction/schema.py (padrão a espelhar)
class DisambiguationResult(BaseModel):
    """Desempate D-01: qual template casa, com confiança."""
    matched_template_id: int | None = Field(  # nullable = "nenhum casa" → quarentena
        description="ID do template que melhor casa; null se nenhum casa com confiança"
    )
    confidence: float = Field(description="0.0-1.0: confiança no casamento")
    reason: str = Field(description="Justificativa curta (metadado, não sensível)")

class MissingFieldsResult(BaseModel):
    """Campos obrigatórios faltantes (D-06) — list-of-pairs, NUNCA dict aberto."""
    fields: list[ExtractedField] = Field(description="Pares campo->valor dos faltantes")
```

### Pattern 3: Dispatch por `step` no worker (estender, não reescrever)
**What:** O worker já bifurca `extract` (coroutine `await`) vs `ingest` (`to_thread`). Adicionar o ramo `classify` como coroutine `await classify_stage(...)`, e o enfileiramento de `step="classify"` após o `extract_stage` concluir (análogo ao `enqueue_pending_extractions` sweep + enfileiramento inline).
**When to use:** `queue/worker.py` `_dispatch`/`_fail_for_step` + um `enqueue_pending_classifications` sweep.
**Anti-pattern:** NÃO enfileirar dentro do `extract_stage` (quebraria o commit único — `repo.enqueue` comita por si). Usar o mesmo desenho de sweep idempotente no startup + enfileiramento por gatilho que a Fase 3 usou para extract.

### Anti-Patterns to Avoid
- **Gerar JSON Schema dinâmico por template** com chaves = nomes de campos → quebra strict mode. Use list-of-pairs.
- **Setar `document.state` direto** → sempre `transition()` (allowlist). Para "classificado", avançar só `last_completed_step` em memória + commit (NÃO `mark_step`, que comita sozinho e quebra atomicidade; NÃO `transition(PROCESSANDO→PROCESSANDO)`, auto-laço fora da allowlist).
- **Chamar OpenAI sem checar registro existente** → double-charge. Checar `ClassificationResult` antes.
- **Embutir lógica de classificação no `router.choose`** → mata o seam D-03 (Critical Failure Mode 4). A Fase 4 classifica no `classify_stage`, não no router de extração.
- **`float` para moeda** → erro de arredondamento. Use `Decimal`.
- **Bloquear documento por campo obrigatório faltante** → D-10 proíbe; só marca, o gate é Fase 5.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fila durável / retry / idempotência | Nova fila | `queue/repo.py` + `worker.py` (add `step="classify"`) | Claim atômico, backoff, resume, dead-letter já prontos e testados |
| Chamada Responses API + Structured Outputs + usage + recusa | Novo wrapper OpenAI | `extraction/openai_client.py` (reusar ou espelhar) | Mapeamento input→prompt/output→completion, tratamento de recusa, segredo nunca logado — tudo resolvido |
| Estado de topo / quarentena | Setar `state` | `pipeline/state_machine.transition` | Allowlist valida; `PROCESSANDO→QUARENTENA` já permitido |
| Persistência atômica idempotente | Lógica nova de commit | Espelhar `extraction/stage.py` | Padrão "checa existente → 1 commit → erro propaga" provado |
| Parsing de datas heterogêneas | Parser próprio de data | `python-dateutil` (`dayfirst=True`) | Cobre dd/mm/aaaa, ISO, etc.; próprio reinventa mal |
| CRUD + validação de API | Endpoints do zero | Espelhar `api/watched_folders.py` | Padrão `*In`/`*Patch`/`*Out`, 404/409/422, `from_attributes` pronto |
| Hooks de data-fetching no front | fetch manual | Espelhar `hooks/useWatchedFolders.ts` | queryKey + invalidate em onSuccess, padrão travado |
| DV de CNPJ/CPF | lib externa | **Algoritmo próprio Módulo 11** | CLAUDE.md PROÍBE dep externa; é trivial e de domínio público |

**Key insight:** ~90% desta fase é composição de padrões já existentes no repositório. O código verdadeiramente novo e específico é: (a) o matcher local por sinais (D-02), (b) o módulo de validação determinística (Módulo 11 + parsers pt-BR), e (c) o construtor de template na UI. Todo o resto é espelhamento.

## Common Pitfalls

### Pitfall 1: Structured Outputs strict mode rejeita schema dinâmico / dict aberto
**What goes wrong:** A tentação para "preencher campos do template" é gerar um JSON Schema cujas chaves são os nomes dos campos do template (`{cnpj_emitente: ..., valor_total: ...}`). Strict mode exige `additionalProperties:false` em TODO objeto e TODOS os campos em `required`; chaves variáveis quebram isso e a API rejeita a requisição imediatamente.
**Why it happens:** O modelo mental "schema derivado do template" sugere um objeto com as chaves do template.
**How to avoid:** Manter **list-of-pairs** (`list[ExtractedField]`), exatamente como a Fase 3. O "schema derivado do template" do EXT-04 vira: (1) as `description`/`hint` dos campos do template embutidas no prompt e nas `description` dos Field, e (2) a validação determinística aplicada DEPOIS sobre o resultado — não um schema com chaves dinâmicas. Para campos opcionais numa chamada estruturada, usar tipo `nullable` (idioma oficial). Nesting suportado até 5 níveis. [CITED: developers.openai.com/api/docs/guides/structured-outputs]
**Warning signs:** Erro 400 da API mencionando `additionalProperties` ou `required` no momento da chamada.

### Pitfall 2: Double-charge da IA (desempate + campos faltantes são pagos)
**What goes wrong:** A Fase 4 tem DUAS chamadas pagas possíveis por bloco (D-01 desempate, D-06 faltantes). Um retry/crash da fila re-executaria o `classify_stage` e re-cobraria.
**Why it happens:** Diferente da Fase 3 (1 chamada, guardada por `UNIQUE(extractions.document_id)`), aqui há 2 chamadas e mais estado.
**How to avoid:** `ClassificationResult` com `UNIQUE(document_id)` (1 classificação por bloco) + checagem do registro existente ANTES de qualquer chamada paga (igual ao `extract_stage`). Persistir tudo num commit único. Se quiser granularidade (desempate feito, faltantes não), modelar flags de progresso no `ClassificationResult` — mas o caminho simples e seguro é tratar o stage como atômico: ou completa e persiste tudo, ou nada.
**Warning signs:** `Usage(step="classify")` com mais de N registros por documento; `call_count` da OpenAI > esperado nos testes respx.

### Pitfall 3: Ambiguidade de data e moeda pt-BR
**What goes wrong:** `dateutil.parser.parse("03/04/2026")` interpreta como mês/dia (en-US) por padrão → vira 4 de março, não 3 de abril. Moeda "1.234,56" parseada como float vira `1.234` (ponto como decimal en-US).
**Why it happens:** Defaults das libs são en-US; documentos brasileiros usam dd/mm/aaaa e vírgula decimal.
**How to avoid:** `dateutil.parser.parse(s, dayfirst=True)` SEMPRE. Para moeda, parser próprio: remover separador de milhar `.`, trocar `,`→`.`, `Decimal(...)`. Guardar SEMPRE bruto + normalizado (D-11); se o parse falhar, marcar inválido (D-10), nunca chutar. Cobrir com testes de casos pt-BR explícitos (Wave 0).
**Warning signs:** Datas trocadas dia↔mês; valores monetários divididos por 1000; `InvalidOperation` do Decimal não tratado.

### Pitfall 4: Quebrar a atomicidade ao enfileirar o próximo step
**What goes wrong:** Enfileirar `step="classify"` de dentro do `extract_stage` (ou enfileirar o próximo passo dentro do `classify_stage`) chama `repo.enqueue`, que comita por si — quebrando o commit único do stage.
**Why it happens:** Parece natural "no fim da extração, enfileira a classificação".
**How to avoid:** Replicar a solução da Fase 3 (Open Question 1 resolvida em 03-04): sweep idempotente no startup do worker (`enqueue_pending_classifications`: blocos com `last_completed_step="extraido"` e SEM `ClassificationResult`) + enfileiramento por gatilho fora do commit do stage. Idempotente por `UNIQUE(content_hash, "classify")` na tabela `jobs`.
**Warning signs:** Jobs duplicados; commit do stage abortado por commit aninhado.

### Pitfall 5: Matcher local sem critério → tudo vira IA (custo) ou tudo casa errado
**What goes wrong:** Se os "sinais identificadores" (D-02) não tiverem semântica clara de avaliação, ou o matcher local for fraco, ou tudo cai na IA (mata o custo-zero, motor da fase) ou casa por engano sem desempate.
**Why it happens:** "Presença de X/Y/Z" é vago; precisa de definição concreta de como um sinal é avaliado sobre `fields_json`/`full_text`.
**How to avoid:** No planejamento, definir o **formato do sinal** (discretion D-02) de forma avaliável: ex. lista de tokens/chaves cuja presença em `fields_json.key` ou em `full_text` (case-insensitive) conta pontos; confiança = fração de sinais presentes. Definir **limiar global** (discretion D-03): acima → casa direto (custo 0); zona cinzenta → IA desempata; nenhum sinal → não casa → quarentena. Aproveitar `doc_type_guess` como sinal extra. Documentar o limiar default em `config.py` (tunável por env, como os `openai_extract_*`).
**Warning signs:** Toda classificação aciona a IA; ou documentos casando com template errado sem desempate.

## Code Examples

### Validação determinística CNPJ (Módulo 11 — próprio, CLAUDE.md)
```python
# Source: algoritmo Módulo 11 de domínio público (Receita Federal); CLAUDE.md Decisão Crítica 3
def is_valid_cnpj(raw: str) -> bool:
    d = [c for c in raw if c.isdigit()]
    if len(d) != 14 or len(set(d)) == 1:
        return False
    nums = list(map(int, d))
    def dv(slice_, weights):
        s = sum(n * w for n, w in zip(slice_, weights))
        r = s % 11
        return 0 if r < 2 else 11 - r
    w1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    w2 = [6] + w1
    return dv(nums[:12], w1) == nums[12] and dv(nums[:13], w2) == nums[13]
# CPF: análogo, 11 dígitos, pesos 10..2 / 11..2. Normalização: "".join(d).
```

### Normalização de data pt-BR (dateutil, dayfirst)
```python
# Source: python-dateutil (dayfirst=True resolve a ambiguidade pt-BR — Pitfall 3)
from dateutil import parser as dtparser
def normalize_date(raw: str) -> str | None:
    try:
        return dtparser.parse(raw.strip(), dayfirst=True).date().isoformat()  # YYYY-MM-DD
    except (ValueError, OverflowError):
        return None  # marca inválido (D-10), guarda bruto (D-11)
```

### Normalização de moeda pt-BR (Decimal próprio)
```python
# Source: parser próprio (sem lib madura pt-BR; CLAUDE.md prefere determinístico)
from decimal import Decimal, InvalidOperation
def normalize_money_brl(raw: str) -> str | None:
    s = "".join(c for c in raw if c.isdigit() or c in ",.-")
    s = s.replace(".", "").replace(",", ".")  # milhar . / decimal ,
    try:
        return str(Decimal(s))
    except (InvalidOperation, ValueError):
        return None
```

### Hook de templates (espelha useWatchedFolders)
```typescript
// Source: frontend/src/hooks/useWatchedFolders.ts (padrão travado)
const TEMPLATES_KEY = ['templates'] as const
export function useTemplates() {
  return useQuery({ queryKey: TEMPLATES_KEY, queryFn: getTemplates })
}
export function useCreateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TemplateCreate) => createTemplate(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEMPLATES_KEY }),
  })
}
// useUpdateTemplate / useDeleteTemplate idem (PATCH/DELETE)
```

## Runtime State Inventory

> Fase mista: cria features novas mas também muda o pipeline e adiciona um `step`. Inventário do que precisa de atenção além de novos arquivos.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Tabela `extractions` (Fase 3) é a FONTE da classificação — **lida, nunca alterada** (D-07 preserva a Extraction bruta). Documentos LEGADOS já em `PROCESSANDO`/`"extraido"` sem `ClassificationResult` existem após o deploy desta fase | Sweep idempotente `enqueue_pending_classifications` no startup do worker (espelha `enqueue_pending_extractions`) para classificar os legados sem job — code |
| Live service config | Tunável novo: limiar de classificação global + (talvez) `openai_classify_model`/temperatura → entram em `config.py` como os `openai_extract_*` (env, sem deploy) | code (config.py) |
| OS-registered state | Nenhum — não há tarefa de SO, serviço externo, nem registro de SO envolvido nesta fase | None — verificado: a fila é in-process, o worker sobe no lifespan do FastAPI; nenhum agendamento de SO |
| Secrets/env vars | `OPENAI_API_KEY` (já existe, `SecretStr`) é reusada nas chamadas D-01/D-06 — nenhum segredo novo | None — chave já provisionada na Fase 1 |
| Build artifacts | Frontend: `types.ts` tem um `Template` MOCK que será SUBSTITUÍDO pela forma real da API; `data/mock.ts` deixa de alimentar a TemplatesPage. Rebuild do Vite necessário | code (substituir tipo + remover dependência do mock) + rebuild |

**Migração de dados:** Não há dado preexistente de template/classificação (features novas). A migração 0004 só CRIA tabelas (como a 0003 fez) — não toca `documents`, logo NÃO recria o trigger `trg_documents_updated_at` (mesmo caveat resolvido da 0003).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Chat Completions + JSON mode | Responses API + Structured Outputs | Já adotado na Fase 3 | Nada a mudar — reusar `openai_client.py` |
| Schema dinâmico com chaves variáveis | list-of-pairs strict-safe | Já adotado na Fase 3 | Manter o padrão na Fase 4 |
| Limiar de confiança por template | Limiar GLOBAL no v1 (por-template = INT2-05/v2) | Decisão desta fase (discretion D-03) | Um tunável global em config.py |

**Deprecated/outdated:** nenhum item novo. Confirmar `openai_extract_model` vigente vale também para a chamada de classificação (modelos giram rápido — CLAUDE.md); o implementador confirma o modelo na conta no momento.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `python-dateutil` com `dayfirst=True` cobre os formatos de data dos documentos reais do cliente | Stack / Pitfall 3 | Datas mal parseadas marcadas inválidas (não bloqueia — D-10); calibrar com fixtures reais |
| A2 | Limiar de classificação GLOBAL default é suficiente no v1 (sem por-template) | Discretion D-03 | Falsos positivos/negativos de casamento; mitigado por "duvidoso→quarentena" e revisão Fase 5 |
| A3 | 3 tabelas (template, template_field, classification_result+filled_field) é a modelagem adequada; sinais e validações persistidos como JSON/colunas no template_field | Discretion (modelo de dados) | Re-migração se a forma do sinal precisar evoluir; baixo risco (Alembic versionado) |
| A4 | Reusar `extraction.openai_client` diretamente (vs criar `classification/openai_client`) é aceitável já que o SYSTEM_INSTRUCTIONS é fixo de extração | Stack | Se o prompt de classificação/faltantes precisar ser diferente, criar funções novas no mesmo módulo ou um cliente irmão; baixo risco |
| A5 | O matcher local por sinais resolve a maioria dos casos sem IA (preservando o custo-zero motor da fase) | Pitfall 5 | Se sinais forem fracos, custo sobe (tudo vira IA); planejamento deve definir formato de sinal avaliável + limiar |

## Open Questions

1. **Granularidade da idempotência das 2 chamadas pagas (desempate vs faltantes)**
   - What we know: `ClassificationResult` UNIQUE(document_id) + checagem prévia evita re-cobrar o stage inteiro.
   - What's unclear: se o stage falhar ENTRE a chamada de desempate (paga) e a de faltantes (paga), o retry re-cobraria o desempate.
   - Recommendation: tratar o stage como atômico (commit único ao fim) → se falhar antes do commit, nada persistido e o retry re-executa ambas. Custo de re-cobrar é aceitável no v1 (raro); alternativa (persistir desempate antes) adiciona complexidade. **Decidir no planejamento**; default = atômico simples.

2. **Formato concreto do sinal identificador (D-02) — discretion**
   - What we know: alimenta matcher local + dica para IA; declarado pelo usuário na UI (S2).
   - What's unclear: estrutura exata (lista de tokens? chave+valor esperado? presença em key vs full_text?).
   - Recommendation: começar simples — lista de termos/chaves cuja presença (em `fields_json.key` OU `full_text`, case-insensitive) pontua; confiança = fração presente. Persistir como JSON no template. Evoluível sem quebrar (v2 = operadores de valor).

3. **Endpoint de visibilidade da classificação (S4)**
   - What we know: `04-UI-SPEC.md` S4 é somente-leitura: template casado + campos (bruto/normalizado) + marca válido/inválido + estado quarentena.
   - What's unclear: se estende `GET /documents` ou cria `GET /documents/{id}` de detalhe.
   - Recommendation: criar `GET /documents/{id}` de detalhe (a lista atual não carrega classificação); mantém a lista leve para o polling. Definir no planejamento.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend | ✓ | 3.12 | — |
| python-dateutil | Normalização de data (D-11) | ✓ (instalado) | 2.9.0.post0 | **Falta no pyproject.toml** — adicionar via `uv add` |
| OpenAI API + chave | Desempate D-01 / faltantes D-06 | ✓ (config `OPENAI_API_KEY`) | — | Sem chave: matcher local ainda casa o que tem sinais fortes; ambíguos → quarentena (degradação graciosa) |
| respx (dev) | Testes sem gastar token | ✓ | >=0.23.1 | — |
| Node (build front) | TemplatesPage real | ✓ (assumido, Fase 2 buildou) | ≥20.19 | — |

**Missing dependencies with no fallback:** nenhuma.
**Missing dependencies with fallback:** `python-dateutil` está instalado mas FORA do `pyproject.toml` — Wave 0 deve adicioná-lo (`uv add python-dateutil==2.9.0.post0`) para builds reprodutíveis no cliente.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`asyncio_mode=auto`) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=["tests"]`) |
| Quick run command | `cd backend && python -m pytest tests/ -x -q` |
| Full suite command | `cd backend && python -m pytest tests/` |
| OpenAI mocking | respx — fixtures `mock_openai`/`openai_success_payload`/`openai_refusal_payload` em `tests/extraction/conftest.py` (reusáveis; criar análogos em `tests/classification/conftest.py`) |
| DB em teste | `schema_engine` (create_all só em teste) + `sqlite_url`/`engine` em `tests/conftest.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TPL-01 | CRUD de template (criar/listar/editar/remover) + validações | integration | `pytest tests/test_api_templates.py -x` | ❌ Wave 0 |
| TPL-01 | Modelos template/campo persistem via migração 0004 | integration | `pytest tests/test_migrations.py -x` | ✅ (estender) |
| TPL-03 | Matcher local casa por sinais; confiança correta | unit | `pytest tests/classification/test_matcher.py -x` | ❌ Wave 0 |
| TPL-03 | classify_stage: casa, mapeia, persiste atômico, marcador "classificado" | integration | `pytest tests/classification/test_stage.py -x` | ❌ Wave 0 |
| TPL-03 | Idempotência: 2ª execução não re-chama IA (call_count==esperado) | integration | `pytest tests/classification/test_stage.py -k idempot -x` | ❌ Wave 0 |
| TPL-03 | Desempate por IA quando ambíguo (Structured Outputs, respx) | integration | `pytest tests/classification/test_stage.py -k desempate -x` | ❌ Wave 0 |
| TPL-04 | Nenhum template casa → QUARENTENA (transition válida) | integration | `pytest tests/classification/test_stage.py -k quarentena -x` | ❌ Wave 0 |
| EXT-04 | Mapeamento pares→campos sem IA (D-05, custo 0) | unit | `pytest tests/classification/test_filler.py -x` | ❌ Wave 0 |
| EXT-04 | Chamada IA só p/ campos obrigatórios faltantes (D-06) | integration | `pytest tests/classification/test_stage.py -k faltantes -x` | ❌ Wave 0 |
| EXT-04 | DV CNPJ/CPF Módulo 11 (válidos/inválidos, repetidos) | unit | `pytest tests/validation/test_doc_ids.py -x` | ❌ Wave 0 |
| EXT-04 | Data pt-BR dayfirst → ISO; moeda pt-BR → Decimal; regex | unit | `pytest tests/validation/test_fields.py -x` | ❌ Wave 0 |
| EXT-04 | Bruto preservado + normalizado guardado; inválido marcado sem bloquear (D-10/D-11) | unit | `pytest tests/validation/test_fields.py -k bruto -x` | ❌ Wave 0 |
| PROC-02/03 | step="classify" enfileirado/despachado; sweep idempotente de legados | integration | `pytest tests/queue/test_worker.py -k classify -x` | ✅ (estender) |
| USE-02 | Usage(step="classify") gravado nas chamadas pagas | integration | `pytest tests/classification/test_stage.py -k usage -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/ -x -q` (suite inteira é rápida; ~25 arquivos, sem token gasto)
- **Per wave merge:** `cd backend && python -m pytest tests/` (full)
- **Phase gate:** Full suite verde + (se aplicável) build do frontend antes de `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/classification/conftest.py` — fixtures respx para desempate/faltantes (espelhar `tests/extraction/conftest.py`)
- [ ] `tests/classification/test_matcher.py` — matcher local por sinais (TPL-03)
- [ ] `tests/classification/test_filler.py` — mapeamento pares→campos (EXT-04/D-05)
- [ ] `tests/classification/test_stage.py` — classify_stage (casa/quarentena/idempotência/desempate/faltantes/usage)
- [ ] `tests/validation/test_doc_ids.py` — Módulo 11 CNPJ/CPF
- [ ] `tests/validation/test_fields.py` — data/moeda/regex pt-BR + bruto/normalizado
- [ ] `tests/test_api_templates.py` — CRUD de templates
- [ ] Estender `tests/test_migrations.py` (0004) e `tests/queue/test_worker.py` (step classify)
- [ ] `uv add python-dateutil==2.9.0.post0` no pyproject.toml

## Security Domain

> `security_enforcement: true`, ASVS level 1, block_on: high.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-tenant local; sem auth de usuário no v1 (PROJECT.md / Out of Scope) |
| V3 Session Management | no | Sem sessões/contas |
| V4 Access Control | no (v1) | Single-tenant; mesmo caveat de `watched_folders` (sem allowlist de raiz no v1 local) |
| V5 Input Validation | **yes** | Pydantic nos bodies de template (FastAPI 422); validação determinística dos valores extraídos; **regex do usuário (D-09) é input não confiável → risco ReDoS (ver abaixo)** |
| V6 Cryptography | no | Sem cripto nova; chave OpenAI já `SecretStr` (não logada) |
| V7/V8 Logging & Data Protection | **yes** | NUNCA logar `full_text`, `fields`, valores extraídos nem a chave — só metadados (document_id/template_id/route). Padrão já estabelecido nos stages da Fase 3 |

### Known Threat Patterns for esta stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| **ReDoS** via regex do usuário (D-09) | Denial of Service | Regex de validação por campo é fornecida pelo OPERADOR (não atacante externo no v1 single-tenant) → risco baixo, mas: usar `re.fullmatch` com input já limitado em tamanho; considerar limite de comprimento do valor e do padrão; documentar a limitação. NÃO compilar regex em loop quente sem cache |
| Injeção via prompt (conteúdo do documento) | Tampering | O `full_text` vai à IA; Structured Outputs limita a saída ao schema. SYSTEM_INSTRUCTIONS fixas; sem few-shot do conteúdo. Recusa tratada (`output_parsed is None`) |
| Vazamento de dados sensíveis em log | Information Disclosure | V7/V8: stages logam só metadados; chave `SecretStr`; replicar a disciplina da Fase 3 nos novos stages |
| Injeção SQL | Tampering | SQLAlchemy ORM/Core parametrizado (sem string-building); padrão já em uso |
| XSS no frontend (nomes de template/valores) | Tampering | React renderiza como texto puro (T-02-11 já estabelecido); não interpretar HTML |
| Path traversal | — | Não aplicável nesta fase (sem operações de arquivo — isso é Fase 6) |

**Block-on-high check:** nenhuma ameaça de severidade alta introduzida que não tenha mitigação padrão. O ReDoS via regex do operador é o único ponto novo de atenção e é mitigável (input single-tenant + `fullmatch` + limites de tamanho).

## Sources

### Primary (HIGH confidence)
- Repositório (lido nesta sessão): `backend/app/models/extraction.py`, `extraction/schema.py`, `extraction/router.py`, `extraction/openai_client.py`, `extraction/stage.py`, `queue/repo.py`, `queue/worker.py`, `pipeline/state_machine.py`, `pipeline/states.py`, `models/document.py`, `models/usage.py`, `models/enums.py`, `config.py`, `api/documents.py`, `api/watched_folders.py`, `alembic/versions/0003_extractions.py`, `tests/conftest.py`, `tests/extraction/conftest.py`, `pyproject.toml`
- `.planning/phases/04-templates-sub-templates-e-classifica-o/04-CONTEXT.md` — decisões D-01..D-11 (autoritativo)
- `.planning/phases/04-templates-sub-templates-e-classifica-o/04-UI-SPEC.md` — contrato de UI travado (S1–S4)
- `CLAUDE.md` — stack prescritiva; Decisão Crítica 3 (Módulo 11 próprio) e 4 (Responses API + Structured Outputs)
- `.planning/REQUIREMENTS.md` / `.planning/ROADMAP.md` / `.planning/STATE.md`

### Secondary (MEDIUM confidence)
- OpenAI Structured Outputs guide (strict mode: `additionalProperties:false`, todos required, nesting 5 níveis, opcional→nullable) — confirma Pitfall 1. [CITED: developers.openai.com/api/docs/guides/structured-outputs]
- `pip index versions python-dateutil` — 2.9.0.post0 confirmado e instalado.

### Tertiary (LOW confidence)
- nenhuma — todas as afirmações verificadas no repositório, em docs oficiais ou no registro PyPI.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versões em `pyproject.toml`; única dep nova (`python-dateutil`) verificada e prescrita por CLAUDE.md
- Architecture: HIGH — todos os padrões a espelhar foram lidos diretamente do código em produção
- Pitfalls: HIGH — derivados do código existente (idempotência/atomicidade), de docs oficiais (strict mode) e da experiência registrada da Fase 3
- Discretion areas (formato de sinal, limiar, granularidade de idempotência): MEDIUM — recomendações dadas, decisão final no planejamento (ver Open Questions)

**Research date:** 2026-06-16
**Valid until:** 2026-07-16 (stack estável; reconfirmar `openai_extract_model` vigente na conta no momento da implementação — modelos giram rápido)

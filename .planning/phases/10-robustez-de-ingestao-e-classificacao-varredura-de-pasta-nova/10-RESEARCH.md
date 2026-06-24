# Phase 10: Classificação robusta e reprocessamento - Research

**Researched:** 2026-06-24
**Domain:** Classificação por sinais (matcher local), normalização de texto, reprocessamento de quarentena, ferramenta de diagnóstico de sinais, fallback opt-in de IA
**Confidence:** HIGH (pesquisa quase inteiramente no código existente; decisões já travadas no CONTEXT)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01..D-12, verbatim)

**Tolerância do matcher (Item 5)**
- **D-01:** Tornar o casamento tolerante via **NORMALIZAÇÃO apenas** — NÃO adotar limiar N-de-M nesta fase. Manter a semântica atual E-de-todas-as-condições-do-grupo / OU-entre-grupos (`matcher.py:152-159`) e a confiança booleana; muda só o pré-processamento do texto antes do match.
- **D-02:** Normalização aplicada ao casamento de condições `texto`: (a) lowercase (já existe); (b) remover acentos (NFKD + drop combining — reusar o padrão de `_strip_accents` introduzido na Phase 9 em `naming.py`); (c) colapsar runs de espaço **e quebras de linha** em espaço único; (d) normalizar/neutralizar pontuação. O `value` do sinal **e** o `full_text` (haystack) passam pela MESMA normalização — senão o casamento fica assimétrico e falha.
- **D-03:** Interação com modo `regex`: normalizar o haystack pode quebrar regex que dependem de quebra de linha/acento. Decisão: a normalização vale para o modo `texto`; **preservar a semântica do `regex`** (a condição regex roda contra um haystack menos normalizado, p.ex. só lowercase como hoje). Detalhe exato a fechar no RESEARCH.
- **D-04:** Tradeoff **aceito conscientemente**: normalização sozinha NÃO resolve sinal com palavra trocada (ex.: `NATUREZA DA OPERAÇÃO` vs `NATUREZA DE OPERAÇÃO`). Esses casos são endereçados pela **ferramenta de testar sinais**. N-de-M fica deferido.

**IA quando nenhum template casa (Item 5)**
- **D-05:** Adicionar **toggle GLOBAL** (config, padrão **DESLIGADO**): "IA classifica quando nenhum template casa". Quando ligado e `matcher.decide` retorna `quarantine` por confiança 0.0 (nada casou), chamar a IA para tentar classificar **antes** de transicionar para QUARENTENA. Desligado = comportamento atual. Custo explícito: cada doc não-casado vira 1 chamada de IA quando ligado.
- **D-06:** Preservar o **seam D-03** (`matcher.decide` separado e puro). O fallback de IA entra no `classify_stage`, não dentro do matcher. Reusar o caminho de IA já existente.

**Ferramenta "testar sinais" (Item 5)**
- **D-07:** Recebe **UPLOAD de um documento de teste**; backend extrai texto e roda os sinais do template, devolvendo detalhamento **por-sinal e por-grupo** (casa/falha). Endpoint backend novo (preview de sinais).
- **D-08:** Usar **texto NATIVO** do PDF (PyMuPDF, custo zero) por padrão. Documento escaneado (sem texto nativo) → avisar que precisaria de IA. Recomendação MVP: restringir a texto nativo OU avisar. Fechar no RESEARCH/planning.
- **D-09:** Usar a MESMA normalização (D-02) e o MESMO motor (`matcher._parse_groups` / `_template_matches` / `_condition_matches`) — resultado idêntico ao da classificação real.

**Reprocessar/reclassificar (Item 6)**
- **D-10:** Nova ação "reprocessar automático" (**sem forçar template**). Estados elegíveis: **QUARENTENA e EM_REVISAO**. **Por-documento E em lote**.
- **D-11:** Transicionar para PROCESSANDO e re-enfileirar `classify` **SEM** `forced_template_id`. `classify_stage` já recarrega os templates do DB a cada run (`stage.py:205`). Reusar `_requeue` (`documents.py:549`) e o payload de classify.
- **D-12:** Em lote sobre todos os docs de um balde (QUARENTENA/EM_REVISAO) da visão `/documents/attention`. Idempotente/seguro.

### Claude's Discretion (a fechar neste RESEARCH / planning)
- Conjunto exato de normalização de pontuação e interação fina com o modo `regex` (D-03) → RESEARCH (FECHADO abaixo).
- Forma do endpoint de preview (multipart vs base64) e dos endpoints de reprocess (single vs batch) → planning (RECOMENDAÇÃO abaixo).
- Onde expor o toggle da IA-fallback na UI de config.

### Deferred Ideas (OUT OF SCOPE)
- UX de dry-run "Negar/Pular/Remover" (Item 12).
- Limiar N-de-M / casamento parcial.
- IA classificar SEMPRE (sem toggle).
- Item 2 (varredura de pasta nova) e Item 7 (re-ingerir split).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| Backlog Item 5 | Matcher menos frágil (normalização) + ferramenta de testar sinais + IA fallback opt-in | Seções "Normalização do matcher", "Ferramenta testar sinais", "IA fallback" |
| Backlog Item 6 | Reprocessar/reclassificar automático (por-doc e em lote, sem forçar template) para QUARENTENA e EM_REVISAO | Seção "Reprocessar" |
</phase_requirements>

## Summary

Esta fase é quase inteiramente **trabalho no código existente** — não há tecnologia nova relevante além de `python-multipart` (necessário se o endpoint de teste de sinais usar `UploadFile`). O risco é de **regressão**, não de descoberta: o matcher tem invariantes de segurança fortes (ReDoS/timeout, falha-fechada, seam `decide` puro, LGPD/não-logar) que devem ser preservados, e há testes legados (`test_matcher_groups.py`, `test_stage.py`) cuja semântica não pode quebrar.

As quatro capacidades mapeiam para pontos cirúrgicos: (1) uma função de normalização nova em `matcher.py` aplicada simetricamente a `value` e `haystack` SÓ no ramo `texto` de `_condition_matches`, deixando `regex` no comportamento atual (só lowercase); (2) um endpoint `POST /templates/preview-signals` que extrai texto nativo via PyMuPDF (`pdf_io.extract_text_and_decide`) e reusa `_parse_groups`/`_group_matches`/`_condition_matches` para um relatório por-grupo/por-sinal; (3) endpoints de reprocess em `documents.py` que copiam a mecânica do `reclassify` existente MAS sem `forced_template_id` e aceitam QUARENTENA+EM_REVISAO, com variante batch; (4) um setting global booleano lido no `classify_stage` que, quando `decide`→quarantine por nada-casou, chama `openai_client.disambiguate` contra TODOS os templates antes de quarentenar.

**Primary recommendation:** Implementar como 4 planos pequenos e independentes (matcher+normalização / preview de sinais / reprocess / IA-fallback) + 1 plano de frontend. O ponto mais delicado é o matcher: a normalização deve ser uma função pura testada isoladamente, aplicada SÓ ao ramo `texto`, e os testes legados de `regex` (`\d{44}`, timeout ReDoS) devem continuar passando intactos.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Normalização de texto p/ casamento | Backend / motor puro (`matcher.py`) | — | Função pura, custo zero, sem IO; espelha `naming._strip_accents` |
| Decisão matched/ambiguous/quarantine | Backend / `matcher.decide` (seam puro) | — | Seam D-03/D-06 a preservar; nunca embutir IA aqui |
| Preview de sinais (extração + relatório) | Backend / API templates + `pdf_io` | Motor puro do matcher | Extrai texto nativo (sem IA) e reusa o motor; UI só renderiza |
| Reprocessar (transição + requeue) | Backend / API documents | State machine + fila | Mesma mecânica de `reclassify`/`retry`; orquestração de estado |
| IA fallback quando nada casa | Backend / `classify_stage` | `openai_client.disambiguate` | Fora do matcher (D-06); reusa caminho de IA pago existente |
| Toggle de config | Backend / `config.py` + API `/config` | `.env` (persist_env_setting) | Mesmo padrão de `review-threshold` |
| Upload + relatório + botões reprocessar | Frontend (React) | TanStack Query hooks | UI consome endpoints novos |

## Standard Stack

Esta fase NÃO introduz bibliotecas de domínio novas. Tudo já está no stack do projeto. Única dependência potencialmente faltante:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `regex` | já instalado | drop-in do `re` com timeout REAL no `.search` (proteção ReDoS) | Já é a base do matcher (`matcher.py:47`) — NÃO trocar |
| PyMuPDF (`fitz`) | 1.27.x | extração de texto nativo do PDF de teste (`pdf_io.extract_text_and_decide`) | Já é o extrator nativo do projeto; custo zero |
| `python-multipart` | latest | requerido por FastAPI para `UploadFile`/`Form` (multipart) | **NÃO está instalado** — ver Package Legitimacy Audit |
| FastAPI | 0.137.x | `UploadFile`/`File` no endpoint de preview | Já no stack |
| Pydantic | 2.13.x | schemas In/Out dos endpoints novos | Já no stack |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `UploadFile` (multipart, requer python-multipart) | base64 no body JSON | base64 evita a dependência nova e o cliente fetch atual (`api.ts`) é JSON-only; PORÉM infla ~33% o payload e é menos idiomático. Ver "Open Questions". |
| `_strip_accents` reusado de `naming.py` | reimplementar em `matcher.py` | Reusar evita duplicação, MAS cria import `automation → classification`? Não: a direção é `classification` importando de `automation`. Avaliar acoplamento (ver Pitfall). |

**Version verification (já fixadas no CLAUDE.md, confirmadas no código):** PyMuPDF 1.27.x, FastAPI 0.137.x, Pydantic 2.13.x. `regex` é dependência transitiva já em uso (`import regex` em `matcher.py`).

## Package Legitimacy Audit

> Esta fase instala no MÁXIMO 1 pacote novo (`python-multipart`), e somente se o endpoint de preview usar `UploadFile`. Se optar por base64, NENHUM pacote novo é necessário.

slopcheck não está disponível no ambiente desta sessão de pesquisa; o item abaixo é, portanto, `[ASSUMED]` e o planner deve gate atrás de um `checkpoint:human-verify` antes de instalar.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `python-multipart` | PyPI | maduro (anos) | dezenas de M/semana | github.com/Kludex/python-multipart | (não rodado) | `[ASSUMED]` — dependência recomendada oficial do FastAPI para forms/uploads; verificar com `pip index versions python-multipart` antes de instalar |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

`python-multipart` é a dependência canônica que o próprio FastAPI instrui a instalar para suportar `Form`/`UploadFile` (a doc do FastAPI levanta `RuntimeError: Form data requires "python-multipart"` se ausente). Mesmo assim, por slopcheck não ter rodado, está marcado `[ASSUMED]` — o planner deve inserir `checkpoint:human-verify` antes do `uv add python-multipart`.

## Architecture Patterns

### System Architecture Diagram

```
                        ┌─────────────────────── PREVIEW DE SINAIS (novo) ───────────────────────┐
  PDF de teste  ──upload(multipart/base64)──▶ POST /templates/preview-signals                      │
                                                   │                                                │
                                                   ▼                                                │
                                          pdf_io.detect_blob_type                                    │
                                                   │ pdf? ──▶ extract_text_and_decide (texto nativo) │
                                                   │ imagem/route="vision" ──▶ aviso "escaneado"     │
                                                   ▼                                                  │
                              matcher._parse_groups(template.signals_json)                            │
                                                   │                                                  │
                              p/ cada grupo: _group_matches ; p/ cada cond: _condition_matches        │
                                                   │  (USANDO a normalização nova p/ texto)           │
                                                   ▼                                                   │
                              relatório { grupo: {casa, condições:[{mode,value,casa}]} }  ──▶ UI       │
                        └─────────────────────────────────────────────────────────────────────────┘

  Ingestão normal (inalterada na forma; matcher mais tolerante por dentro):
   extract_stage ──▶ classify_stage ─┬─ matcher.match_templates (normalização nova p/ texto)
                                      ├─ matcher.decide ──▶ matched / ambiguous / quarantine
                                      │                         │ambiguous──▶ IA desempate (já existe)
                                      │                         │quarantine + toggle ON + nada-casou
                                      │                         │      └──▶ IA classifica TODOS (NOVO, D-05)
                                      └─ filler ──▶ validação ──▶ persistência atômica

  Reprocessar (novo, D-10..D-12):
   UI botão (por-doc ou lote) ──▶ POST /documents/{id}/reprocess  |  POST /documents/reprocess (batch)
        │ doc em QUARENTENA ou EM_REVISAO?                          │ itera ids do balde
        ▼                                                           ▼
   apaga CR existente (Pitfall 3) ──▶ transition(PROCESSANDO) ──▶ _requeue(classify, {content_hash}) [SEM forced]
        └──▶ worker roda classify_stage com os templates ATUAIS
```

### Pattern 1: Normalização pura aplicada simetricamente (D-02/D-03)
**What:** Uma função `_normalize_text(s: str) -> str` em `matcher.py`, aplicada ao `haystack` UMA vez e ao `value` de cada condição `texto`. NUNCA aplicada ao ramo `regex`.
**When to use:** Só no ramo `texto`/default de `_condition_matches`.
**Example (decisão fechada — ver detalhamento na seção "Normalização"):**
```python
# Source: novo, espelha naming._strip_accents (naming.py:146-154)
import re as _re  # módulo stdlib só p/ a regex de normalização (não confundir com `regex`)
import unicodedata

_PUNCT_RE = _re.compile(r"[^\w\s]", _re.UNICODE)   # tudo que não é palavra/espaço → espaço
_WS_RE = _re.compile(r"\s+")                        # runs de espaço E \n → 1 espaço

def _normalize_text(s: str) -> str:
    """Normaliza p/ casamento tolerante de `texto` (D-02). PURA. Não loga (V7)."""
    decomposed = unicodedata.normalize("NFKD", s or "")
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = no_accents.lower()
    no_punct = _PUNCT_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", no_punct).strip()
```

### Pattern 2: Reuso do motor puro na ferramenta de teste (D-09)
**What:** O endpoint de preview NÃO reimplementa lógica de casamento — chama `_parse_groups`, e para cada grupo/condição usa `_group_matches`/`_condition_matches` (que já passarão a usar a normalização). Para o relatório por-sinal, itera as condições e chama `_condition_matches(cond, haystack_normalizado)` individualmente.
**When to use:** Endpoint de preview.
**Nota de seam:** O matcher hoje só expõe resultado booleano agregado. Para o relatório por-sinal, o endpoint precisa do haystack normalizado E do haystack lowercase-só (para regex). **Recomendação:** expor um helper público no matcher, ex. `evaluate_groups(groups, full_text) -> list[GroupReport]`, para que tanto o stage quanto o preview consumam a MESMA preparação de haystack (evita o preview montar o haystack "por fora" e divergir — risco D-09).

### Pattern 3: Reprocess = reclassify menos o template forçado
**What:** `reprocess` copia `reclassify_document` (`documents.py:600-653`) com 3 diferenças: (a) aceita QUARENTENA **e** EM_REVISAO; (b) NÃO recebe `template_id` no body; (c) `_requeue` com payload `{"content_hash": ...}` SEM `forced_template_id`.
**Crítico (Pitfall 3, herdado):** apagar o `ClassificationResult` existente ANTES de re-enfileirar — senão a idempotência do `classify_stage` (`stage.py:163-174`) faz no-op e o doc volta sem reclassificar.

### Anti-Patterns to Avoid
- **Embutir IA no matcher:** o fallback D-05 vive no `classify_stage`, nunca em `matcher.decide` (quebra o seam D-03/D-06).
- **Normalizar o haystack do regex:** quebra patterns que dependem de `\n`/acento/pontuação (ex.: `\d{44}` é imune, mas um pattern com `\.` ou `$` quebraria). Manter regex no haystack lowercase-só atual.
- **Reimplementar o casamento no preview:** viola D-09 (resultado divergiria do real).
- **Logar `full_text` / `value` de sinal / conteúdo do doc de teste:** viola LGPD/V7 — vale TAMBÉM para o endpoint de preview e o reprocess.
- **`eval`/dispatch implícito:** manter dispatch explícito por etiqueta (já é a regra do matcher e do naming).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Remoção de acentos | tabela própria de mapeamento | `unicodedata.normalize("NFKD")` + drop combining (reusar `_strip_accents`) | Stdlib cobre Latin-1/Unicode; já é o padrão do projeto |
| Extração de texto nativo no preview | parser de PDF próprio | `pdf_io.extract_text_and_decide` | Já existe, decide texto-vs-visão e dá custo zero |
| Detecção escaneado-vs-texto | heurística nova | `extract_text_and_decide` devolve `route="vision"` quando não há texto nativo | Reusa o limiar `openai_extract_min_chars_per_page` |
| Re-enfileirar job respeitando UNIQUE | enqueue cru | `_requeue` (`documents.py:549`) | Já resolve a UNIQUE `uq_jobs_hash_step` (reset → pending) |
| Transição de estado | set `doc.state =` direto | `transition()` (state machine) | Allowlist + commit atômico interno |
| Persistir setting sem reiniciar | escrever `.env` manual | `persist_env_setting` + `get_settings.cache_clear()` | Padrão de `/config/review-threshold` (atômico) |
| Proteção ReDoS | tetos de tamanho como defesa única | `regex` lib com `timeout=` no `.search` | Já implementado; tetos são só defesa em profundidade |

**Key insight:** Praticamente todo "tijolo" desta fase já existe. O valor está em **compor** corretamente preservando invariantes, não em construir.

## Runtime State Inventory

> Esta fase NÃO é rename/refactor/migração. Adiciona código e 1 setting de config. Mesmo assim, mapeio o estado relevante para o reprocess:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `ClassificationResult` de docs em QUARENTENA (template_id=NULL) e EM_REVISAO precisa ser APAGADO antes do reprocess (senão idempotência faz no-op) | Apagar CR no endpoint reprocess (cascade limpa FilledFields), igual ao `reclassify` |
| Stored data | `Job` com (content_hash, "classify") possivelmente `done` de uma classificação anterior | `_requeue` já reseta a linha para `pending` (não precisa apagar) |
| Live service config | Novo setting `classify_ai_fallback_enabled` (bool, default False) no `.env` | Novo campo em `Settings` + endpoint `/config` que persiste; default OFF preserva comportamento atual |
| OS-registered state | Nenhum | None — verificado: nenhuma tarefa de SO referencia classificação |
| Secrets/env vars | `OPENAI_API_KEY` já existe (SecretStr); o fallback D-05 reusa o cliente existente | None — chave inalterada |
| Build artifacts | `python-multipart` (se usar UploadFile) é nova dependência de runtime | `uv add python-multipart` + reinstalar; sem isso, `UploadFile` levanta RuntimeError |

**Migração de dados vs edição de código:** O reprocess é **edição de comportamento** (novo endpoint), não migração de dados — não altera registros existentes em massa; cada doc é reprocessado sob demanda. A config nova tem default que preserva o comportamento atual, então NÃO há migração Alembic (é setting de env, não coluna).

## Common Pitfalls

### Pitfall 1: Quebrar o regime de ReDoS/timeout ao mexer no matcher
**What goes wrong:** Ao adicionar a normalização, mexer no ramo `regex` ou nos tetos `_MAX_HAYSTACK_LEN`/`_REGEX_TIMEOUT_S`.
**Why it happens:** A normalização e o regex compartilham `_condition_matches`.
**How to avoid:** Bifurcar CEDO em `_condition_matches`: `if mode == "regex": <inalterado, haystack lowercase-só>` ; `else: <usa haystack normalizado>`. O `match_templates` deve preparar AMBOS os haystacks (normalizado p/ texto, lowercase-só p/ regex) e passá-los adiante, OU `_condition_matches` recebe o `full_text` cru e normaliza por-condição (mais simples, ligeiramente mais custo). Recomendação: preparar os dois haystacks UMA vez em `match_templates`/no helper público e passar o adequado por modo.
**Warning signs:** `test_matcher_groups.py::test_regex_*` e `test_redos*` falhando.

### Pitfall 2: Assimetria de normalização (D-02 explícito)
**What goes wrong:** Normalizar só o `haystack` e não o `value` do sinal (ou vice-versa) → casamento falha.
**How to avoid:** No ramo `texto`, normalizar AMBOS com a MESMA função: `_normalize_text(value) in haystack_normalizado`.
**Warning signs:** Um sinal "Nota Fiscal" não casa um texto que claramente contém "nota fiscal".

### Pitfall 3: Idempotência do classify_stage no reprocess
**What goes wrong:** Re-enfileirar `classify` sem apagar o `ClassificationResult` existente → `stage.py:163-174` vê o CR e faz no-op (não reclassifica).
**How to avoid:** Apagar o CR (e cascade FilledFields) ANTES de `transition`/`_requeue`, exatamente como `reclassify_document` (`documents.py:631-637`).
**Warning signs:** "Reprocessei e nada mudou" — o doc volta ao mesmo estado.

### Pitfall 4: Transição inválida no reprocess de EM_REVISAO
**What goes wrong:** EM_REVISAO→PROCESSANDO É válida (`states.py:32-37`), e QUARENTENA→PROCESSANDO também (`states.py:40`). Mas chamar reprocess sobre um doc que NÃO está num desses estados.
**How to avoid:** Guard semântico explícito ANTES do `transition` (como `retry`/`reclassify` fazem): `if doc.state not in {QUARENTENA, EM_REVISAO}: 409`. A allowlist sozinha não basta (PROCESSANDO é alcançável de vários estados).
**Warning signs:** 500 em vez de 409 ao reprocessar um doc CONCLUIDO.

### Pitfall 5: Custo silencioso do toggle de IA-fallback (D-05)
**What goes wrong:** Ligar o toggle faz TODO doc não-casado virar 1 chamada paga de IA; um lote grande de docs heterogêneos gera custo inesperado.
**How to avoid:** Default OFF (já é a decisão); rotular claramente na UI ("cada documento não reconhecido gera 1 chamada de IA"); persistir `Usage(step="classify")` na chamada (igual ao desempate, `stage.py:234-241`) para a cobrança aparecer.
**Warning signs:** Pico de tokens após ligar o toggle.

### Pitfall 6: python-multipart ausente quebra o endpoint de preview
**What goes wrong:** `UploadFile`/`File()` sem `python-multipart` → `RuntimeError` em runtime (não no import).
**How to avoid:** `uv add python-multipart` ANTES; OU usar base64 (sem dependência). Decidir no planning.
**Warning signs:** Erro só aparece ao testar o upload, não no boot.

### Pitfall 7: Documento de teste escaneado (D-08)
**What goes wrong:** Usuário faz upload de um PDF escaneado (sem texto nativo) na ferramenta de teste; `extract_text_and_decide` devolve `route="vision"` e texto vazio/curto → todos os sinais "falham" e confunde o usuário.
**How to avoid:** Quando `route == "vision"` (ou texto abaixo do limiar), o endpoint devolve um flag `scanned=true` e a UI mostra "Este documento parece escaneado; o teste de sinais só funciona com PDF de texto nativo. Use o caminho de IA na ingestão real." NÃO chamar IA na ferramenta (MVP, sem custo).
**Warning signs:** Usuário reporta "todos os sinais falham" num scan.

### Pitfall 8: Acoplamento de import classification→automation
**What goes wrong:** Importar `_strip_accents` de `app.automation.naming` dentro de `app.classification.matcher` cria dependência cross-package.
**Why it matters:** O matcher é descrito como motor PURO de classificação; importar de `automation` mistura camadas.
**How to avoid:** Recomendação: **copiar** o corpo de `_strip_accents` (4 linhas de stdlib) para `matcher._normalize_text` em vez de importar — o CONTEXT diz "reusar o PADRÃO", não necessariamente o símbolo. Mantém o matcher autossuficiente. (Se preferir DRY estrito, extrair para `app/shared/text.py` — mais trabalho, decisão de planning.)

## Code Examples

### Bifurcação por modo no matcher (texto normalizado vs regex lowercase-só)
```python
# Source: refactor de matcher._condition_matches (matcher.py:118-149)
def _condition_matches(cond: dict, haystack_norm: str, haystack_lower: str) -> bool:
    value = str(cond.get("value", ""))
    mode = cond.get("mode", "texto")
    if mode == "regex":
        # INALTERADO: regex roda contra haystack só-lowercase, com tetos + timeout.
        if not value or len(value) > _MAX_SIGNAL_REGEX_LEN:
            return False
        try:
            pattern = regex.compile(value, regex.IGNORECASE)
            return pattern.search(
                haystack_lower[:_MAX_HAYSTACK_LEN], timeout=_REGEX_TIMEOUT_S
            ) is not None
        except (regex.error, TimeoutError):
            return False
    # texto/default: AMBOS normalizados (D-02 simétrico).
    needle = _normalize_text(value)
    if not needle:
        return False
    return needle in haystack_norm
```
*(O `match_templates` prepara `haystack_norm = _normalize_text(full_text)` e `haystack_lower = (full_text or "").lower()` UMA vez e repassa aos grupos. Mesmo helper consumido pelo preview — D-09.)*

### Endpoint de reprocess (single) — espelho do reclassify sem template
```python
# Source: novo em documents.py, espelha reclassify_document (documents.py:600-653)
@router.post("/documents/{document_id}/reprocess", response_model=DocumentDetailOut)
def reprocess_document(request: Request, document_id: int) -> DocumentDetailOut:
    engine = request.app.state.engine
    with get_session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"documento {document_id} não encontrado")
        if doc.state not in (DocState.QUARENTENA, DocState.EM_REVISAO):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "reprocessar só é permitido para QUARENTENA ou EM_REVISAO",
            )
        cr = session.scalar(
            select(ClassificationResult).where(ClassificationResult.document_id == document_id)
        )
        if cr is not None:
            session.delete(cr)  # Pitfall 3: senão idempotência faz no-op
        try:
            transition(session, doc, DocState.PROCESSANDO)
        except InvalidTransition as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        _requeue(
            session,
            content_hash=doc.content_hash,
            step=CLASSIFY_STEP,
            payload={"content_hash": doc.content_hash},  # SEM forced_template_id
        )
        return _build_detail(session, doc, _folder_path_for(session, doc))
```
*(Batch: novo `POST /documents/reprocess` recebendo `{"ids":[...]}` ou `{"bucket":"quarentena"|"em_revisao"}`; itera a mesma lógica numa só sessão, ignorando ids fora dos estados elegíveis — retorna `{reprocessed: N}`. Recomendação: aceitar `bucket` (resolve os ids no backend a partir de `/documents/attention`) para o botão "reprocessar todos" — D-12.)*

### IA fallback no classify_stage (D-05/D-06)
```python
# Source: novo ramo em classify_stage, ANTES de quarentenar (stage.py:251-256)
# Após decision.status == "quarantine" e matched_template_id is None:
if matched_template_id is None and settings.classify_ai_fallback_enabled and forced_template_id is None:
    # nada casou (confiança 0.0) + toggle ON → IA tenta classificar contra TODOS.
    result, usage = await openai_client.disambiguate(
        _candidates_summary(templates),   # TODOS os templates, não só os "ambiguous"
        extraction.full_text,
    )
    called_ai = True
    usages.append(Usage(document_id=doc.id, step=USAGE_STEP,
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens))
    confidence = result.confidence
    if result.matched_template_id is not None and result.matched_template_id in by_id:
        matched_template_id = result.matched_template_id
    # se ainda None → segue para quarentena (com o Usage da tentativa persistido).
```
*(Reusa `disambiguate` (já existe) com TODOS os templates como candidatos. O seam `matcher.decide` permanece puro: a decisão de chamar IA é do stage. O `Usage` é persistido mesmo quando a IA não casa — a tentativa foi paga.)*

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Matcher substring case-insensitive literal (E exato) | + normalização (acento/pontuação/espaço/quebra) p/ `texto` | Esta fase | Menos quarentenas por diferenças mecânicas; tradeoff: não resolve palavra trocada (D-04) |
| Quarentena terminal exige reclassify com template manual | Reprocessar automático sem template (QUARENTENA+EM_REVISAO) | Esta fase | Tuning de templates sem re-ingerir |
| IA só desempata "ambiguous" | + IA classifica quando nada casa (opt-in OFF) | Esta fase | Recuperação opcional, custo explícito |

**Deprecated/outdated:** nada removido; tudo é aditivo e retrocompatível (default OFF, normalização não quebra grupos que já casavam — só amplia o que casa).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `python-multipart` é a dependência correta e legítima para `UploadFile` no FastAPI | Package Audit | Baixo — é a dependência oficial documentada; mitigável escolhendo base64 |
| A2 | Normalizar pontuação removendo `[^\w\s]→espaço` é a escolha certa p/ os documentos do cliente (DANFE etc.) | Normalização | Médio — pontuação em CNPJ/datas vira espaço; mas o casamento de CNPJ literal costuma ser por `regex` (imune) ou o usuário ajusta via ferramenta de teste. Validar com o caso DANFE real do piloto. |
| A3 | Copiar `_strip_accents` em vez de importar de `automation` é preferível p/ pureza do matcher | Pitfall 8 | Baixo — decisão de estilo; ambos funcionam |
| A4 | `disambiguate` com TODOS os templates como candidatos funciona bem para "classificar quando nada casa" (não só desempatar 2-3) | IA fallback | Médio — o prompt foi escrito para desempate entre poucos candidatos; com muitos templates pode degradar. Validar com o número real de templates do cliente; se necessário, prompt dedicado (mas D-06 pede reusar o caminho existente). |
| A5 | Batch reprocess por `bucket` resolve os ids no backend a partdos estados elegíveis | Reprocess | Baixo — alinhado a D-12; alternativa é o frontend mandar a lista de ids |

## Open Questions

1. **Multipart (`UploadFile`) vs base64 no endpoint de preview**
   - What we know: o cliente fetch atual (`api.ts`) é JSON-only; `UploadFile` exige `python-multipart` (não instalado).
   - What's unclear: se vale adicionar a dependência ou enviar base64.
   - Recommendation: **multipart + `python-multipart`** (idiomático, sem inflar payload, e o React envia `FormData` direto). Gate de slopcheck antes de instalar. Decidir no planning.

2. **Pontuação na normalização afeta sinais com pontuação intencional**
   - What we know: D-02 pede "normalizar/neutralizar pontuação"; CNPJ `12.345.678/0001-99` e datas têm pontuação.
   - What's unclear: se algum cliente usa sinal `texto` com pontuação como âncora.
   - Recommendation: aplicar a normalização de pontuação simetricamente (sinal e haystack viram "12 345 678 0001 99") — como ambos passam pela MESMA função, o casamento continua funcionando. Documentar e cobrir com teste (CNPJ literal como `texto` deve casar pós-normalização). Sinais que precisam de pontuação exata podem usar modo `regex` (imune).

3. **Helper público no matcher para o relatório por-sinal**
   - What we know: o matcher hoje só expõe booleano agregado; o preview precisa de detalhamento por-grupo/sinal.
   - Recommendation: adicionar `evaluate_groups(groups, full_text) -> list[GroupReport]` público (dataclass com `matched: bool` e `conditions: list[ConditionReport]`), consumido pelo preview. O `match_templates` pode reusá-lo internamente (ou ambos compartilham a preparação de haystack). Fechar a forma exata no planning.

4. **Onde expor o toggle de IA-fallback na UI**
   - Recommendation: `ConfigPage.tsx` ao lado do limiar de revisão (mesmo padrão `/config`); novo endpoint `GET/PUT /config/ai-fallback` espelhando `/config/review-threshold`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PyMuPDF (`fitz`) | extração de texto no preview | ✓ | 1.27.x | — |
| `regex` lib | matcher (já em uso) | ✓ | instalada | — |
| OpenAI SDK + chave | IA fallback (D-05) | ✓ (SDK) / por-instância (chave) | 2.41.x | toggle OFF = sem IA |
| `python-multipart` | `UploadFile` no preview | ✗ | — | base64 no body JSON (sem dependência) |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** `python-multipart` — fallback base64.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (mock OpenAI via respx/fakes) |
| Config file | `backend/pyproject.toml` (pytest config) |
| Quick run command | `cd backend && uv run pytest tests/classification -x -q` |
| Full suite command | `cd backend && uv run pytest -q` |

### Phase Requirements → Test Map
| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| D-02 | normalização simétrica casa "NATUREZA DA"≈"NATUREZA DE"? (NÃO — D-04) ; casa acento/quebra/pontuação | unit | `uv run pytest tests/classification/test_matcher_norm.py -x` | ❌ Wave 0 |
| D-02 | sinal "nota fiscal" casa texto "Nota\nFiscal" / "NOTA FISCAL" / "Notá Fiscál" | unit | idem | ❌ Wave 0 |
| D-03 | regex `\d{44}` e ReDoS/timeout INTACTOS pós-mudança | unit | `uv run pytest tests/classification/test_matcher_groups.py -x` | ✅ (legados — devem continuar verdes) |
| D-05 | toggle OFF = quarentena direta; ON + nada casou = chama IA antes de quarentenar; Usage persistido | unit (mock IA) | `uv run pytest tests/classification/test_stage_ai_fallback.py -x` | ❌ Wave 0 |
| D-07/D-09 | preview reusa o motor: relatório por-grupo/sinal idêntico ao real; escaneado→flag scanned | api | `uv run pytest tests/test_api_templates.py -x` | ✅ (estender) |
| D-10/D-11 | reprocess QUARENTENA→PROCESSANDO + requeue classify SEM forced; apaga CR; doc fora dos estados→409 | api | `uv run pytest tests/test_api_documents.py -x` | ✅ (estender) |
| D-12 | reprocess batch sobre balde; idempotente | api | idem | ✅ (estender) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/classification -x -q`
- **Per wave merge:** `uv run pytest -q` (backend) + `npm run build` (frontend, type-check)
- **Phase gate:** suite completa verde antes de `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/classification/test_matcher_norm.py` — cobre D-02/D-03 (normalização e bifurcação regex)
- [ ] `tests/classification/test_stage_ai_fallback.py` — cobre D-05 (toggle ON/OFF, Usage)
- [ ] Estender `tests/test_api_templates.py` — endpoint preview (texto nativo, escaneado, por-sinal)
- [ ] Estender `tests/test_api_documents.py` — reprocess single + batch + guards 409
- [ ] (se multipart) garantir `python-multipart` instalado antes dos testes de upload

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Pydantic nos bodies; `UploadFile` com checagem de magic bytes (`detect_blob_type`) e teto de tamanho do upload; modo de sinal já é `Literal` (422) |
| V5 ReDoS | yes | `regex` lib com `timeout` + tetos — **NÃO alterar** ao adicionar normalização |
| V7/V8 Logging & Data Protection (LGPD) | yes | NUNCA logar `full_text`, valores de sinal, ou conteúdo do PDF de teste (vale p/ preview e reprocess) |
| V4 Access Control | n/a (single-tenant, sem auth) | — |
| V6 Cryptography | no | — |

### Known Threat Patterns for FastAPI + upload + regex do operador
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| ReDoS via regex de sinal colada pelo operador | DoS | timeout REAL no `.search` (já existe); não regredir |
| Upload de arquivo gigante na ferramenta de teste | DoS | limitar tamanho do upload (ler até N MB; rejeitar maior); `_MAX_HAYSTACK_LEN` já corta o haystack |
| Vazamento de conteúdo sensível em log | Information Disclosure | não logar conteúdo do doc de teste nem valores; preview retorna só casa/falha + os valores DE SINAL (config do operador, não do documento) |
| Upload de não-PDF / PDF malformado | Tampering/DoS | `detect_blob_type` (magic bytes) → 422 amigável; PDF malformado → erro controlado |

## Sources

### Primary (HIGH confidence — código do próprio projeto)
- `backend/app/classification/matcher.py` — motor puro, `_condition_matches`, `decide`, tetos ReDoS
- `backend/app/classification/stage.py` — `classify_stage`, idempotência, quarentena, caminho de IA
- `backend/app/api/documents.py` — `reclassify`/`retry`/`_requeue`/`attention` (base do reprocess)
- `backend/app/api/templates.py` — CRUD, `_loads_signals_groups` (seam sincronizado com matcher)
- `backend/app/api/config.py` + `backend/app/config.py` — padrão de setting global + persist `.env`
- `backend/app/automation/naming.py` — `_strip_accents` (padrão de normalização, Phase 9)
- `backend/app/extraction/pdf_io.py` — `extract_text_and_decide`, `detect_blob_type`, render
- `backend/app/classification/openai_client.py` + `schema.py` — `disambiguate` (reuso D-05)
- `backend/app/pipeline/states.py` — allowlist (QUARENTENA/EM_REVISAO → PROCESSANDO válidas)
- `backend/app/queue/worker.py` — dispatch do step classify com/sem `forced_template_id`
- `.planning/notes/2026-06-24-melhorias-teste-usuario-final.md` — Itens 5 e 6 (sintomas reais)
- `frontend/src/lib/api.ts`, `frontend/src/pages/{TemplatesPage,DocumentsPage,AttentionPage}.tsx`, `frontend/src/hooks/*` — pontos de integração UI

### Secondary (MEDIUM confidence)
- CLAUDE.md / Resumo Prescritivo — stack travado (PyMuPDF, FastAPI, Pydantic, Responses API)

### Tertiary (LOW confidence)
- `python-multipart` como dependência do FastAPI para uploads — conhecimento de treinamento `[ASSUMED]`, verificar com `pip index versions python-multipart` + slopcheck antes de instalar.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — nenhuma tecnologia nova além de multipart opcional; tudo no código
- Architecture: HIGH — pontos de alteração mapeados exatos (arquivo:linha)
- Pitfalls: HIGH — derivados de invariantes documentados no próprio código (ReDoS, idempotência, seam, LGPD)
- IA fallback (A4) e pontuação (A2): MEDIUM — dependem de validação contra docs reais do piloto

**Research date:** 2026-06-24
**Valid until:** 2026-07-24 (código estável; revisar se o matcher/stage mudar antes do planning)

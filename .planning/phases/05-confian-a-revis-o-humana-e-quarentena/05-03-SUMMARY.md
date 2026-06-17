---
phase: 05-confian-a-revis-o-humana-e-quarentena
plan: 03
subsystem: api
tags: [review-endpoints, triage, attention, reclassify, retry, approve, patch-field, config-threshold, fastapi, pytest]

# Dependency graph
requires:
  - phase: 05-confian-a-revis-o-humana-e-quarentena
    plan: 01
    provides: "compute_confidence (puro), confidence_score/manually_corrected (colunas), review_confidence_threshold (tunable), migração 0005"
  - phase: 05-confian-a-revis-o-humana-e-quarentena
    plan: 02
    provides: "classify_stage roteia EM_REVISAO + aceita forced_template_id; repo.requeue_step; worker lê forced_template_id"
  - phase: 04-templates-sub-templates-e-classifica-o
    provides: "api/documents.py (get_document/list_documents), transition+InvalidTransition (allowlist), validate_field, ClassificationResult/FilledField/Template"
provides:
  - "POST /documents/{id}/retry (FALHA→PROCESSANDO + reenfileira extract/classify por last_completed_step; não-FALHA → 409)"
  - "POST /documents/{id}/reclassify (valida template 404, apaga CR de quarentena ANTES, QUARENTENA→PROCESSANDO, requeue_step com forced_template_id; não-QUARENTENA → 409)"
  - "PATCH /documents/{id}/fields/{field_name} (revalida via validate_field SEM IA, manually_corrected=True, recalcula confidence_score; doc fica EM_REVISAO)"
  - "POST /documents/{id}/approve (EM_REVISAO→CONCLUIDO só com obrigatórios válidos, guard D-07; senão 409)"
  - "GET /documents/attention (3 baldes num payload, EM_REVISAO com campos editáveis, sem N+1 via selectinload; registrado ANTES de /documents/{id})"
  - "GET/PUT /config/review-threshold (limiar global legível/editável, persiste no .env atômico + cache_clear, 422 fora de [0,1])"
  - "config.persist_env_setting + config.env_file_path (escrita atômica de tunables no .env)"
affects: [05-04 frontend AttentionPage/ConfidenceBadge/useAttention/api.ts]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pré-condição de estado explícita ANTES do transition: a allowlist permite PROCESSANDO a partir de vários estados, então retry/reclassify checam doc.state == FALHA/QUARENTENA antes do transition (allowlist necessária, não suficiente)"
    - "_build_detail extraído de get_document: endpoints de ação retornam o mesmo DocumentDetailOut sem duplicar a query do CR/FilledFields"
    - "_has_invalid_required re-deriva a validade ATUAL dos obrigatórios (não confia no confidence_score persistido — Pitfall 4 / D-07)"
    - "Endpoint dedicado /attention com selectinload(ClassificationResult.filled_fields) monta EM_REVISAO num passo (Open Q3 evita N+1)"
    - "persist_env_setting: escrita atômica (tmp + os.replace) substituindo/anexando a chave; + get_settings.cache_clear() relê sem reiniciar"

key-files:
  created:
    - backend/app/api/config.py
    - backend/tests/test_api_config.py
  modified:
    - backend/app/api/documents.py
    - backend/app/config.py
    - backend/app/main.py
    - backend/tests/test_api_review.py

key-decisions:
  - "Pré-condição de estado explícita em retry/reclassify: a allowlist (states.py) permite EM_REVISAO→PROCESSANDO e QUARENTENA→PROCESSANDO e FALHA→PROCESSANDO, então transition sozinho NÃO distingue a origem — adicionado guard doc.state == FALHA/QUARENTENA antes do transition para honrar o <behavior> (não-FALHA/não-QUARENTENA → 409)"
  - "Reclassify checa template (404) ANTES do guard de estado: template inexistente → 404 mesmo em doc QUARENTENA; doc não-QUARENTENA com template válido → 409"
  - "Steps do worker (extract/classify/extraido) duplicados como constantes em documents.py para evitar importar worker.py (imports pesados); as strings são contrato estável da fila"
  - "persist_env_setting/env_file_path em config.py (ponto único) para a escrita do .env ser atômica e testável via monkeypatch, sem poluir o .env real"

patterns-established:
  - "Guard de transição = allowlist (transition) + pré-condição de estado explícita quando o destino é alcançável de múltiplas origens"
  - "Persistência de tunable global no .env + cache_clear como seam de config runtime (sem reiniciar o processo)"

requirements-completed: [REV-02, REV-03, REV-04, REV-05]

# Metrics
duration: 8min
completed: 2026-06-17
---

# Phase 5 Plan 03: API de Triagem + Limiar Global Summary

**Os 4 endpoints de ação de revisão (retry/reclassify/patch-de-campo/approve), cada um com a allowlist + pré-condição de estado como guard (409), o `GET /documents/attention` dedicado (3 baldes num payload, sem N+1), e o `GET/PUT /config/review-threshold` (limiar global persistido no `.env` + cache_clear) — a superfície que a UI do Plan 04 consome para resolver cada documento parado e ajustar o limiar.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-17T03:45:07Z
- **Tasks:** 3
- **Files modified:** 6 (2 criados, 4 editados)

## Accomplishments

- **4 endpoints de ação (REV-04/REV-05, Task 1):** em `api/documents.py`, cada um com `transition` como guard de allowlist (InvalidTransition → 409) MAIS uma pré-condição de estado explícita onde necessário:
  - `POST /retry` — só FALHA (senão 409), `FALHA→PROCESSANDO`, reenfileira `classify` se `last_completed_step=="extraido"` senão `extract`.
  - `POST /reclassify` — valida `Template` (404 se inexistente, T-05-07), só QUARENTENA (senão 409), APAGA o CR de quarentena ANTES (Pitfall 3, cascade limpa FilledFields), `QUARENTENA→PROCESSANDO`, `requeue_step` com `forced_template_id` (D-09).
  - `PATCH /fields/{field_name}` — revalida via `validate_field` SEM IA (D-08), `manually_corrected=True`, recalcula `confidence_score` no MESMO commit (Pitfall 4); doc permanece EM_REVISAO.
  - `POST /approve` — guard D-07 via `_has_invalid_required` (re-deriva a validade ATUAL dos obrigatórios), `EM_REVISAO→CONCLUIDO`; obrigatório inválido ou doc fora de EM_REVISAO → 409.
- **GET /documents/attention (REV-03, Task 2):** 3 baldes (`falha`/`quarentena`/`em_revisao`) + `counts` num payload só (Open Q3). EM_REVISAO traz `confidence_score` + os campos editáveis montados com `selectinload(ClassificationResult.filled_fields)` (sem N+1). Motivo de QUARENTENA fixo do UI-SPEC; motivo de FALHA = `last_error` do job (por content_hash) ou fallback. Registrado ANTES de `GET /documents/{document_id}` (senão "attention" seria capturado como id → 422). PROCESSANDO/CONCLUIDO/RECEBIDO não aparecem.
- **GET/PUT /config/review-threshold (REV-02/D-03, Task 3):** novo `api/config.py`. GET lê `get_settings().review_confidence_threshold`. PUT valida `ge=0.0 le=1.0` (422 fora), persiste `REVIEW_CONFIDENCE_THRESHOLD=<valor>` no `.env` via `persist_env_setting` (escrita atômica tmp+os.replace), e `get_settings.cache_clear()` para o stage reler sem reiniciar. Registrado em `main.py`.
- **Schemas estendidos:** `ClassificationOut.confidence_score` + `ClassificationFieldOut.manually_corrected`, populados em `get_document` (refatorado para reusar `_build_detail`) e em todos os retornos de ação.
- **Testes:** `test_api_review.py` (14 casos: guards 409, retry roteia classify/extract, reclassify apaga CR + payload com forced_template_id, patch revalida + sem-IA via `respx call_count==0` + recalcula score, approve bloqueia→desbloqueia, 3 baldes do /attention) + `test_api_config.py` (5 casos: default, persiste+reflete, 422 x2, sem duplicar chave). Suite completa verde (280 passed).

## Task Commits

1. **Task 1+2: 4 endpoints de ação + GET /attention** - `559438c` (feat)
2. **Task 3: GET/PUT /config/review-threshold + registro no main** - `c1d1773` (feat)

_Task 1 era `tdd="true"`: os testes (RED, 9 falhas confirmadas com endpoints ausentes) foram escritos antes da implementação (GREEN). Tasks 1 e 2 compartilham o mesmo arquivo (`documents.py`, schemas/helpers intertravados) e foram entregues num commit lógico único; ambos os blocos de teste estão no mesmo commit que prova as rotas._

## Files Created/Modified

- `backend/app/api/documents.py` - +5 rotas (retry/reclassify/patch/approve/attention); schemas estendidos (confidence_score/manually_corrected) + novos (FieldPatchIn/ReclassifyIn/AttentionItemOut/ReviewItemOut/AttentionOut); helpers `_build_detail`/`_field_out`/`_folder_path_for`/`_template_field`/`_has_invalid_required`/`_requeue`; get_document refatorado para reusar `_build_detail`
- `backend/app/api/config.py` (NOVO) - router `/config` com GET/PUT /review-threshold
- `backend/app/config.py` - +`env_file_path()` e `persist_env_setting()` (escrita atômica de tunable no .env)
- `backend/app/main.py` - +`app.include_router(config_api.router)`
- `backend/tests/test_api_review.py` - 14 casos (substitui os 4 scaffolds skip do Wave 0)
- `backend/tests/test_api_config.py` (NOVO) - 5 casos sobre .env temporário

## Decisions Made

- **Pré-condição de estado explícita em retry/reclassify** (decisão de implementação, dentro do escopo do `<behavior>`): a allowlist `TRANSITIONS` (states.py) permite `PROCESSANDO` a partir de FALHA, EM_REVISAO E QUARENTENA — logo `transition(...PROCESSANDO)` NÃO distingue a origem e não daria 409 para um doc EM_REVISAO num retry. Adicionei `if doc.state != DocState.FALHA → 409` (retry) e `if doc.state != DocState.QUARENTENA → 409` (reclassify) ANTES do transition. O `<behavior>` exige explicitamente "retry em doc não-FALHA → 409" e "reclassify em doc não-QUARENTENA → 409", então o guard é parte do contrato, não scope creep.
- **Ordem dos guards no reclassify:** template (404) antes da pré-condição de estado (409) — template inexistente é erro de input mais fundamental; um doc QUARENTENA com template inexistente devolve 404.
- **Constantes de step duplicadas em documents.py** (EXTRACT_STEP/CLASSIFY_STEP/EXTRACTED_STEP) em vez de importar `worker.py` — evita arrastar os imports pesados do worker para a camada de API; as strings são contrato estável da fila.
- **persist_env_setting/env_file_path centralizados em config.py:** escrita atômica (tmp + os.replace) testável por monkeypatch de um ponto único, sem poluir o .env real.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Import de `WatchedFolder` removido por engano durante a edição dos imports**
- **Found during:** Task 1 (após o primeiro bloco de edição de imports)
- **Issue:** Ao reescrever o bloco de imports de `documents.py` (adicionando transition/repo/validate_field/etc.), o import existente `from app.models.watched_folder import WatchedFolder` foi omitido, quebrando `list_documents`/`get_document`/`_folder_path_for` com `NameError` (7 testes de `test_api_documents.py`).
- **Fix:** Restaurado o import. Confirmado com a suite verde.
- **Files modified:** backend/app/api/documents.py
- **Commit:** `559438c`

**2. [Rule 1 - Bug] respx `assert_all_called` falhava no teste de patch sem-IA**
- **Found during:** Task 1 (teste `test_patch_field_revalidates_without_ai`)
- **Issue:** `respx.mock(...)` por padrão exige que TODAS as rotas mockadas sejam chamadas ao sair do contexto. O teste prova justamente que o patch NÃO chama a OpenAI (`call_count==0`), então a rota mockada nunca é chamada → respx levantava `AssertionError` ("some routes were not called").
- **Fix:** `respx.mock(base_url=..., assert_all_called=False)` — a asserção forte de não-chamada é `route.call_count == 0`, que é o ponto do teste (T-05-11).
- **Files modified:** backend/tests/test_api_review.py
- **Commit:** `559438c`

---

**Total deviations:** 2 auto-fixed (2 bugs de implementação/teste, ambos detectados e resolvidos no mesmo ciclo TDD)
**Impact on plan:** Sem scope creep. Ambos são correções de mecânica (import perdido; flag do mock) descobertas pelos próprios testes do plano. A pré-condição de estado em retry/reclassify (documentada em Decisions) é exigência do `<behavior>`, não desvio.

## Threat Surface

Todas as mitigações do `<threat_model>` materializadas:
- **T-05-07** (template forçado inexistente): `session.get(Template, template_id)` None → 404 antes de qualquer transição/reenfileiramento.
- **T-05-08** (mass-assignment no patch): FilledField buscado por `(cr.id do doc-alvo, field_name)`; `FieldPatchIn` só expõe `raw_value`.
- **T-05-09/T-05-10** (transição ilegal / approve com obrigatório inválido): `transition` (allowlist) + pré-condição de estado + `_has_invalid_required` re-derivado → 409.
- **T-05-11** (re-chamar IA no patch): patch usa SÓ `validate_field`; teste prova `respx call_count==0`.
- **T-05-14** (nenhuma automação de arquivo): `grep` confirma 0 ocorrências de shutil/os.rename/os.replace/automation em documents.py (approve só transita estado).
- **T-05-15** (limiar fora de faixa / corromper roteamento): `ReviewThresholdIn(threshold: float = Field(ge=0.0, le=1.0))` → 422; `.env` reescrito com chave única, valor já validado (nunca input cru em SQL/shell).

Nenhuma nova superfície de ameaça fora do registro do plano.

## Issues Encountered

- Nenhum bloqueio. Os 2 bugs (import perdido, flag respx) foram pegos pela própria suite de testes do plano e corrigidos no mesmo ciclo.

## User Setup Required

None - nenhuma configuração externa. O PUT do limiar grava no `.env` do diretório de trabalho do processo; o default 0.8 segue valendo quando a chave não está presente.

## Next Phase Readiness

- Superfície completa para o Plan 04 (frontend): `GET /documents/attention` (3 baldes + campos editáveis), `POST /retry|/reclassify|/approve`, `PATCH /fields/{name}`, `GET/PUT /config/review-threshold`. Os schemas Out (`confidence_score`/`manually_corrected`) já estão no `DocumentDetailOut`/`ReviewItemOut` que o `lib/api.ts` e `types.ts` do Plan 04 vão espelhar.

## Self-Check: PASSED

- FOUND: backend/app/api/config.py
- FOUND: backend/tests/test_api_config.py
- FOUND: backend/app/api/documents.py (5 rotas: retry/reclassify/patch/approve/attention; except InvalidTransition x3; validate_field no patch; requeue_step; sem automação de arquivo)
- FOUND: backend/app/main.py (config_api.router registrado)
- FOUND commit: 559438c
- FOUND commit: c1d1773
- Suite completa: 280 passed

---
*Phase: 05-confian-a-revis-o-humana-e-quarentena*
*Completed: 2026-06-17*

---
phase: 04-templates-sub-templates-e-classificacao
plan: 05
subsystem: classificacao
tags: [classification, stage, queue, worker, openai, idempotency, quarantine, atomic-commit, tdd]

# Dependency graph
requires:
  - phase: 04-templates-sub-templates-e-classificacao
    plan: 01
    provides: "Modelos ClassificationResult (UNIQUE document_id = rede anti double-charge) + FilledField (raw/normalized D-11, valid D-10); tunable classify_match_threshold; conftest respx de classify"
  - phase: 04-templates-sub-templates-e-classificacao
    plan: 02
    provides: "validation.fields.validate_field (Módulo 11 CNPJ/CPF, data dayfirst→ISO, moeda→Decimal) consumido por campo do template"
  - phase: 04-templates-sub-templates-e-classificacao
    plan: 03
    provides: "matcher.match_templates/decide (política D-03), filler.map_fields (missing_required), openai_client.disambiguate/fill_missing_fields, schema (DisambiguationResult/MissingFieldsResult)"
  - phase: 03-extracao-generica-via-ia-e-medicao-de-tokens
    provides: "extract_stage (forma/garantias a espelhar 1-para-1) + worker bifurcado por step (EXTRACT_STEP, _dispatch, _fail_for_step, enqueue_pending_extractions)"
provides:
  - "classify_stage async idempotente atômico (espelha extract_stage): matcher → (IA desempate) → filler → (IA faltantes) → validate_field → persistência num commit único"
  - "Quarentena via transition(QUARENTENA) com add(ClassificationResult(template_id=None)) ANTES (commit junto pelo transition)"
  - "CLASSIFIED_STEP='classificado' (marcador em memória) + USAGE_STEP='classify' (1 Usage por chamada paga)"
  - "worker: CLASSIFY_STEP, dispatch classify (coroutine await), _fail_for_step por content_hash, enqueue_pending_classifications (sweep idempotente de legados) chamado no startup"
affects: [classificacao, fila, stage, revisao-fase5]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Stage atômico idempotente: checa ClassificationResult ANTES de QUALQUER chamada paga (T-04-13/risco #1); commit único no caminho casou"
    - "Quarentena: add(ClassificationResult) + Usage ANTES de transition(QUARENTENA) — o transition faz o commit interno comitando tudo junto (T-04-14)"
    - "Merge D-06 por field_name normalizado (replica filler._norm: NFKD+casefold+espaços) casando ExtractedField.key da IA com o campo faltante"
    - "worker: classify despachado como coroutine (await direto, NUNCA to_thread — Pitfall 1); sweep idempotente no startup espelha enqueue_pending_extractions"

key-files:
  created:
    - backend/app/classification/stage.py
    - backend/tests/classification/test_stage.py
    - backend/tests/queue/test_classify_dispatch.py
  modified:
    - backend/app/queue/worker.py

key-decisions:
  - "classify_stage espelha extract_stage 1-para-1 em forma/garantias (idempotência por checagem prévia, commit único, marcador em memória, recusa propaga ao worker)"
  - "Quarentena resolve a atomicidade via ordem: add(CR template_id=None)[+Usage] ANTES de transition(QUARENTENA); o transition comita tudo junto — nunca estado parcial"
  - "Merge D-06 por NOME de campo (não por posição): ExtractedField.key da IA casa com o field_name faltante via normalização idêntica à do filler"
  - "Campo inválido (DV CNPJ/data) → FilledField.valid=False; documento SEGUE em PROCESSANDO (D-10 marca, não bloqueia) — não vira quarentena"
  - "Sweep de classify gateia em last_completed_step=='extraido' SEM ClassificationResult — um passo adiante do sweep de extract; idempotente por UNIQUE(content_hash, step)"
  - "Lacuna consciente de idempotência v1 (RESEARCH OQ1): falha ENTRE desempate e faltantes re-cobra o desempate no retry — ACEITO (raro), documentado em test_stage.py para evitar 'correção' regressiva"

patterns-established:
  - "Arquivo de testes de worker do classify separado (tests/queue/test_classify_dispatch.py) espelhando test_dispatch.py + test_enqueue_sweep.py — o plano citava test_worker.py (inexistente); seguimos a convenção real do repo"

requirements-completed: [TPL-03, TPL-04, EXT-04]

# Metrics
duration: 6min
completed: 2026-06-16
---

# Phase 4 Plan 05: classify_stage + fiação na fila Summary

**`classify_stage` async idempotente atômico (espelha `extract_stage`) que compõe matcher + (IA desempate) + filler + (IA faltantes) + validação/normalização num commit único, manda não-casados para QUARENTENA via `transition`, e a fiação na fila (novo `step="classify"` despachado como coroutine + sweep idempotente cobrindo legados) — fecha o pipeline ingest→extract→classify end-to-end com a rede dura contra double-charge**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-16T21:30:21Z
- **Completed:** 2026-06-16
- **Tasks:** 2 (ambas TDD RED→GREEN)
- **Files modified:** 4 (3 criados, 1 modificado)

## Accomplishments
- `classify_stage` espelha `extract_stage`: idempotência checa `ClassificationResult` ANTES de qualquer chamada paga (T-04-13/risco #1), commit atômico único no caminho casou, marcador "classificado" em memória, recusa/erro propagam ao worker
- Quarentena via `transition(QUARENTENA)` com `add(ClassificationResult(template_id=None))` + `Usage` ANTES — o `transition` comita tudo junto (T-04-14); o CR com template_id=None fica PERSISTIDO (prova explícita no teste), sem estado parcial
- Merge D-06 por field_name: a chamada paga de faltantes só roda para os obrigatórios sem par; o `ExtractedField.key` da IA casa com o campo faltante por normalização idêntica à do filler
- Campo inválido (DV CNPJ falho) → `FilledField.valid=False` + `invalid_reason`; o documento SEGUE em PROCESSANDO (D-10 marca, não bloqueia) — não vira quarentena
- `Usage(step="classify")` gravado exatamente 1x por chamada paga; caso custo-zero (matcher resolveu) → 0 Usage
- worker: `CLASSIFY_STEP`, `_dispatch` despacha `classify_stage` como coroutine (await direto, NUNCA `to_thread` — Pitfall 1), `_fail_for_step` roteia classify por content_hash, `enqueue_pending_classifications` (sweep idempotente de blocos "extraido" sem ClassificationResult) chamado no `run_worker` startup; `repo.py` intacto
- Suíte completa do backend verde: 247 testes (14 novos: 6 de stage + 8 de worker/sweep); ruff limpo

## Task Commits

Cada tarefa seguiu o ciclo TDD RED→GREEN com commits atômicos:

1. **Task 1 RED: testes falhando de classify_stage** - `a21d547` (test)
2. **Task 1 GREEN: classify_stage async idempotente atômico** - `f9941e0` (feat)
3. **Task 2 RED: testes falhando de classify worker dispatch + sweep** - `0e9d551` (test)
4. **Task 2 GREEN: fiação step=classify no worker + sweep de legados** - `d7e9c52` (feat)

## Files Created/Modified
- `backend/app/classification/stage.py` - `classify_stage` async + `ClassifyStageResult` + `CLASSIFIED_STEP`/`USAGE_STEP` + helpers (`_norm` merge D-06, `_candidates_summary`, `_missing_field_specs`)
- `backend/app/queue/worker.py` - `CLASSIFY_STEP`, ramo classify no `_dispatch` (coroutine await), `_fail_for_step` rotea classify por content_hash, `enqueue_pending_classifications` + chamada no startup
- `backend/tests/classification/test_stage.py` - 6 testes (casa/quarentena/idempotência/desempate/faltantes-merge/campo-inválido) + comentário da lacuna consciente
- `backend/tests/queue/test_classify_dispatch.py` - 8 testes (dispatch classify, FALHA por content_hash, sweep enfileira/idempotente/ignora-classificado/ignora-estado-errado, _fail_for_step, desempate via respx)

## Decisões Made
- **classify_stage espelha extract_stage 1-para-1:** mesma forma de idempotência (checagem prévia + UNIQUE), mesmo commit único, mesmo marcador em memória, mesma propagação de recusa/erro ao worker — reduz superfície de bug e mantém consistência de pipeline.
- **Ordem da quarentena (add ANTES de transition):** como `state_machine.transition` faz `session.commit()` interno, adicionar o `ClassificationResult(template_id=None)` + `Usage` à sessão ANTES e só então chamar o `transition` garante que tudo é comitado junto num único commit atômico, sem estado parcial (doc em QUARENTENA com registro).
- **Merge D-06 por nome (não por posição):** o stage replica a normalização do filler para casar `ExtractedField.key` ↔ `field_name` faltante (case-insensitive, NFKD); campos que a IA não devolver permanecem ausentes e são validados como obrigatório-faltante (D-10).
- **Arquivo de teste de worker separado:** o plano citava `tests/queue/test_worker.py`, que não existe no repo (o teste de dispatch é `tests/queue/test_dispatch.py` e o sweep vive em `tests/extraction/test_enqueue_sweep.py`). Criei `tests/queue/test_classify_dispatch.py` espelhando ambos os padrões reais, em vez de inventar um arquivo `test_worker.py` fora da convenção. Desvio de NOME de arquivo apenas — comportamento e cobertura exatamente os do plano.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `assert_all_called` do respx falhava os cenários sem chamada paga**
- **Found during:** Task 1 GREEN (test_casa_sem_ia)
- **Issue:** O `respx.mock(...)` por padrão exige que toda rota registrada seja chamada; nos cenários onde o matcher resolve sem IA (casa/quarentena/idempotência/campo-inválido) a rota `/responses` é registrada mas legitimamente NÃO é chamada — `assert_all_called` quebrava o teste.
- **Fix:** `respx.mock(base_url=..., assert_all_called=False)` nos testes do stage; os cenários que DEVEM chamar a IA continuam provando `route.call_count == 1` explicitamente. Sem impacto no comportamento do código de produção.
- **Files modified:** backend/tests/classification/test_stage.py
- **Commit:** f9941e0 (incluído no GREEN da Task 1)

**Desvio de nomenclatura (não-funcional):** arquivo de teste de worker criado como `tests/queue/test_classify_dispatch.py` (convenção real do repo) em vez do `tests/queue/test_worker.py` citado no plano (inexistente). Documentado em "Decisões Made".

## Threat Surface

Mitigações do `<threat_model>` aplicadas e provadas:
- **T-04-13** (double-charge): checagem de `ClassificationResult` ANTES de qualquer chamada paga — teste de idempotência prova `call_count` inalterado na 2ª execução.
- **T-04-14** (integridade de estado): quarentena só via `transition`; "classificado" só avança o marcador em memória + commit único (sem `mark_step`/auto-laço).
- **T-04-15** (enqueue dentro do stage): NÃO enfileiramos no stage; sweep idempotente no startup + UNIQUE(content_hash, step).
- **T-04-16** (vazamento): log só de metadados (document_id/template_id); `_candidates_summary` usa só config do operador (id/sinais), não conteúdo do documento.

Nenhuma superfície de segurança nova fora do `<threat_model>` foi introduzida.

## Known Stubs
None - todos os caminhos (casa/quarentena/desempate/faltantes/campo-inválido) estão wired e testados end-to-end.

## Issues Encountered
- Imports não usados (`TemplateField`/`Path` nos testes, `CLASSIFIED_STEP` no worker) pegos por ruff — removidos. Sem impacto funcional.
- `DeprecationWarning` do adapter de datetime do SQLite (Python 3.12) aparece em testes de fila — PRÉ-EXISTENTE (já em test_dispatch.py/test_queue.py), fora de escopo deste plano.

## User Setup Required
None - nenhuma configuração de serviço externo. Tunables (`classify_match_threshold`, `openai_classify_*`) já existem desde o Plan 01; `OPENAI_API_KEY` desde a Fase 1.

## Next Phase Readiness
- Pipeline ingest→extract→classify completo end-to-end; blocos extraídos legados são varridos e classificados no startup do worker.
- Fase 5 (revisão humana) tem a base: documentos não-casados ficam em QUARENTENA com `ClassificationResult(template_id=None)` persistido (motivo legível futuro); campos preenchidos guardam bruto+normalizado+valid/invalid_reason para o gate de revisão.
- Sem blockers.

## Self-Check: PASSED

Todos os 4 arquivos criados/modificados existem; os 4 commits de tarefa (a21d547, f9941e0, 0e9d551, d7e9c52) estão presentes no histórico; suíte completa do backend 247/247 verde; ruff limpo; greps de aceitação confirmados (`await classify_stage` no worker, `ClassificationResult`/`transition(...QUARENTENA)` no stage, `to_thread` ausente do ramo classify, `mark_step` só em comentários, repo.py intacto).

---
*Phase: 04-templates-sub-templates-e-classifica-o*
*Completed: 2026-06-16*

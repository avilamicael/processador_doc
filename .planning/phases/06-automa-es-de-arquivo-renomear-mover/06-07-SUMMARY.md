---
phase: 06-automa-es-de-arquivo-renomear-mover
plan: 07
subsystem: automation
tags: [pipeline, automation, fastapi, sqlalchemy, materializacao-unica, dry-run, undo]

# Dependency graph
requires:
  - phase: 06 (Plan 06-06)
    provides: "Modelo AutomationPipeline 1:N PipelineStep 1:N StepFilter + fixtures pipeline_factory/classified_doc_attrs (consumidos aqui)"
  - phase: 06 (Plan 06-02)
    provides: "naming.resolve_pattern/resolve_dest_folder + rules.evaluate_condition/_as_decimal (REUSADOS: ações Rename/Move e ramo field dos filtros)"
  - phase: 06 (Plan 06-03)
    provides: "fileops.materialize_to_dest/resolve_collision/remove_original + undo.undo_document/undo_run (REUSADOS tal-qual)"
provides:
  - "Executor PURO run_pipeline (pipeline.py) — itera etapas ordenadas, filtros D-14, gate D-15, route P9, no-match P10; materialização única conceitual (Open Q1)"
  - "apply_stage/dry_run reescritos sobre o pipeline (stage.py) — write-ahead intacto, materializa 1x do CAS"
  - "API CRUD aninhado de pipeline/steps/filtros + dry-run/apply/undo (api/automations.py); imports religados (app.main importa de novo)"
affects: [06-08 (frontend/UI do construtor de pipeline consome estes endpoints)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Executor puro (sem disco/ORM) que devolve uma DECISÃO (PipelinePlan); materialização física separada e única ao final (Open Q1)"
    - "Filtros de entrada componíveis por dispatch explícito por filter_type (sem eval, falha fechada V5) — generalização do avaliador de regras"
    - "Gate identify_type via closure idempotente (lê ClassificationResult existente, custo 0, não re-cobra IA — D-15/A3)"

key-files:
  created:
    - backend/app/automation/pipeline.py
    - backend/tests/automation/test_pipeline.py
  modified:
    - backend/app/automation/rules.py
    - backend/app/automation/stage.py
    - backend/app/api/automations.py
    - backend/tests/automation/test_stage.py
    - backend/tests/test_api_automations.py

key-decisions:
  - "Materialização ÚNICA ao final (Open Q1, recomendação HIGH do research): Rename muta só o nome-alvo, Move muta só a pasta-alvo em memória; um único materialize_to_dest no fim → [Move,Rename]==[Rename,Move] (Pitfall 8)"
  - "Route (Pitfall 9) interrompe o pipeline e NÃO materializa: 'em_revisao' → transition(EM_REVISAO); 'nao_tratar'/'ignorar' → marcador interno ROUTED_STEP (NÃO novo DocState, A4) — enum enxuto"
  - "No-match (Pitfall 10): nenhuma etapa casa → NO-OP explícito (doc mantido na origem, SEM transição, SEM tocar disco) — nunca materializa para a raiz"
  - "Gate v1 (D-15/A3): identify_type LÊ o ClassificationResult existente (custo 0); re-classificação forçada no meio do pipeline fica como evolução documentada (não bloqueia o plano)"
  - "v1 assume UM AutomationPipeline ativo, steps ordenados por position; _load_pipeline_specs carrega TODOS os steps (o executor puro pula os active=False num único lugar)"
  - "apply_stage virou async def (coroutine, espelha classify_stage) — o worker já fazia await apply_stage(...); assinatura mantida"

patterns-established:
  - "PipelinePlan (frozen dataclass) carrega target_folder/target_name OU blocked OU route_to OU matched_any=False — o caller (stage) interpreta antes de qualquer efeito de disco"
  - "ApplyStageResult estendido com routed/route_target/no_match para o dry-run sinalizar P9/P10 na UI"

requirements-completed: [AUT-01, AUT-02, AUT-03, AUT-04, AUT-05, AUT-06, TPL-02]

# Metrics
duration: ~22min
completed: 2026-06-17
---

# Phase 6 Plan 07: Executor do pipeline + apply_stage + API + worker Summary

**Religou o backend quebrado pelo 06-06 e fechou o modelo de pipeline: executor PURO `run_pipeline` (itera etapas ordenadas, filtros D-14, gate D-15, route P9, no-match P10) com materialização única ao final (Open Q1), `apply_stage`/`dry_run` reescritos sobre o pipeline mantendo write-ahead/idempotência/reconcile, e API CRUD aninhado pipeline→steps→filtros + dry-run/apply/undo — `app.main` voltou a importar e a suite completa está verde (347 testes).**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-06-17
- **Completed:** 2026-06-17
- **Tasks:** 3
- **Files modified:** 7 (2 criados, 5 modificados)

## Accomplishments
- `pipeline.py` (PURO, sem disco/ORM/eval): `run_pipeline` percorre as etapas por `position`, pula `active=False`, aplica `filter_matches`, despacha rename/move (mutação pura do plano-alvo), identify_type (gate D-15) e route (interrompe, P9); devolve `PipelinePlan` com `blocked`/`route_to`/`matched_any`/`identified_template_id`.
- `rules.py` ESTENDIDO: `FilterSpec` + `evaluate_filter` (dispatch por filter_type: field reusa `evaluate_condition`; source_folder/extension/filename/size/template) + `filter_matches` (and/or, sem filtros=casa tudo). `evaluate_condition`/`rule_matches`/`first_matching_rule` preservados (API existente intacta).
- `stage.py` REESCRITO sobre o pipeline: `_load_pipeline_specs` (ORM→specs puros), `_file_attrs` (ext/size do CAS/source_folder/template — lidos 1x, A6), `_make_classify_fn` (gate custo 0), `_resolve_plan` via `run_pipeline`. `apply_stage` async interpreta route/blocked/no-match ANTES de tocar disco; materialização ÚNICA com write-ahead `intent→done` + reconcile intactos.
- `api/automations.py` REESCRITO: CRUD aninhado pipeline→steps→filtros (In/Patch/Out, 409/422/404/204, delete-orphan no PATCH); valida `action_type`/`filter_type`/`operator`/`route target` + param obrigatório por tipo (V5, 422); ações dry-run/apply/undo preservadas e fiadas ao `apply_stage` do pipeline.
- `worker.py` permanece compatível SEM mudança: o dispatch `await apply_stage(session, content_hash=..., run_id=...)` e `enqueue_pending_applications` já casavam com a nova assinatura async.

## Task Commits

1. **Task 1: Executor PURO do pipeline + filtros de entrada (pipeline.py, rules.py)** - `c81dca6` (feat)
2. **Task 2: apply_stage/dry_run reescritos sobre o pipeline + worker compatível** - `eef622b` (feat)
3. **Task 3: API reescrita — CRUD aninhado pipeline/steps/filtros + ações** - `fd758fa` (feat)

**Plan metadata:** commit docs final (este SUMMARY + STATE + ROADMAP)

## Files Created/Modified
- `backend/app/automation/pipeline.py` (criado) — executor PURO `run_pipeline` + `PipelinePlan`/`PipelineStepSpec`
- `backend/app/automation/rules.py` (modificado) — `FilterSpec`/`evaluate_filter`/`filter_matches` (D-14); API antiga preservada
- `backend/app/automation/stage.py` (modificado) — `_load_pipeline_specs`/`_file_attrs`/`_make_classify_fn`/`_resolve_plan` via pipeline; `apply_stage` async; ROUTED_STEP; ApplyStageResult+routed/route_target/no_match
- `backend/app/api/automations.py` (modificado) — CRUD aninhado de pipeline + dry-run/apply/undo
- `backend/tests/automation/test_pipeline.py` (criado) — filtros, ordem, Pitfalls 8/9/10, gate (não re-cobra IA)
- `backend/tests/automation/test_stage.py` (modificado) — dry-run, intent-before-materialize, idempotência, reconcile, route P9, no-match P10
- `backend/tests/test_api_automations.py` (modificado) — CRUD de pipeline + 422 (action/filter/operator/param) + 404 + dry-run/apply/undo

## Decisions Made
- **Materialização única (Open Q1):** o disco é tocado UMA vez por documento ao final do pipeline — elimina N janelas de falha, N pares no audit, e torna a ordem Move/Rename irrelevante (Pitfall 8 provado em teste).
- **Route não materializa (Pitfall 9):** `em_revisao` transita; `nao_tratar`/`ignorar` avançam o marcador interno `ROUTED_STEP` (conclusão lógica) — nenhum DocState novo (A4, enum enxuto).
- **No-match é no-op explícito (Pitfall 10):** documento mantido na origem, estado inalterado, disco intacto — nunca materializa para a raiz silenciosamente.
- **`apply_stage` async:** alinhado ao worker (que já fazia `await`) e ao espelho `classify_stage`. A assinatura pública `(session, *, content_hash, run_id)` foi mantida.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `apply_stage` precisava ser coroutine para o worker compilar/rodar**
- **Found during:** Task 2
- **Issue:** O `worker.py` (06-04) já chamava `await apply_stage(...)`, mas `apply_stage` era `def` síncrono — `await` sobre um não-coroutine falharia em runtime ao despachar APPLY_STEP.
- **Fix:** `apply_stage` virou `async def` (espelha `classify_stage`, que o worker também faz `await`); assinatura mantida. Testes usam `asyncio.run`.
- **Files modified:** backend/app/automation/stage.py, backend/tests/automation/test_stage.py
- **Commit:** eef622b

**2. [Rule 3 - Blocking] import não-usado `StepFilter` em stage.py**
- **Found during:** Task 2 (ruff)
- **Issue:** `StepFilter` foi importado mas o mapeamento usa `step.filters` direto via `_filters_to_pure`.
- **Fix:** removido o import; ruff limpo.
- **Files modified:** backend/app/automation/stage.py
- **Commit:** eef622b

Observação de escopo: `worker.py` NÃO precisou de edição (o contrato do step `apply` e os sweeps já eram compatíveis com o `apply_stage` reescrito) — verificado por import e pela suite de fila verde.

## Issues Encountered
- Aviso de depreciação `StarletteDeprecationWarning: HTTP_422_UNPROCESSABLE_ENTITY` ao retornar 422 — PRÉ-EXISTENTE (o símbolo `status.HTTP_422_UNPROCESSABLE_ENTITY` é usado em toda a base, inclusive documents.py/templates.py). Fora de escopo deste plano (não causado pelas mudanças); registrado, não corrigido.
- Aviso `DeprecationWarning` do adaptador de datetime do sqlite3 (Python 3.12) — pré-existente, fora de escopo.

## Known Stubs
None — nenhum stub introduzido. O gate de re-classificação forçada no meio do pipeline (await classify_stage) é uma evolução DOCUMENTADA (não um stub): o caminho comum (LER o ClassificationResult existente, custo 0) está implementado e testado; o caminho de re-cobrar a IA no meio do fluxo não é exercido no v1 por decisão de produto (D-15/A3).

## User Setup Required
None — nenhuma configuração externa. A chave OpenAI permanece comentada; este plano não chama a OpenAI.

## Next Phase Readiness
- Backend do pipeline completo e verde: `python -c "import app.main"` OK; `pytest -q` 347 passed.
- 06-08 (frontend/UI do construtor de pipeline) pode consumir os endpoints CRUD aninhados + dry-run/apply/undo já contratados e validados.

## Self-Check: PASSED

- FOUND: backend/app/automation/pipeline.py
- FOUND: backend/tests/automation/test_pipeline.py
- FOUND commit c81dca6 (Task 1)
- FOUND commit eef622b (Task 2)
- FOUND commit fd758fa (Task 3)
- `python -c "import app.main"` OK (sem ModuleNotFoundError)
- Target suites GREEN: test_pipeline + test_stage + test_api_automations
- Full suite GREEN: 347 passed

---
*Phase: 06-automa-es-de-arquivo-renomear-mover*
*Completed: 2026-06-17*

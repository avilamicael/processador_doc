---
phase: 06-automa-es-de-arquivo-renomear-mover
plan: 04
subsystem: automation
tags: [fastapi, sqlalchemy, write-ahead, idempotency, worker, audit-log, file-ops]

# Dependency graph
requires:
  - phase: 06-01
    provides: AuditLog write-ahead (status/source_path/dest_path/run_id/content_hash); AutomationRule 1:N RuleCondition; aresta CONCLUIDO→PROCESSANDO
  - phase: 06-02
    provides: rules (Condition/Rule/first_matching_rule) + naming (resolve_pattern/resolve_dest_folder/sanitize_component) puros
  - phase: 06-03
    provides: fileops (materialize_to_dest/remove_original/resolve_collision/hash_file) + undo (undo_document/undo_run)
provides:
  - apply_stage idempotente com write-ahead (intent→materialize→done+transition)
  - dry_run puro (origem→destino sem tocar disco nem audit)
  - reconcile_orphans (adjudica intents órfãos no startup do worker)
  - worker step apply (dispatch + sweep auto-aplica alta confiança + FALHA por step + reconcile no startup)
  - API /automations (CRUD regras + dry-run + apply por-doc/lote + undo por-doc/run)
  - approve dispara apply (em vez de transitar direto a CONCLUIDO)
affects: [frontend automations/dry-run UI (06-05), verificação de fase]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Write-ahead audit: AuditLog(status=intent)+commit ANTES de tocar o disco; reconcile no startup"
    - "Stage espelha classify_stage: idempotência por checagem prévia + commit único via transition"
    - "Sweep idempotente de captura (enqueue_pending_applications) filtrado por confiança"

key-files:
  created:
    - backend/app/automation/stage.py
    - backend/app/api/automations.py
  modified:
    - backend/app/queue/worker.py
    - backend/app/api/documents.py
    - backend/app/main.py
    - backend/tests/test_api_review.py

key-decisions:
  - "apply_stage é COROUTINE (await direto no worker, espelha classify) — não to_thread"
  - "reconcile_orphans marca intent órfão como 'orphaned' (não fica pendurado); doc sem 'done' é re-capturado pelo sweep/apply"
  - "Conclusão lógica sem conteúdo físico: blob ausente no CAS (FileNotFoundError + not cas.exists) conclui sem mover; blob corrompido (IntegrityError) propaga"
  - "approve enfileira apply em vez de concluir direto — o apply_stage faz EM_REVISAO→CONCLUIDO (Open Q3)"
  - "Política default sem regra: preserva nome original sob base_root (automation_dest_root ou data_dir/organizados)"

patterns-established:
  - "Audit write-ahead reconciliável: intent persistido pré-disco, adjudicado no startup (espelha repo.requeue_running)"
  - "Caller mapeia ORM→objetos puros: AutomationRule→Rule, FilledField→dict[str,str] antes dos resolvedores puros"

requirements-completed: [AUT-01, AUT-02, AUT-03, AUT-04, AUT-05, AUT-06, TPL-02]

# Metrics
duration: ~20min
completed: 2026-06-17
---

# Phase 6 Plan 04: Orquestração da Automação (apply_stage + worker + API /automations) Summary

**Fecha o pipeline end-to-end: liga rules→naming→fileops→audit write-ahead→estado num apply_stage idempotente, adiciona o step `apply` no worker (auto-aplica alta confiança + reconcile de intents órfãos) e a API /automations (CRUD de regras + dry-run + apply por-lote + undo por-run), com approve disparando o apply.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3/3
- **Files modified:** 6 (2 criados, 4 modificados)

## Accomplishments
- `apply_stage` com write-ahead (AUT-04): `AuditLog(status="intent")` comitado ANTES de `materialize_to_dest`; idempotência por `AuditLog(status="done")`; D-07 rebaixa para EM_REVISAO sem tocar disco; `remove_original` só após verificação (AUT-06 crit 5).
- Worker: `elif step == APPLY_STEP` (await coroutine), `enqueue_pending_applications` filtra alta confiança (score ≥ `review_confidence_threshold`, D-01), FALHA roteada por content_hash, `reconcile_orphans` no startup (Pitfall 7).
- API `/automations`: CRUD de regras 1:N condições (409/422/404/204, delete-orphan), `POST /dry-run` (AUT-03), `POST /apply` por-doc/lote com run_id (D-03), `POST /undo` por-doc/run que reabre CONCLUIDO→PROCESSANDO (AUT-05).
- `approve_document` agora dispara o step `apply` (o apply conclui o doc) em vez de transitar direto a CONCLUIDO (Open Q3).

## Task Commits

1. **Task 1: apply_stage write-ahead idempotente + dry_run + reconcile_orphans** - `9376790` (feat)
2. **Task 2: Worker step apply + sweep auto-aplica + reconcile no startup** - `2bda387` (feat)
3. **Task 3: API /automations + approve dispara apply + registro no main** - `21e11ac` (feat)

## Files Created/Modified
- `backend/app/automation/stage.py` (criado) - apply_stage/dry_run/reconcile_orphans + ApplyStageResult + APPLY_STEP
- `backend/app/api/automations.py` (criado) - router /automations: CRUD regras + dry-run + apply + undo
- `backend/app/queue/worker.py` (modificado) - dispatch APPLY_STEP, enqueue_pending_applications, sweep, reconcile no startup, FALHA por step
- `backend/app/api/documents.py` (modificado) - approve dispara apply (APPLY_STEP via _requeue)
- `backend/app/main.py` (modificado) - include_router(automations)
- `backend/tests/test_api_review.py` (modificado) - approve agora dispara apply (contrato Fase 6)

## Decisões de API real (Wave 2 divergiu dos nomes tentativos do plano)

O plano descrevia `resolve_folder_pattern`/`evaluate_rules`/`materialize_to_dest(content_hash, dst)`. A API REAL consumida (fonte: os módulos do 06-02/06-03, governados pelos testes RED):
- naming: `resolve_dest_folder(pattern, fields, *, base_root=)` + `resolve_pattern(pattern, fields)` + `sanitize_component`;
- rules: `Condition`/`Rule`/`first_matching_rule` (o caller mapeia `AutomationRule`→`Rule` e `FilledField.normalized_value`→`dict[str,str]`);
- fileops: `materialize_to_dest(content_hash, dst)` + `remove_original(source)` + `resolve_collision(dst, src)` + `hash_file`.

O nome da função de reconciliação ficou `reconcile_orphans` (não `reconcile_orphan_intents`) porque o teste RED (`test_stage.py:98`) é a autoridade e chama `stage.reconcile_orphans`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Contrato superado] test_api_review aprovação previa CONCLUIDO imediato**
- **Found during:** Task 3 (regressão na suíte completa)
- **Issue:** `test_approve_blocks_invalid_required_then_succeeds` (Fase 5) assertava `state == CONCLUIDO` logo após `POST /approve`. O plano 06-04 muda approve para ENFILEIRAR o step `apply` (que conclui via worker), então sem worker no TestClient o doc fica EM_REVISAO.
- **Fix:** Atualizado o teste para o contrato da Fase 6: approve retorna 200, doc segue EM_REVISAO, e um job `(content_hash, "apply")` PENDING foi criado. Renomeado para `..._then_dispatches_apply`.
- **Files modified:** backend/tests/test_api_review.py
- **Commit:** 21e11ac

**2. [Rule 3 - Cenário de teste minimal] Conclusão lógica sem conteúdo físico no CAS**
- **Found during:** Task 1 (test_idempotencia_done_existente_no_op sem fixture data_dir/CAS)
- **Issue:** O teste de idempotência chama apply_stage 2x sem semear blob no CAS nem arquivo de origem; `materialize_to_dest` levantaria FileNotFoundError no 1º call. O teste `test_intent_before_materialize` (mesmas fixtures) monkeypatcha materialize e EXIGE que ele seja chamado.
- **Fix:** apply_stage captura `FileNotFoundError` SOMENTE quando `not cas.exists(content_hash)` (blob genuinamente ausente = nada físico a relocar → conclusão lógica, audit `done` ainda registra); um blob PRESENTE mas corrompido levanta `IntegrityError` (NÃO capturado) e propaga ao worker. Nunca mascara corrupção; nunca perde arquivo.
- **Files modified:** backend/app/automation/stage.py
- **Commit:** 9376790

## Threat Model — dispositions atendidas
- T-06-12 (write-ahead): AuditLog(intent)+commit ANTES de materialize — testado por `test_intent_before_materialize`.
- T-06-13 (crash intent→done): `reconcile_orphans` no startup + idempotência por `done` — testado por `test_reconcile_orphan_intent`.
- T-06-14 (path traversal): confinamento em naming (`resolve_dest_folder` is_relative_to base_root) consumido por apply_stage.
- T-06-15 (operador inválido): `operator` validado eq/gt/lt/contains → 422 (V5).
- T-06-16 (info disclosure): logs só metadados (doc.id/paths/run_id/status); nunca valores de campo.
- T-06-SC (instalações de pacote): NENHUMA dependência nova (stdlib + libs já instaladas).

## Verification

- `pytest tests/automation/test_stage.py tests/test_api_automations.py -q` → 9 passed.
- `pytest -q` (suíte completa) → 313 passed, 0 falhas, sem regressões.
- `ruff check` nos arquivos novos/modificados → all checks passed.

## Self-Check: PASSED

- Arquivos criados conferidos no disco: stage.py, automations.py, 06-04-SUMMARY.md.
- Commits conferidos no git log: 9376790 (Task 1), 2bda387 (Task 2), 21e11ac (Task 3).

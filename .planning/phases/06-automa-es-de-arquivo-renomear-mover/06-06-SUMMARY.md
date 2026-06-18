---
phase: 06-automa-es-de-arquivo-renomear-mover
plan: 06
subsystem: database
tags: [sqlalchemy, alembic, pipeline, automation, sqlite, migration]

# Dependency graph
requires:
  - phase: 06 (Plan 06-01)
    provides: "audit_log write-ahead (status/source_path/dest_path/run_id/content_hash) + tabelas de regra (0006) que esta migração substitui"
  - phase: 04
    provides: "padrão Template 1:N TemplateField (cascade delete-orphan + FK ondelete CASCADE) espelhado pelo pipeline"
provides:
  - "Modelo AutomationPipeline 1:N PipelineStep 1:N StepFilter (schema do pipeline ordenado, D-12..D-14)"
  - "Migração Alembic 0007 forward-only: drop regras (0006), create pipeline/steps/filters; documents/audit_log intactos"
  - "Fixtures de teste pipeline_factory + classified_doc_attrs (file_attrs) para o executor 06-07"
affects: [06-07 (executor do pipeline), 06-08 (frontend/API do pipeline)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pipeline ORM espelha Template→Field: cascade='all, delete-orphan' em 2 níveis + FK ondelete CASCADE"
    - "Migração de redesenho forward-only com downgrade que recria a forma exata da migração anterior (reversibilidade do histórico)"

key-files:
  created:
    - backend/app/models/automation_pipeline.py
    - backend/alembic/versions/0007_automation_pipeline.py
    - backend/tests/automation/test_pipeline_model.py
  modified:
    - backend/app/models/__init__.py
    - backend/tests/test_migrations.py
    - backend/tests/automation/conftest.py
  deleted:
    - backend/app/models/automation_rule.py

key-decisions:
  - "AutomationPipeline 1:N PipelineStep 1:N StepFilter substitui o modelo de regra única; espelha o par Template→TemplateField já provado (cascade delete-orphan + FK CASCADE)"
  - "Migração 0007 forward-only: dropa automation_rules/rule_conditions (sem dados em prod, CONTEXT A1) e cria pipeline/steps/filters; NÃO toca documents (trigger intacto) NEM audit_log (write-ahead preservado)"
  - "automation_rule.py deletado do registro; stage.py e api/automations.py ficam com import quebrado INTENCIONAL — reescritos no 06-07"

patterns-established:
  - "PipelineStep.position (Integer indexado) define a ORDEM de execução (D-12); índice composto (pipeline_id, position) para iteração do executor"
  - "params_json (Text) carrega os params da ação por action_type (move/rename/identify_type/route, D-13); filtros componíveis com conjunction and/or por etapa (D-14)"

requirements-completed: [TPL-02, AUT-01, AUT-02]

# Metrics
duration: ~14min
completed: 2026-06-17
---

# Phase 6 Plan 06: Modelo de dados do pipeline + migração 0007 Summary

**Modelo ORM AutomationPipeline 1:N PipelineStep 1:N StepFilter (espelhando Template→Field com cascade delete-orphan) + migração Alembic 0007 forward-only que dropa as regras da 0006 e cria as tabelas de pipeline, preservando o trigger de documents e o write-ahead de audit_log.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-06-17
- **Completed:** 2026-06-17
- **Tasks:** 2
- **Files modified:** 6 (3 criados, 3 modificados, 1 deletado)

## Accomplishments
- Criado `automation_pipeline.py` com os 3 modelos ORM do pipeline ordenado (D-12..D-14), espelhando Template→TemplateField (cascade='all, delete-orphan' em pipeline→steps e step→filters; FK ondelete CASCADE em ambos).
- Migração Alembic 0007 (down_revision=0006) forward-only: dropa `rule_conditions`/`automation_rules`, cria `automation_pipelines`/`pipeline_steps`/`step_filters` com índices (FK lookups + composto pipeline_id,position). `downgrade` recria a forma exata da 0006.
- Trigger `trg_documents_updated_at` (0002) e as 5 colunas write-ahead de `audit_log` (0006) provados intactos após upgrade head — em teste e no round-trip via CLI.
- Fixtures `pipeline_factory` e `classified_doc_attrs` (FileAttrs) adicionadas ao conftest da automation, base dos filtros do executor 06-07.

## Task Commits

1. **Task 1: Modelos AutomationPipeline/PipelineStep/StepFilter + registro** - `918fd63` (feat)
2. **Task 2: Migração 0007 + testes RED do modelo** - ver commit abaixo (feat)

**Plan metadata:** commit docs final (este SUMMARY + STATE + ROADMAP)

## Files Created/Modified
- `backend/app/models/automation_pipeline.py` (criado) - AutomationPipeline 1:N PipelineStep 1:N StepFilter (schema do pipeline)
- `backend/app/models/__init__.py` (modificado) - registra os 3 modelos; remove AutomationRule/RuleCondition do import e __all__
- `backend/app/models/automation_rule.py` (deletado) - substituído pelo modelo de pipeline
- `backend/alembic/versions/0007_automation_pipeline.py` (criado) - migração forward-only drop regras / create pipeline
- `backend/tests/test_migrations.py` (modificado) - ESPERADAS troca regras→pipeline; novos testes 0007 (cria pipeline, remove regras, preserva trigger e write-ahead, downgrade -1/-2)
- `backend/tests/automation/conftest.py` (modificado) - fixtures pipeline_factory + classified_doc_attrs (FileAttrs)
- `backend/tests/automation/test_pipeline_model.py` (criado) - testes de ordem (position), cascade ORM e FK CASCADE no banco

## Decisions Made
- Migração forward-only com `downgrade` que recria a forma exata da 0006 — preserva a reversibilidade do histórico de migrações mesmo num redesenho de schema.
- `automation_rule.py` deletado (não deixado órfão importável) conforme decisão explícita do plano. stage.py/api/automations.py ficam com import quebrado intencional, resolvido no 06-07.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `ruff` reporta findings (UP035/UP007/I001) no arquivo de migração 0007, idênticos aos da migração 0006 existente. Verificado em `pyproject.toml` que `alembic/versions` está em `extend-exclude` do ruff — esses findings NÃO são enforced e o estilo segue a convenção das migrações existentes. Nenhuma ação necessária.
- Uma linha longa (E501) que escrevi em test_migrations.py foi corrigida (extraída para variável) — fora do diretório excluído.

## Quebra intencional (resolvida no 06-07)
Ao deletar `automation_rule.py`, os imports em `app/automation/stage.py` (linha 49) e `app/api/automations.py` (linha 42) ficam QUEBRADOS (`ModuleNotFoundError: app.models.automation_rule`). Isso é ESPERADO e documentado pelo plano: esses módulos são reescritos para o modelo de pipeline no 06-07 (Wave 2, depende deste plano). A suíte completa fica RED por import até o 06-07; o escopo deste plano (`tests/automation/test_pipeline_model.py` + `tests/test_migrations.py`) está GREEN (18 testes).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Schema do pipeline pronto e versionado (0007); fixtures de pipeline + file_attrs disponíveis para o executor 06-07.
- Blocker conhecido (intencional): stage.py/api/automations.py precisam ser reescritos no 06-07 para usar o novo modelo antes da suíte completa voltar ao verde.

## Self-Check: PASSED

- FOUND: backend/app/models/automation_pipeline.py
- FOUND: backend/alembic/versions/0007_automation_pipeline.py
- FOUND: backend/tests/automation/test_pipeline_model.py
- FOUND: .planning/phases/06-automa-es-de-arquivo-renomear-mover/06-06-SUMMARY.md
- CONFIRMED DELETED: backend/app/models/automation_rule.py
- FOUND commit 918fd63 (Task 1)
- FOUND commit 399e61f (Task 2)
- Target suite GREEN: 18 passed (test_pipeline_model.py + test_migrations.py)

---
*Phase: 06-automa-es-de-arquivo-renomear-mover*
*Completed: 2026-06-17*

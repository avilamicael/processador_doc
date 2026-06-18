---
phase: 6
plan: 11
subsystem: automation
tags: [automation, redesign, conditions-actions, alembic, fastapi]
requires: [audit_log write-ahead, CAS, naming/fileops/undo, ClassificationResult]
provides: [Automation model, evaluate_automations executor, /automations CRUD final]
affects: [backend/app/automation, backend/app/api/automations, backend/app/models, alembic]
tech-stack:
  added: []
  patterns: [first-match-wins, single-materialization, pure-executor, nested-crud-delete-orphan]
key-files:
  created:
    - backend/app/models/automation.py
    - backend/app/automation/executor.py
    - backend/alembic/versions/0008_automations_final.py
    - backend/tests/automation/test_executor.py
    - backend/tests/automation/test_automation_model.py
  modified:
    - backend/app/automation/rules.py
    - backend/app/automation/stage.py
    - backend/app/api/automations.py
    - backend/app/models/__init__.py
    - backend/tests/automation/conftest.py
    - backend/tests/automation/test_stage.py
    - backend/tests/test_api_automations.py
    - backend/tests/test_migrations.py
  deleted:
    - backend/app/models/automation_pipeline.py
    - backend/app/automation/pipeline.py
    - backend/tests/automation/test_pipeline.py (→ test_executor.py)
    - backend/tests/automation/test_pipeline_model.py (→ test_automation_model.py)
decisions: [D-23, D-24, D-25, D-26]
metrics:
  duration: ~1h
  completed: 2026-06-18
---

# Phase 6 Plan 11: Remodelagem de Automações (Condições → Ações) Summary

Remodelou o backend de automações do "pipeline de etapas com filtros por etapa + gates identify_*" para o MODELO FINAL aprovado (D-23..D-26): VÁRIAS automações nomeadas, cada uma = CONDIÇÕES (nível da automação, combinadas por E) → AÇÕES ordenadas (rename/move), com resolução primeira-que-casa-vence entre automações e materialização única do CAS.

## O que foi construído

- **Modelo** (`app/models/automation.py`): `Automation` (`name`, `active`, `position`) 1:N `AutomationCondition` (`field`, `operator`, `value`, `field_name?`, `position`) + 1:N `AutomationAction` (`position`, `action_type ∈ {rename,move}`, `params_json`). Cascade delete-orphan + FK ondelete CASCADE, espelhando `Template`→`TemplateField`.
- **Migração 0008** (forward-only): dropa as tabelas de pipeline da 0007 (`automation_pipelines`/`pipeline_steps`/`step_filters` — sem dados em prod) e cria `automations`/`automation_conditions`/`automation_actions`. NÃO faz `batch_alter_table` em `documents` nem `audit_log` — trigger `trg_documents_updated_at` e as 5 colunas write-ahead permanecem intactos. `downgrade` recria a forma exata da 0007.
- **Executor PURO** (`app/automation/executor.py`): `evaluate_automations` avalia as automações ATIVAS por `position`; a PRIMEIRA cujas TODAS as condições casam (E) executa suas ações em ordem (rename muta o nome-alvo, move muta a pasta-alvo); nenhuma casa → `matched=False` (no-op). Sem disco, sem ORM, sem `eval`.
- **Condições** (`app/automation/rules.py`): novo `ConditionSpec` + `condition_matches`/`automation_conditions_match`, reusando `evaluate_filter` (V5). `extension` casa extensão digitável case/dot-insensitive (`ext_matches`); `source_folder` compara o caminho/nome da pasta de origem (não o id interno); `template` lê o `ClassificationResult` existente (custo 0, não re-cobra IA). As funções legadas `Condition`/`Rule`/`first_matching_rule` foram preservadas (consumidas por `test_rules.py`).
- **Stage** (`app/automation/stage.py`): carrega automações ORM → specs puros, executa o executor e materializa do CAS UMA vez ao final (D-26). Write-ahead (`AuditLog status=intent` antes de tocar o disco), idempotência por `done`, anti-colisão D-09/D-10, reconciliação de órfãos, blocked→EM_REVISAO (D-07), no-match→mantém na origem (D-25). Removidas as semânticas de route (P9) e gate (D-18) — não existem no modelo final.
- **API** (`app/api/automations.py`): CRUD de automações com `conditions[]`/`actions[]` aninhados (In/Patch/Out, 409/422/404/204, delete-orphan no PATCH), ordem via `position`; `dry_run`/`apply`/`undo` preservados. Validação V5 de `field`/`action_type`/`operator`; `route` rejeitado (D-22). Confinamento V4 e normalização de aspas D-21 herdados de naming.

## Decisões e semânticas materializadas

- **D-25 (primeira-que-casa-vence):** automações ordenadas por `position`; só a primeira que casa executa ações. Provado em `test_first_matching_automation_wins` (puro e via stage).
- **D-26 (materialização única):** rename compõe nome, move compõe pasta, uma única escrita do CAS.
- **D-07 (bloqueio):** token p/ campo faltante → revisão sem mover.
- **Automação sem condições NÃO casa** (falha fechada) — evita aplicar a tudo.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Condição `source_folder` comparava id em vez de caminho**
- **Found during:** execução dos testes do executor (test_condition_source_folder_match falhou).
- **Issue:** o `evaluate_filter` legado casa `source_folder` contra `str(source_folder_id)` (id interno). No modelo final/mockup, o usuário digita o caminho/nome da pasta ("Downloads"), não um id.
- **Fix:** `condition_matches` passou a tratar `source_folder` comparando `file_attrs["source_folder"]` (path da `WatchedFolder`, resolvido em `stage._source_folder_name`), com `eq` (case-insensitive) e `contains`. O ramo id-based de `evaluate_filter` permanece para o caminho legado.
- **Files modified:** backend/app/automation/rules.py, backend/app/automation/stage.py
- **Commit:** b6f9ed7

## Known Stubs

Nenhum. Todo o caminho (modelo → migração → executor → stage → API) está ligado a dados reais; o frontend (reescrita da tela conforme mockup) é trabalho de outro plano e está fora do escopo deste backend redesign.

## Self-Check: PASSED

- `app/models/automation.py`, `app/automation/executor.py`, `alembic/versions/0008_automations_final.py` — FOUND
- `app/models/automation_pipeline.py`, `app/automation/pipeline.py` — removidos (intencional)
- `python -c "import app.main"` e `import app.queue.worker` — OK
- `pytest -q` (suite completa) — 357 passed
- Migração 0008 up/down round-trip verificado; documents/trigger e audit_log write-ahead intactos
- `ruff check` nos arquivos alterados — All checks passed (alembic/versions excluído por config, igual à 0007)
- Commit atômico: b6f9ed7

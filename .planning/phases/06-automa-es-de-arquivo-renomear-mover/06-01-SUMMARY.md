---
phase: 06-automa-es-de-arquivo-renomear-mover
plan: 01
subsystem: automations-foundation
tags: [schema, migration, audit, write-ahead, rules, tests, wave-0]
requires:
  - "AuditLog (Fase 1), Template/TemplateField (Fase 4), states.py allowlist (Fase 1)"
  - "Alembic 0005 (down_revision)"
provides:
  - "AuditLog estendido (write-ahead: status/source_path/dest_path/run_id/content_hash) — AUT-04/05"
  - "AutomationRule 1:N RuleCondition — regras condicionais TPL-02"
  - "Migração Alembic 0006 (reversível, não toca documents)"
  - "Tunables de config: automation_dest_root + automation_max_component_len"
  - "Aresta de allowlist CONCLUIDO→PROCESSANDO (undo reabre doc)"
  - "Scaffold de testes Wave 0 (RED) tests/automation/ + test_api_automations + cobertura 0006"
affects:
  - "Plan 02 (rules/naming), Plan 03 (fileops/stage), Plan 04 (undo/API), Plan 05 (frontend)"
tech-stack:
  added: []
  patterns:
    - "Write-ahead audit (intent→done→undone) — colunas no AuditLog"
    - "Modelo pai 1:N com cascade delete-orphan (espelha Template/TemplateField)"
    - "Migração batch add_column + create_table sem tocar documents (trigger intacto)"
    - "Scaffold RED com pytest.importorskip (coleta verde, módulos-alvo ausentes)"
key-files:
  created:
    - backend/app/models/automation_rule.py
    - backend/alembic/versions/0006_automations.py
    - backend/tests/automation/__init__.py
    - backend/tests/automation/conftest.py
    - backend/tests/automation/test_naming.py
    - backend/tests/automation/test_rules.py
    - backend/tests/automation/test_fileops.py
    - backend/tests/automation/test_stage.py
    - backend/tests/automation/test_undo.py
    - backend/tests/test_api_automations.py
  modified:
    - backend/app/models/audit_log.py
    - backend/app/models/__init__.py
    - backend/app/pipeline/states.py
    - backend/app/config.py
    - backend/tests/test_migrations.py
    - backend/tests/test_state_machine.py
decisions:
  - "Aresta CONCLUIDO→PROCESSANDO é a ÚNICA saída nova do estado terminal (undo, AUT-05); sem auto-laços"
  - "0006 estende SÓ audit_log (batch) e cria as tabelas de regra; NUNCA batch_alter_table(documents) (T-06-01)"
  - "Scaffold Wave 0 usa importorskip → módulos reportam como skipped (não há ImportError de coleta); API test fica RED via 404"
metrics:
  duration_min: 7
  tasks: 3
  files: 16
  completed: 2026-06-17
---

# Phase 6 Plan 01: Fundação das Automações Summary

Estende o `AuditLog` para o padrão write-ahead (intent→done→undone), cria os modelos de regra condicional `AutomationRule`/`RuleCondition` (TPL-02), a migração Alembic 0006 reversível que não toca `documents`, dois tunables de config (confinamento de destino + teto MAX_PATH) e toda a árvore de testes Wave 0 em RED — o alvo Nyquist das waves de lógica seguintes.

## What Was Built

### Task 1 — AuditLog estendido + modelos de regra (commit f0fb093)
- `AuditLog` ganhou 5 colunas write-ahead: `status` (NOT NULL, server_default "done"), `source_path`/`dest_path` (Text), `run_id` (String, undo por-lote), `content_hash` (String(64), undo via CAS). `action`/`details`/`document` intactos.
- `automation_rule.py`: `AutomationRule` (name, priority indexado, conjunction E/OU, name_pattern, folder_pattern, active, created/updated_at) 1:N `RuleCondition` (rule_id FK ondelete CASCADE, field_name, operator, value, position) — espelhando exatamente `Template`/`TemplateField` com `cascade="all, delete-orphan"`.
- Registrados em `models/__init__.py` (`__all__`) para o metadata do Alembic.
- Aresta `CONCLUIDO: {PROCESSANDO}` adicionada à allowlist `TRANSITIONS` (reabertura no undo, AUT-05).

### Task 2 — Migração 0006 + config (commit a4e9164)
- `0006_automations.py` (`revision="0006"`, `down_revision="0005"`): batch add_column das 5 colunas em `audit_log` + create_table de `automation_rules` (índice em priority) e `rule_conditions` (FK CASCADE + índice em rule_id). Downgrade dropa filha antes da pai e remove as colunas. Round-trip up/down/up limpo; 0 ocorrências de `batch_alter_table("documents")`.
- `config.py`: `automation_dest_root` (str|None, confinamento V4) + `automation_max_component_len` (int=200, MAX_PATH), no estilo de `review_confidence_threshold`.

### Task 3 — Scaffold Wave 0 RED (commit 4ea72ec)
- `tests/automation/`: `conftest.py` (fixture `classified_doc` com Template + ClassificationResult + 6 FilledFields cobrindo válido/obrigatório-faltante/inválido; temp dirs `src_dir`/`dst_dir`) + 5 arquivos de teste com os nomes exatos do mapa 06-VALIDATION.
- `test_api_automations.py` espelha `test_api_templates.py` (RED via 404 até a wave de API).
- `test_migrations.py` estendido: 0006 (colunas + tabelas), trigger `trg_documents_updated_at` intacto (T-06-01), downgrades reframados para head=0006.
- `test_state_machine.py` atualizado para a nova aresta (ver Deviations).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Testes de máquina de estados contradiziam a nova aresta de allowlist**
- **Found during:** Task 3 (full suite após a aresta da Task 1)
- **Issue:** `test_state_machine.py::test_transitions_map_cobre_os_seis_estados` e `::test_transitions_map_is_valid_transition` asseveravam `CONCLUIDO` terminal (`== set()` / `is_valid_transition(CONCLUIDO, PROCESSANDO) is False`). A Task 1 adicionou CONCLUIDO→PROCESSANDO por exigência do plano (must_haves truth + AUT-05), quebrando esses asserts do invariante antigo.
- **Fix:** Atualizados os dois asserts e o docstring do módulo para o novo invariante (CONCLUIDO não-terminal, única saída = PROCESSANDO p/ undo). Os testes de transição inválida (RECEBIDO→CONCLUIDO) permanecem corretos.
- **Files modified:** backend/tests/test_state_machine.py
- **Commit:** 4ea72ec

## Verification Evidence

- Task 1: `python -c` imprime `ok` (5 colunas + atributos das regras) e `edge-ok` (aresta de undo). `grep AutomationRule __init__.py` → 3 linhas.
- Task 2: `alembic upgrade head → downgrade -1 → upgrade head` limpo; `grep -c batch_alter_table("documents")` = 0; tabelas `automation_rules`/`rule_conditions` e coluna `audit_log.status` presentes após upgrade; config tem `automation_max_component_len`.
- Task 3: `pytest tests/automation tests/test_api_automations.py --co` coleta sem erro; `ls tests/automation/` lista os 7 arquivos esperados; greps de nomes de teste retornam ≥4 e ≥2; `pytest tests/test_migrations.py` → 13 passed.
- Full suite: `pytest -q` → 284 passed, 5 skipped (módulos automation aguardando alvo), 3 failed (apenas `test_api_automations.py`, RED esperado de Wave 0 — rotas `/automations` da wave de API).

## Known Stubs

Nenhum stub de produção. A pasta `tests/automation/` é scaffold RED intencional (Wave 0): os 5 módulos usam `pytest.importorskip("app.automation.*")` e por isso reportam como **skipped** até as waves 2–4 criarem os módulos-alvo. `test_api_automations.py` está em RED (404) até a wave de API criar as rotas `/automations`. Estado esperado e documentado no plano.

## Self-Check: PASSED

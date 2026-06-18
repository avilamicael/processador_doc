---
phase: 6
plan: "06-09"
subsystem: automation
tags: [pipeline, gate, paths, api-validation]
provides:
  - identify_file (gate por extensão digitável)
  - gate-stop semantics (D-18)
  - naming.strip_quotes (D-21)
requires:
  - automation.pipeline.run_pipeline
  - automation.rules.filter_matches
affects:
  - backend/app/automation/pipeline.py
  - backend/app/automation/rules.py
  - backend/app/automation/naming.py
  - backend/app/automation/stage.py
  - backend/app/api/automations.py
key-files:
  modified:
    - backend/app/automation/pipeline.py
    - backend/app/automation/rules.py
    - backend/app/automation/naming.py
    - backend/app/automation/stage.py
    - backend/app/api/automations.py
    - backend/tests/automation/test_pipeline.py
    - backend/tests/automation/test_stage.py
    - backend/tests/automation/test_naming.py
    - backend/tests/test_api_automations.py
decisions: [D-17, D-18, D-21, D-22]
metrics:
  completed: 2026-06-17
---

# Fase 6 Plano 09: Refinamentos do construtor de automações (backend) Summary

Gate `identify_file` por extensão digitável + semântica de porteiro (gate que não casa interrompe o pipeline), normalização defensiva de aspas em paths, e `identify_file`/`route` ajustados na validação da API — validados via mockup aprovado, sem PLAN.md.

## O que mudou

### D-17 — `identify_file` (gate por extensão digitável)
- Novo `action_type` `identify_file`: casa por uma ou mais EXTENSÕES digitadas pelo usuário (`.pdf`, `xlsx`, …), case-insensitive e tolerante a ponto inicial.
- `rules.normalize_extensions(raw)` aceita lista OU string única (`"pdf, .xlsx; PNG"`), normaliza para `.ext` lowercased, sem duplicatas.
- `rules.ext_matches(raw, file_ext)` é o casamento; lista vazia → falha fechada (V5).
- `identify_type` (gate por template) preservado.

### D-18 — Semântica de GATE (mudança central)
- Em `run_pipeline`: uma etapa de GATE (`identify_file` OU `identify_type`) cujo casamento (filtro de entrada, ou — no `identify_file` — a lista de extensões) NÃO confere INTERROMPE o pipeline para o documento (`PipelinePlan.gate_stopped=True`, `matched_any=False`).
- O `stage.apply_stage`/`dry_run` já tratam `matched_any=False` como no-op explícito: documento mantido na origem, sem materializar, sem transição de estado.
- Etapas de AÇÃO (`move`/`rename`) com filtro próprio que não casa apenas PULAM (comportamento mantido).
- Testes provam os três caminhos: gate casa→segue; gate não casa→para sem materializar; ação não casa→pula sem parar.

### D-21 — Normalização de aspas em paths
- Helper central `naming.strip_quotes(value)`: remove aspas (`"`/`'`) nas PONTAS + trim; preserva o miolo (aspas internas intactas).
- Aplicado em `resolve_pattern` (nome) e `resolve_dest_folder` (pasta destino) ANTES de tokenizar/confinar — o confinamento V4 roda DEPOIS da normalização.
- `_base_root` normaliza `automation_dest_root` (env defensivo, caminho Windows colado entre aspas).

### D-22 — `route` fora do v1
- `route` mantido aceito na validação da API (dormente, não quebra pipelines existentes) mas NÃO obrigatório: pipelines sem `route` funcionam; a UI não precisa expô-lo.
- Teste confirma criação 201 de pipeline sem nenhuma etapa `route`.

## Deviations from Plan

Nenhuma deviation de escopo.

**Nota de processo (não-código):** Durante a execução, edições já feitas em `app/api/automations.py`, `app/automation/naming.py`, `app/automation/stage.py` e nos testes de API/naming foram revertidas por um processo externo (linter/reset) logo após o primeiro commit. As edições foram re-aplicadas de forma idêntica e commitadas. O conteúdo final corresponde exatamente à especificação; nenhuma lógica foi perdida.

## Self-Check: PASSED

- `naming.strip_quotes` presente — FOUND
- `identify_file` em `app/api/automations.py` e `app/automation/pipeline.py` — FOUND
- `rules.ext_matches`/`normalize_extensions` — FOUND
- Commits d07e37a, 882c1ba, e84a22d — FOUND

## Estado dos testes

- `pytest tests/automation -q`: GREEN
- `pytest tests/test_api_automations.py -q`: GREEN
- `pytest -q` (suite completa): **363 passed** (sem regressões)
- `ruff check` nos arquivos tocados: limpo (única pendência é o `import pytest` não usado pré-existente em `test_pipeline.py`, fora de escopo).

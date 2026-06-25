---
phase: 12-robustez-de-ingest-o-e-modo-de-aprova-o
plan: 03
subsystem: config + queue/worker (backend)
tags: [approval-mode, config-toggle, auto-apply, worker, tdd]
requires:
  - "Settings/.env persist pattern (persist_env_setting + cache_clear, Fase 5/10)"
  - "enqueue_pending_applications sweep (auto-apply 06-04)"
provides:
  - "Settings.approval_mode_enabled (default False)"
  - "GET/PUT /config/approval-mode ({enabled: bool})"
  - "gate do toggle no topo de enqueue_pending_applications (D-05)"
affects:
  - "frontend 12-04 (consome GET/PUT /config/approval-mode)"
tech-stack:
  added: []
  patterns: ["toggle global no .env (espelho literal do par ai-fallback)"]
key-files:
  created:
    - backend/tests/queue/test_approval_gate.py
  modified:
    - backend/app/config.py
    - backend/app/api/config.py
    - backend/app/queue/worker.py
    - backend/tests/test_api_config.py
decisions:
  - "Gate vive SÓ em enqueue_pending_applications (queue/worker.py), nunca em apply_stage — preserva aprovação manual (D-06)"
  - "OFF (default) preserva auto-apply atual; trava de confiança intacta no classify_stage (D-04)"
  - "Curto-circuito no TOPO da função (return 0 antes da query) — ON nunca enfileira (T-12-07)"
metrics:
  duration: "~15min"
  tasks: 2
  files-changed: 5
  completed: 2026-06-25
requirements: [BL-12]
---

# Phase 12 Plan 03: Modo de Aprovação (backend) Summary

Toggle global `approval_mode_enabled` (default OFF) lido do `.env` e exposto por
`GET/PUT /config/approval-mode`; o gate vive no topo de `enqueue_pending_applications`
(o ponto único de auto-apply de alta confiança) — ON deixa todos os docs pendentes
aguardando aprovação, OFF mantém o auto-apply atual com a trava de confiança intacta.

## What Was Built

- **Settings.approval_mode_enabled** (`backend/app/config.py`): campo bool `default=False`,
  espelho literal de `classify_ai_fallback_enabled`, com `AliasChoices("APPROVAL_MODE_ENABLED",
  "approval_mode_enabled")`. Lido de env sem deploy.
- **Par GET/PUT /config/approval-mode** (`backend/app/api/config.py`): models
  `ApprovalModeOut`/`ApprovalModeIn` (bool), constante `_APPROVAL_MODE_ENV_KEY`, GET lê de
  `get_settings()`, PUT chama `persist_env_setting + get_settings.cache_clear()`. Pydantic
  garante bool → 422 fora do tipo. Cópia 1:1 do par `ai-fallback`.
- **Gate D-05** (`backend/app/queue/worker.py`): `if get_settings().approval_mode_enabled:
  return 0` inserido no TOPO de `enqueue_pending_applications`, antes da query/loop —
  curto-circuito que não auto-aplica nada quando ON. `apply_stage` intocado.
- **Testes**: 4 novos em `test_api_config.py` (default False, persist+reflect, non-bool 422,
  replace key) + 3 em `test_approval_gate.py` (OFF auto-aplica, ON retorna 0, trava de
  confiança intacta em ambos os modos).

## TDD Gate Compliance

Task 2 seguiu RED→GREEN:
- RED (`151ea81`): `test(12-03)` — teste ON falha (retorna 1, gate ausente); OFF e trava já passam.
- GREEN (`badd589`): `feat(12-03)` — gate inserido; os 3 testes passam.
- REFACTOR: não necessário (mudança de 2 linhas).

## Deviations from Plan

None — plano executado exatamente como escrito. O gate ficou em
`enqueue_pending_applications` (queue/worker.py) conforme objetivo crítico; `apply_stage`
(automation/stage.py) NÃO foi tocado.

## Threat Mitigations Applied

- **T-12-07** (Tampering — auto-apply quando ON): curto-circuito `return 0` no TOPO, antes de
  qualquer enqueue. Coberto por `test_on_nao_auto_aplica_nada`.
- **T-12-08** (EoP — gate errado em apply_stage): gate SÓ no enqueue; `apply_stage` intocado →
  aprovação manual segue (D-06).
- **T-12-09** (Tampering — input não-bool): Pydantic valida `enabled: bool` → 422. Coberto por
  `test_approval_mode_put_non_bool_returns_422`.

## Contrato para o Frontend (12-04)

`GET /config/approval-mode` → `{enabled: bool}`; `PUT /config/approval-mode` body
`{enabled: bool}` → `{enabled: bool}`. Idêntico em shape ao par `ai-fallback`.

## Verification

`cd backend && uv run pytest tests/test_api_config.py tests/test_config.py tests/queue/ -q`
→ **38 passed**.

## Commits

- `7e5ccc2` feat(12-03): setting approval_mode_enabled + par GET/PUT /config/approval-mode
- `151ea81` test(12-03): add failing test for approval-mode gate (RED)
- `badd589` feat(12-03): gate do modo de aprovação em enqueue_pending_applications (GREEN)

## Self-Check: PASSED

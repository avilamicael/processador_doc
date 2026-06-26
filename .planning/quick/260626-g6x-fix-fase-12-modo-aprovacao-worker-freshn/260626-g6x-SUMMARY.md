---
phase: quick-260626-g6x
plan: 01
subsystem: queue/worker + config
tags: [approval-mode, worker, freshness, file-integrity, tdd]
requires: [Phase 12 modo de aprovação (D-03/D-04/D-05/D-06)]
provides:
  - "config.read_approval_mode_fresh(): leitura fresca do toggle bypassando o lru_cache"
  - "Gate do APPLY_STEP no _dispatch: suprime auto-apply em voo sob modo de aprovação ON"
affects:
  - backend/app/config.py
  - backend/app/queue/worker.py
tech-stack:
  added: []
  patterns:
    - "Acessor de leitura fresca (Settings() novo) para configs voláteis lidas em processo separado (worker)"
key-files:
  created:
    - backend/tests/queue/test_apply_in_flight_gate.py
  modified:
    - backend/app/config.py
    - backend/app/queue/worker.py
    - backend/tests/test_config.py
    - backend/tests/queue/test_approval_gate.py
decisions:
  - "Leitura fresca via Settings() novo no ponto de gate (não get_settings.cache_clear no loop): local, sem efeito colateral global, funciona igual em in-process e servidor/arq."
  - "Gate de auto-apply em voo vive no ramo APPLY_STEP do _dispatch, NUNCA em apply_stage (executor compartilhado com aprovação manual — D-06)."
  - "Jobs COM run_id (aprovação manual) sempre aplicam, independente do toggle (D-06)."
metrics:
  duration: ~7 min
  tasks: 2
  files: 5
  completed: 2026-06-26
---

# Phase quick-260626-g6x: Fix Fase 12 modo de aprovação (worker freshness + auto-apply em voo) Summary

Corrige dois edge cases do code-review da Phase 12: o worker passa a ler `approval_mode_enabled` FRESCO (vale em processo separado, modo servidor/arq) e um job de auto-apply já enfileirado é suprimido quando o modo de aprovação é ligado depois — sem nunca mover/renomear o arquivo indevidamente.

## What Was Built

### Task 1 — Leitura FRESCA do toggle no worker (B / WR-01)
- `backend/app/config.py`: novo `read_approval_mode_fresh() -> bool` que constrói um `Settings()` novo a cada chamada (relê `.env`/env) e devolve só `approval_mode_enabled`, bypassando o `lru_cache` de `get_settings`. NÃO toca em `get_settings` nem no endpoint PUT /config/approval-mode.
- `backend/app/queue/worker.py`: o gate de `enqueue_pending_applications` (sweep) trocou `get_settings().approval_mode_enabled` por `read_approval_mode_fresh()`. Motivo: em modo servidor/arq o worker roda em outro processo e o `cache_clear()` do request da API nunca chega lá.

### Task 2 — Gate do APPLY_STEP para auto-apply EM VOO (A / WR-03)
- `backend/app/queue/worker.py`: no ramo `APPLY_STEP` do `_dispatch`, ANTES de abrir a sessão e chamar `apply_stage`: se `run_id is None` (= auto-apply) E `read_approval_mode_fresh()` (modo ON) → loga só metadados e `return` (no-op). Como `_run_once` faz `mark_done` quando `_dispatch` retorna sem exceção, o job conclui em DONE sem mover e sem entrar em loop de retry. Jobs COM `run_id` (aprovação manual) caem direto no `apply_stage` — sempre aplicam (D-06).

## Tests

- `backend/tests/test_config.py`: `test_read_approval_mode_fresh_bypassa_lru_cache` — prende o cache de `get_settings` em False, flipa o env para `true` sem cache_clear, e prova que `get_settings()` segue False enquanto `read_approval_mode_fresh()` vê True.
- `backend/tests/queue/test_approval_gate.py`: `test_gate_do_sweep_le_o_toggle_fresco` — cache preso em OFF + env ON sem cache_clear → sweep retorna 0 (gate lê fresco).
- `backend/tests/queue/test_apply_in_flight_gate.py` (novo): 3 casos — (1) sem run_id + ON: apply_stage NÃO chamado, job DONE, doc segue PROCESSANDO/CLASSIFIED; (2) sem run_id + OFF: apply_stage chamado; (3) com run_id + ON: apply_stage chamado (D-06). `apply_stage` espiado via monkeypatch (sem tocar no disco).

Padrão TDD: cada task com commit RED (teste falhando) → commit GREEN (implementação).

### Resultados
- Task 1 (config + approval_gate): 17 passed.
- Task 2 (apply_in_flight_gate): 3 passed.
- Suíte completa do backend: **528 passed** (eram 523 antes; +5 testes novos), 0 regressão. `ruff check` limpo em todos os arquivos tocados.

## Deviations from Plan

None - plano executado exatamente como escrito.

## Threat Model Coverage

- T-g6x-01 (Tampering — apply_stage via job auto em voo): mitigado pelo gate do `_dispatch` (Task 2); teste (1) prova arquivo intacto.
- T-g6x-02 (Integridade — toggle velho no worker): mitigado por `read_approval_mode_fresh` (Task 1).
- T-g6x-03 (DoS — no-op em loop de retry): mitigado — `_dispatch` retorna sem exceção → `mark_done`; teste assert `Job.status == DONE` numa passada.

## Commits

- `a261b56` test(RED): leitura fresca do toggle (WR-01)
- `0665816` feat(GREEN): read_approval_mode_fresh + gate do sweep fresco (WR-01)
- `192af4a` test(RED): gate do APPLY_STEP para auto-apply em voo (WR-03)
- `c1ac0a1` feat(GREEN): gate do APPLY_STEP suprime auto-apply em voo (WR-03)

## Self-Check: PASSED

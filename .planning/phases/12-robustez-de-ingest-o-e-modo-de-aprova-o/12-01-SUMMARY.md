---
phase: 12-robustez-de-ingest-o-e-modo-de-aprova-o
plan: 01
subsystem: ingest/watcher
tags: [watcher, ingestao, dedup, D-01, BL-02]
requires:
  - scan_and_enqueue (caminho idempotente de varredura existente)
  - active_folder_paths (pastas ativas+existentes do DB)
provides:
  - run_watcher varre pastas recém-ativadas em runtime (diff current - previous)
  - _scan_new_active_folders (helper testável do scan de diff)
affects:
  - ingestão de pastas criadas/reativadas após o cadastro
tech-stack:
  added: []
  patterns:
    - "diff current - previous retido entre iterações do loop de supervisão"
    - "try/except BLE001 espelhando o scan de startup (falha nunca derruba o watcher)"
key-files:
  created: []
  modified:
    - backend/app/ingest/watcher.py
    - backend/tests/test_watcher.py
decisions:
  - "D-01 opção 2: o diff vive no loop externo (run_watcher retém previous_paths), não em _watch_for_reconfig"
  - "Helper _scan_new_active_folders extraído para tornar o diff testável sem timing do awatch"
metrics:
  duration: ~8min
  completed: 2026-06-25
  tasks: 2
  files: 2
---

# Phase 12 Plan 01: Varrer pastas recém-ativadas em runtime — Summary

Fecha a lacuna de ingestão D-01/BL-02: quando uma pasta monitorada passa a existir ou é reativada depois do boot, `run_watcher` agora varre os arquivos JÁ presentes nela (diff `current - previous` reusando `scan_and_enqueue`), sem `/rescan` manual, de forma idempotente e sem derrubar o watcher em caso de falha.

## What Was Built

- **`run_watcher` retém `previous_paths` entre iterações** do loop de supervisão. Sementado com `set(initial_paths)` (as pastas já varridas no scan de startup) para não re-varrê-las. No topo de cada ciclo, chama o novo helper e depois atualiza `previous_paths = current_paths` — antes do ramo "sem pastas ativas", cobrindo ambos os caminhos.
- **`_scan_new_active_folders(engine, current_paths, previous_paths)`**: novo helper que calcula `new_paths = current_paths - previous_paths` e, se não-vazio, chama `await scan_and_enqueue(engine, sorted(new_paths))` envolto no MESMO `try/except Exception:  # noqa: BLE001` do scan inicial — loga `logger.info` o nº enfileirado, `logger.exception` em falha, e NUNCA propaga.
- **3 testes novos** em `test_watcher.py` cobrindo: varredura de pasta nova (diff), pasta já observada não re-varrida (diff vazio), e idempotência de varrer a mesma pasta nova duas vezes (dedup gate).

## Task-by-Task

| Task | Nome | Commit | Resultado |
| ---- | ---- | ------ | --------- |
| 1 (RED) | Testes falhando para scan de pasta nova | 448bae0 | `test(12-01)` — ImportError esperado |
| 1 (GREEN) | `_scan_new_active_folders` + plumbing no `run_watcher` | e1a0dbc | `feat(12-01)` — 7/7 verde |
| 2 | Regressão watcher + dedup | (sem commit — verificação) | 9/9 verde, zero regressão |

## Deviations from Plan

**1. [Implementação] Diff extraído para helper `_scan_new_active_folders` em vez de inline no `run_watcher`.**
- **Motivo:** o `<action>` descrevia retenção inline de `previous_paths` e o bloco try/except dentro do loop. Testar o diff inline exigiria dirigir o `awatch` (timing de ~5s, flaky). Extrair o passo diff+scan+try/except para um helper preserva exatamente o comportamento descrito (mesmo try/except BLE001, mesma idempotência) e o torna testável de forma determinística — alinhado ao estilo dos analogs (`test_scan_*` chamam `scan_and_enqueue` direto, evitando o `awatch`).
- **Impacto:** `run_watcher` ainda retém `previous_paths` e varre apenas o diff, exatamente como D-01 (opção 2 do PATTERNS). Nenhuma mudança de comportamento observável; apenas organização para testabilidade.
- **Arquivos:** backend/app/ingest/watcher.py
- **Commit:** e1a0dbc

Nenhum bug, funcionalidade crítica ausente ou issue bloqueante (Rules 1-3) encontrado. `_watch_for_reconfig` não foi tocado (segue só sinalizando `local_stop`), conforme a nota de implementação.

## Threat Model Adherence

- **T-12-01 (mitigate):** varredura restrita a `current - previous` derivado de `active_folder_paths` (só pastas cadastradas+ativas+existentes); reusa `scan_and_enqueue` (mesma estabilização/hash/gate). ✓
- **T-12-03 (mitigate):** `try/except Exception: # noqa: BLE001` espelhando o scan de startup — falha loga e segue, nunca propaga. ✓
- **T-12-02 (accept):** scan roda só no diff (pastas novas), não a cada ciclo; idempotente por dedup. ✓

Sem nova superfície de ameaça fora do `<threat_model>`.

## Verification

- `cd backend && uv run pytest tests/test_watcher.py tests/test_dedup_gate.py -x` → **9 passed**.
- `uv run ruff check app/ingest/watcher.py tests/test_watcher.py` → **All checks passed**.
- Cenário manual coberto por teste (`test_scan_new_active_folder_enqueues_existing_files`): pasta cadastrada ativa com arquivo dentro, ausente da iteração anterior → arquivo enfileirado sem `/rescan`.

## Known Stubs

Nenhum.

## Self-Check: PASSED

- FOUND: backend/app/ingest/watcher.py (`_scan_new_active_folders`)
- FOUND: backend/tests/test_watcher.py (3 testes novos)
- FOUND commit: 448bae0 (test)
- FOUND commit: e1a0dbc (feat)

## TDD Gate Compliance

- RED gate: 448bae0 `test(12-01)` (falha por ImportError antes da implementação). ✓
- GREEN gate: e1a0dbc `feat(12-01)` (7/7 verde após implementação). ✓
- REFACTOR: não necessário (código limpo na primeira passagem).

---
phase: 09-automacao-destino-de-arquivo-configuravel-e-transformacao-de
plan: 01
subsystem: automation
tags: [automation, path-resolution, windows, security, dry-run]
requires:
  - "naming.resolve_dest_folder (Fase 6)"
  - "stage.apply_stage/dry_run (Fase 6 + 06.2 multi-saída)"
  - "executor.evaluate_automations (passa base_root, trata None como blocked)"
provides:
  - "resolve_dest_folder com política absoluto-literal / relativo+base (D-01/D-02/D-03)"
  - "checagem de anchor existente (D-05) no dry_run e apply_stage"
  - "dry-run via API expõe o caminho absoluto REAL no dest_path (D-04)"
affects:
  - "todas as automações move/copy com destino absoluto (C:\\, UNC, /posix)"
tech-stack:
  added: []
  patterns:
    - "Detecção absoluto-vs-relativo OS-independente via ntpath/PureWindowsPath (Pitfall 1)"
    - "Caminho absoluto literal SEM .resolve() (Pitfall 2 — não canonizar contra CWD)"
    - "Ramo absoluto SEM is_relative_to (confinamento V4 removido — D-03)"
    - "Sanitização só por SEGMENTO; anchor (drive/UNC) nunca sanitizado (D-08)"
    - "Anchor existence gate antes de qualquer mkdir/materialize (D-05)"
key-files:
  created: []
  modified:
    - backend/app/automation/naming.py
    - backend/app/automation/stage.py
    - backend/tests/automation/test_naming.py
    - backend/tests/automation/test_stage.py
    - backend/tests/automation/test_undo.py
    - backend/tests/test_api_automations.py
decisions:
  - "[09-01] resolve_dest_folder com 3 ramos: Windows-absoluto (drive/UNC), POSIX-absoluto (/...) e relativo+base. _is_abs_windows exige DRIVE real (não anchor genérico) — um leading-slash puro vira POSIX, não Windows, evitando que ntpath converta /tmp em \\tmp e quebre separadores."
  - "[09-01] POSIX-absoluto (A2 RESEARCH RESOLVED) HABILITADO — necessário para o dry-run com tmp_path em Linux/WSL expor o caminho literal (D-04) e conveniência do dev; em produção (Windows) o ramo drive/UNC cobre o caso real."
  - "[09-01] D-05 implementado em stage.py via _anchor_missing/_plan_anchor_missing: extrai o anchor (drive Windows OU raiz POSIX) e checa exists() ANTES do mkdir; cobre o move E cada PlannedCopy (1 anchor inexistente bloqueia tudo). Bloqueio espelha a postura D-07 (EM_REVISAO, sem AuditLog, sem disco)."
metrics:
  duration: ~22 min
  tasks: 4
  files_modified: 6
  completed: 2026-06-24
---

# Phase 9 Plan 01: Política de Destino Absoluto/Relativo + Anchor Existente Summary

Reescrita da política de destino da automação: caminhos absolutos (Windows `C:\`, UNC `\\srv\share`, e POSIX `/...`) são aceitos LITERAIS — anchor preservado sem mutilar (`C:`→`C_` eliminado), sem prefixo do CWD/base, sem confinamento V4 (D-03); caminhos relativos continuam sob a base padrão; raiz/drive inexistente bloqueia no dry-run e no apply antes de qualquer `mkdir` (D-05); e um teste de integração de API prova o caminho absoluto real no `dest_path` do dry-run (D-04).

## What Was Built

- **`naming.resolve_dest_folder` (reescrita):** três ramos detectados de forma OS-independente — `_is_abs_windows` (drive/UNC via `PureWindowsPath().drive`), `_is_abs_posix` (`/...` via `PurePosixPath`), e o relativo (junta `base_root`). Ramo absoluto: anchor literal preservado, segmentos resolvidos+sanitizados, SEM `.resolve()` e SEM `is_relative_to`. D-07 (campo faltante → None) preservado nos três ramos. Helper `_resolve_segments` compartilhado.
- **`stage.py` (D-05):** `_anchor_missing` extrai o anchor (drive Windows quando há drive real; senão `Path().anchor` POSIX) e checa `exists()`. `_plan_anchor_missing` cobre o move e cada `PlannedCopy`. Wired no `dry_run` (→ `blocked=True`, sem disco) e no `apply_stage` (→ EM_REVISAO, sem AuditLog, antes do write-ahead/mkdir).
- **Testes:** RED→GREEN para naming (absoluto/UNC/relativo/cross-OS/anchor/sem-confinamento/D-07), stage (anchor inexistente bloqueia dry-run e apply), undo (move com destino absoluto restaura origem), e integração de API (dry-run mostra o caminho absoluto real, D-04).

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Testes RED (naming + stage + undo) | 7477459 | test_naming.py, test_stage.py, test_undo.py |
| 2 | Reescrever resolve_dest_folder (abs literal / rel+base) | 89e1537 | naming.py |
| 3 | Checagem de anchor existente (D-05) | cb4d8df | stage.py |
| 4 | Integração D-04 (dry-run mostra caminho real) + ramo POSIX | 388379f | test_api_automations.py, naming.py |

## Deviations from Plan

### Auto-fixed / decisões dentro da discrição do plano

**1. [Rule 3 - Blocking] Ramo POSIX-absoluto habilitado em `resolve_dest_folder`**
- **Found during:** Task 4
- **Issue:** O teste de integração D-04 usa `tmp_path` (POSIX `/tmp/...` no runner Linux/WSL) como destino absoluto. Com `_is_abs_windows` usando `ntpath.isabs`, `/tmp/...` era detectado como "absoluto Windows" e convertido em `\tmp\...`, quebrando os separadores e falhando o teste.
- **Fix:** `_is_abs_windows` passou a exigir DRIVE/UNC real (`PureWindowsPath().drive`), e um novo ramo `_is_abs_posix` (`PurePosixPath.is_absolute()`) trata `/...` como caminho POSIX literal. A2 do RESEARCH marca POSIX-absoluto como opcional/discrição (RESOLVED) — habilitá-lo é a escolha alinhada com os testes (Task 1 usa `Z:\` Windows para anchor inexistente; o dev/CI Linux usa POSIX real).
- **Files modified:** backend/app/automation/naming.py
- **Commit:** 388379f (junto com o teste D-04, pois o teste depende deste ramo)

**2. [Rule 1 - Bug] `_anchor_missing` não confundir POSIX com Windows**
- **Found during:** Task 3 (regressão capturada por `test_intent_before_materialize`)
- **Issue:** `PureWindowsPath("/tmp/x").anchor` retorna `'\\'` (não-vazio) — a primeira versão do helper marcava QUALQUER caminho POSIX absoluto como tendo anchor `'\\'`, e `Path('\\').exists()` é False no Linux → bloqueava indevidamente automações relativas/sem-drive (rename-only sob a base).
- **Fix:** `_anchor_missing` só usa o anchor Windows quando há `win.drive` real; senão usa `Path().anchor` (raiz POSIX `/`, que existe). Assim só `Z:\` (drive inexistente) bloqueia, e a base POSIX padrão não.
- **Files modified:** backend/app/automation/stage.py
- **Commit:** cb4d8df

**Nota sobre `naming.py` em 2 commits:** o arquivo foi tocado na Task 2 (reescrita central) e na Task 4 (ramo POSIX). Isso é intencional — o ramo POSIX só virou requisito ao escrever o teste de integração D-04 da Task 4, que roda em runner POSIX.

## must_haves — verificação

| Truth | Status |
| ----- | ------ |
| Destino com drive Windows resolve absoluto literal (sem CWD, sem C_) | ✅ test_dest_absolute_kept_literal |
| Destino UNC resolve absoluto e literal | ✅ test_dest_unc_absolute |
| Destino sem drive/UNC continua relativo → base padrão | ✅ test_dest_relative_uses_base |
| Detecção independe do OS do runner (Linux/WSL) | ✅ test_abs_detection_cross_os (passa em Linux) |
| Segmentos após o anchor sanitizados; anchor nunca | ✅ test_segments_sanitized_anchor_kept |
| Absoluto fora da base não vira None (sem is_relative_to) | ✅ test_abs_no_confinement |
| Raiz/drive inexistente bloqueia no dry-run e apply (sem criar unidade) | ✅ test_missing_root_blocks_dry_run / _apply |
| Undo de destino absoluto devolve à origem | ✅ test_undo_absolute_dest_restores_source |
| Dry-run via API carrega o caminho absoluto real no dest_path (D-04) | ✅ test_dry_run_absolute_dest_shows_real_path |

## Threat Model — dispositions aplicadas

- **T-09-01 (Tampering, mitigate):** `sanitize_component` neutraliza `/ \ : ..` por segmento; o anchor não vem de campo. ✅
- **T-09-02 (Elevation, accept):** confinamento V4 removido no ramo absoluto — aceito por D-03 (single-tenant); risco residual documentado no docstring de `naming.py`. ✅
- **T-09-03 (Tampering, mitigate):** sem `.resolve()` no ramo absoluto (verificado por grep — só aparece em comentários). ✅
- **T-09-04 (DoS, mitigate):** `Path(anchor).exists()` checado ANTES do mkdir, no dry-run E no apply. ✅

## Verification

- `cd backend && uv run pytest tests/automation -q` → **89 passed**.
- `cd backend && uv run pytest tests/test_api_automations.py -k absolute_dest -q` → **1 passed** (D-04).
- `cd backend && uv run pytest -q` (suíte completa) → **442 passed**, zero regressão.
- `grep -n "\.resolve()" backend/app/automation/naming.py` → só docstrings/comentários, nenhuma chamada.

## Sem mudança de schema

Confirmado pelo RESEARCH e pela execução: `AuditLog.source_path`/`dest_path` e `params_json.dest_folder` já são strings. Nenhum Alembic, nenhum modelo novo.

## Known Stubs

Nenhum. A política de destino está totalmente implementada e testada (unit + integração).

## Self-Check: PASSED
- Arquivos modificados existem (naming.py, stage.py, 4 arquivos de teste). ✅
- Commits existem: 7477459, 89e1537, cb4d8df, 388379f. ✅

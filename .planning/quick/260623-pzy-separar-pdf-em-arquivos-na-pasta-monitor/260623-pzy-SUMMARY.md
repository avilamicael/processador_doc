---
phase: quick-260623-pzy
plan: 01
subsystem: ingestão / automação de arquivo
tags: [split-to-files, anti-loop, audit, fileops, watched-folder, alembic-0009]
requires:
  - process_ingest (pipeline/ingest_stage.py) já cria 1 Document/bloco + CAS por content_hash
  - fileops.materialize_to_dest / remove_original / resolve_collision (máquina segura)
  - IngestedOriginal (gate de dedup por hash) + AuditLog write-ahead (status intent/done)
provides:
  - opt-in split_to_files por pasta (modelo + migração 0009 + API + UI)
  - materialização-na-pasta dos blocos + remoção segura do original (reversível, sem loop)
affects:
  - backend/app/pipeline/ingest_stage.py (passo 8 novo)
  - backend/app/queue/worker.py, backend/app/ingest/watcher.py (threading do opt-in)
  - frontend (ConfigPage Pastas)
tech-stack:
  added: []
  patterns:
    - "ingested_originals reusado como gate anti-loop keyed por content_hash do bloco (commit ANTES de gravar)"
    - "AuditLog write-ahead intent->done por bloco e pela remoção do original (action='apply', reversível)"
key-files:
  created:
    - backend/alembic/versions/0009_split_to_files.py
    - backend/tests/test_split_to_files.py
  modified:
    - backend/app/models/watched_folder.py
    - backend/app/api/watched_folders.py
    - backend/app/pipeline/ingest_stage.py
    - backend/app/queue/worker.py
    - backend/app/ingest/watcher.py
    - backend/tests/test_migrations.py
    - frontend/src/types.ts
    - frontend/src/pages/ConfigPage.tsx
decisions:
  - "action='apply' nos AuditLog de bloco/remoção: o undo de apply restaura via destino OU via CAS — a reversão desejada (apagar bloco, restaurar original do CAS). Propriedade garantida: reversível e nunca perde."
  - "Gate anti-loop reusa ingested_originals (mesma tabela/semântica de 'hash já visto' que o watcher já consulta) — mais limpo que mecanismo dedicado; commit do gate ANTES de qualquer arquivo aparecer na pasta fecha a corrida com o watcher."
  - "Migração 0009 forward-only, SÓ watched_folders — documents/trigger trg_documents_updated_at intactos."
metrics:
  duration_min: 12
  completed: 2026-06-23
  tasks: 3
  files: 10
---

# Quick 260623-pzy: Separar PDF em arquivos na pasta monitorada (opt-in) — Summary

Opt-in por pasta (`split_to_files`, default OFF) que, ao ingerir um PDF multipágina, SEPARA o PDF em arquivos físicos NA PRÓPRIA PASTA (faixas de páginas no nome, ex.: `doc_p1-2.pdf`/`doc_p3-4.pdf`/`doc_p5.pdf`), substituindo o original ANTES da IA — de forma reversível, sem perda e sem loop do watcher, reusando a máquina de arquivo segura existente (fileops/CAS/AuditLog/gate de dedup).

## O que foi entregue

- **Task 1 — opt-in (modelo + migração 0009 + API)** [`fac9975`]: `WatchedFolder.split_to_files` (Boolean, default OFF, `server_default 0`); migração `0009` forward-only que SÓ toca `watched_folders` (documents/trigger intactos); `WatchedFolderIn/Patch/Out` + create/update propagam o campo.
- **Task 2 — materialização-na-pasta (TDD)** [`094ad47` RED, `9fa31ed` GREEN]: `process_ingest` ganha o keyword-only `split_to_files=False`. Após o commit único dos blocos, um passo NOVO (só com opt-in ON, PDF, folder conhecida) executa a ordem-garantia:
  - **(A) anti-loop primeiro**: registra cada bloco em `ingested_originals` (`original_hash = content_hash` do bloco) e COMMITA esse gate ANTES de gravar qualquer arquivo — o watcher reconhece o arquivo de bloco como duplicata no instante em que ele aparece (no-op, sem re-ingerir/re-separar);
  - **(B) nome** derivado do stem do original + faixa de páginas, `sanitize_component` (Windows);
  - **(C)** por bloco: `AuditLog` write-ahead `intent` → `materialize_to_dest` (escreve do CAS, verifica hash) → `done`;
  - **(D)** SÓ depois de TODOS verificados: `AuditLog` `intent` → `remove_original` → `done`. Falha em (C) não chega aqui (original preservado; também está no CAS por `original_hash`).
  - Threading do opt-in: `worker._process_job_blocking` lê `split_to_files` do payload e repassa; `watcher._stabilize_hash_gate_enqueue` ganha o parâmetro e o inclui no payload nos DOIS call sites (`scan_and_enqueue`, `_handle_changes`).
- **Task 3 — UI** [`0b90b8c`]: `types.ts` (Folder/FolderCreate/FolderPatch); toggle `Switch` "Separar fisicamente o PDF em arquivos na pasta" no form da aba Pastas (ajuda PT-BR: original recuperável, depende de "Separar a cada N páginas"); create/update enviam o campo; a linha indica "Separa em arquivos" quando ligado.

## Invariantes de segurança cobertas (7 testes em `test_split_to_files.py`)

- N arquivos gravados + original removido do disco (`block_count==3` para 5pp/N=2);
- original recuperável do CAS byte-a-byte após a substituição (nunca perde);
- gate anti-loop: cada bloco tem `IngestedOriginal(original_hash==content_hash)`;
- AuditLog write-ahead: 4 registros `done` (3 blocos + 1 remoção), nenhum pendurado em `intent`;
- opt-in OFF (e default sem argumento) = comportamento atual idêntico (nada gravado/removido, sem AuditLog, Documents criados como hoje);
- idempotência/crash-safety: re-rodar cai no gate de duplicata (no-op), sem duplicar arquivos nem perder o original.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Testes de migração com profundidade de downgrade hardcoded quebraram com a 0009**
- **Found during:** Task 2 (suíte completa após adicionar a migração 0009)
- **Issue:** `test_downgrade_um_passo_reverte_so_o_modelo_final` (`downgrade -1`) e `test_downgrade_remove_toda_a_automacao` (`downgrade -3`) assumiam `head=0008`. Com a 0009 no topo, `-1` passou a reverter só o `split_to_files` (não o modelo final), falhando os asserts.
- **Fix:** ajustei as profundidades para manter o ALVO de cada teste idêntico (`-1`→`-2`, `-3`→`-4`, descendo a 0009 primeiro) e adicionei 2 testes dedicados à 0009 (coluna presente após head + trigger intacto; `downgrade -1` remove só `split_to_files` preservando o resto).
- **Files modified:** backend/tests/test_migrations.py
- **Commit:** 9fa31ed

**2. [Rule 3 - Blocking] Tests precisavam de uma WatchedFolder real (FK)**
- **Found during:** Task 2 GREEN (1ª execução)
- **Issue:** `ingested_originals.source_folder_id` é FK NOT-NULL-quando-presente para `watched_folders.id`; o gate anti-loop insere com `source_folder_id=folder_id`. Os testes passavam `folder_id=1` sem criar a pasta → `FOREIGN KEY constraint failed`.
- **Fix:** helper `_make_folder` cria uma `WatchedFolder` real e os testes usam o id retornado (espelha a realidade: o watcher sempre passa `folder.id`).
- **Files modified:** backend/tests/test_split_to_files.py
- **Commit:** 9fa31ed

## Verificação

- `pytest tests/test_split_to_files.py tests/test_ingest_stage.py tests/test_watcher.py tests/test_migrations.py` → 33 passed; suíte completa do backend → **419 passed**.
- `alembic upgrade head && downgrade -1 && upgrade head` → sem erro.
- `tsc --noEmit` limpo; `npm run build` verde.
- `ruff check` limpo nos arquivos tocados.

## Notas para verificação AO VIVO (orquestrador / WSL)

Pasta com `split_to_files=True` + `pages_per_block=2`; dropar um PDF de 5 páginas → a pasta passa a ter 3 arquivos de bloco, o original some, e NÃO há novo job/loop (logs do watcher: "Duplicata ignorada (gate)" para os blocos). Chave OpenAI vazia NÃO bloqueia (split-to-files é antes da IA).

## Self-Check: PASSED

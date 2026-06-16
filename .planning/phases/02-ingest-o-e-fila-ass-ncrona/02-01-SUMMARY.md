---
phase: 02-ingest-o-e-fila-ass-ncrona
plan: 01
subsystem: database
tags: [sqlalchemy, alembic, sqlite, pikepdf, watchfiles, pydantic, migrations, pytest]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "Base declarativa, modelos Document/Page/AuditLog/Usage, DocState, Alembic 0001 (com trigger trg_documents_updated_at), fixtures pytest (engine/sqlite_url), CAS, máquina de estados"
provides:
  - "Tabela jobs (fila durável in-process) com UNIQUE(original_hash, step) — base de PROC-02/PROC-03"
  - "Tabela ingested_originals com original_hash unique — gate de dedup pré-split (D-09)"
  - "Tabela watched_folders (path + pages_per_block + active) — config de pasta monitorada (D-02)"
  - "Enum JobStatus(pending/running/done/failed) com CHECK constraint no banco"
  - "Coluna documents.origin_original_id (FK nullable SET NULL) — vínculo bloco→original"
  - "Migração Alembic 0002 reversível (head único) preservando o trigger updated_at"
  - "watchfiles==1.2.0 e pikepdf==10.8.0 instalados e importáveis"
  - "6 arquivos de teste Wave 0 coletáveis (skeletons skip) + fixture schema_engine em conftest"
affects: [queue-worker, ingest-watcher, splitter, stabilizer, ingest-stage, dedup-gate, watched-folders-api, documents-api]

# Tech tracking
tech-stack:
  added: [watchfiles==1.2.0, pikepdf==10.8.0]
  patterns:
    - "SAEnum string-valued + CHECK constraint para status de fila (espelha DocState)"
    - "UniqueConstraint nomeado via __table_args__ como chave de idempotência"
    - "Recriação explícita do trigger updated_at após batch recreate de documents no SQLite"
    - "Skeletons de teste Wave 0: import lazy do alvo futuro + pytest.mark.skip (Nyquist Rule)"

key-files:
  created:
    - backend/app/models/watched_folder.py
    - backend/app/models/ingested_original.py
    - backend/app/models/job.py
    - backend/alembic/versions/0002_ingestion.py
    - backend/tests/test_stabilizer.py
    - backend/tests/test_splitter.py
    - backend/tests/test_dedup_gate.py
    - backend/tests/test_queue.py
    - backend/tests/test_ingest_stage.py
    - backend/tests/test_watcher.py
  modified:
    - backend/app/models/enums.py
    - backend/app/models/document.py
    - backend/app/models/__init__.py
    - backend/pyproject.toml
    - backend/tests/conftest.py
    - backend/tests/test_models.py
    - backend/tests/test_migrations.py

key-decisions:
  - "active (Boolean) usa server_default text('1') no SQLite — boolean renderiza como INTEGER"
  - "FK documents.origin_original_id nomeada (fk_documents_origin_original_id) para drop_constraint determinístico no downgrade batch"
  - "Migração final escrita à mão como 0002_ingestion.py (autogenerate descartado) para inserir a recriação do trigger e ordenar FKs"

patterns-established:
  - "Fila durável modelada como tabela jobs: idempotência por UNIQUE(original_hash, step), backoff por attempts/max_attempts/next_run_at, status via CHECK"
  - "Gate de dedup = coluna hash unique (mesma mecânica de Document.content_hash) numa tabela de originais separada"
  - "Toda migração com batch recreate de documents deve recriar o trigger trg_documents_updated_at (WR-05)"

requirements-completed: [ING-05, ING-06, PROC-02, PROC-03]

# Metrics
duration: 12min
completed: 2026-06-16
---

# Phase 2 Plan 01: Substrato de schema da ingestão Summary

**Três novas tabelas (jobs, ingested_originals, watched_folders) + enum JobStatus + coluna documents.origin_original_id, criadas pela migração Alembic 0002 reversível que preserva o trigger updated_at, com watchfiles/pikepdf instalados e 6 skeletons de teste Wave 0 coletáveis.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-16T00:42:00Z
- **Completed:** 2026-06-16T00:54:00Z
- **Tasks:** 3
- **Files modified:** 17 (10 criados, 7 modificados)

## Accomplishments
- Fila durável `jobs` modelada com chave de idempotência `UNIQUE(original_hash, step)` (PROC-03) e campos de backoff/retry (PROC-02): `attempts`, `max_attempts`, `next_run_at`, `status` (CHECK).
- Gate de dedup pré-split: tabela `ingested_originals` com `original_hash` unique (D-09) + contadores `block_count`/`duplicate_hits` (D-10).
- Config de pasta monitorada (`watched_folders`: path unique, `pages_per_block` nullable, `active` default True) — D-02/D-05.
- Coluna de vínculo `documents.origin_original_id` (FK nullable SET NULL) ligando cada bloco ao original.
- Migração Alembic `0002` reversível (head único, sem drift de modelo — `alembic check` limpo) que recria o trigger `trg_documents_updated_at` derrubado pelo batch recreate de `documents`.
- `watchfiles==1.2.0` (MIT) e `pikepdf==10.8.0` (MPL-2.0) instalados; 6 skeletons de teste Wave 0 coletáveis + fixture `schema_engine` compartilhada.

## Task Commits

Each task was committed atomically:

1. **Task 1: Dependências + esqueletos de teste Wave 0** - `c35738c` (chore)
2. **Task 2: JobStatus + 3 modelos novos + coluna de vínculo** - `ce67006` (feat — TDD RED+GREEN combinado)
3. **Task 3: Migração Alembic 0002 + teste de round-trip** - `755dbd4` (feat — TDD RED+GREEN combinado)

**Plan metadata:** (este commit de docs)

## Files Created/Modified
- `backend/app/models/enums.py` - Adicionado `JobStatus(str, Enum)` (pending/running/done/failed)
- `backend/app/models/watched_folder.py` - Modelo `WatchedFolder` (D-02): path unique, pages_per_block nullable, active default True, timestamps
- `backend/app/models/ingested_original.py` - Modelo `IngestedOriginal` (D-09): original_hash unique = gate de dedup, block_count/duplicate_hits, FK opcional para watched_folders
- `backend/app/models/job.py` - Modelo `Job` (PROC-02/PROC-03): status SAEnum, UniqueConstraint uq_jobs_hash_step, attempts/max_attempts/next_run_at/payload/last_error
- `backend/app/models/document.py` - Coluna `origin_original_id` (FK nullable SET NULL → ingested_originals)
- `backend/app/models/__init__.py` - Registro de Job/IngestedOriginal/WatchedFolder/JobStatus em imports + __all__
- `backend/alembic/versions/0002_ingestion.py` - Migração das 3 tabelas + coluna, com recriação do trigger updated_at no upgrade/downgrade
- `backend/pyproject.toml` + `backend/uv.lock` - watchfiles + pikepdf
- `backend/tests/conftest.py` - Fixture `schema_engine` compartilhada (create_all só em teste)
- `backend/tests/test_models.py` - Testes dos novos modelos (defaults, gate dedup, idempotência, vínculo)
- `backend/tests/test_migrations.py` - ESPERADAS + 3 tabelas; testes de origin_original_id, uq_jobs_hash_step, downgrade -1
- `backend/tests/test_{stabilizer,splitter,dedup_gate,queue,ingest_stage,watcher}.py` - 6 skeletons Wave 0 (skip, import lazy)

## Decisions Made
- **Migração escrita à mão** (autogenerate descartado): o `autogenerate` produziu o DDL correto, mas o arquivo final `0002_ingestion.py` foi reescrito para (a) numerar como `0002`/`down_revision=0001`, (b) inserir a recriação do trigger `trg_documents_updated_at` após o batch recreate de `documents`, e (c) garantir a ordem de FKs. Validado com `alembic check` = "No new upgrade operations detected" (sem drift modelo↔migração).
- **`active` com `server_default=text("1")`**: SQLite renderiza Boolean como INTEGER; o server_default literal evita NULL no INSERT via SQL cru.
- **FK nomeada** `fk_documents_origin_original_id`: nome explícito para `drop_constraint` determinístico no downgrade em modo batch.

## Deviations from Plan
None - plan executed exactly as written.

(Observação: as tasks 2 e 3 são `tdd="true"`. O config do projeto tem `tdd_mode: false`, então o ciclo RED→GREEN foi seguido — teste falhando confirmado antes da implementação — mas RED e GREEN foram consolidados num único commit `feat(...)` por task, em vez de commits `test(...)`/`feat(...)` separados. Não há divergência funcional do plano.)

## Issues Encountered
None - o `autogenerate` do Alembic detectou todas as tabelas, índices e a FK corretamente na primeira passada; o único ajuste manual previsto (trigger) foi aplicado conforme o `<action>` da Task 3.

## TDD Gate Compliance
As tasks 2 e 3 são marcadas `tdd="true"`. Ciclo RED→GREEN cumprido (testes falhando confirmados antes da implementação em ambas). RED e GREEN foram consolidados em commits `feat(...)` únicos por task — não há commits `test(...)` separados no log. Avaliação: aceitável dado `tdd_mode: false` na config do projeto; a prova de comportamento (gate de dedup, idempotência, round-trip + trigger) está nos testes versionados junto à implementação.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Schema da Fase 2 versionado e reversível pronto: planos seguintes (fila/worker, watcher, splitter, stabilizer, ingest_stage, APIs) podem persistir estado.
- Os 6 skeletons de teste Wave 0 são placeholders intencionais (skip + import lazy do alvo futuro) — cada onda posterior os substituirá pela implementação real; não bloqueiam a suite (6 skipped, 65 passed).
- Dependências `watchfiles` (watcher) e `pikepdf` (splitter) instaladas e importáveis.

## Self-Check: PASSED

Todos os 10 arquivos-chave + SUMMARY confirmados em disco; os 3 commits de task (c35738c, ce67006, 755dbd4) confirmados no git log.

---
*Phase: 02-ingest-o-e-fila-ass-ncrona*
*Completed: 2026-06-16*

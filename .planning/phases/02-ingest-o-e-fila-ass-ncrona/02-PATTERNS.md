# Phase 2: Ingestão e Fila Assíncrona - Pattern Map

**Mapped:** 2026-06-15
**Files analyzed:** 22 (15 backend + 7 frontend)
**Analogs found:** 19 / 22 (3 net-new with no in-repo analog: TanStack Query client + hooks)

> Phase 2 is almost entirely **costura** (wiring) over a complete Phase-1 substrate: CAS (`store`), state machine (`transition`/`mark_step`), SQLAlchemy 2.0 models, Alembic, FastAPI lifespan, pytest fixtures. Almost every new file has a close, recent in-repo analog. The genuinely net-new surface is the **in-process SQLite queue** (no library, but built on documented SQLite/SQLAlchemy primitives) and the **frontend data layer** (TanStack Query — not yet installed). The planner should copy structure and conventions from the analogs below rather than inventing.

---

## File Classification

### Backend (new + modified)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/models/watched_folder.py` | model | CRUD | `app/models/usage.py` / `app/models/document.py` | exact |
| `app/models/ingested_original.py` | model | CRUD (dedup gate) | `app/models/document.py` (unique hash) | exact |
| `app/models/job.py` | model | event-driven (queue) | `app/models/document.py` (SAEnum/state pattern) | role-match |
| `app/models/__init__.py` (modify) | config (registry) | — | existing `app/models/__init__.py` | exact |
| `app/storage/queue_repo.py` *(or `queue/repo.py`)* | service/repository | event-driven (claim/enqueue) | `app/storage/cas.py` (module-fn boundary) + `app/storage/db.py` (session usage) | role-match |
| `app/queue/worker.py` *(or `pipeline/worker.py`)* | service (async loop) | event-driven / batch | `app/pipeline/state_machine.py` (advances docs) + lifespan in `main.py` | partial |
| `app/ingest/watcher.py` | service (async) | streaming/event-driven | `main.py` lifespan (asyncio wiring) — no FS-watch analog | partial |
| `app/ingest/stabilizer.py` | utility | file-I/O | `app/storage/cas.py` (Path/stdlib FS, streaming) | partial |
| `app/ingest/splitter.py` | utility | file-I/O / transform | `app/storage/cas.py` (Path in, bytes/temp out; pure stdlib boundary) | partial |
| `app/pipeline/ingest_stage.py` | service | request-response (orchestration) | `app/pipeline/state_machine.py` (orchestrates transition/mark_step) | role-match |
| `app/pipeline/states.py` (maybe modify) | config (allowlist) | — | existing `app/pipeline/states.py` | exact |
| `app/api/watched_folders.py` | route/controller | CRUD | *no `api/` exists yet* — `main.py` `@app.get` + `get_session` | partial |
| `app/api/documents.py` | route/controller | request-response (read) | `main.py` `/health` (get_session + read) | partial |
| `app/config.py` (modify) | config | — | existing `app/config.py` (computed_field, Field/env) | exact |
| `app/main.py` (modify) | config (composition root) | — | existing `app/main.py` lifespan | exact |
| `alembic/versions/0002_*.py` | migration | — | `alembic/versions/0001_initial.py` | exact |

### Tests (new)

| New Test File | Role | Closest Analog | Match Quality |
|---------------|------|----------------|---------------|
| `tests/test_queue.py` | test | `tests/test_state_machine.py` (engine fixture + commit/reload assertions) | role-match |
| `tests/test_dedup_gate.py` | test | `tests/test_state_machine.py` + `tests/test_cas.py` | role-match |
| `tests/test_splitter.py` | test | `tests/test_cas.py` (tmp_path FS) | role-match |
| `tests/test_stabilizer.py` | test | `tests/test_cas.py` (tmp_path FS) | role-match |
| `tests/test_watcher.py` | test (integration) | `tests/conftest.py` fixtures + asyncio_mode=auto | partial |
| `tests/test_ingest_stage.py` | test | `tests/test_state_machine.py` (terminal-state assertions) | role-match |
| `tests/test_migrations.py` (modify) | test | existing `tests/test_migrations.py` (`ESPERADAS` set + round-trip) | exact |

### Frontend (modified + net-new)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/lib/api.ts` (client) | utility | request-response (fetch) | **NONE — net-new** (no API client exists) | none |
| `src/hooks/useDocuments.ts` etc. | hook | request-response (polling) | **NONE — net-new** (TanStack Query not installed) | none |
| `src/main.tsx` (modify) | provider wiring | — | existing `src/main.tsx` (StrictMode root) | exact |
| `src/types.ts` (modify) | model (types) | — | existing `src/types.ts` (`Doc`/`Folder`/`DocStatus` unions) | exact |
| `src/components/StatusPill.tsx` (modify) | component | — | existing `StatusPill.tsx` (token-driven pill) | exact |
| `src/pages/DocumentsPage.tsx` (modify) | component | request-response (poll) | existing `DocumentsPage.tsx` (table/stat/chips structure) | exact |
| `src/pages/ConfigPage.tsx` (modify, `PastasTab`) | component | CRUD | existing `ConfigPage.tsx` `PastasTab` (folder-row/switch) | exact |

---

## Pattern Assignments

### `app/models/watched_folder.py` (model, CRUD)

**Analog:** `app/models/usage.py` (simple table) + `app/models/document.py` (timestamps + `__init__` default + docstring header style).

**Imports + declaration pattern** (`usage.py` 8-23):
```python
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base

class WatchedFolder(Base):
    __tablename__ = "watched_folders"
    id: Mapped[int] = mapped_column(primary_key=True)
```

**Timestamp columns** — copy verbatim from `document.py` 68-76:
```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now(), nullable=False
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
)
```

**Fields this phase needs (per D-02):** `path: Mapped[str]` (String, unique recommended), `pages_per_block: Mapped[int | None]` (None/0 = "não separar" — see UI-SPEC field), `active: Mapped[bool]` (default True; maps to UI `.switch`). Follow the column style in `document.py`.

**Convention to preserve:** every model file opens with a module docstring tying columns to decision IDs (see `document.py` 1-9). New models cite D-02 / D-09 / PROC-03 accordingly.

---

### `app/models/ingested_original.py` (model, CRUD — dedup gate D-09)

**Analog:** `app/models/document.py` — specifically the **unique-indexed hash column** which is the exact mechanism the dedup gate reuses.

**Unique hash column pattern** (`document.py` 34-38) — this is the gate:
```python
# Hash SHA-256 (hex) do conteúdo — base de dedup; unique global.
content_hash: Mapped[str] = mapped_column(
    String(64), index=True, unique=True, nullable=False
)
```
For `ingested_originals`, rename to `original_hash` and keep `String(64), index=True, unique=True`. RESEARCH Pattern 3 specifies: `original_filename`, `source_folder_id` (FK → `watched_folders.id`, nullable), `block_count`, `duplicate_hits` (default 0 — feeds D-10 counter), `created_at`.

**FK + nullable pattern** — copy from `audit_log.py` 26-28:
```python
document_id: Mapped[int | None] = mapped_column(
    ForeignKey("documents.id", ondelete="SET NULL"), index=True, nullable=True
)
```

**Block→original link (RESEARCH Open Question 1):** add nullable FK column `origin_original_id` on `documents` via the migration (model change in `document.py` + ALTER in `0002`).

---

### `app/models/job.py` (model, event-driven — the queue table)

**Analog:** `app/models/document.py` — for the **SAEnum status column** and the `__init__` default trick. The Job `status` should mirror how `DocState` is persisted (string-valued, CHECK constraint).

**SAEnum pattern** (`document.py` 44-56) — reuse for `status` (pending|running|done|failed):
```python
state: Mapped[DocState] = mapped_column(
    SAEnum(
        DocState, name="ck_documents_doc_state", native_enum=False,
        create_constraint=True,
        values_callable=lambda enum: [member.value for member in enum],
        length=20,
    ),
    default=DocState.RECEBIDO, server_default=DocState.RECEBIDO.value, nullable=False,
)
```
Define a `JobStatus(str, Enum)` in `app/models/enums.py` alongside `DocState` (same file, same `(str, Enum)` style — see `enums.py` 16-29) and use the identical SAEnum config (`name="ck_jobs_status"`).

**Idempotency key (PROC-03):** `UniqueConstraint("original_hash", "step")` via `__table_args__` (RESEARCH Pattern 1 sketch, lines 205-219). `original_hash: String(64), index=True`; `next_run_at: DateTime(timezone=True), index=True`; `status: ..., index=True`; `attempts`/`max_attempts: Integer`; `payload: Text`; `last_error: Text nullable`. Add to `app/models/__init__.py` `__all__` + imports (see registry below).

---

### `app/models/__init__.py` (modify — model registry)

**Analog:** itself (lines 1-21). Pattern: importing the package registers all tables in `Base.metadata` (required for Alembic autogenerate + tests). **Add the three new models** to both the import block and `__all__`, keeping alphabetical order:
```python
from app.models.ingested_original import IngestedOriginal
from app.models.job import Job
from app.models.watched_folder import WatchedFolder
```
Failure to add here means Alembic autogenerate won't see the tables (env.py 19 does `import app.models`).

---

### `app/storage/queue_repo.py` (repository, event-driven — enqueue/claim/mark)

**Analog:** `app/storage/cas.py` for the **module-level-functions-behind-a-single-boundary** convention (no class), and `app/storage/db.py` `get_session` for session usage. This is the swappable `enqueue`/`claim` interface (RESEARCH §structure rationale — lets a future arq/Redis backend slot in).

**Module boundary + docstring convention** (`cas.py` 1-25): module docstring states the public interface explicitly:
```python
"""... Interface pública: store, path_for, exists, read_bytes, open_blob."""
```
Mirror this: `"""Interface pública: enqueue, claim_next, mark_done, mark_retry, mark_failed, requeue_running."""`

**Atomic claim (RESEARCH Pattern 1, lines 222-240)** — the critical primitive; SQLite ≥3.35 `UPDATE ... RETURNING`, single-writer:
```python
row = session.execute(text("""
    UPDATE jobs SET status='running', attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP
     WHERE id = (SELECT id FROM jobs
                  WHERE status='pending' AND next_run_at <= CURRENT_TIMESTAMP
                  ORDER BY next_run_at LIMIT 1)
    RETURNING id, original_hash, step, payload, attempts, max_attempts
""")).first()
session.commit()
```
**Verify A1 at plan time:** `sqlite3.sqlite_version >= 3.35`; fallback is conditional `UPDATE`+`SELECT` in one transaction (still safe — single writer per D-11).

**Backoff (RESEARCH Pattern 2, lines 245-256):** `next_run_at = now + min(BASE * 2**attempts, MAX) + jitter`; on `attempts >= max_attempts` set `status='failed'` (dead-letter → doc `FALHA`). Tunables (`BASE`, `MAX`, `max_attempts`) belong in `config.py` Settings (see below).

**Resume on startup (RESEARCH lines 240):** `UPDATE jobs SET status='pending' WHERE status='running'` — call from worker startup.

---

### `app/queue/worker.py` (service, async loop)

**Analog (state advancement):** `app/pipeline/state_machine.py` — the worker advances docs ONLY through `transition`/`mark_step`, never by setting `document.state` directly (Anti-Pattern in RESEARCH 359; state_machine docstring 41-46 forbids X→X auto-loops — worker must check current state first).

**Analog (async task wiring):** `main.py` lifespan (see below). The worker is an `asyncio.Task`.

**Terminal-state rule (RESEARCH Pitfall 6, lines 424-429 + CONTEXT Integration Points):** at end of Phase-2 pipeline the doc stays in **`PROCESSANDO`** with `last_completed_step` = an "aguardando extração" marker. **Never** call `transition(..., CONCLUIDO)`. Copy the `mark_step` usage from `state_machine.py` 66-76:
```python
def mark_step(session, document, step):
    document.last_completed_step = step
    session.commit(); session.refresh(document)
    return document
```

**CPU-bound isolation (RESEARCH Pitfall 4):** wrap `splitter.split_pdf(...)` in `await asyncio.to_thread(...)` so pikepdf never blocks the shared event loop.

---

### `app/ingest/stabilizer.py` (utility, file-I/O)

**Analog:** `app/storage/cas.py` — stdlib-only (`pathlib`, `os`), streaming/chunk discipline, Windows-aware atomic FS ops. No FS-watch analog exists; stabilizer is pure FS polling.

**Pattern to copy (RESEARCH Pattern 4, lines 282-304):** async quiescence loop on `(st.st_size, st.st_mtime_ns)` + Windows lock-test via `path.open("rb")`. Default window goes in `config.py` (D-04). Preserve `cas.py`'s defensive FS style (handle `FileNotFoundError`, no partial reads).

---

### `app/ingest/splitter.py` (utility, transform — pikepdf)

**Analog:** `app/storage/cas.py` — `store(src: Path) -> str` is the model: a pure function with a `Path` in and content-addressed result out. The splitter is `split_pdf(src: Path, pages_per_block: int | None) -> list[bytes]` (RESEARCH Pattern 5, lines 312-323).

**CAS handoff decision (RESEARCH A4, line 326):** lowest-risk path is write each block to a temp file on the same volume as `data_dir`, then `cas.store(temp)` (signature already takes `Path` — see `cas.py` 64). Optionally extend CAS with `store_bytes` — but that is a `cas.py` modification; prefer reusing `store` as-is. Note: `cas.store` is idempotent by content (cas.py 97-101), so re-storing the same block is a free no-op — this underpins the idempotency guarantee.

**License note (CLAUDE.md):** use **pikepdf** (MPL), not PyMuPDF (AGPL) for split.

---

### `app/pipeline/ingest_stage.py` (service, orchestration)

**Analog:** `app/pipeline/state_machine.py` — same package, same role (orchestrates the domain without touching HTTP). It composes: dedup-gate check (`ingested_originals`) → `cas.store(original)` → `split_pdf` → per-block `cas.store` + create `Document` + `transition(RECEBIDO→PROCESSANDO)` + `mark_step("ingested"/awaiting-extraction)`.

**Extension allowlist (CONTEXT discretion / ING-04):** accept only `.pdf/.jpg/.jpeg/.png`; silently ignore others (no Document, no job — RESEARCH Open Question 2: light debug log only; quarantine is Phase 5).

**Reuse, don't hand-roll** (RESEARCH "Don't Hand-Roll" table): `cas.store` for hash+atomic copy, `transition`/`mark_step` for state. Test with `test_state_machine.py`-style commit-then-reload assertions.

---

### `app/api/watched_folders.py` + `app/api/documents.py` (routes)

**Analog:** `app/main.py` — there is **no `api/` package yet**, so `main.py` is the only in-repo FastAPI pattern. Copy:

**Route + session pattern** (`main.py` 45-54):
```python
@app.get("/health")
def health() -> dict[str, str]:
    engine = app.state.engine
    with get_session(engine) as session:
        session.execute(text("SELECT 1")).scalar()
    return {"status": "ok", ...}
```
New routes get the engine from `app.state.engine` (set in lifespan, `main.py` 31) and use `get_session` as a context manager. Keep routes **thin** (CONTEXT "API fina": validate/read/configure only; logic lives in `pipeline/`/`ingest/`).

**Endpoints (D-12 + UI-SPEC + RESEARCH Open Question 3):**
- `watched_folders.py`: `GET/POST/PATCH/DELETE /watched-folders` (CRUD, D-02). Validate the path (RESEARCH Security V5/V12: `Path.resolve()`, reject traversal).
- `documents.py`: `GET /documents` (list of blocks/Documents, with per-state counts), `GET /documents/duplicates-count` (D-10 — `SUM(duplicate_hits)`), `POST /rescan` ("Forçar varredura" — re-emits candidates through stabilize→dedup→enqueue, idempotent).

**Wiring:** `main.py` must `app.include_router(...)` for the new routers (modification below).

---

### `app/config.py` (modify — add Settings fields)

**Analog:** itself (lines 35-79). Add new env-backed fields next to `database_url`/`openai_api_key`. RESEARCH Runtime State Inventory specifies: `stabilization_window_seconds` (D-04 default ~3-5s, A2), and optionally `queue_poll_interval`, `queue_max_attempts`, backoff `BASE`/`MAX`.

**Field pattern** — follow the `Field(... validation_alias=AliasChoices(...))` style (config.py 50-54) for env aliasing, or plain typed defaults like `database_url: str | None = None` (line 54). Do **not** put folder config here — folders live in the DB (D-02). Keep `@computed_field` style if any derived value is needed (lines 57-79).

---

### `app/main.py` (modify — lifespan spawns watcher + worker; include routers)

**Analog:** itself (lines 18-42). RESEARCH Pattern 6 (lines 332-348) extends the existing lifespan:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings(); ensure_data_dir(settings)
    engine = create_db_engine(settings.effective_database_url)
    app.state.engine = engine
    stop = asyncio.Event()
    watcher_task = asyncio.create_task(run_watcher(engine, stop))
    worker_task  = asyncio.create_task(run_worker(engine, stop))
    try:
        yield
    finally:
        stop.set()
        for t in (watcher_task, worker_task): t.cancel()
        await asyncio.gather(watcher_task, worker_task, return_exceptions=True)
        engine.dispose()
```
**Preserve** the existing WAL-verification block (main.py 26-29) — keep it. **Add** `app.include_router(...)` for `api/watched_folders.py` and `api/documents.py`.

**Single-worker constraint (RESEARCH Pitfall 5 / CLAUDE.md):** document/force `uvicorn --workers 1` — multiple workers would duplicate watcher+worker.

---

### `alembic/versions/0002_*.py` (migration)

**Analog:** `alembic/versions/0001_initial.py` — copy its structure exactly.

**Patterns to copy:**
- Revision header block (0001 lines 1-18); set `down_revision = '0001'`.
- `op.create_table(...)` + `with op.batch_alter_table(...) as batch_op: batch_op.create_index(...)` (0001 lines 24-39) — **batch mode is required for SQLite** (env.py 54 sets `render_as_batch=True`).
- **Adding `documents.origin_original_id`** (new nullable FK) must use `batch_alter_table` `add_column` (SQLite can't plain-ALTER-ADD-FK; batch recreates the table). Reference the trigger caveat: 0001 lines 84-90 create `trg_documents_updated_at` — a batch recreate of `documents` may need to recreate/preserve that trigger; handle explicitly in `upgrade`/`downgrade`.
- CHECK-constraint-as-SAEnum renders inline (0001 line 32) — the `Job.status` enum will render the same way.
- `downgrade()` drops in reverse with batch ops (0001 lines 93-116).

**Generate, then hand-adjust** (per CLAUDE.md / D-10: schema only via Alembic, never `create_all`).

---

### Tests (Wave 0 — RESEARCH §Validation Architecture)

**Analog:** `tests/test_state_machine.py` (DB tests) and `tests/test_cas.py` (FS tests); fixtures in `tests/conftest.py`.

**Engine fixture reuse** (conftest.py 12-25): tests get `engine` (SQLite WAL over `tmp_path`) for free.

**Schema-in-test pattern** (test_state_machine.py 29-36) — `create_all` is allowed ONLY in tests:
```python
@pytest.fixture
def schema_engine(engine: Engine) -> Iterator[Engine]:
    Base.metadata.create_all(engine)
    try: yield engine
    finally: Base.metadata.drop_all(engine)
```

**Commit-then-reload assertion style** (test_state_machine.py 103-117) — open a second `get_session` and re-query to prove persistence. Use this for `test_queue.py` (claim/backoff/resume/idempotent), `test_dedup_gate.py`, `test_ingest_stage.py` (terminal-state stays `PROCESSANDO`, never `CONCLUIDO`).

**Migration test extension** (test_migrations.py 23, 40-50): add the three new tables to the `ESPERADAS` set and assert `0002` round-trips up/down (lines 121-134 pattern). Async tests rely on `asyncio_mode = "auto"` (pyproject) — no decorator needed.

---

### Frontend

#### `src/types.ts` (modify — real domain unions)

**Analog:** itself (lines 7-30). Replace the **mock** `DocStatus = 'encontrado' | 'leitura' | 'tratado' | 'erro'` with the real backend domain-state union (UI-SPEC Color table): `'recebido' | 'processando' | 'em_revisao' | 'concluido' | 'quarentena' | 'falha'`. Update/replace `Doc`/`Folder` interfaces to match API shapes (drop mock-only fields `type`/`tmpl`/`who`/`rec`/`freq`/`last` — UI-SPEC says hide Tipo/Template/Responsável). Keep the `interface`/`export type` style.

#### `src/components/StatusPill.tsx` (modify)

**Analog:** itself (lines 1-12) — token-driven: `color: var(--st-${status})`, `background: var(--st-${status}-bg)`. **Extend** to map real domain states → label → `--st-*` token per UI-SPEC table (lines 112-120), instead of the 4 mock keys + `STATUS_LABELS`. Note UI-SPEC: "Aguardando extração" reuses `--st-encontrado` (blue, muted); never green/`--st-tratado` in Phase 2.

#### `src/pages/DocumentsPage.tsx` (modify)

**Analog:** itself — keep the full visual structure (stat-grid lines 56-67, toolbar/chips 72-94, `table.docs` 98-167, table-foot 171-180). Replace the `DOCS` mock import (line 1) with a TanStack Query hook. UI-SPEC contract: polling 3-5s, `keepPreviousData`/`placeholderData` (no flicker), columns reduced to Arquivo/Pasta/Status/Tamanho/Data, duplicates indicator in `.table-foot` with neutral `--text-3`, empty/loading/error states render **inside** the table card.

#### `src/pages/ConfigPage.tsx` (modify — `PastasTab` only)

**Analog:** `PastasTab` (lines 48-94) — reuse `.folder-row`, `.folder-icon`, `Switch`. Replace `FOLDERS` mock with API data; drop mock meta (`rec`/`types`/`freq`/`last` — UI-SPEC line 174); show split rule + active toggle. Wire "Adicionar pasta" (line 58) to a create form (modal/inline) → POST. **Do not** wire `RegrasTab` (out of scope v2). Destructive remove uses the UI-SPEC confirmation copy with `--st-erro`.

#### `src/lib/api.ts` + `src/hooks/*.ts` + `src/main.tsx` (NET-NEW data layer)

**Analog: NONE.** There is no API client or data-fetching layer in the repo (package.json has only `react`/`react-dom` — TanStack Query is NOT installed). Planner: treat as net-new, using **TanStack Query 5.101** (CLAUDE.md frontend stack) + a typed fetch client (CLAUDE.md recommends `openapi-typescript`/`openapi-fetch` against FastAPI's OpenAPI — optional). Install: `npm i @tanstack/react-query`.

`main.tsx` modification analog = itself (lines 6-10): wrap `<App />` with `<QueryClientProvider client={queryClient}>` inside the existing `StrictMode` root.

---

## Shared Patterns

### Database session boundary
**Source:** `app/storage/db.py` `get_session` (lines 88-108)
**Apply to:** every backend file touching the DB (models are read/written through it; routes, repo, worker, ingest_stage)
```python
with get_session(engine) as session:
    ...  # commits only if new/dirty/deleted; rollback+raise on exception
```
Never open raw connections; never couple to SQLite SQL (db.py docstring 1-10). Engine comes from `app.state.engine` (main.py 31) in HTTP code, or is passed into the watcher/worker tasks.

### State transitions
**Source:** `app/pipeline/state_machine.py` `transition`/`mark_step` (lines 24-76) + allowlist `app/pipeline/states.py` (19-44)
**Apply to:** worker, ingest_stage — anything that advances a Document
- Always go through `transition` (validates against `TRANSITIONS`); never set `document.state =` directly.
- No X→X auto-loops — check current state first (state_machine docstring 41-46).
- Phase-2 terminal = `PROCESSANDO` + `mark_step` marker, NOT `CONCLUIDO` (Pitfall 6).

### Content-addressed storage
**Source:** `app/storage/cas.py` `store` (lines 64-122)
**Apply to:** ingest_stage (store original), splitter→ingest_stage (store each block)
- `store(src: Path) -> sha256_hex`; copies (never moves) the original (D-07); idempotent by content (D-08) — re-storing is a free no-op.

### Model conventions
**Source:** `app/models/document.py` (docstring 1-9; SAEnum 44-56; timestamps 68-76; `__init__` default 62-66)
**Apply to:** `watched_folder.py`, `ingested_original.py`, `job.py`
- Module docstring ties columns to decision IDs.
- `Mapped[...] = mapped_column(...)` SQLAlchemy 2.0 typed style.
- Enum columns via `SAEnum(..., native_enum=False, create_constraint=True, values_callable=...)`; enum members defined in `enums.py` as `(str, Enum)`.
- Register every new model in `app/models/__init__.py` (imports + `__all__`) or Alembic won't see it.

### Alembic-only schema evolution
**Source:** `alembic/env.py` (1-13, `render_as_batch=True`) + `alembic/versions/0001_initial.py`
**Apply to:** every schema change (new tables + `documents.origin_original_id`)
- `batch_alter_table` for all index/column/ALTER ops (SQLite).
- Never `create_all` in production (only in tests).

### Config / Settings
**Source:** `app/config.py` (35-93)
**Apply to:** stabilization window + queue tunables
- Env-backed via `BaseSettings`; `Field(validation_alias=AliasChoices(...))` for aliases; `@computed_field` for derived values; `get_settings()` is `lru_cache`d. Secrets (none new this phase) use `SecretStr`.

### Async task lifecycle
**Source:** `app/main.py` lifespan (18-42)
**Apply to:** watcher + worker
- Spawn via `asyncio.create_task` in lifespan startup; signal shutdown with an `asyncio.Event` (`stop`) + `task.cancel()` + `asyncio.gather(..., return_exceptions=True)`; `engine.dispose()` last. `watchfiles.awatch(*paths, stop_event=stop)` for clean stop.

### Frontend tokens (locked design)
**Source:** `frontend/src/index.css` (tokens) + existing components/pages; UI-SPEC is authoritative
**Apply to:** all frontend changes
- Use `var(--token)` only (never hardcode hex); reuse existing CSS classes (`.card`, `.table.docs`, `.folder-row`, `.btn-primary`, `.chip`, `.pill`, `.switch`); pt-BR copy per UI-SPEC Copywriting Contract; icon-only buttons need `aria-label`/`title`.

---

## No Analog Found

Files with no close in-repo match (planner uses RESEARCH/CLAUDE.md stack instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/lib/api.ts` | utility (HTTP client) | request-response | No API client exists; net-new. Use typed fetch (optionally openapi-fetch). |
| `src/hooks/use*.ts` | hook | request-response (polling) | TanStack Query not installed (package.json: only react/react-dom). Net-new per CLAUDE.md stack. |
| `app/ingest/watcher.py` | service | event-driven (FS) | No filesystem-watcher analog in repo. Pattern from RESEARCH Pattern 6 + watchfiles docs; async-task lifecycle borrows from `main.py` lifespan. |

> Partial-analog files (`stabilizer.py`, `splitter.py`, `queue_repo.py`, `worker.py`, `api/*`) have a structural/convention analog (cas.py / state_machine.py / main.py) but their core logic (FS quiescence, pikepdf split, SQLite atomic claim, FastAPI routers) is new and specified in RESEARCH Patterns 1-6 — copy the *conventions* from the analog, the *logic* from RESEARCH.

---

## Metadata

**Analog search scope:** `backend/app/` (models, storage, pipeline, config, main), `backend/alembic/`, `backend/tests/`, `frontend/src/` (pages, components, types, data, App, main); `frontend/package.json`, `backend/pyproject.toml`.
**Files scanned:** 24 source files read in full (Phase-1 backend substrate + frontend design substrate).
**Pattern extraction date:** 2026-06-15

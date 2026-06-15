---
phase: 01-funda-o-de-estado-e-storage
fixed_at: 2026-06-15T00:00:00Z
review_path: .planning/phases/01-funda-o-de-estado-e-storage/01-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 1: Code Review Fix Report

**Fixed at:** 2026-06-15
**Source review:** .planning/phases/01-funda-o-de-estado-e-storage/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (1 Critical + 6 Warning; IN-01 included because the WR-01 fix touches the same Windows-path code in `config.py`)
- Fixed: 7
- Skipped: 0

**Verification:** Full backend suite green (`uv run pytest -q` → 52 passed, up from 50;
two new regression tests added). `uv run ruff check .` → all checks passed. Alembic
`upgrade head` → `downgrade base` round-trips cleanly on SQLite.

## Fixed Issues

### CR-01: `cas.store` cleanup `finally` can delete a just-committed blob

**Files modified:** `backend/app/storage/cas.py`
**Commit:** f3c8872
**Applied fix:** Replaced the overloaded `tmp_path` + `.endswith(".tmp")` string-suffix
guard with an explicit `cleanup_target: Path | None` handle. The handle is set to `None`
the instant a temp file is consumed (by the idempotency unlink, or by the final
`os.replace(staged_tmp, final_path)`), so the `finally` block can never reach the
committed blob. Added a defensive `assert cleanup_target != path_for(hasher.hexdigest())`
before unlinking as defense-in-depth (D-08, no-data-loss module). Existing CAS tests
(11) still pass, including the atomicity / no-orphan-`.tmp` assertions.

### WR-01: SQLite URL built with raw Windows backslashes

**Files modified:** `backend/app/config.py`
**Commit:** 139258e
**Applied fix:** `effective_database_url` now builds the default SQLite URL via
`"sqlite:///" + (self.data_dir / "app.db").as_posix()`, normalizing backslashes to
forward slashes so the URL parses correctly on Windows (the primary platform).
Same commit also fixed IN-01 (below). 9 config tests pass.

### WR-02: `create_db_engine` used two different SQLite detections

**Files modified:** `backend/app/storage/db.py`
**Commit:** f9b3f91
**Applied fix:** Detect the dialect exactly once via
`make_url(url).get_backend_name() == "sqlite"` and drive BOTH the
`check_same_thread=False` connect-arg and the PRAGMA registration from that single
`is_sqlite` flag. They can no longer diverge, so WAL / foreign_keys / busy_timeout can
never be silently skipped on an unusual SQLite URL. 8 db tests pass.

### WR-03: `get_session` rebuilt a `sessionmaker` on every call

**Files modified:** `backend/app/storage/db.py`
**Commit:** 9fd3e81 (combined with WR-04 — same function)
**Applied fix:** Added a module-level `WeakKeyDictionary` cache keyed by engine and a
`get_session_factory(engine)` helper that creates the `sessionmaker` once per engine and
reuses it. `get_session` now consumes the cached factory. Kept the `get_session(engine)`
public signature to avoid breaking ~30 existing call sites (main.py + tests). The weak
dict lets engines be garbage-collected when disposed.

### WR-04: `get_session` committed on every successful exit, including read-only blocks

**Files modified:** `backend/app/storage/db.py`
**Commit:** 9fd3e81 (combined with WR-03 — same function)
**Applied fix:** Commit now only fires when there is pending work:
`if session.in_transaction() and (session.new or session.dirty or session.deleted)`.
Read-only blocks (e.g. the health endpoint's `SELECT 1`) no longer emit a needless
`COMMIT`, avoiding write-intent contention with the single writer under SQLite WAL.
Write paths (state machine `transition`/`mark_step`, model persistence) still commit —
verified by the 26 session/model/state-machine tests.

### WR-06: `state` enum had no CHECK constraint in the migration

**Files modified:** `backend/app/models/document.py`, `backend/alembic/versions/0001_initial.py`, `backend/tests/test_models.py`
**Commit:** d4e9963
**Applied fix:** Added `create_constraint=True` and the named constraint
`ck_documents_doc_state` to the `SAEnum` in the model AND to the matching
`sa.Enum(...)` in migration 0001. SQLAlchemy now renders
`CONSTRAINT ck_documents_doc_state CHECK (state IN (...))` inline in the
`CREATE TABLE`, so the DB rejects out-of-domain states (D-06 enforced at the storage
boundary, not only in Python). Because the CHECK is inline, `op.drop_table` in
downgrade removes it cleanly — no extra downgrade step needed under SQLite batch mode.
Added a regression test (`test_state_fora_do_dominio_eh_rejeitado_pelo_banco`) that a
raw-SQL INSERT with an invalid state raises `IntegrityError`.

> **Migration-editing note (per verification guidance):** the CHECK constraint and the
> WR-05 trigger were added by **editing the shipped migration 0001** rather than
> creating a new migration. This is acceptable ONLY because nothing has shipped yet and
> there is no production database — confirmed by re-running `alembic upgrade head` then
> `alembic downgrade base`, which round-trips cleanly.

### WR-05: `documents.updated_at` would not auto-update under Alembic/raw-SQL writes

**Files modified:** `backend/alembic/versions/0001_initial.py`, `backend/tests/test_migrations.py`
**Commit:** 45794b0
**Applied fix:** The ORM-side `onupdate=func.now()` only fires on ORM flushes. Added a
SQLite `AFTER UPDATE` trigger `trg_documents_updated_at` (created in migration 0001,
gated on `op.get_bind().dialect.name == "sqlite"`) that stamps
`updated_at = CURRENT_TIMESTAMP` on every UPDATE — including raw SQL and Alembic data
migrations. SQLite's `recursive_triggers` defaults OFF, so the trigger's own UPDATE does
not re-fire it. Downgrade drops the trigger before dropping the table. Postgres (server
mode) would use a different mechanism, intentionally out of scope for this single-tenant
phase. Added a regression test
(`test_updated_at_avanca_em_update_via_sql_cru`) proving a raw-SQL UPDATE that does not
touch `updated_at` still advances it off its seeded year-2000 value.

### IN-01: Double-backslash literal in the default-dir fallback (folded into WR-01)

**Files modified:** `backend/app/config.py`
**Commit:** 139258e
**Applied fix:** Changed `os.path.expandvars(r"%SystemDrive%\\ProgramData")` to a single
backslash `r"%SystemDrive%\ProgramData"`. Included here because the file and the
Windows-path concern are the same as WR-01; trivial and correctness-improving.

## Skipped Issues

None — all in-scope findings were fixed.

The remaining Info findings (IN-02 `mark_step` validation, IN-03 idempotent
self-transition, IN-04 bare `assert` for WAL invariant) were out of scope
(`critical_warning`) and are left for the developer to address as design decisions in
a later phase.

---

_Fixed: 2026-06-15_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

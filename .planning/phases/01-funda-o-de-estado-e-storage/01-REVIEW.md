---
phase: 01-funda-o-de-estado-e-storage
reviewed: 2026-06-15T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - backend/app/config.py
  - backend/app/storage/db.py
  - backend/app/storage/cas.py
  - backend/app/models/document.py
  - backend/app/models/page.py
  - backend/app/models/audit_log.py
  - backend/app/models/usage.py
  - backend/app/models/enums.py
  - backend/app/pipeline/states.py
  - backend/app/pipeline/state_machine.py
  - backend/app/main.py
  - backend/alembic/env.py
  - backend/alembic/versions/0001_initial.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-06-15
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

This is a clean, well-documented foundation phase. The CAS uses streaming hashing
and atomic `os.replace`; the state machine validates against an explicit allowlist
and refuses invalid transitions; the OpenAI key is a `SecretStr` and is not leaked
by the health endpoint; migrations exist and `create_all` is confined to test
fixtures. Test coverage is thorough.

However, several real defects survive the tests because the tests are all written
on **POSIX** and never exercise the **Windows** path / concurrency behavior that
the project explicitly names as the primary target. The most serious is a
**data-loss / corruption risk in `cas.store`**: the cleanup `finally` block can
delete a freshly committed blob, and the staged-temp logic relies on a variable
state that is wrong on the error path. There are also Windows-specific path
fragilities (SQLite URL built with backslashes, double-backslash literal in the
default-dir fallback) and a SQLAlchemy session-factory-per-call inefficiency that
also subtly breaks the documented "FastAPI dependency" contract.

## Critical Issues

### CR-01: `cas.store` cleanup `finally` can delete a just-committed blob (data corruption / loss)

**File:** `backend/app/storage/cas.py:98-109`
**Issue:**
The happy path stages the temp into the shard directory and then renames it onto
the final blob path:

```python
staged_tmp = final_path.parent / tmp_path.name   # ".<uuid>.tmp"
os.replace(tmp_path, staged_tmp)
tmp_path = staged_tmp
os.replace(tmp_path, final_path)   # staged_tmp -> final blob
return content_hash
finally:
    if tmp_path.exists() and tmp_path.name.endswith(".tmp"):
        tmp_path.unlink(missing_ok=True)
```

After the final `os.replace`, `tmp_path` still points at `staged_tmp` (it was
never reassigned to `final_path`), and `staged_tmp` no longer exists, so on the
*happy path* the cleanup is a no-op — by luck. The defect is on the **error /
concurrency path**:

1. `final_path.parent` and the `staged_tmp` name (`.<uuid>.tmp`) live in the same
   shard directory as the final blob. If `os.replace(tmp_path, final_path)` raises
   (e.g. Windows `PermissionError` because another process/AV has the destination
   open, or a transient `OSError`), `tmp_path` is `staged_tmp`, which *does* exist
   and *does* end in `.tmp`, so it is unlinked — correct. But the blob that may
   already be partially present is left in an inconsistent state with no signal to
   the caller.
2. More importantly, the `.endswith(".tmp")` guard is the **only** thing standing
   between this `finally` and `final_path`. The temp filename is derived from
   `uuid4().hex` and the suffix `.tmp`; should any future refactor make `tmp_path`
   alias the final path (or should `path_for` ever produce a hash-shard collision
   with a `.tmp`-suffixed name), the cleanup would delete a committed,
   content-addressed blob — silent, irreversible loss of a client document, which
   is the one thing D-08 / the integrity constraint forbids.

This is fragile-by-construction: correctness depends on a string-suffix check
rather than on tracking which temp files this call actually owns.

**Fix:** Track the temp file explicitly and never let cleanup touch the final
blob. Clear the handle once it has been consumed by `os.replace`:

```python
staged_tmp = final_path.parent / tmp_path.name
os.replace(tmp_path, staged_tmp)
os.replace(staged_tmp, final_path)   # staged_tmp consumed
tmp_path = None                       # nothing left to clean
return content_hash
finally:
    if tmp_path is not None and tmp_path.exists():
        tmp_path.unlink(missing_ok=True)
```

Use a dedicated, mutable `cleanup_target` variable rather than overloading
`tmp_path`, and assert `cleanup_target != final_path` before unlinking.

## Warnings

### WR-01: SQLite URL built with raw Windows backslashes is fragile on the primary platform

**File:** `backend/app/config.py:75`
**Issue:**
```python
return f"sqlite:///{self.data_dir / 'app.db'}"
```
On Windows `data_dir` stringifies with backslashes, producing
`sqlite:///C:\ProgramData\ProcessadorDocumentos\app.db`. SQLAlchemy generally
tolerates this, but f-string interpolation of an OS path into a URL is exactly the
class of bug that bites only on Windows (the primary target) and is invisible to
the POSIX-only tests. A drive-relative path (`sqlite:///C:app.db`, missing the
slash after the drive) or special characters in `%ProgramData%` would break
parsing.

**Fix:** Build the URL with SQLAlchemy's URL helper and a normalized POSIX-style
path, or use the `sqlite:///` + forward-slash form:

```python
from sqlalchemy.engine import URL
return URL.create("sqlite", database=str(self.data_dir / "app.db")).render_as_string()
# or, minimally:
return "sqlite:///" + (self.data_dir / "app.db").as_posix()
```

### WR-02: `create_db_engine` gates PRAGMAs on `url.startswith("sqlite")` but `check_same_thread` on the raw string

**File:** `backend/app/storage/db.py:48-55`
**Issue:** Two different SQLite detections are used:
`url.startswith("sqlite")` for `connect_args`, and `engine.dialect.name == "sqlite"`
for PRAGMA registration. They will agree for normal URLs, but a URL like
`sqlite+pysqlite:///...` still starts with `sqlite`, while a future relative path
or an unusual scheme could make the two diverge — yielding an engine with
`check_same_thread=False` but **no WAL/foreign_keys/busy_timeout applied**, or
vice versa. The health endpoint asserts WAL only in `lifespan`; a silent PRAGMA
gap on a non-matching SQLite URL would not be caught here.

**Fix:** Detect the dialect once and drive both decisions from it:

```python
from sqlalchemy.engine import make_url
backend = make_url(url).get_backend_name()
if backend == "sqlite":
    connect_args["check_same_thread"] = False
engine = create_engine(url, ...)
if engine.dialect.name == "sqlite":
    _register_sqlite_pragmas(engine)
```

### WR-03: `get_session` builds a new `sessionmaker` on every call

**File:** `backend/app/storage/db.py:65-81`
**Issue:** `get_session` calls `make_session_factory(engine)` on each invocation,
constructing a fresh `sessionmaker` per session. `sessionmaker` is meant to be
created once and reused; rebuilding it per request is wasteful and, more
importantly, signals that the intended "single session factory per engine"
lifecycle is not actually wired. The health endpoint and every future request
path pay this cost.

**Fix:** Create the factory once (e.g. store it on `app.state` alongside the
engine, or memoize per-engine) and have `get_session` consume it:

```python
def get_session(factory: sessionmaker[Session]) -> Iterator[Session]: ...
```

### WR-04: `get_session` commits on *every* successful exit, including read-only blocks

**File:** `backend/app/storage/db.py:74-79`
**Issue:** The context manager unconditionally `session.commit()`s on success.
For the health endpoint (`SELECT 1`) and all future read paths this issues a
needless `COMMIT`, and under SQLite WAL a write-intent commit on a read-only
session can contend with the single writer (the Phase-2 worker), undermining the
"serialize writes through one worker" model. It also makes the function unsuitable
as a generic read dependency.

**Fix:** Either expose separate read vs write helpers, or only commit when the
session is dirty:

```python
yield session
if session.in_transaction() and (session.new or session.dirty or session.deleted):
    session.commit()
```

### WR-05: `documents.updated_at` will not auto-update under Alembic/raw-SQL writes

**File:** `backend/app/models/document.py:70-75`, `backend/alembic/versions/0001_initial.py:31`
**Issue:** `updated_at` uses `onupdate=func.now()`, which is a **SQLAlchemy
ORM-side** hook — it only fires on flushes through the ORM. The migration emits
only `server_default=CURRENT_TIMESTAMP` and no trigger, so any update that does
not go through the ORM (a raw SQL `UPDATE`, an Alembic data migration, or the
state-machine if it ever switches to bulk update) leaves `updated_at` stale. For
an audit-sensitive, undo-oriented product this silently produces wrong timestamps.

**Fix:** Document that all writes must go through the ORM, or add a DB-level
trigger / `server_onupdate` so the timestamp is correct regardless of write path.
At minimum, add a test that asserts `updated_at` advances after a `transition()`.

### WR-06: `state` enum has no CHECK constraint in the migration — invalid states can be persisted

**File:** `backend/alembic/versions/0001_initial.py:28`
**Issue:** The model uses `SAEnum(..., native_enum=False)`, which normally renders
a `CHECK (state IN (...))` constraint so the DB rejects unknown values. The
generated migration column is
`sa.Enum(..., native_enum=False, length=20)` with **no `create_constraint=True`**,
so on SQLite the column is just `VARCHAR(20)` with no enforcement. A bug elsewhere
(or a direct SQL write) could store an out-of-domain `state`, and the state
machine — which trusts `document.state` as a valid `DocState` — would then read a
value that is not in `TRANSITIONS`, where `TRANSITIONS.get(from_state, set())`
silently treats it as a dead state. The data-integrity guarantee (D-06: "no
illegal flow") is only enforced in Python, not at the storage boundary.

**Fix:** Render the CHECK constraint in the migration (and confirm the model emits
it):

```python
sa.Column('state', sa.Enum(..., native_enum=False, length=20, create_constraint=True,
                           name='ck_documents_doc_state'), ...)
```
Add a test that an out-of-range `state` INSERT is rejected.

## Info

### IN-01: Double-backslash literal in the default-dir fallback

**File:** `backend/app/config.py:30`
**Issue:** `os.path.expandvars(r"%SystemDrive%\\ProgramData")` contains a literal
double backslash. On Windows this expands to `C:\\ProgramData`; `PureWindowsPath`
happens to collapse the doubled separator so the resulting path is correct, but
the doubled backslash is unintended and misleading. (The branch is also rarely
reached because `PROGRAMDATA` is normally set on Windows.)
**Fix:** Use a single backslash: `os.path.expandvars(r"%SystemDrive%\ProgramData")`.

### IN-02: `mark_step` mutates and commits with no validation or bound on `step`

**File:** `backend/app/pipeline/state_machine.py:66-76`
**Issue:** `mark_step` writes any arbitrary string to `last_completed_step` and
commits, with no allowlist of valid step names and no check that the document is
in a state where marking a step makes sense (e.g. it will happily mark a step on a
`CONCLUIDO` or `QUARENTENA` document). The column is also unbounded `String`. This
is acceptable for a foundation phase but is an open door for the resume/idempotency
logic in Phase 2 to drift.
**Fix:** Introduce a `Step` enum (mirroring `DocState`) and validate against it, or
at least document the contract that callers must pass a known step.

### IN-03: Idempotent self-transition (e.g. PROCESSANDO→PROCESSANDO) raises instead of being a no-op

**File:** `backend/app/pipeline/state_machine.py:41-44`, `backend/app/pipeline/states.py:19-44`
**Issue:** Self-loops are deliberately excluded from `TRANSITIONS`, so a worker
that retries and re-requests its current state gets `InvalidTransition`. The
docstring frames this as intentional (caller checks first), which is a defensible
design, but it makes the most common retry/resume case error-prone: any caller
that forgets the pre-check turns a benign retry into an exception. Given the
project's emphasis on idempotent resume, consider making same-state transitions an
explicit no-op return rather than an error.
**Fix:** Optionally `if from_state == to_state: return document` before validation,
or document the pre-check requirement prominently in the worker contract.

### IN-04: `lifespan` uses bare `assert` for the WAL invariant

**File:** `backend/app/main.py:29`
**Issue:** `assert str(mode).lower() == "wal", ...` enforces the WAL guarantee with
an `assert`, which is stripped when Python runs under `-O` (a plausible production
packaging flag for the PyInstaller/sidecar path). If optimized out, the app would
boot without confirming WAL — the exact integrity check this line exists to make.
**Fix:** Raise an explicit exception:
`if str(mode).lower() != "wal": raise RuntimeError("WAL não habilitado ...")`.

---

_Reviewed: 2026-06-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

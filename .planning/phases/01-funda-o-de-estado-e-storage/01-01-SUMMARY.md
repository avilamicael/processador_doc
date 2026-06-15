---
phase: 01-funda-o-de-estado-e-storage
plan: 01
subsystem: infra
tags: [fastapi, sqlalchemy, sqlite, wal, pydantic-settings, uv, pytest, python-3.12]

# Dependency graph
requires: []
provides:
  - "Repositório backend instalável com uv (Python 3.12) e lockfile reprodutível"
  - "Settings (pydantic-settings): data_dir único configurável (padrão %ProgramData%\\ProcessadorDocumentos), DATABASE_URL, OPENAI_API_KEY como SecretStr"
  - "Camada de banco única (app/storage/db.py): Base DeclarativeBase 2.0, create_db_engine com PRAGMAs WAL/busy_timeout/foreign_keys gated em dialeto sqlite, get_session"
  - "App FastAPI com lifespan (ensure_data_dir + engine + assert WAL) e GET /health que confirma a fundação sem expor a chave OpenAI"
affects: [02-ingestao-e-fila, 03-extracao-ia, 08-distribuicao-atualizacao]

# Tech tracking
tech-stack:
  added: [fastapi==0.137.1, uvicorn[standard]==0.40.*, pydantic==2.13.4, pydantic-settings, sqlalchemy==2.0.*, alembic==1.18.4, pytest, pytest-asyncio, ruff, httpx, uv]
  patterns:
    - "Camada de banco atrás de interface (Base/create_db_engine/get_session) — porta aberta para Postgres trocando só a connection string"
    - "PRAGMAs SQLite aplicados via listener connect somente quando dialect.name == sqlite"
    - "Segredos como SecretStr — nunca em repr/str/logs/respostas"
    - "Pasta de dados única configurável com padrão por plataforma"

key-files:
  created:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/.python-version
    - backend/.gitignore
    - backend/.env.example
    - backend/app/__init__.py
    - backend/app/config.py
    - backend/app/storage/__init__.py
    - backend/app/storage/db.py
    - backend/app/main.py
    - backend/tests/__init__.py
    - backend/tests/conftest.py
    - backend/tests/test_config.py
    - backend/tests/test_db.py
  modified: []

key-decisions:
  - "data_dir exposto como computed_field (não campo armazenado) para evitar recoerção do flavour de Path pela validação pydantic sob monkeypatch de os.name"
  - "DATABASE_URL explícita tem precedência; ausente deriva sqlite:///<data_dir>/app.db (banco dentro da pasta de dados — D-01)"
  - "PRAGMAs WAL/busy_timeout=5000/foreign_keys=ON aplicados por conexão apenas no dialeto sqlite"
  - "OPENAI_API_KEY como SecretStr; valor só acessível via get_secret_value()"

patterns-established:
  - "Fronteira única de banco: todo acesso passa por app/storage/db.py (Base, create_db_engine, get_session)"
  - "Configuração centralizada em app/config.py com get_settings() cacheado e ensure_data_dir()"
  - "TDD por tarefa: testes RED antes da implementação, ruff limpo, suíte verde"

requirements-completed: [USE-01]

# Metrics
duration: 6min
completed: 2026-06-15
---

# Phase 1 Plan 1: Fundação de Estado e Storage Summary

**Backend FastAPI instalável com uv (Python 3.12), Settings com data_dir padrão %ProgramData% e chave OpenAI mascarada (SecretStr), engine SQLite WAL atrás de interface abstraível e endpoint /health que prova a fundação subindo.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-15T22:05:07Z
- **Completed:** 2026-06-15T22:10:30Z
- **Tasks:** 3
- **Files created:** 14

## Accomplishments
- Repositório `backend/` instalável com `uv sync` (Python 3.12 buscado automaticamente), dependências pinadas e `uv.lock` reprodutível — sem libs de fases futuras (openai/pymupdf/watchfiles direto/arq).
- `app/config.py`: pasta de dados única configurável com padrão `%ProgramData%\ProcessadorDocumentos` no Windows e `~/.processador_documentos` fora dele; `DATABASE_URL` deriva SQLite dentro da pasta de dados; `OPENAI_API_KEY` como `SecretStr` nunca exposto em `repr`/`str`/logs.
- `app/storage/db.py`: camada de banco única (`Base`, `create_db_engine`, `get_session`) com PRAGMAs WAL/`busy_timeout`/`foreign_keys` aplicados apenas no dialeto sqlite — porta aberta para Postgres pela connection string.
- `app/main.py`: FastAPI com `lifespan` (garante pasta de dados, abre engine, confirma WAL) e `GET /health` retornando `{status, db, version}` sem nunca incluir a chave OpenAI.
- 17 testes passando; ruff limpo; grep confirma que a chave não é logada.

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold do repositório backend e dependências** - `d14bf3a` (chore)
2. **Task 2: Settings (data dir + chave OpenAI) com padrão %ProgramData%** - `7e31ee7` (feat, inclui testes RED→GREEN)
3. **Task 3: Camada de banco SQLite WAL + FastAPI /health** - `93772ba` (feat, inclui testes RED→GREEN)

_Tarefas TDD: testes e implementação foram consolidados num único commit por tarefa (executor sequencial)._

## Files Created/Modified
- `backend/pyproject.toml` - Projeto `processador-documentos`, deps pinadas + grupo dev, config ruff/pytest (asyncio_mode=auto).
- `backend/uv.lock` - Lockfile reprodutível.
- `backend/.python-version` - `3.12`.
- `backend/.gitignore` - Ignora `.venv/`, `__pycache__/`, `*.db*`, `.env`, `data/`.
- `backend/.env.example` - Documenta `DATA_DIR`, `DATABASE_URL`, `OPENAI_API_KEY` sem valores.
- `backend/app/config.py` - `Settings`, `get_settings()` cacheado, `ensure_data_dir()`.
- `backend/app/storage/db.py` - `Base`, `create_db_engine`, `get_session`, PRAGMAs WAL gated em sqlite.
- `backend/app/main.py` - App FastAPI, `lifespan`, `GET /health`.
- `backend/tests/conftest.py` - Fixtures `sqlite_url`, `engine` (arquivo temporário).
- `backend/tests/test_config.py` - 9 testes de config.
- `backend/tests/test_db.py` - 8 testes de banco + healthcheck.

## Decisions Made
- **`data_dir` como `computed_field`** (não campo armazenado): pydantic recoage o tipo `Path` para o flavour do `os.name` durante a validação; sob `monkeypatch` de `os.name="nt"` em Linux isso instanciaria `WindowsPath` (impossível). Computar a partir de uma entrada bruta `data_dir_raw` (string, alias `DATA_DIR`) resolve sem acoplar.
- **Precedência `DATABASE_URL`** sobre o default SQLite mantém a porta para Postgres sem código condicional acoplado a sqlite.
- **PRAGMAs por conexão** via listener `connect` garantem WAL/foreign_keys em cada conexão nova (testado com 2 conexões).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Testes de Path forçando `os.name="nt"` em host Linux**
- **Found during:** Task 2 (Settings)
- **Issue:** O teste original montava `Path(r"C:\ProgramData")` e forçava `os.name="nt"`, fazendo `pathlib`/pydantic tentar instanciar `WindowsPath`, o que é impossível em Linux (`NotImplementedError`). Era um defeito na estratégia de teste, não na lógica de derivação.
- **Fix:** Reescrito para cobrir o ramo real (PROGRAMDATA presente → `<programdata>/ProcessadorDocumentos`) com caminhos representáveis no SO de CI, e um teste dedicado de `_default_data_dir()` cobrindo a lógica do ramo Windows sem instanciar `WindowsPath`. A implementação de `config.py` também foi ajustada para `data_dir` computado (ver Decisions) eliminando a recoerção de Path.
- **Files modified:** backend/tests/test_config.py, backend/app/config.py
- **Verification:** 9 testes de config verdes; ruff limpo.
- **Committed in:** 7e31ee7 (Task 2 commit)

**2. [Rule 3 - Blocking] Teste de URL Postgres exigia driver `psycopg` ausente nesta fase**
- **Found during:** Task 3 (db layer)
- **Issue:** O teste criava `create_engine("postgresql+psycopg://...")` para provar que PRAGMAs SQLite não rodam em Postgres, mas a resolução do dialeto importa `psycopg`, que (corretamente) não é dependência da Fase 1 — `ModuleNotFoundError`.
- **Fix:** Substituído por verificação sem driver via `make_url(...).get_backend_name() == "postgresql"` (a derivação de PRAGMA é gated em `dialect.name == "sqlite"`, logo não roda para postgresql), mais um teste que confirma PRAGMAs aplicados por conexão no sqlite.
- **Files modified:** backend/tests/test_db.py
- **Verification:** 8 testes de db verdes; sem instalar psycopg (sem inflar deps da fase).
- **Committed in:** 93772ba (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 bug de teste, 1 bloqueio de dependência)
**Impact on plan:** Ambos os ajustes corrigem a estratégia de teste para o host de CI sem alterar o escopo nem adicionar dependências de fases futuras. Comportamento e critérios de aceite preservados.

## Issues Encountered
- `pathlib` não permite instanciar `WindowsPath` em Linux — tratado no Deviation 1 movendo `data_dir` para `computed_field` e testando o ramo via PROGRAMDATA.

## User Setup Required
None - nenhuma configuração de serviço externo necessária nesta fase. (Para rodar localmente: copiar `backend/.env.example` para `backend/.env` é opcional; defaults funcionam sem `.env`.)

## Next Phase Readiness
- Fundação pronta: config (data dir + chave OpenAI), engine SQLite WAL atrás de interface e app subindo via `/health`.
- Porta aberta para Postgres (connection string) e para a fila in-process (Fase 2) — nada bloqueia esses desenhos.
- **Pendente nas próximas plans desta fase:** modelos de domínio (Document/Page/AuditLog/Usage), máquina de estados explícita, CAS por hash e migrações Alembic (D-04..D-10). DIST-01/DIST-02 têm a fundação estabelecida mas só serão integralmente comprovados com a fila (Fase 2) e validação real em Windows.

## Self-Check: PASSED

All 9 declared files exist on disk; all 3 task commit hashes (`d14bf3a`, `7e31ee7`, `93772ba`) present in git history.

---
*Phase: 01-funda-o-de-estado-e-storage*
*Completed: 2026-06-15*

---
phase: 01-funda-o-de-estado-e-storage
plan: 02
subsystem: domain-model
tags: [sqlalchemy-2.0, alembic, sqlite, domain-model, state-machine-foundation, python-3.12]

# Dependency graph
requires:
  - "01-01: Base DeclarativeBase, create_db_engine, get_session (app/storage/db.py)"
  - "01-01: Settings.effective_database_url (app/config.py)"
provides:
  - "DocState (str, Enum) — estados de topo enxutos: RECEBIDO/PROCESSANDO/EM_REVISAO/CONCLUIDO/QUARENTENA/FALHA (D-04)"
  - "Modelos de domínio Document/Page/AuditLog/Usage (SQLAlchemy 2.0 Mapped) com state persistido + marcador interno last_completed_step (D-05) + content_hash único (dedup, D-07)"
  - "Alembic wireado à fundação (target_metadata=Base.metadata, URL de get_settings, render_as_batch=True) + migração 0001_initial criando todas as tabelas"
  - "Schema versionado round-trip provado (upgrade head / downgrade base) sem create_all em produção (D-10)"
affects: [01-03-state-machine, 01-04-cas, 02-ingestao-e-fila, 03-extracao-ia, 08-distribuicao-atualizacao]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Modelos de domínio com SQLAlchemy 2.0 typed (Mapped/mapped_column) herdando da Base única"
    - "Pacote app/models/__init__ importa todos os modelos — garante registro em Base.metadata para Alembic"
    - "Enum de domínio persistido pelo valor string (SAEnum native_enum=False + values_callable)"
    - "Alembic desde o dia 1: env.py lê metadata e URL da app, render_as_batch para ALTER TABLE SQLite futuro"
    - "Schema evolui SOMENTE via migração versionada; create_all restrito a fixtures de teste"

key-files:
  created:
    - backend/app/models/__init__.py
    - backend/app/models/enums.py
    - backend/app/models/document.py
    - backend/app/models/page.py
    - backend/app/models/audit_log.py
    - backend/app/models/usage.py
    - backend/alembic.ini
    - backend/alembic/env.py
    - backend/alembic/script.py.mako
    - backend/alembic/README
    - backend/alembic/versions/0001_initial.py
    - backend/tests/test_models.py
    - backend/tests/test_migrations.py
  modified:
    - backend/pyproject.toml

key-decisions:
  - "Document.__init__ aplica default state=RECEBIDO já na instância (antes do flush), não só no INSERT — a UI/state machine lê state antes de persistir"
  - "state persistido pelo valor do enum (native_enum=False, values_callable) — coluna de texto portável SQLite↔Postgres, sem tipo ENUM nativo"
  - "env.py: precedência sqlalchemy.url explícito do ini > Settings.effective_database_url — permite forçar o DB em testes/CI sem tocar Settings"
  - "render_as_batch=True no contexto Alembic — base para ALTER TABLE seguro no SQLite nas migrações futuras (Fase 8 / T-01-07)"
  - "ruff exclui alembic/versions (migrações são artefatos gerados pelo Alembic); env.py mantido lint-clean"

patterns-established:
  - "Todo modelo novo: herdar de Base, usar Mapped/mapped_column, e importar em app/models/__init__"
  - "Toda mudança de schema: nova migração Alembic versionada (nunca create_all em app)"
  - "DocState é a fonte única dos estados de topo; subetapas internas vão em last_completed_step"

requirements-completed: []
requirements-partial: [PROC-01]

# Metrics
duration: 5min
completed: 2026-06-15
---

# Phase 1 Plan 2: Modelos de Domínio e Migrações Alembic Summary

**Modelos de domínio enxutos (Document/Page/AuditLog/Usage) com estado persistido por documento (DocState) e marcador interno de última etapa, mais Alembic desde o dia 1 com a migração 0001 criando todo o schema — versionado e reversível, sem nunca recriar o banco.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-15T22:13:47Z
- **Completed:** 2026-06-15T22:18:19Z
- **Tasks:** 3
- **Files created:** 13 (1 modificado)

## Accomplishments
- `DocState(str, Enum)` com exatamente os 6 estados enxutos de topo (D-04): `RECEBIDO`, `PROCESSANDO`, `EM_REVISAO`, `CONCLUIDO`, `QUARENTENA`, `FALHA` — identificadores sem acento, valores em string para persistência/serialização previsível.
- `Document` carrega o **estado persistido** (`state`, default `RECEBIDO` já na instância), o **marcador interno de última etapa** (`last_completed_step`, nullable — D-05, base de resume/idempotência) e `content_hash` único (referência ao CAS por hash — D-07, base de dedup).
- `Page`/`AuditLog`/`Usage` mínimos com relationships e FKs (`AuditLog.document_id` nullable; cascades configurados) — estrutura de domínio pronta para as fases 2/3/6.
- Alembic inicializado e **wireado à fundação**: `target_metadata = Base.metadata` (com `import app.models` registrando todas as tabelas), URL lida de `get_settings().effective_database_url` (honra `DATABASE_URL`; não hardcoded), `render_as_batch=True` para ALTER TABLE seguro no SQLite (T-01-07).
- Migração `0001_initial.py` (`revision="0001"`, `down_revision=None`) cria as 4 tabelas; `upgrade head`/`downgrade base` fazem round-trip determinístico (T-01-06).
- 12 testes novos (8 de modelos + 4 de migração) provando default state, colunas, metadata, persistência round-trip e schema versionado vindo do Alembic (não de `create_all`). Suíte total: 29 verde; ruff limpo.

## Task Commits

Each task was committed atomically:

1. **Task 1: Modelos de domínio + enum de estados** - `0fc64f4` (feat, inclui testes TDD RED→GREEN)
2. **Task 2: Inicializar Alembic e migração inicial 0001** - `809ba02` (feat)
3. **Task 3: Teste de integração das migrações (round-trip)** - `8e62f62` (test)

## Files Created/Modified
- `backend/app/models/enums.py` - `DocState(str, Enum)` com os 6 estados de topo (D-04).
- `backend/app/models/document.py` - `Document` com `state` (default RECEBIDO), `last_completed_step`, `content_hash` único, timestamps e relationships.
- `backend/app/models/page.py` - `Page` (FK→documents, page_number).
- `backend/app/models/audit_log.py` - `AuditLog` (document_id nullable, action, details, created_at) — base write-ahead da Fase 6.
- `backend/app/models/usage.py` - `Usage` (document_id, step, prompt/completion_tokens) — base da medição da Fase 3.
- `backend/app/models/__init__.py` - importa todos os modelos para registro em `Base.metadata`.
- `backend/alembic.ini` - config; `sqlalchemy.url` vazio (URL injetada por env.py).
- `backend/alembic/env.py` - metadata=Base, URL de Settings, render_as_batch=True.
- `backend/alembic/script.py.mako`, `backend/alembic/README` - scaffold do Alembic.
- `backend/alembic/versions/0001_initial.py` - migração inicial criando documents/pages/audit_log/usage.
- `backend/tests/test_models.py` - 8 testes de modelos/enum/persistência.
- `backend/tests/test_migrations.py` - 4 testes de migração via API do Alembic (sem create_all).
- `backend/pyproject.toml` - ruff `extend-exclude = ["alembic/versions"]` (migrações geradas).

## Decisions Made
- **Default de `state` na instância via `Document.__init__`**: a coluna SQLAlchemy `default` só aplica no flush; a behavior do plano exige que um `Document` recém-instanciado já tenha `state == RECEBIDO` (a state machine/UI lê antes de persistir). Resolvido com `kwargs.setdefault("state", DocState.RECEBIDO)`.
- **`state` persistido pelo valor string** (`native_enum=False` + `values_callable`): coluna de texto portável SQLite↔Postgres, sem depender de tipo ENUM nativo do banco — alinhado à porta aberta para Postgres da 01-01.
- **Precedência de URL no env.py** (ini explícito > Settings): permite que `test_migrations.py` force o banco temporário via `cfg.set_main_option("sqlalchemy.url", ...)` sem mexer em `Settings`, mantendo `DATABASE_URL` como caminho de produção.
- **`ruff extend-exclude alembic/versions`**: migrações são saída gerada pelo Alembic (template/autogenerate); reformatá-las divergiria da ferramenta. `env.py` foi mantido lint-clean manualmente.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Default de `state` não aparecia na instância antes do flush**
- **Found during:** Task 1 (TDD RED)
- **Issue:** A behavior do plano exige `Document(...).state == DocState.RECEBIDO` numa instância recém-criada. O `default=` do `mapped_column` só é aplicado no INSERT/flush, então `state` vinha `None` antes de persistir — o teste de behavior falhou (RED legítimo).
- **Fix:** Adicionado `__init__` em `Document` com `kwargs.setdefault("state", DocState.RECEBIDO)`; `server_default`/`default` mantidos para o INSERT. Comportamento idempotente e sem efeito colateral em estado explícito.
- **Files modified:** backend/app/models/document.py
- **Verification:** 8 testes de modelos verdes.
- **Committed in:** 0fc64f4 (Task 1)

**2. [Rule 3 - Blocking] Lint dos artefatos gerados pelo Alembic**
- **Found during:** Task 2
- **Issue:** `alembic init` e o autogenerate produzem `env.py` e `0001_initial.py` que não passam no ruff configurado (line-length, typing legado nos templates) — bloqueando o critério implícito de suíte/lint limpos da fase.
- **Fix:** `pyproject.toml` ganhou `extend-exclude = ["alembic/versions"]` (migrações são artefatos gerados); `env.py` (código de aplicação que editamos) foi mantido lint-clean ajustando a ordem dos imports. Nenhuma alteração de comportamento.
- **Files modified:** backend/pyproject.toml, backend/alembic/env.py
- **Verification:** `ruff check app/ tests/ alembic/env.py` → All checks passed.
- **Committed in:** 809ba02 (Task 2)

**3. [Rule 1 - Lint] `UP042` em `DocState(str, Enum)`**
- **Found during:** Task 1
- **Issue:** ruff sugere `enum.StrEnum`; o plano especifica explicitamente a forma `(str, Enum)` (ver `<action>` e `key_links.pattern`).
- **Fix:** Honrada a forma explícita do plano com `# noqa: UP042` comentado — `(str, Enum)` dá semântica previsível de `.value` para persistência. Behavior idêntica.
- **Files modified:** backend/app/models/enums.py
- **Committed in:** 0fc64f4 (Task 1)

---

**Total deviations:** 3 auto-fixadas (1 bug de default, 1 bloqueio de lint de artefato gerado, 1 lint honrando a forma explícita do plano)
**Impact on plan:** Nenhuma alteração de escopo ou de critérios de aceite. Todas as behaviors e acceptance_criteria do plano preservados; nenhuma dependência de fases futuras adicionada.

## Issues Encountered
- Nenhum bloqueio. O único ajuste de design (default de `state` na instância) foi capturado como Deviation 1 e validado por teste.

## Known Stubs
Nenhum stub. `AuditLog` e `Usage` são intencionalmente apenas estrutura nesta fase (uso write-ahead na Fase 6; gravação de tokens na Fase 3) — documentado no plano (`modeling_guidance`) e nos docstrings dos modelos; não são stubs que bloqueiem o objetivo da plan.

## User Setup Required
None — nenhuma configuração externa. As migrações rodam com `cd backend && uv run alembic upgrade head` (usa a `DATABASE_URL` da config ou o SQLite default em `data_dir`).

## Next Phase Readiness
- **Plan 01-03 (state machine):** `DocState` e `Document.last_completed_step` prontos; a máquina de estados (D-06, transições válidas/inválidas sem corromper) constrói diretamente sobre estes modelos.
- **Plan 01-04 (CAS):** `Document.content_hash` (único) já é o ponto de ancoragem do conteúdo endereçado por hash (D-07/D-08); falta só o layout de diretórios + cópia imutável.
- **Fase 2+:** schema versionado e migrável garante upgrades sem perda (D-10); `Page`/`AuditLog`/`Usage` dão a estrutura para separação, auditoria/undo e medição de uso.

## Self-Check: PASSED

All 13 declared created files exist on disk; pyproject.toml modified; all 3 task commit hashes (`0fc64f4`, `809ba02`, `8e62f62`) present in git history.

---
*Phase: 01-funda-o-de-estado-e-storage*
*Completed: 2026-06-15*

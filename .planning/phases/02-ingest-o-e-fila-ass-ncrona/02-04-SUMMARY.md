---
phase: 02-ingest-o-e-fila-ass-ncrona
plan: 04
subsystem: api
tags: [watchfiles, fastapi, asyncio, lifespan, sqlite, dedup, hot-folder]

# Dependency graph
requires:
  - phase: 02-01
    provides: "modelos watched_folders, ingested_originals, jobs; documents.origin_original_id"
  - phase: 02-02
    provides: "wait_stable (estabilizador), is_supported_ext/split_pdf (separador), sha256_file (hashing)"
  - phase: 02-03
    provides: "queue.repo.enqueue, queue.worker.run_worker, pipeline.ingest_stage.process_ingest"
provides:
  - "Watcher de pastas (run_watcher): awatch sobre pastas ativas do DB → estabiliza → hash do original → dedup gate → enqueue"
  - "scan_and_enqueue: varredura reusável (startup + /rescan), idempotente por dedup"
  - "Lifespan estendido: sobe watcher+worker como asyncio.Task e encerra limpo no shutdown (preserva check WAL)"
  - "API CRUD /watched-folders com validação/normalização de path (Path.resolve, V5/V12) e unicidade (409)"
  - "API /documents (lista + counts por estado), /documents/duplicates-count, POST /rescan"
affects: [phase-05-frontend, phase-03-extracao]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Watcher supervisor: relê pastas ativas do DB periodicamente e reinicia awatch quando o conjunto de paths muda (reconfiguração em runtime)"
    - "Routers finos por request.app.state.engine + get_session (sem dependência global)"
    - "1 worker uvicorn documentado (watcher/worker como task por processo)"

key-files:
  created:
    - backend/app/ingest/watcher.py
    - backend/app/api/__init__.py
    - backend/app/api/watched_folders.py
    - backend/app/api/documents.py
    - backend/tests/test_api_watched_folders.py
    - backend/tests/test_api_documents.py
  modified:
    - backend/app/main.py
    - backend/tests/test_watcher.py

key-decisions:
  - "Supervisor que relê pastas do DB a cada 5s (vs reinício acoplado à API) para reconfiguração robusta (A5)"
  - "scan_and_enqueue como caminho único compartilhado por startup, rescan e watcher (estabiliza→hash→gate→enqueue)"
  - "Path.resolve() no create/edit normaliza e barra path traversal acidental; v1 sem allowlist de raízes (single-tenant local)"

patterns-established:
  - "Watcher: candidato do awatch é só candidatura → wait_stable antes de qualquer leitura de conteúdo"
  - "Dedup gate no watcher: original já em ingested_originals → incrementa duplicate_hits, não enfileira; UNIQUE da fila cobre re-emissão"
  - "DELETE de pasta preserva Documents (SET NULL) — descadastro nunca apaga histórico"

requirements-completed: [ING-02, ING-06, PROC-02]

# Metrics
duration: 5min
completed: 2026-06-16
---

# Phase 2 Plan 04: Watcher + API de ingestão Summary

**Watcher watchfiles (estabiliza→hash→dedup gate→enqueue) subido no lifespan junto ao worker, mais a API fina de pastas/documentos/rescan que a UI consome — fecha o backend da Fase 2.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-16T01:14:11Z
- **Completed:** 2026-06-16T01:19:29Z
- **Tasks:** 3
- **Files modified:** 8 (6 created, 2 modified)

## Accomplishments
- `run_watcher`: observa as pastas ATIVAS do DB via `awatch`, com supervisor que relê a configuração e reinicia a observação quando as pastas mudam (reconfiguração em runtime — A5); cada candidato passa por estabilização, hash do original (D-09), dedup gate e enqueue.
- `scan_and_enqueue`: caminho determinístico reusável usado no scan inicial do startup e no endpoint `/rescan` — idempotente por dedup (gate + UNIQUE da fila).
- Lifespan estendido em `main.py`: sobe watcher+worker como `asyncio.Task`, encerra ambos limpo (`stop.set()` → cancel → `gather(return_exceptions=True)` → `engine.dispose()`), preservando o check WAL existente; documenta `uvicorn --workers 1` (Pitfall 5 / T-02-12).
- API `/watched-folders` (CRUD) com path normalizado/validado via `Path.resolve()` (V5/V12 — T-02-10), unicidade → 409, path vazio/`..` → 422; DELETE preserva Documents (D-03).
- API `/documents` (lista + counts por estado, com `last_completed_step` para a UI distinguir "Aguardando extração"), `/documents/duplicates-count` (SUM de duplicate_hits, D-10), `POST /rescan`.

## Task Commits

1. **Task 1: Watcher + lifespan watcher/worker** - `7f9e86c` (feat)
2. **Task 2: API CRUD pastas monitoradas (validação de path)** - `5cfe000` (test + fix)
3. **Task 3: API documentos — lista/counts/duplicados/rescan** - `f2d36a3` (test)

_Nota: os routers da API foram criados no commit do Task 1 por serem dependência de import do `main.py`; os respectivos testes vieram nos Tasks 2 e 3._

## Files Created/Modified
- `backend/app/ingest/watcher.py` - run_watcher (awatch + supervisor) + scan_and_enqueue + caminho estabiliza→hash→gate→enqueue
- `backend/app/api/__init__.py` - pacote da API HTTP
- `backend/app/api/watched_folders.py` - CRUD de pastas com Path.resolve() e unicidade (409)
- `backend/app/api/documents.py` - GET /documents (lista+counts), /documents/duplicates-count, POST /rescan
- `backend/app/main.py` - lifespan sobe/derruba watcher+worker; include_router; doc 1-worker
- `backend/tests/test_watcher.py` - scan idempotente, dedup gate, import do app
- `backend/tests/test_api_watched_folders.py` - CRUD + 409 + 422 + DELETE preserva Documents
- `backend/tests/test_api_documents.py` - lista/counts, duplicados, rescan

## Decisions Made
- **Supervisor por polling do DB (5s):** escolhido sobre reinício acoplado à API; desacopla a task do watcher das rotas e tolera add/remove de pastas em runtime (A5). `awatch` fixa paths na construção, então o reinício com novo conjunto é a forma correta.
- **`scan_and_enqueue` como caminho único:** startup, `/rescan` e (via `_handle_changes`) o watcher convergem no mesmo estabiliza→hash→gate→enqueue, garantindo idempotência consistente.
- **Path.resolve() sem allowlist de raízes no v1:** normaliza e barra traversal acidental; allowlist de raízes fica para evolução (single-tenant local, a pasta é escolha do operador).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Constante HTTP 422 deprecada**
- **Found during:** Task 2 (API CRUD de pastas)
- **Issue:** `status.HTTP_422_UNPROCESSABLE_ENTITY` emite `StarletteDeprecationWarning` no Starlette atual; tende a quebrar em versões futuras.
- **Fix:** Trocado para `status.HTTP_422_UNPROCESSABLE_CONTENT` (constante não-deprecada, verificada disponível).
- **Files modified:** backend/app/api/watched_folders.py
- **Verification:** `pytest tests/test_api_watched_folders.py -q` verde, sem warning.
- **Committed in:** 5cfe000 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Correção mínima de forward-compat; sem scope creep.

## Issues Encountered
- **Rotas não aparecem em `app.routes` no FastAPI 0.137:** `include_router` agora produz objetos `_IncludedRouter` resolvidos na build do app (lazy). Verificação ajustada para inspecionar `app.openapi()['paths']`, que confirma `/watched-folders`, `/documents`, `/documents/duplicates-count`, `/rescan` registrados. Comportamento esperado da versão, não um defeito.

## User Setup Required
None - nenhuma configuração de serviço externo exigida por este plano.

## Threat Flags
Nenhuma superfície de segurança nova além da prevista no threat_model do plano (path da pasta tratado com `Path.resolve()` + rejeição — T-02-10; 1 worker documentado — T-02-12).

## Next Phase Readiness
- Backend da Fase 2 fechado: rodando, o sistema monitora pastas reais, estabiliza, deduplica e enfileira; o worker processa até o estado terminal PROCESSANDO + "aguardando_extracao".
- A API é a fronteira pronta para o Plano 05 (frontend): CRUD de pastas, lista de documentos com counts, contador de duplicados e rescan.
- Pré-requisito operacional: rodar `uvicorn app.main:app --workers 1` (documentado em `main.py`).

## Self-Check: PASSED

- All 7 created files present on disk.
- All 3 task commits present in git log (7f9e86c, 5cfe000, f2d36a3).
- Full suite: 115 passed.

---
*Phase: 02-ingest-o-e-fila-ass-ncrona*
*Completed: 2026-06-16*

---
phase: 03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens
plan: 04
subsystem: queue
tags: [worker, dispatch, async-vs-thread, content-hash, sweep, idempotencia, dead-letter, tdd]

# Dependency graph
requires:
  - phase: 03
    plan: 03
    provides: "extract_stage (async, idempotente, commit atômico Extraction+Usage+marcador 'extraido'); EXTRACTED_STEP; ExtractStageResult(called_ai)"
  - phase: 03
    plan: 02
    provides: "openai_client (ExtractionRefused), AsyncOpenAI/Responses API mockada via respx"
  - phase: 02
    provides: "queue.repo (claim_next/schedule_retry/mark_done/mark_failed/enqueue idempotente/requeue_running), worker._run_once/_process_job_blocking/_fail_documents_for_original, ingest_stage.AWAITING_EXTRACTION_STEP"
  - phase: 01
    provides: "state_machine.transition (allowlist PROCESSANDO→FALHA), DocState, Document, Extraction (UNIQUE document_id), get_session"
provides:
  - "Worker bifurcado por step: ingest→to_thread (inalterado); extract→await extract_stage no loop (Pitfall 1 async-vs-thread)"
  - "FALHA por content_hash do bloco (Pitfall 2): _fail_document_for_content_hash + _fail_for_step roteando por step ao esgotar retries"
  - "AuthenticationError não-retryável → dead-letter imediato + FALHA (T-03-14, sem backoff infinito)"
  - "enqueue_pending_extractions: sweep idempotente no startup que enfileira (content_hash,'extract') p/ blocos aguardando_extracao sem Extraction (cobre legados da Fase 2)"
  - "Pipeline ingest→extract completo end-to-end: documento na pasta → ingerido → extraído → Extraction+Usage persistidos → marcador 'extraido'"
affects: [phase-04-templates, phase-05-validacao, phase-07-deterministic]

# Tech tracking
tech-stack:
  added: []
  patterns: ["dispatch bifurcado por step (coroutine no loop vs CPU-bound em to_thread)", "identidade do job de extract = content_hash do bloco (reusa coluna original_hash sem mudar schema)", "variante de FALHA por step roteada de uma só função (_fail_for_step)", "sweep idempotente no startup análogo a requeue_running (UMA vez)", "AuthenticationError como não-retryável → mark_failed direto (não schedule_retry)"]

key-files:
  created:
    - backend/tests/queue/__init__.py
    - backend/tests/queue/conftest.py
    - backend/tests/queue/test_dispatch.py
    - backend/tests/extraction/test_enqueue_sweep.py
  modified:
    - backend/app/queue/worker.py

key-decisions:
  - "extract roda como COROUTINE com await direto no loop do worker (extract_stage abre sessão própria); NUNCA asyncio.to_thread (sem event loop na thread → RuntimeError) nem asyncio.run (já num loop). Só o PyMuPDF interno do stage vai a to_thread (Pitfall 1 / T-03-12)"
  - "Job de extract usa (block.content_hash, 'extract') como chave: o campo da fila chama-se original_hash mas semanticamente é 'identidade do trabalho'; não muda o schema da fila. UNIQUE uq_jobs_hash_step garante 1 job por bloco (Pitfall 2 / T-03-13)"
  - "FALHA roteada por step: ingest→_fail_documents_for_original (por origin_original_id); extract→_fail_document_for_content_hash (achado por content_hash, espelha o existente mas por hash do bloco)"
  - "AuthenticationError (chave OpenAI inválida) é NÃO-retryável (T-03-14): dead-letter IMEDIATO via mark_failed + FALHA no bloco, em vez de backoff que só queimaria tempo/dinheiro sem curar. Re-tentável manualmente após corrigir a chave"
  - "Sweep no startup (Open Question 1) em vez de enqueue inline no ingest: repo.enqueue comita por si, e enfileirar dentro do ingest quebraria o commit único atômico do ingest_stage. O sweep (análogo a requeue_running) roda UMA vez, é idempotente e cobre os legados da Fase 2 sem tocar a atomicidade"

patterns-established:
  - "Dispatch async-vs-thread: _dispatch decide por step se o trabalho é coroutine (await no loop) ou CPU/IO-bound (to_thread); reusa TODO o esqueleto claim/retry/backoff/dead-letter da Fase 2"
  - "Sweep idempotente no startup: select dos Documents prontos sem Extraction (subquery NOT IN join Extraction) → repo.enqueue (no-op se já existe); conta só jobs novos criados"
  - "Teste de fila que toca a IA: conftest local em tests/queue/ reexpõe um respx MockRouter de /v1/responses (o mock_openai de tests/extraction/ está fora de escopo)"

requirements-completed: [EXT-02, USE-02]

# Metrics
duration: 12min
completed: 2026-06-16
---

# Phase 3 Plan 04: Wiring da Extração na Fila/Worker Summary

**Costurou o último elo da Fase 3: o worker agora bifurca o dispatch por `step` — `ingest` continua via `asyncio.to_thread` (CPU/IO-bound, inalterado) e `extract` roda como COROUTINE com `await extract_stage(...)` direto no loop (Pitfall 1 async-vs-thread; só o PyMuPDF interno vai a thread) — roteia a FALHA por `content_hash` do bloco ao esgotar retries (Pitfall 2; a chave do job de extract é o hash do bloco, não do original), trata `AuthenticationError` como não-retryável (dead-letter imediato em vez de backoff infinito, T-03-14) e enfileira os jobs de `extract` via um sweep idempotente no startup (`enqueue_pending_extractions`, análogo a `requeue_running`) que cobre inclusive os Documents legados que a Fase 2 deixou em `aguardando_extracao`. Com isso o pipeline ingest→extract fica completo end-to-end: documento colocado na pasta é ingerido, extraído (texto/visão), `Extraction`+`Usage` persistidos e o marcador `"extraido"` avançado. Provado por 7 testes (3 dispatch + 4 sweep), OpenAI mockada (0 token), sem regressão na suíte (170 passed).**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-16
- **Completed:** 2026-06-16
- **Tasks:** 2 completed (ambas TDD RED→GREEN)
- **Files created:** 4 (1 conftest + 1 __init__ + 2 testes); **modified:** 1 (`worker.py`)

## Accomplishments

- **Dispatch bifurcado por step (Task 1 / Pitfall 1 / T-03-12):** `_run_once` agora chama `_dispatch(engine, step=..., original_hash=..., payload=...)`, que decide: `extract` → `await extract_stage(session, content_hash=original_hash)` numa sessão própria, no loop (a chamada OpenAI é o ponto async; NUNCA `to_thread`, NUNCA `asyncio.run`); qualquer outro step (`ingest`) → `await asyncio.to_thread(_process_job_blocking, ...)` como na Fase 2 (inalterado). Todo o esqueleto `except → schedule_retry → (esgotou) → FALHA → mark_done` foi preservado; recusa/erro do `extract_stage` (`ExtractionRefused`, `fitz.FileDataError`, rede) cai no mesmo caminho de retry/backoff (D-08).
- **FALHA por content_hash do bloco (Task 1 / Pitfall 2 / T-03-13):** nova `_fail_document_for_content_hash(engine, content_hash)` acha o `Document` por `content_hash` e usa `transition(session, doc, DocState.FALHA)` (allowlist PROCESSANDO→FALHA existe) — espelha `_fail_documents_for_original` mas pela identidade do bloco. `_fail_for_step` roteia a variante correta por step ao esgotar retries (`ingest`→original; `extract`→content_hash). O original é preservado no CAS; a FALHA é re-tentável (allowlist FALHA→PROCESSANDO).
- **AuthenticationError não-retryável (Task 1 / T-03-14):** chave OpenAI inválida não cura com backoff — só queima tempo/dinheiro. O worker captura `openai.AuthenticationError` ANTES do `except Exception` genérico e faz dead-letter IMEDIATO (`repo.mark_failed`, não `schedule_retry`) + FALHA no bloco. Log só metadados (`job_id`/`step`), nunca a chave nem o conteúdo (T-03-15). Re-tentável manualmente após corrigir a chave.
- **Sweep idempotente no startup (Task 2 / Open Question 1):** `enqueue_pending_extractions(session)` seleciona Documents em `PROCESSANDO` + `last_completed_step=="aguardando_extracao"` que ainda NÃO têm `Extraction` (subquery `NOT IN` join Extraction) e, para cada, `repo.enqueue(original_hash=content_hash, step="extract", payload={"content_hash": ...})`. Chamado UMA vez no startup de `run_worker` (junto ao `requeue_running`). Idempotente: `repo.enqueue` é no-op para `(content_hash,"extract")` já existente (UNIQUE `uq_jobs_hash_step`); conta só jobs novos. Cobre os Documents legados da Fase 2 sem tocar a atomicidade do `ingest_stage` (enfileirar inline quebraria o commit único, pois `repo.enqueue` comita).

## Task Commits

Cada task seguiu o ciclo TDD RED → GREEN, commitada atomicamente:

1. **Task 1: dispatch bifurcado + FALHA por content_hash** — `d6055d6` (test, RED) → `137cbb3` (feat, GREEN)
2. **Task 2: sweep idempotente de enqueue de extract** — `cd916c5` (test, RED) → `a04ffd2` (feat, GREEN)

## Files Created

- `backend/tests/queue/__init__.py` — pacote de testes da fila (novo diretório)
- `backend/tests/queue/conftest.py` — `mock_openai` local (respx `/v1/responses`); o de `tests/extraction/` está fora de escopo de `tests/queue/`
- `backend/tests/queue/test_dispatch.py` — 3 testes (extract→stage+done; extract esgota→FALHA por content_hash; ingest inalterado)
- `backend/tests/extraction/test_enqueue_sweep.py` — 4 testes (enfileira pendentes; idempotente 2x; ignora já-extraído; ignora estado errado)

## Files Modified

- `backend/app/queue/worker.py` — `_dispatch` (bifurcação por step), `_fail_document_for_content_hash`, `_fail_for_step`, tratamento de `AuthenticationError`, `enqueue_pending_extractions` (sweep) + chamada no startup de `run_worker`

## Verification Evidence

- `uv run pytest tests/queue/test_dispatch.py tests/test_queue.py -x -q` → 15 passed (3 novos dispatch + 12 da suíte de fila da Fase 2, sem regressão no ingest)
- `uv run pytest tests/extraction/test_enqueue_sweep.py -x -q` → 4 passed
- `uv run pytest tests/queue tests/extraction -q` → 47 passed
- `uv run pytest -q` (suíte completa do backend) → **170 passed**, sem regressões (+7 testes vs. Plan 03)
- `uv run ruff check app/queue/worker.py tests/queue/ tests/extraction/test_enqueue_sweep.py` → All checks passed
- Nenhum teste gasta token (respx mocka `POST /v1/responses`); o caminho extract é exercitado como coroutine async (não to_thread), provando o Pitfall 1

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `respx.mock` exigia rota chamada no teste de FALHA**
- **Found during:** Task 1
- **Issue:** O teste `test_dispatch_extract_esgota_retries...` monkeypatcha `extract_stage` para falhar ANTES de tocar a IA, mas a fixture `mock_openai` (via `respx.mock`) assere no exit que todas as rotas registradas foram chamadas — quebrando com "some routes were not called".
- **Fix:** Remover `mock_openai` desse teste (o caminho de FALHA não depende de tocar a OpenAI — vira asserção positiva de que a IA não é necessária para a FALHA).
- **Files modified:** `backend/tests/queue/test_dispatch.py`
- **Commit:** `137cbb3`

_Ajustes menores de lint (import sort em `worker.py` e nos testes; `except AuthenticationError as exc` → `except AuthenticationError` por `exc` não-usado) aplicados antes dos commits._

## Known Stubs

Nenhum. Este plan fecha a Fase 3: o wiring está completo e o pipeline ingest→extract roda end-to-end. O que vem depois é a Fase 4 (templates dirigindo a extração) — por desenho do roadmap, não stub.

## Threat Flags

Nenhuma surface nova além do `<threat_model>` do plano. T-03-12 (await em to_thread → RuntimeError) mitigado: extract roda como coroutine no loop, provado por `test_dispatch_extract_chama_stage_e_marca_done` (`call_count==1`). T-03-13 (colisão de idempotência entre blocos) mitigado: chave `(content_hash,"extract")` + UNIQUE, provado por `test_sweep_idempotente`. T-03-14 (chave inválida → retry caro infinito) mitigado: `AuthenticationError` → dead-letter imediato. T-03-15 (log de chave/conteúdo) mitigado: log só `job_id`/`step`/`content_hash`/motivo.

## Notas para a Fase 4 (templates)

- **Seam D-03 (`router.choose`)** é onde a Fase 4 pluga o atalho local custo-zero quando um template casa (sem mudar o motor genérico). O wiring da fila já está pronto: basta o `extract_stage`/router decidir a rota.
- **Re-extração após template:** re-despachar um job de extract continua idempotente (`extract_stage` é no-op se `Extraction` já existe). Para FORÇAR re-extração (ex.: template mudou), a Fase 4 precisará de uma política de invalidação da `Extraction` antes de re-enfileirar — fora do escopo desta fase.

## Self-Check: PASSED

Os 5 artefatos-chave (4 criados + `worker.py` modificado) existem em disco e os 4 commits de tarefa (`d6055d6`, `137cbb3`, `cd916c5`, `a04ffd2`) estão presentes no histórico git.

---
phase: 02-ingest-o-e-fila-ass-ncrona
plan: 03
subsystem: infra
tags: [sqlite, queue, asyncio, worker, backoff, dedup, pikepdf, idempotency, cas]

requires:
  - phase: 01-foundation
    provides: "CAS (cas.store), máquina de estados (transition/mark_step), modelos Document/Job/IngestedOriginal, camada de banco (get_session)"
  - phase: 02-01
    provides: "schema da Fase 2 — jobs (UNIQUE hash+step), ingested_originals (original_hash unique), documents.origin_original_id"
  - phase: 02-02
    provides: "split_pdf/is_supported_ext (separador pikepdf + allowlist), tunables de fila em get_settings()"
provides:
  - "Repositório de fila SQLite com claim atômico (UPDATE...RETURNING), backoff exponencial+jitter, dead-letter e resume (PROC-02)"
  - "ingest_stage.process_ingest: dedup gate pré-split → store → split → 1 Document/bloco em estado terminal 'aguardando_extracao' (ING-04/ING-06/PROC-03)"
  - "Worker async (run_worker) com resume no startup, split via asyncio.to_thread, mark_done/backoff/FALHA; _run_once testável"
  - "sha256_file (hashing por streaming) — identidade do original"
affects: [02-04-watcher-lifespan, 02-05-ui-status, 03-extracao]

tech-stack:
  added: []
  patterns:
    - "Claim atômico single-writer via UPDATE...WHERE id=(SELECT...LIMIT 1) RETURNING (SQLite ≥3.35)"
    - "Backoff exponencial+jitter com dead-letter→FALHA (Pattern 2)"
    - "Gate de dedup pré-split sobre ingested_originals (Pattern 3)"
    - "Trabalho CPU/IO-bound (split) despachado em asyncio.to_thread com sessão própria por thread (Pitfall 4)"
    - "_run_once: corpo do loop refatorado em função testável (evita await infinito em teste)"

key-files:
  created:
    - backend/app/queue/__init__.py
    - backend/app/queue/repo.py
    - backend/app/queue/worker.py
    - backend/app/pipeline/ingest_stage.py
    - backend/app/ingest/hashing.py
  modified:
    - backend/tests/test_queue.py
    - backend/tests/test_dedup_gate.py
    - backend/tests/test_ingest_stage.py
    - backend/tests/conftest.py

key-decisions:
  - "claim_next compara next_run_at contra um :now bind-ado em Python (não CURRENT_TIMESTAMP do SQLite) — evita mismatch de formato tz-aware (microssegundos+offset) vs segundos que impedia reivindicar jobs devidos agora"
  - "Bloco escrito em temp no volume de data_dir e cas.store-ado (A4 — menor risco, store é idempotente); imagem = 1 bloco = o próprio arquivo (D-07)"
  - "Worker despacha process_ingest inteiro via to_thread com sessão própria (sessões SQLAlchemy não cruzam threads); claim/mark ficam na coroutine"
  - "Documents do original vão a FALHA sempre via transition (allowlist), nunca state direto; tolerante a estados sem aresta para FALHA"

patterns-established:
  - "Fila durável in-process: repo de funções de módulo atrás de fronteira única (estilo cas.py)"
  - "Estado terminal da Fase 2: PROCESSANDO + last_completed_step='aguardando_extracao', constante AWAITING_EXTRACTION_STEP, NUNCA CONCLUIDO (Pitfall 6)"

requirements-completed: [ING-04, ING-06, PROC-02, PROC-03]

duration: 18min
completed: 2026-06-16
---

# Phase 2 Plan 03: Núcleo idempotente — fila SQLite + worker + ingest_stage Summary

**Fila SQLite com claim atômico (UPDATE...RETURNING) + backoff/jitter + resume, e ingest_stage que faz dedup gate pré-split → store → split em 1 Document/bloco no estado terminal "aguardando extração", orquestrado por um worker async que despacha o split em asyncio.to_thread.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-16T01:03:00Z
- **Completed:** 2026-06-16T01:21:00Z
- **Tasks:** 3 (todos TDD: RED→GREEN)
- **Files modified:** 9 (5 criados, 4 modificados)

## Accomplishments
- `app/queue/repo.py`: enqueue idempotente (UNIQUE hash+step), `claim_next` atômico single-writer via `UPDATE...RETURNING`, `schedule_retry` com backoff exponencial+jitter e dead-letter, `mark_done`/`mark_failed`, `requeue_running` (resume após crash)
- `app/pipeline/ingest_stage.py`: `process_ingest` orquestra allowlist (ING-04) → gate de dedup pré-split (D-09/D-10) → store do original (D-07) → split → 1 `Document`/bloco em PROCESSANDO + `aguardando_extracao` (nunca CONCLUIDO); reprocesso idempotente por content_hash único do bloco
- `app/queue/worker.py`: `run_worker` faz resume no startup, loop poll→claim→processa→done/backoff até `stop`; split em `asyncio.to_thread`; ao esgotar tentativas, Documents do original vão a FALHA via `transition`
- Suite inteira verde: 99 passed, 1 skipped (stub Wave 0 não relacionado)

## Task Commits

1. **Task 1: Repositório de fila (enqueue/claim/backoff/resume)** — `fe3ef18` (feat, TDD RED+GREEN)
2. **Task 2: ingest_stage (dedup gate/store/split/Documents/terminal)** — `ace0265` (feat, TDD RED+GREEN)
3. **Task 3: Worker async (resume/to_thread/done/FALHA)** — `c0d62bb` (feat, TDD RED+GREEN)

_Tasks TDD foram commitadas como RED+GREEN combinados por task (testes + implementação juntos), cada uma verificada a verde antes do commit._

## Files Created/Modified
- `backend/app/queue/__init__.py` — pacote da fila (vazio)
- `backend/app/queue/repo.py` — repositório da fila: claim atômico, backoff, resume
- `backend/app/queue/worker.py` — worker async: loop poll→claim→processa→done/backoff, resume, to_thread
- `backend/app/pipeline/ingest_stage.py` — orquestração gate→store→split→Documents→terminal
- `backend/app/ingest/hashing.py` — `sha256_file` (streaming) para identidade do original
- `backend/tests/test_queue.py` — testes do repo (idempotência/claim/backoff/resume) + worker (done/falha→FALHA)
- `backend/tests/test_dedup_gate.py` — dedup pré-split (duplicate_hits, sem Documents novos)
- `backend/tests/test_ingest_stage.py` — allowlist, estado terminal, split N, imagem=1
- `backend/tests/conftest.py` — fixture `data_dir` compartilhada (isola o CAS por teste)

## Decisions Made
- **Bind de `:now` no claim:** o SQLAlchemy persiste datetimes tz-aware como `...+00:00` com microssegundos, enquanto `CURRENT_TIMESTAMP` do SQLite rende segundos sem offset — a comparação lexicográfica entre os dois era incorreta e impedia reivindicar jobs devidos "agora". Bind-amos o mesmo `_utcnow()` usado em enqueue/schedule_retry, mantendo ambos os lados no formato de armazenamento idêntico.
- **Worker dispatcha `process_ingest` inteiro em `to_thread` com sessão própria:** sessões SQLAlchemy não cruzam threads; o claim/mark permanecem na coroutine; o trabalho pesado (split + escritas) roda na thread.
- **`sha256_file` adicionado** (não previsto explicitamente como arquivo, mas necessário): o worker recebe `original_hash` no Job, mas os testes precisam computar o hash para enfileirar com o valor correto; helper de streaming reusável e alinhado ao CAS.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] claim_next nunca reivindicava jobs devidos por mismatch de timestamp**
- **Found during:** Task 1 (testes do claim falharam — `claim_next` retornava None com job enfileirado agora)
- **Issue:** `next_run_at <= CURRENT_TIMESTAMP` comparava `2026-06-16 01:05:21.283470+00:00` (formato do SQLAlchemy para datetime tz-aware) contra `2026-06-16 01:05:21` (segundos, sem offset) lexicograficamente — o job devido "agora" ficava ~1s preso e o resume não via nada em running.
- **Fix:** Bind-ar `:now = _utcnow()` no UPDATE em vez de `CURRENT_TIMESTAMP`, alinhando ambos os lados ao formato de armazenamento.
- **Files modified:** backend/app/queue/repo.py
- **Verification:** test_claim_atomico/test_backoff/test_resume_on_startup passam.
- **Committed in:** `fe3ef18` (Task 1 commit)

**2. [Rule 3 - Blocking] Helper sha256_file ausente (necessário para identidade do original nos testes/worker)**
- **Found during:** Task 1 (testes do worker precisavam computar o original_hash do PDF)
- **Issue:** Não havia utilitário de hash de arquivo fora do CAS; duplicá-lo com hashlib em cada teste seria frágil.
- **Fix:** Criado `app/ingest/hashing.py` com `sha256_file` por streaming (64 KiB), alinhado ao CAS.
- **Files modified:** backend/app/ingest/hashing.py
- **Verification:** imports OK; usado por test_queue/test_dedup_gate/test_ingest_stage.
- **Committed in:** `fe3ef18` (Task 1 commit)

**3. [Rule 1 - Bug de teste] PDFs de teste com páginas idênticas eram deduplicados pelo CAS**
- **Found during:** Task 2 (split de 5 páginas gerava 2 Documents em vez de 3)
- **Issue:** `pikepdf.add_blank_page` cria páginas byte-idênticas; cada bloco de 1 página tinha o MESMO content_hash → o CAS deduplicava e o ingest_stage (corretamente) tratava como bloco repetido. Era artefato do fixture, não bug de produção (documentos reais diferem por página).
- **Fix:** Helper `_make_pdf` passou a injetar um content stream único por página (`(pagina N)`), gerando blocos byte-distintos.
- **Files modified:** backend/tests/test_queue.py, test_dedup_gate.py, test_ingest_stage.py
- **Verification:** test_split_multipagina_cria_n_documentos e test_terminal_state passam com N esperado.
- **Committed in:** `ace0265` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** Todos necessários para correção. O bug do claim era crítico (a fila não funcionaria); o helper de hash e a correção do fixture viabilizaram a verificação. Sem scope creep.

## Issues Encountered
- A constante terminal `AWAITING_EXTRACTION_STEP="aguardando_extracao"` é exportada de `ingest_stage` para consumo da UI (Plano 05) via API.

## User Setup Required
None - nenhuma configuração de serviço externo.

## Next Phase Readiness
- **Pronto para 02-04 (watcher + lifespan):** `enqueue` (carregar `original_hash` + payload), `run_worker(engine, stop)` para `asyncio.create_task` no lifespan, e `_run_once` testável. O worker já faz resume e encerra limpo no `stop` Event.
- **Requisito operacional:** rodar uvicorn com **1 worker** (single-writer SQLite, D-11) — documentado na pesquisa (A3) e em CLAUDE.md; com >1 worker uvicorn haveria duplicação de watcher/worker.
- **Contrato para UI (Plano 05):** Documents terminam em PROCESSANDO + `aguardando_extracao`; a contagem de duplicados vem de `ingested_originals.duplicate_hits`.

---
*Phase: 02-ingest-o-e-fila-ass-ncrona*
*Completed: 2026-06-16*

## Self-Check: PASSED

- Arquivos criados verificados: queue/__init__.py, queue/repo.py, queue/worker.py, pipeline/ingest_stage.py, ingest/hashing.py — todos presentes.
- Commits verificados: fe3ef18, ace0265, c0d62bb — todos presentes no histórico.
- Suite completa: 99 passed, 1 skipped (stub Wave 0 não relacionado); ruff limpo.

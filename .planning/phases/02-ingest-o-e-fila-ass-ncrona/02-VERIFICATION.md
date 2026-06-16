---
phase: 02-ingest-o-e-fila-ass-ncrona
verified: 2026-06-16T05:30:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Verificação visual end-to-end (PLAN 02-05 Task 3)"
    expected: |
      1. Subir backend + frontend. Em Configurações → Pastas monitoradas, adicionar pasta real → aparece na lista.
      2. Copiar PDF multi-página para a pasta. Editar para 'Separar a cada 1 página' e copiar outro PDF.
      3. Na tela Documentos: documentos entram na fila e mudam de estado por polling (Na fila → Processando → Aguardando extração) SEM flicker da tabela. Nenhum aparece como 'Tratado'/'Concluído' (verde).
      4. PDF separado vira N documentos independentes (1 por página).
      5. Copiar o MESMO PDF novamente: nenhum duplicado na lista; contador 'N duplicados ignorados' (neutro, rodapé) incrementa.
      6. Remover pasta: diálogo destrutivo aparece; documentos já ingeridos PERMANECEM.
      7. Parar backend: mensagem de erro com 'Tentar novamente' aparece dentro do card; reiniciar: recuperação.
    why_human: "Comportamento visual, polling sem flicker, estados visuais, confirmação destrutiva, feedback de erro — não verificáveis por grep/static analysis."
---

# Phase 2: Ingestão e Fila Assíncrona — Verification Report

**Phase Goal:** O usuário configura, pela interface, uma ou mais pastas monitoradas (cada uma com sua regra de separação de páginas) e cada arquivo colocado nelas entra numa fila assíncrona idempotente que nunca reprocessa nem cobra duas vezes o mesmo arquivo. Ingestão é exclusivamente por pasta monitorada no v1.
**Verified:** 2026-06-16T05:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Success Criteria do ROADMAP)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | O usuário configura pela interface uma ou mais pastas monitoradas (caminho + páginas por bloco) e vê os documentos entrando na fila com seu estado | VERIFIED (parcial — backend verificado; UI visual requer humano) | `app/api/watched_folders.py`: CRUD completo com `GET /watched-folders`, `POST`, `PATCH`, `DELETE`. `app/api/documents.py`: `GET /documents` com `counts` por estado e `last_completed_step`. Frontend: `useWatchedFolders` + `useDocuments` + `StatusPill` fiados. 10 testes API de pastas + 6 testes de documentos passando. |
| 2 | Arquivos colocados na pasta monitorada são processados automaticamente apenas após estarem estáveis (arquivo parcialmente escrito não é processado) | VERIFIED | `app/ingest/stabilizer.py`: `async def wait_stable` implementa loop de quiescência `(st_size, st_mtime_ns)` + lock-test ao fim. `app/ingest/watcher.py:110`: `await wait_stable(file_path)` antes de qualquer hash/enqueue. 5 testes em `test_stabilizer.py`: estável/removido/remoção-durante-espera/reinício-em-escrita-incremental/config-global — todos passando. |
| 3 | Um documento multi-página é separado em blocos pela quantidade de páginas configurada na pasta, e cada bloco vira um documento independente no pipeline | VERIFIED | `app/ingest/splitter.py`: `split_pdf` produz `ceil(M/N)` blocos. `app/pipeline/ingest_stage.py:134–176`: cada bloco → `cas.store` → `Document(content_hash=..., origin_original_id=...)` em PROCESSANDO + `"aguardando_extracao"`. `test_split_multipagina_cria_n_documentos`: 5 páginas/bloco=2 → 3 Documents com `origin_original_id` setado. 8 testes de splitter passando (incluindo `test_no_split`, `test_blocos_sao_pdfs_validos`). |
| 4 | Enviar o mesmo arquivo duas vezes é detectado por hash e não gera reprocessamento nem cobrança dupla, mesmo após retry/crash da fila (com visibilidade de duplicados ignorados na interface) | VERIFIED | Gate de dedup em `ingest_stage.py:108–116` e em `watcher.py:126–135`. Atomicidade CR-02: única transação em `process_ingest` — crash antes do `session.commit()` final faz rollback total; gate nunca vê original meio-criado. `test_resume_apos_crash_no_meio_dos_blocos_nao_perde_nem_duplica` prova isso diretamente. `test_dedup_gate_segunda_ingestao_nao_cria_documentos`: 2ª ingestão → 0 novos Documents, `duplicate_hits=1`. `GET /documents/duplicates-count` expõe `SUM(duplicate_hits)`. Frontend: `useDuplicatesCount` + exibição neutra no rodapé da tabela. `test_scan_is_idempotent` e `test_scan_increments_duplicate_hits_when_already_ingested` passando. |

**Score:** 4/4 truths verified (com caveat de verificação visual humana no SC-1)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/models/watched_folder.py` | Config de pasta monitorada (path + pages_per_block + active) | VERIFIED | Classe `WatchedFolder`, `path unique`, `pages_per_block nullable`, `active default True`. |
| `backend/app/models/ingested_original.py` | Gate de dedup com `original_hash unique` | VERIFIED | `original_hash String(64) unique index`, `duplicate_hits int default 0`, `block_count`. |
| `backend/app/models/job.py` | Modelo Job com `UNIQUE(original_hash, step)` | VERIFIED | `UniqueConstraint("original_hash", "step", name="uq_jobs_hash_step")`. JobStatus enum: pending/running/done/failed. |
| `backend/alembic/versions/0002_ingestion.py` | Migração das 3 tabelas + `origin_original_id` | VERIFIED | `down_revision = '0001'`. 8 testes de migração passando, incluindo round-trip up/down/up e trigger `updated_at`. |
| `backend/app/ingest/stabilizer.py` | Quiescência size/mtime + lock-test | VERIFIED | `async def wait_stable` — loop sobre `(st_size, st_mtime_ns)`, reinicia em mudança, lock-test ao fim, retorna False em FileNotFoundError/OSError. |
| `backend/app/ingest/splitter.py` | Separação de PDF por N páginas via pikepdf | VERIFIED | `def split_pdf` → `ceil(M/N)` blocos; None/0 = 1 bloco; try/except `pikepdf.PdfError` → ValueError controlado. `SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}`. |
| `backend/app/queue/repo.py` | enqueue/claim_next/mark_done/schedule_retry/mark_failed/requeue_running | VERIFIED | Claim atômico via `UPDATE ... RETURNING` (linha 111). Backoff exponencial+jitter em `schedule_retry`. `requeue_running` reverte running→pending. `enqueue` captura `IntegrityError` para idempotência. |
| `backend/app/queue/worker.py` | Loop async poll→claim→process→backoff | VERIFIED | `async def run_worker(engine, stop)`. `requeue_running` no startup (linha 152). `await asyncio.to_thread(...)` para split CPU-bound (linha 117). Encerra limpo em `stop.is_set()`. |
| `backend/app/pipeline/ingest_stage.py` | Orquestração gate→store→split→Documents→terminal | VERIFIED | `def process_ingest`: gate dedup (passso 2), store original (3), split (5), Documents em PROCESSANDO+"aguardando_extracao" (6), commit único (7). `AWAITING_EXTRACTION_STEP = "aguardando_extracao"`. NUNCA marca CONCLUIDO. |
| `backend/app/ingest/watcher.py` | run_watcher: awatch sobre paths do DB → estabiliza → dedup gate → enqueue | VERIFIED | `async def run_watcher`. Supervisor relê DB a cada 5s para reconfiguração. `scan_and_enqueue` reutilizável para rescan. Scan inicial no startup. |
| `backend/app/api/watched_folders.py` | CRUD de pastas com validação de path | VERIFIED | `_normalize_path`: rejeita vazio, symlink, arquivo não-diretório. `resolve()` normaliza. 409 em duplicata. DELETE preserva Documents (FK SET NULL). |
| `backend/app/api/documents.py` | GET /documents, GET /documents/duplicates-count, POST /rescan | VERIFIED | `GET /documents` com items + counts por estado + `last_completed_step`. `GET /documents/duplicates-count` → SUM(duplicate_hits). `POST /rescan` → `scan_and_enqueue`. |
| `backend/app/main.py` | Lifespan sobe watcher+worker + inclui routers | VERIFIED | `asyncio.create_task(run_watcher(...))` + `run_worker(...)`. `stop.set()` + cancel + gather no finally. WAL check preservado. `include_router` para watched_folders e documents. |
| `frontend/src/lib/api.ts` | Cliente fetch tipado | VERIFIED | `getDocuments`, `getDuplicatesCount`, `getWatchedFolders`, `createWatchedFolder`, `updateWatchedFolder`, `deleteWatchedFolder`, `postRescan`. Lança `ApiError` em `!res.ok`. |
| `frontend/src/hooks/useDocuments.ts` | Hook TanStack Query com polling | VERIFIED | `refetchInterval: 4000`, `refetchIntervalInBackground: false`, `placeholderData: keepPreviousData`. `useRescan` invalida `['documents']`. |
| `frontend/src/hooks/useWatchedFolders.ts` | Hook TanStack Query CRUD pastas | VERIFIED | `useWatchedFolders`, `useCreateFolder`, `useUpdateFolder`, `useDeleteFolder` — cada mutation invalida `['watched-folders']`. |
| `frontend/src/components/StatusPill.tsx` | Pílula mapeando estados de domínio reais | VERIFIED | Mapeia todos os 6 estados. Caso especial: `processando + "aguardando_extracao"` → label "Aguardando extração", token `encontrado` (nunca verde). |
| `frontend/src/main.tsx` | QueryClientProvider wrapping App | VERIFIED | `<QueryClientProvider client={queryClient}><App /></QueryClientProvider>` dentro de `<StrictMode>`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/models/__init__.py` | Job, IngestedOriginal, WatchedFolder | imports + registro Base.metadata | VERIFIED | Todos os 3 modelos + JobStatus importados e disponíveis. |
| `alembic/versions/0002_ingestion.py` | `0001` | `down_revision = '0001'` | VERIFIED | Confirmado no arquivo linha 1 do cabeçalho. |
| `app/pipeline/ingest_stage.py` | `ingested_originals` (gate D-09) | SELECT por `original_hash` antes do split | VERIFIED | Linhas 108–116: SELECT + retorno "duplicate" se existe. Atomicidade: sem commit por bloco. |
| `app/pipeline/ingest_stage.py` | estado PROCESSANDO + marcador | set em memória, commit único | VERIFIED | Linhas 164–171: `state=DocState.PROCESSANDO, last_completed_step=AWAITING_EXTRACTION_STEP`. Não usa `transition` dentro do loop (preserva atomicidade). |
| `app/queue/repo.py` | `jobs (UPDATE ... RETURNING)` | claim atômico single-writer | VERIFIED | Linha 98–115: `UPDATE ... WHERE id=(SELECT ... LIMIT 1) RETURNING ...`. |
| `app/main.py` | `run_watcher + run_worker` | `asyncio.create_task` no lifespan | VERIFIED | Linhas 57–58: `create_task(run_watcher(...))` e `create_task(run_worker(...))` com mesmo `stop` Event. |
| `app/ingest/watcher.py` | `app.queue.repo.enqueue` | candidato estável → hash → gate → enqueue | VERIFIED | Linha 144: `repo.enqueue(session, original_hash=..., step="ingest", payload=...)`. |
| `app/api/watched_folders.py` | `watched_folders (DB)` | `Path.resolve()` + persiste | VERIFIED | `_normalize_path` (linha 43–81): resolve + rejeita symlink/arquivo. `folder.path = resolved`. |
| `frontend/src/pages/DocumentsPage.tsx` | `useDocuments` (GET /documents) | hook de polling TanStack Query | VERIFIED | Linha 55: `useDocuments()`. Confirmado ausência de mock `DOCS`. |
| `frontend/src/pages/ConfigPage.tsx` | `useWatchedFolders` (CRUD /watched-folders) | hook TanStack Query + mutations | VERIFIED | Linha 8–11: imports `useCreateFolder, useDeleteFolder, useUpdateFolder, useWatchedFolders`. |
| `frontend/src/main.tsx` | `QueryClientProvider` | wrap do App | VERIFIED | Linha 11: `<QueryClientProvider client={queryClient}>`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `DocumentsPage.tsx` | `docsQuery.data` | `useDocuments()` → `GET /documents` → SQLAlchemy query sobre `Document` + joins | Sim: query real `select(Document, WatchedFolder.path).outerjoin(...)` | FLOWING |
| `ConfigPage.tsx` (PastasTab) | `useWatchedFolders().data` | `GET /watched-folders` → `select(WatchedFolder)` | Sim: query real sobre tabela `watched_folders` | FLOWING |
| `DocumentsPage.tsx` (contador duplicados) | `dupQuery.data?.count` | `useDuplicatesCount()` → `GET /documents/duplicates-count` → `SUM(duplicate_hits)` | Sim: `func.coalesce(func.sum(IngestedOriginal.duplicate_hits), 0)` | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Suite completa de testes | `cd backend && .venv/bin/python -m pytest tests/ -q` | 121 passed, 12 warnings in 9.08s | PASS |
| watchfiles + pikepdf importáveis | `.venv/bin/python -c "import watchfiles, pikepdf; print(watchfiles.__version__, pikepdf.__version__)"` | `1.2.0 10.8.0` | PASS |
| Modelos importáveis com constraints | `.venv/bin/python -c "from app.models import Job, IngestedOriginal, WatchedFolder, JobStatus; from app.models.document import Document; assert hasattr(Document, 'origin_original_id')"` | OK | PASS |
| down_revision correto em migração | `grep -E "down_revision.*['\"]0001['\"]" alembic/versions/0002_ingestion.py` | `down_revision: Union[str, Sequence[str], None] = '0001'` | PASS |
| UniqueConstraint no job | `grep -q "uq_jobs_hash_step" app/models/job.py` | presente | PASS |
| RETURNING no claim | `grep -q "RETURNING" app/queue/repo.py` | presente (linha 111) | PASS |
| requeue_running no worker | `grep -q "requeue_running" app/queue/worker.py` | presente (linha 152) | PASS |
| asyncio.to_thread no worker | `grep -q "asyncio.to_thread" app/queue/worker.py` | presente (linha 117) | PASS |
| Ausência de CONCLUIDO em ingest_stage/queue | `grep -rn "DocState.CONCLUIDO" app/queue/ app/pipeline/ingest_stage.py` | 0 ocorrências funcionais (só comentários/docstrings) | PASS |
| Frontend build de produção | `cd frontend && npm run build` | 121 módulos transformados, exit 0 | PASS |
| TanStack Query no package.json | `grep "@tanstack/react-query" package.json` | `"@tanstack/react-query"` presente | PASS |
| Mock DOCS ausente em DocumentsPage | `grep -q "DOCS" src/pages/DocumentsPage.tsx` | DOCS mock ausente | PASS |
| Tipos de domínio reais em types.ts | ausência de `'encontrado'\|'leitura'\|'tratado'\|'erro'` como DocState | tipos mock substituídos por DocState real | PASS |

### Probe Execution

Não há probes convencionais `scripts/*/tests/probe-*.sh` neste projeto. Step 7c: SKIPPED (sem probes declarados).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ING-02 | 02-02, 02-04, 02-05 | Processamento automático por pasta monitorada, só após arquivo estável; múltiplas pastas configuráveis pela interface | SATISFIED | `wait_stable` + `run_watcher` + API CRUD + UI `useWatchedFolders`. |
| ING-04 | 02-02, 02-03, 02-04 | Aceita PDF, JPG, PNG | SATISFIED | `SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}` + `is_supported_ext`. `test_extension_allowlist` prova rejeição de .txt. |
| ING-05 | 02-01, 02-02, 02-03 | Separação por N páginas por pasta; cada bloco = documento independente | SATISFIED | `split_pdf` + `process_ingest` criando N Documents com `origin_original_id`. `test_split_multipagina_cria_n_documentos`. |
| ING-06 | 02-01, 02-03, 02-04, 02-05 | Dedup por hash; sem reprocessar nem cobrar duas vezes | SATISFIED | Gate em `ingest_stage` (pré-split) + gate no `watcher` (pré-enqueue). `test_dedup_gate_segunda_ingestao_nao_cria_documentos`. Visibilidade via `/documents/duplicates-count` + frontend. |
| PROC-02 | 02-01, 02-03, 02-04 | Fila assíncrona com worker em background, retry e backoff | SATISFIED | `queue/repo.py` (`schedule_retry` com exponencial+jitter) + `queue/worker.py` (loop async + `asyncio.to_thread`). `test_backoff` e `test_backoff_esgota_vira_failed`. |
| PROC-03 | 02-01, 02-03 | Fila idempotente (chave hash+etapa), sem reexecução de etapa concluída | SATISFIED | `UNIQUE(original_hash, step)` em `jobs` + `enqueue` capturando IntegrityError + atomicidade de `process_ingest`. `test_idempotent` e `test_resume_on_startup`. |

Todos os 6 requisitos mapeados para a Fase 2 em REQUIREMENTS.md estão SATISFIED. Requisitos ING-01 e ING-03 foram removidos do v1 (confirmado em REQUIREMENTS.md e CONTEXT.md) — corretamente fora de escopo.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/ingest/splitter.py` | 70 | Captura apenas `pikepdf.PdfError`; `FileNotFoundError`/`PermissionError`/`OSError` escapam como exceções cruas (WR-06 do REVIEW.md) | Warning | Em produção, arquivo removido entre estabilização e split gera retry/FALHA em vez de descarte silencioso. Worker captura com `except Exception` genérico, então não há crash — mas a mensagem de erro perde contexto e o documento vai a FALHA permanente por algo não-culpa-do-arquivo. |
| `backend/app/queue/repo.py` | 193–198 | `requeue_running` não reseta `next_run_at` nem decrementa `attempts` (WR-02 do REVIEW.md) | Warning | 5 crashes de infra durante o mesmo job (Windows reiniciando) podem mandar um documento válido a dead-letter/FALHA permanente sem que o job tenha falhado por mérito próprio. |
| `backend/app/ingest/watcher.py` | 283 | `_folder_for_path(file_path.resolve(), ...)` segue symlinks no resolve mas passa `file_path` original para `_stabilize_hash_gate_enqueue` (WR-03) | Warning | Arquivo-symlink dentro da pasta monitorada apontando para fora pode ser processado — o hash e o CAS operam sobre o alvo do symlink. Superfície reduzida pelo endurecimento da API (rejeita symlinks como pastas), mas não eliminada. |
| `backend/app/queue/repo.py` | 104,154 | `CURRENT_TIMESTAMP` (sem offset) coexiste com datetimes Python tz-aware no `next_run_at` (WR-04) | Info | Armadilha latente: `updated_at` e `next_run_at` em formatos diferentes. Hoje não quebra porque nada compara `updated_at` contra datetime Python. |
| `frontend/src/pages/DocumentsPage.tsx` | 26 | `STAT_TOKEN: Record<DocState, ...>` contém `concluido: 'tratado'` — o token visual para um estado inalcançável nesta fase | Info | Não produz código executável problemático (estado nunca setado); é mapeamento de reserva forward-compat. Não é stub. |
| `frontend/src/App.tsx` | 32,83 | Toggle "watcher global" controla apenas `useState(true)` local; não pausa o watcher real (IN-02 do REVIEW.md) | Info | Falsa sensação de controle. Visualmente enganoso mas não quebra o pipeline; sem endpoint real de controle do watcher nesta fase. |
| `frontend/src/pages/DocumentsPage.tsx` | 35–40 | `formatSize` sempre retorna `'—'` — campo `size` nunca é populado pela API (IN-01 do REVIEW.md) | Info | Coluna "Tamanho" sempre exibe `—`. Código morto efetivo; não é blocker. |

Nenhum marcador `TBD`, `FIXME` ou `XXX` encontrado em arquivos da fase.

**Classificação:** 0 BLOCKERS. 3 Warnings (WR-02, WR-03, WR-06) — todos documentados no REVIEW.md e conhecidos; nenhum compromete os critérios de sucesso da fase.

### Human Verification Required

#### 1. Verificação visual end-to-end — Documentos + Pastas monitoradas

**Origem:** Plano 02-05, Task 3 (checkpoint:human-verify, gate=blocking). Esta é a única gate bloqueante pendente.

**Test:** Subir backend (`cd backend && .venv/bin/python -m uvicorn app.main:app --workers 1`) e frontend (`cd frontend && npm run dev`). Seguir os 8 passos:

1. Ir em Configurações → Pastas monitoradas. Adicionar pasta real → deve aparecer na lista (persistida).
2. Copiar PDF multi-página para a pasta. Editar a pasta para "Separar a cada 1 página" e copiar outro PDF. Ir para Documentos.
3. Confirmar que documentos aparecem entrando na fila e mudam de estado por polling (Na fila → Processando → Aguardando extração) SEM flicker/piscar da tabela. Nenhum documento como "Tratado"/"Concluído" (verde).
4. Confirmar que o PDF separado virou N documentos independentes (1 por página).
5. Copiar o MESMO PDF novamente (ou clicar "Forçar varredura"). Confirmar: nenhum duplicado na lista; contador "{n} duplicados ignorados" (neutro, rodapé) incrementa.
6. Remover pasta: confirmar diálogo destrutivo ("Manter pasta"/"Remover"); confirmar que documentos já ingeridos PERMANECEM.
7. Parar o backend: confirmar mensagem de erro com "Tentar novamente" dentro do card. Reiniciar e confirmar recuperação.
8. Estado vazio (nenhum documento): confirmar copy "Nenhum documento ainda" centrado na tabela.

**Expected:** Todos os 8 passos passam.
**Why human:** Comportamento visual (polling sem flicker, estados visuais corretos, labels pt-BR), confirmação destrutiva, feedback de erro/vazio/loading — não verificáveis por análise estática nem testes unitários/de integração.

---

## Gaps Summary

Nenhum gap bloqueante encontrado. Todos os 4 critérios de sucesso do ROADMAP estão cobertos pela implementação e pelos testes automatizados. O status `human_needed` reflete exclusivamente a gate bloqueante de verificação visual (Task 3 do Plano 02-05), que é a última etapa obrigatória antes de considerar a fase completa.

Os 3 warnings técnicos (WR-02, WR-03, WR-06) documentados no REVIEW.md são conhecidos e aceitáveis para o v1 — nenhum compromete a correção dos critérios de sucesso. As 2 notas informacionais (toggle de watcher cosmético, coluna Tamanho sempre `—`) são menores e documentadas.

---

_Verified: 2026-06-16T05:30:00Z_
_Verifier: Claude (gsd-verifier)_

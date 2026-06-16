---
phase: 2
slug: ingest-o-e-fila-ass-ncrona
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-15
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (backend, `asyncio_mode="auto"`); `tsc -b && vite build` (frontend) |
| **Config file** | backend/pyproject.toml `[tool.pytest.ini_options]` + backend/tests/conftest.py |
| **Quick run command** | `cd backend && .venv/bin/python -m pytest tests/ -x -q` |
| **Full suite command** | `cd backend && .venv/bin/python -m pytest tests/ -q` |
| **Frontend build check** | `cd frontend && npm run build` |
| **Estimated runtime** | < 60s backend suite; frontend build ~10-30s |

---

## Sampling Rate

- **After every task commit:** `cd backend && .venv/bin/python -m pytest tests/ -x -q` (ou `npm run build` para tasks de frontend)
- **After every plan wave:** `cd backend && .venv/bin/python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite verde + `npm run build` verde
- **Max feedback latency:** ~60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | PROC-02/03 | T-02-SC | Pacotes aprovados (slopcheck OK); coleta sem ImportError | unit/infra | `cd backend && .venv/bin/python -m pytest tests/ -q --collect-only` | ✅ | ⬜ pending |
| 02-01-02 | 01 | 1 | ING-05/06, PROC-03 | T-02-02 | Modelos registrados; UNIQUE(hash,step) e original_hash unique | unit | `cd backend && .venv/bin/python -m pytest tests/test_models.py -q` | ✅ | ⬜ pending |
| 02-01-03 | 01 | 1 | ING-05/06, PROC-02/03 | T-02-01 | Schema só via Alembic; round-trip + trigger preservado | integration | `cd backend && .venv/bin/python -m pytest tests/test_migrations.py -q` | ✅ | ⬜ pending |
| 02-02-01 | 02 | 2 | ING-02 | T-02-03 | Não processa arquivo parcial (quiescência + lock-test) | unit | `cd backend && .venv/bin/python -m pytest tests/test_stabilizer.py tests/test_config.py -q` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | ING-04/05 | T-02-04 | ceil(M/N) blocos; PDF malformado controlado; allowlist | unit | `cd backend && .venv/bin/python -m pytest tests/test_splitter.py -q` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 3 | PROC-02/03 | T-02-07/08 | Claim atômico; backoff+jitter; resume; idempotência | unit | `cd backend && .venv/bin/python -m pytest tests/test_queue.py -q` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 3 | ING-04/06, PROC-03 | T-02-08 | Dedup gate no-op; estado terminal PROCESSANDO, nunca CONCLUIDO | unit | `cd backend && .venv/bin/python -m pytest tests/test_dedup_gate.py tests/test_ingest_stage.py -q` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 3 | PROC-02 | T-02-09 | Worker resume + split via to_thread; falha→FALHA | unit | `cd backend && .venv/bin/python -m pytest tests/test_queue.py -q` | ❌ W0 | ⬜ pending |
| 02-04-01 | 04 | 4 | ING-02/06 | T-02-12 | Watcher estabiliza→hash→gate→enqueue; scan idempotente | integration | `cd backend && .venv/bin/python -m pytest tests/test_watcher.py -q` | ❌ W0 | ⬜ pending |
| 02-04-02 | 04 | 4 | ING-02 | T-02-10 | CRUD pastas; Path.resolve() valida path traversal; DELETE preserva docs | integration | `cd backend && .venv/bin/python -m pytest tests/test_api_watched_folders.py -q` | ❌ W0 | ⬜ pending |
| 02-04-03 | 04 | 4 | ING-06, PROC-02 | T-02-11 | Lista sem duplicatas + counts; contador de duplicados; rescan | integration | `cd backend && .venv/bin/python -m pytest tests/test_api_documents.py -q` | ❌ W0 | ⬜ pending |
| 02-05-01 | 05 | 5 | ING-02/06 | T-02-SC | TanStack Query + hooks tipados; build verde | build | `cd frontend && npm run build` | ✅ (build) | ⬜ pending |
| 02-05-02 | 05 | 5 | ING-02/06 | T-02-11/13 | Estados reais; sem flicker; nunca "Tratado"; build verde | build | `cd frontend && npm run build` | ✅ (build) | ⬜ pending |
| 02-05-03 | 05 | 5 | ING-02/06 | T-02-13 | Verificação visual end-to-end (humana) | manual | checkpoint:human-verify | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Criados como skeletons coletáveis no Plano 01 Task 1, preenchidos nos planos das ondas correspondentes:

- [ ] `tests/test_stabilizer.py` — ING-02 (preenchido no Plano 02)
- [ ] `tests/test_splitter.py` — ING-04/05 (preenchido no Plano 02)
- [ ] `tests/test_queue.py` — PROC-02/03 (preenchido no Plano 03)
- [ ] `tests/test_dedup_gate.py` — ING-06 (preenchido no Plano 03)
- [ ] `tests/test_ingest_stage.py` — ING-04/D-06 (preenchido no Plano 03)
- [ ] `tests/test_watcher.py` — ING-02 (preenchido no Plano 04)
- [ ] `tests/conftest.py` — fixture `schema_engine` (adicionada no Plano 01)
- [ ] Framework install: `uv add watchfiles==1.2.0 pikepdf==10.8.0` (Plano 01); `npm i @tanstack/react-query` (Plano 05)
- [ ] `tests/test_api_watched_folders.py`, `tests/test_api_documents.py` — criados no Plano 04 (não skeleton; net-new com a feature)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Documentos entram na fila e mudam de estado por polling SEM flicker | ING-02 | Comportamento visual/temporal no navegador | Plano 05 Task 3 passos 3-4 |
| Contador de duplicados incrementa de forma neutra ao reenviar o mesmo arquivo | ING-06 | Verificação visual do tratamento (não-alerta) | Plano 05 Task 3 passo 6 |
| Remover pasta preserva documentos já ingeridos (D-03) | ING-02 | Confirmação de UX destrutiva + persistência | Plano 05 Task 3 passo 7 |
| Estados vazio/erro renderizam dentro do card | ING-02 | Estado de UI sob falha de rede | Plano 05 Task 3 passo 8 |

> A lógica subjacente a cada item acima TEM cobertura automatizada no backend (dedup gate, terminal state, CRUD, counts). A verificação manual confirma apenas a camada visual/temporal.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (checkpoint usa `<human-check>` — exceção permitida)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready

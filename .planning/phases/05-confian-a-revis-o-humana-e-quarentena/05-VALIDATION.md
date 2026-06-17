---
phase: 05
slug: confian-a-revis-o-humana-e-quarentena
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-16
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0 + pytest-asyncio (`asyncio_mode = "auto"`); OpenAI mockado via `respx` (0 token) |
| **Config file** | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| **Quick run command** | `cd backend && uv run pytest tests/classification/ -x -q` |
| **Full suite command** | `cd backend && uv run pytest -q` |
| **Frontend** | sem runner de teste (vitest ausente); verificação = `cd frontend && npm run build` (tsc -b + vite build) + checkpoint visual |
| **Estimated runtime** | ~10-20s backend (sem rede; respx mocka OpenAI) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/classification/ -x -q` (cálculo de confiança + roteamento — rápido, sem rede). Para tasks de API: `cd backend && uv run pytest tests/test_api_review.py tests/test_api_config.py -x -q`.
- **After every plan wave:** Run `cd backend && uv run pytest -q` (suite completa). Frontend: `cd frontend && npm run build`.
- **Before `/gsd:verify-work`:** Full suite verde + `npm run build` verde + checkpoint visual da AttentionPage aprovado.
- **Max feedback latency:** ~20 segundos (backend).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | REV-01, REV-02 | T-05-01 / — | compute_confidence pura; tunable lido da config | unit | `cd backend && uv run pytest tests/classification/test_confidence.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | REV-01, REV-02 | T-05-01 | Migração 0005 não toca documents (trigger intacto); 3 scaffolds coletam | unit/migration | `cd backend && uv run alembic upgrade head && uv run pytest --collect-only -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | REV-01, REV-02, REV-05 | T-05-04, T-05-05 | Roteia EM_REVISAO por score/obrigatório inválido; NUNCA auto-CONCLUIDO; forced_template_id pula matcher; atomicidade preservada | unit | `cd backend && uv run pytest tests/classification/test_stage_routing.py tests/classification/test_forced_template.py tests/classification/test_stage.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | REV-05 | T-05-06 | requeue_step reseta job existente; worker repassa forced_template_id | unit | `cd backend && uv run pytest tests/ -k "queue or worker or repo" -q` | ✅ | ⬜ pending |
| 05-03-01 | 03 | 3 | REV-04, REV-05 | T-05-07..T-05-11 | 4 endpoints com allowlist como guard (409); patch sem IA (call_count==0); approve gate D-07 | integration | `cd backend && uv run pytest tests/test_api_review.py -x -q` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 3 | REV-03 | T-05-12, T-05-14 | GET /documents/attention: 3 baldes sem N+1; docs fora dos 3 estados excluídos; nenhuma automação de arquivo | integration | `cd backend && uv run pytest tests/test_api_review.py -x -q` | ❌ W0 | ⬜ pending |
| 05-03-03 | 03 | 3 | REV-02 | T-05-15 | GET/PUT limiar; 422 fora de [0,1]; cache invalidado | integration | `cd backend && uv run pytest tests/test_api_config.py -x -q` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 4 | REV-02, REV-03, REV-04 | T-05-16, T-05-18 | types/api/hooks/ConfidenceBadge tipados; faixas TRAVADAS; invalidação | build | `cd frontend && npm run build` | ✅ (tsc) | ⬜ pending |
| 05-04-02 | 04 | 4 | REV-02..REV-05 | T-05-16, T-05-17 | AttentionPage 3 baldes + ações; gates disabled; texto puro; S6; nav | build | `cd frontend && npm run build` | ✅ (tsc) | ⬜ pending |
| 05-04-03 | 04 | 4 | REV-03, REV-04, REV-05 | T-05-17 | Verificação visual: baldes, ConfidenceBadge, correção inline, gates, S6, sem visualizador (D-06) | manual/visual | checkpoint:human-verify | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/classification/test_confidence.py` — função pura compute_confidence (REV-01) — criado no Plan 01 Task 1
- [ ] `backend/tests/classification/test_stage_routing.py` — EM_REVISAO vs PROCESSANDO+classificado + persistência do score (REV-02/REV-04) — scaffold no Plan 01 Task 2, preenchido no Plan 02 Task 1
- [ ] `backend/tests/classification/test_forced_template.py` — caminho forced_template_id pula matcher (REV-05) — scaffold no Plan 01 Task 2, preenchido no Plan 02 Task 1
- [ ] `backend/tests/test_api_review.py` — 4 endpoints + attention + guards + sem-IA no patch (REV-03/REV-04/REV-05) — scaffold no Plan 01 Task 2, preenchido no Plan 03 Tasks 1-2
- [ ] `backend/tests/test_api_config.py` — GET/PUT limiar (REV-02) — criado no Plan 03 Task 3
- [ ] Fixtures reusadas (não criar novas): `tests/classification/conftest.py` (respx + schema_engine); `tests/test_api_documents.py` (fixture `client` sobre schema_engine)

*Reuso: conftest e fixtures de API já existem desde a Fase 4 — apenas os arquivos de teste acima são novos.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visão "Precisam de atenção" (3 baldes, polling sem flicker, ConfidenceBadge na cor certa, correção inline, gates de Aprovar/Reclassificar, S6 na Config, ausência de visualizador D-06, tema claro/escuro) | REV-03, REV-04, REV-05, REV-02 | Frontend sem runner de teste (vitest ausente); comportamento visual/interativo | Plan 04 Task 3 checkpoint:human-verify — passos detalhados de subir backend+frontend, semear docs nos 3 estados e exercitar cada ação |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (frontend usa `npm run build`; o comportamento visual tem checkpoint)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (cada task tem comando automatizado; o único manual é o checkpoint final)
- [x] Wave 0 covers all MISSING references (5 arquivos de teste mapeados; scaffolds no Plan 01)
- [x] No watch-mode flags (todos os comandos são one-shot `-q`/`build`)
- [x] Feedback latency < 20s (backend sem rede; respx)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-16

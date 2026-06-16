---
phase: 3
slug: extra-o-gen-rica-via-ia-e-medi-o-de-tokens
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-16
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `03-RESEARCH.md` §Validation Architecture + `03-AI-SPEC.md` §5. A Fase 3 **não tem gate de qualidade** (D-09) — os evals de qualidade são offline/dev; esta VALIDATION valida a **integração** (extração end-to-end, schema estruturado, texto nativo sem custo de IA, tokens persistidos sem dupla).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode = "auto"`, já em `backend/pyproject.toml`) |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| **Quick run command** | `cd backend && uv run pytest tests/extraction -x -q` |
| **Full suite command** | `cd backend && uv run pytest` |
| **OpenAI mock** | `respx` (adicionar ao grupo `dev`) — CI sem gastar token |
| **Estimated runtime** | ~15 segundos (unit, OpenAI mockada) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/extraction -x -q`
- **After every plan wave:** Run `cd backend && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite green + evals Code (`uv run pytest tests/evals -m "not live"`)
- **Max feedback latency:** ~15 segundos

---

## Per-Task Verification Map

> Preenchido após o planejamento (task IDs vêm dos PLAN.md). Mapa-base dos comportamentos a cobrir (de RESEARCH §Phase Requirements → Test Map):

| Requirement | Behavior | Test Type | Automated Command | File Exists |
|-------------|----------|-----------|-------------------|-------------|
| EXT-01 | Texto nativo extraído de PDF com texto (leitura local sem custo de IA) | unit | `uv run pytest tests/extraction/test_pdf_io.py -x` | ❌ W0 |
| EXT-01 | Heurística escolhe `native_text` p/ PDF com texto, `vision` p/ escaneado/imagem | unit | `uv run pytest tests/extraction/test_router.py -x` | ❌ W0 |
| EXT-02 | `extract_stage` produz `ExtractionResult` conforme schema (OpenAI mockado) | unit | `uv run pytest tests/extraction/test_stage.py -x` | ❌ W0 |
| EXT-02 | Recusa (`output_parsed is None`) → FALHA via fila, sem corromper estado | unit | `uv run pytest tests/extraction/test_stage.py::test_refusal -x` | ❌ W0 |
| EXT-02 | Persistência de `Extraction` (fields + full_text + type guess) | unit | `uv run pytest tests/extraction/test_persistence.py -x` | ❌ W0 |
| USE-02/SC4 | `Usage(step="extract")` gravado com input/output tokens, 1 por extração (sem dupla) | unit | `uv run pytest tests/extraction/test_usage.py -x` | ❌ W0 |
| Idempotência | Re-claim do mesmo bloco não re-chama IA nem duplica Usage | integration | `uv run pytest tests/extraction/test_idempotency.py -x` | ❌ W0 |
| Dispatch | Worker roteia `step="extract"` p/ caminho async (não `to_thread`) | integration | `uv run pytest tests/queue/test_dispatch.py -x` | ❌ W0 |
| Estado | Sucesso → PROCESSANDO + `last_completed_step="extraido"` via `mark_step` (NÃO `transition`) | unit | `uv run pytest tests/extraction/test_state.py -x` | ❌ W0 |
| Migração | Alembic 0003 cria `extractions` (upgrade/downgrade limpos) | integration | `uv run pytest tests/test_migrations.py -x` | ❌ verificar padrão |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/extraction/` — diretório novo (não existe). Criar com fixtures.
- [ ] `tests/extraction/conftest.py` — fixture de `AsyncOpenAI` mockado via respx; fixtures de PDF com texto e PDF escaneado/imagem sintéticos.
- [ ] `uv add --group dev respx` — mockar OpenAI em CI sem gastar token.
- [ ] (Evals AI-SPEC §5, opcional nesta fase) `tests/evals/fixtures/<tipo>/<caso>.{pdf,golden.json}` rotulados pelo operador — dataset 10–20 exemplos.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Extração real ponta-a-ponta com chave OpenAI válida | EXT-02 | Gasta token/precisa de chave válida + internet (não roda em CI) | Configurar `OPENAI_API_KEY`, colocar 1 PDF e 1 imagem na pasta monitorada, observar `Extraction` + `Usage` gravados e estado `extraido` |
| Qualidade de extração (fidelidade, campos espelhados) | — (flywheel/Fase 5) | LLM-judge gasta token; rubrica calibrada pelo operador | Nightly `uv run pytest tests/evals -m live`; revisão amostral |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (`tests/extraction/`, respx)
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

---
phase: 10
slug: robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-24
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derivado da seção "Validation Architecture" de `10-RESEARCH.md`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (mock OpenAI via respx/fakes) |
| **Config file** | `backend/pyproject.toml` (pytest config) |
| **Quick run command** | `cd backend && uv run pytest tests/classification -x -q` |
| **Full suite command** | `cd backend && uv run pytest -q` |
| **Estimated runtime** | ~30 s (classification) / ~90 s (full backend) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest tests/classification -x -q`
- **After every plan wave:** Run `cd backend && uv run pytest -q` + `cd frontend && npm run build` (type-check)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds (quick) / ~90 seconds (full)

---

## Per-Task Verification Map

> Task IDs preenchidos pelo planner. Mapa de requisito→comportamento→teste abaixo (de `10-RESEARCH.md`).

| Decisão | Behavior | Threat Ref | Test Type | Automated Command | File Exists | Status |
|---------|----------|------------|-----------|-------------------|-------------|--------|
| D-02 | normalização simétrica casa acento/quebra/pontuação (e NÃO casa palavra trocada DA≠DE, por D-04) | T-10-01 | unit | `uv run pytest tests/classification/test_matcher_norm.py -x` | ❌ W0 | ⬜ pending |
| D-02 | sinal "nota fiscal" casa "Nota\nFiscal" / "NOTA FISCAL" / "Notá Fiscál" | T-10-01 | unit | idem | ❌ W0 | ⬜ pending |
| D-03 | regex `\d{44}` e ReDoS/timeout INTACTOS pós-mudança (não-regressão) | T-10-02 | unit | `uv run pytest tests/classification/test_matcher_groups.py -x` | ✅ legados | ⬜ pending |
| D-05 | toggle OFF = quarentena direta; ON + nada casou = IA antes de quarentenar; Usage persistido | T-10-03 | unit (mock IA) | `uv run pytest tests/classification/test_stage_ai_fallback.py -x` | ❌ W0 | ⬜ pending |
| D-07/D-09 | preview reusa o motor: relatório por-grupo/sinal idêntico ao real; escaneado→flag scanned | T-10-04 | api | `uv run pytest tests/test_api_templates.py -x` | ✅ estender | ⬜ pending |
| D-10/D-11 | reprocess QUARENTENA→PROCESSANDO + requeue classify SEM forced; apaga CR antes; estado inválido→409 | T-10-05 | api | `uv run pytest tests/test_api_documents.py -x` | ✅ estender | ⬜ pending |
| D-12 | reprocess batch sobre balde; idempotente | T-10-05 | api | idem | ✅ estender | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/classification/test_matcher_norm.py` — cobre D-02/D-03 (normalização simétrica + bifurcação regex intacta)
- [ ] `tests/classification/test_stage_ai_fallback.py` — cobre D-05 (toggle ON/OFF, chamada de IA, Usage)
- [ ] Estender `tests/test_api_templates.py` — endpoint preview de sinais (texto nativo, escaneado→flag, por-sinal/grupo)
- [ ] Estender `tests/test_api_documents.py` — reprocess single + batch + guards 409 (estado inválido)
- [ ] (se preview usar multipart) garantir `python-multipart` instalado antes dos testes de upload

---

## Manual-Only Verifications

| Behavior | Decisão | Why Manual | Test Instructions |
|----------|---------|------------|-------------------|
| Renderização visual da ferramenta de testar sinais (upload→resultado por-sinal no DOM) | D-07/D-09 | UI visual não-automatizável | Subir frontend, no construtor de templates fazer upload de um PDF de teste e conferir o detalhamento por-sinal/grupo |
| Botão "reprocessar" (por-doc e lote) na tela de atenção | D-10/D-12 | UX visual | Quarentenar um doc, editar o template para casar, reprocessar e confirmar que sai da quarentena |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

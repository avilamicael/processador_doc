---
phase: 4
slug: templates-sub-templates-e-classifica-o
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-16
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (backend); respx para mock da OpenAI |
| **Config file** | backend/pyproject.toml |
| **Quick run command** | `cd backend && uv run pytest -q` |
| **Full suite command** | `cd backend && uv run pytest` |
| **Estimated runtime** | ~{N} seconds (preencher na Wave 0) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run pytest -q`
- **After every plan wave:** Run `cd backend && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** {N} seconds (preencher na Wave 0)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | TPL-01 | T-04-SC | python-dateutil canônico fixado; install gatável | integration | `cd backend && grep -q python-dateutil pyproject.toml && python -c "from app.config import get_settings; get_settings()"` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | TPL-01, EXT-04 | T-04-02 | UNIQUE(document_id) rede anti double-charge | integration | `cd backend && python -c "from app.models import ClassificationResult; assert ClassificationResult.__table__.c.document_id.unique"` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | TPL-01 | T-04-01 | 0004 só cria tabelas, não toca documents | integration | `cd backend && uv run alembic upgrade head && uv run pytest tests/test_migrations.py -x` | ✅ (estender) | ⬜ pending |
| 04-02-01 | 02 | 2 | EXT-04 | T-04-05 | Módulo 11 próprio; data dayfirst; moeda Decimal | unit | `cd backend && uv run pytest tests/validation/test_doc_ids.py -x` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 2 | EXT-04 | T-04-03 | regex via re.fullmatch + teto de tamanho (ReDoS); bruto+normalizado, marca sem bloquear | unit | `cd backend && uv run pytest tests/validation/test_fields.py -x` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 2 | TPL-03, EXT-04 | T-04-06 / T-04-07 | schema strict list-of-pairs/nullable; segredo só na criação; recusa tratada | integration | `cd backend && uv run pytest tests/classification/ -x -q` | ❌ W0 | ⬜ pending |
| 04-03-02 | 03 | 2 | TPL-03, EXT-04 | T-04-08 | matcher por sinais custo-zero; filler sem IA | unit | `cd backend && uv run pytest tests/classification/test_matcher.py tests/classification/test_filler.py -x` | ❌ W0 | ⬜ pending |
| 04-04-01 | 04 | 2 | TPL-01 | T-04-09 / T-04-10 | ORM parametrizado; regex só armazenada (não executada no HTTP) | integration | `cd backend && uv run pytest tests/test_api_templates.py -x` | ❌ W0 | ⬜ pending |
| 04-04-02 | 04 | 2 | TPL-03, TPL-04 | T-04-11 | detalhe somente leitura; log só metadados | integration | `cd backend && uv run pytest tests/test_api_documents.py -x` | ✅ (estender) | ⬜ pending |
| 04-05-01 | 05 | 3 | TPL-03, TPL-04, EXT-04 | T-04-13 / T-04-14 / T-04-16 | idempotência sem double-charge; quarentena via transition; marcador em memória; log metadados | integration | `cd backend && uv run pytest tests/classification/test_stage.py -x` | ❌ W0 | ⬜ pending |
| 04-05-02 | 05 | 3 | TPL-03 | T-04-15 | sweep idempotente; não enfileirar no stage; repo.py intacto | integration | `cd backend && uv run pytest tests/queue/test_worker.py -k classify -x` | ✅ (estender) | ⬜ pending |
| 04-06-01 | 06 | 4 | TPL-01, TPL-03 | T-04-12 | tipos/hooks tipados; sem mock | integration | `cd frontend && npx tsc --noEmit` | ❌ W0 | ⬜ pending |
| 04-06-02 | 06 | 4 | TPL-01, TPL-03, TPL-04 | T-04-12 | render texto puro (sem dangerouslySetInnerHTML); design system travado | integration | `cd frontend && npx tsc --noEmit && npm run build` | ❌ W0 | ⬜ pending |
| 04-06-03 | 06 | 4 | TPL-01, TPL-03, TPL-04 | T-04-18 | verificação visual contra 04-UI-SPEC.md | human-check | checkpoint:human-verify (blocking) | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Preenchido pelo planner/executor a partir das tarefas dos PLAN.md (cobertura: TPL-01, TPL-03, TPL-04, EXT-04).*

---

## Wave 0 Requirements

- [ ] `uv add python-dateutil==2.9.0.post0` — dependência instalada mas ausente do pyproject.toml (gap identificado na pesquisa)
- [ ] Stubs de teste para o matcher local por sinais, validação determinística (Módulo 11 CNPJ/CPF, parsers pt-BR de data/moeda) e `classify_stage`
- [ ] Reuso do scaffold respx (mock da Responses API) da Fase 3 para as chamadas de desempate/faltantes

*Detalhe final preenchido a partir da seção "Validation Architecture" do 04-RESEARCH.md.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Construtor de templates (UX do editor schema-first) | TPL-01 | Interação visual no navegador | Criar/editar/remover template pela UI, conferir contra 04-UI-SPEC.md |
| Visibilidade de classificação (somente leitura) | TPL-03/TPL-04 | Render visual de campos bruto+normalizado e status de quarentena | Conferir um documento classificado e um em quarentena na UI |

*Verificações de backend (matcher, validação, normalização, pipeline classify, idempotência/não-double-charge) têm verificação automatizada.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < {N}s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

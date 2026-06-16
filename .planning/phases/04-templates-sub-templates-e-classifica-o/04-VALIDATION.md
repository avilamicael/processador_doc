---
phase: 4
slug: templates-sub-templates-e-classifica-o
status: draft
nyquist_compliant: false
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
| {N}-01-01 | 01 | 1 | REQ-{XX} | T-{N}-01 / — | {expected secure behavior or "N/A"} | unit | `{command}` | ✅ / ❌ W0 | ⬜ pending |

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

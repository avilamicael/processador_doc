---
phase: 06
slug: automa-es-de-arquivo-renomear-mover
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-17
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Fonte: seção "Validation Architecture" de `06-RESEARCH.md`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`backend/tests/`, `conftest.py` com fixtures de sessão/engine SQLite em memória) |
| **Config file** | `backend/tests/conftest.py` |
| **Quick run command** | `cd backend && . .venv/bin/activate && pytest tests/automation -x -q` |
| **Full suite command** | `cd backend && . .venv/bin/activate && pytest -q` |
| **Estimated runtime** | ~30 segundos (suite atual + nova pasta automation) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/automation -x -q`
- **After every plan wave:** Run `pytest -q` (suite completa)
- **Before `/gsd:verify-work`:** Full suite verde + verificação manual no Windows (lock/MAX_PATH/reservados)
- **Max feedback latency:** ~30 segundos

---

## Per-Task Verification Map

> Mapa por requisito (IDs de tarefa atribuídos pelo planner). Cada requisito da fase tem cobertura automatizada planejada, salvo as verificações Windows-only listadas em "Manual-Only".

| Requirement | Behavior | Threat Ref | Test Type | Automated Command | File Exists | Status |
|-------------|----------|------------|-----------|-------------------|-------------|--------|
| AUT-01 | tokens `{campo}`→nome sanitizado | — | unit | `pytest tests/automation/test_naming.py -x` | ❌ W0 | ⬜ pending |
| AUT-01/D-07 | campo faltante → None (→revisão) | — | unit | `pytest tests/automation/test_naming.py::test_missing_field_blocks -x` | ❌ W0 | ⬜ pending |
| AUT-01/D-08 | sanitiza 9 chars + reservados + `{data:aaaa-mm}` | — | unit | `pytest tests/automation/test_naming.py -k sanitize -x` | ❌ W0 | ⬜ pending |
| AUT-02 | tokens em pasta-destino + mkdir | V4 (path traversal) | unit | `pytest tests/automation/test_naming.py -k folder -x` | ❌ W0 | ⬜ pending |
| AUT-03 | dry-run resolve origem→destino sem tocar disco | — | unit | `pytest tests/automation/test_stage.py -k dry_run -x` | ❌ W0 | ⬜ pending |
| AUT-04 | audit `intent` escrito ANTES; nunca sobrescreve | T-06 write-ahead | unit | `pytest tests/automation/test_fileops.py -k no_overwrite -x` | ❌ W0 | ⬜ pending |
| AUT-04/D-09 | colisão conteúdo diferente → `_1`/`_2`, ambos sobrevivem | — | unit | `pytest tests/automation/test_fileops.py -k collision_suffix -x` | ❌ W0 | ⬜ pending |
| AUT-04/D-10 | colisão conteúdo idêntico (mesmo SHA) → pula | — | unit | `pytest tests/automation/test_fileops.py -k collision_duplicate -x` | ❌ W0 | ⬜ pending |
| AUT-05 | undo por-doc e por-run restaura origem | — | unit | `pytest tests/automation/test_undo.py -x` | ❌ W0 | ⬜ pending |
| AUT-05 | undo quando destino sumiu → restaura do CAS | — | unit | `pytest tests/automation/test_undo.py -k cas_fallback -x` | ❌ W0 | ⬜ pending |
| AUT-06 | materializar do CAS + verificar hash (EXDEV simulado) | T-06 integridade | unit | `pytest tests/automation/test_fileops.py -k cross_device -x` | ❌ W0 | ⬜ pending |
| AUT-06 | hash divergente pós-cópia → aborta, não remove origem | T-06 integridade | unit | `pytest tests/automation/test_fileops.py -k integrity -x` | ❌ W0 | ⬜ pending |
| TPL-02/D-04 | condições `=,>,<,contém` + E/OU; numérico via Decimal | — | unit | `pytest tests/automation/test_rules.py -x` | ❌ W0 | ⬜ pending |
| TPL-02/D-05 | primeira regra que casa vence (ordem de prioridade) | — | unit | `pytest tests/automation/test_rules.py -k precedence -x` | ❌ W0 | ⬜ pending |
| AUT-04/reconcile | crash entre intent/done → reconciliação no startup | T-06 write-ahead | unit | `pytest tests/automation/test_stage.py -k reconcile -x` | ❌ W0 | ⬜ pending |
| API | endpoints regras/dry-run/apply/undo (409/422/404) | V4/V5 | integration | `pytest tests/test_api_automations.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/automation/__init__.py` + `tests/automation/conftest.py` — fixtures de doc classificado com FilledFields + temp dirs (origem/destino, mesmo e diferente "volume")
- [ ] `tests/automation/test_naming.py` — AUT-01/02, D-06/07/08
- [ ] `tests/automation/test_rules.py` — TPL-02, D-04/05
- [ ] `tests/automation/test_fileops.py` — AUT-04/06, D-09/10, EXDEV
- [ ] `tests/automation/test_stage.py` — orquestração, dry-run, idempotência, reconciliação
- [ ] `tests/automation/test_undo.py` — AUT-05 + fallback CAS
- [ ] `tests/test_api_automations.py` — espelha `test_api_templates.py`
- [ ] `tests/test_migrations.py` — estender p/ cobrir 0006 (trigger de documents intacto)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Lock de arquivo em uso (WinError 32) | AUT-04/AUT-06 | WSL2/Linux não reproduz fielmente o lock NTFS | No cliente Windows: manter o destino aberto em outro processo e aplicar — operação deve falhar controlada, sem perda, com audit `intent` reconciliável |
| MAX_PATH (260) | AUT-01/AUT-02 | Limite específico do Windows | No Windows: padrão que gere caminho > 260 chars → truncamento/erro controlado (lógica de truncamento coberta por unit no Linux) |
| Nomes reservados (CON/PRN/NUL…) | AUT-01/D-08 | Reserva específica do Windows | Lista de reservados coberta por unit; confirmar no Windows que destino com nome reservado é sanitizado e o arquivo aparece |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

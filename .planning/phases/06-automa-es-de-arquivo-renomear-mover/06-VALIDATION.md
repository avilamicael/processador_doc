---
phase: 06
slug: automa-es-de-arquivo-renomear-mover
status: replan
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-17
revised: 2026-06-17
revision: pipeline-redesign
---

# Phase 06 — Validation Strategy (REPLAN: modelo de PIPELINE)

> Per-phase validation contract para feedback sampling durante a execução.
> Fonte: seção "Validation Architecture" de `06-RESEARCH.md` (re-pesquisa pós REDESIGN).
>
> **REPLAN (2026-06-17).** As automações viraram um PIPELINE ordenado de etapas (D-12..D-16).
> Os tijolos físicos (`naming.py`/`fileops.py`/`undo.py`/`rules.py`) são REUSADOS — seus testes
> (`test_naming.py`/`test_rules.py`/`test_fileops.py`/`test_undo.py`) JÁ estão VERDES (provado em
> 06-02-SUMMARY: 12 testes; 06-03-SUMMARY: 22 passed, 1 skipped). O trabalho NOVO do REPLAN é o
> executor do pipeline, o modelo de dados e a reescrita de stage/API — cobertos pelos novos
> Wave 0 gaps abaixo.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`backend/tests/`, `conftest.py` com fixtures de sessão/engine SQLite em memória) |
| **Config file** | `backend/tests/conftest.py` + `backend/tests/automation/conftest.py` |
| **Quick run command** | `cd backend && . .venv/bin/activate && pytest tests/automation -x -q` |
| **Full suite command** | `cd backend && . .venv/bin/activate && pytest -q` |
| **Frontend build check** | `cd frontend && npx tsc --noEmit && npm run build` |
| **Estimated runtime** | ~30 segundos (backend) + build do frontend |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/automation -x -q` (backend) / `npx tsc --noEmit` (frontend)
- **After every plan wave:** Run `pytest -q` (suite completa)
- **Before `/gsd:verify-work`:** Full suite verde + `npm run build` + verificação manual no Windows (lock/MAX_PATH/reservados) + checkpoint visual do 06-08
- **Max feedback latency:** ~30 segundos

---

## Per-Task Verification Map (modelo de PIPELINE)

> Mapa por requisito/decisão. Os tijolos REUSADOS já estão verdes (06-02/06-03). As linhas NOVAS
> do REPLAN (D-12/D-13/D-14/D-15, P8/P9/P10, modelo, API, migração 0007) são Wave 0 a criar.

### Tijolos reusados (JÁ VERDES — não replanejados)

| Requirement | Behavior | Test Type | Automated Command | Status |
|-------------|----------|-----------|-------------------|--------|
| AUT-01/D-07/D-08 | tokens `{campo}`→nome sanitizado; faltante→None; reservados/`{data:fmt}` | unit | `pytest tests/automation/test_naming.py -x` | ✅ green (06-02) |
| AUT-02/V4 | tokens em pasta-destino confinada (is_relative_to) | unit | `pytest tests/automation/test_naming.py -k folder -x` | ✅ green (06-02) |
| AUT-04/D-09/D-10 | anti-colisão sufixo/skip; nunca sobrescreve | unit | `pytest tests/automation/test_fileops.py -x` | ✅ green (06-03) |
| AUT-06 | materializar do CAS + verificar hash (EXDEV); divergente→aborta | unit | `pytest tests/automation/test_fileops.py -k "cross_device or integrity" -x` | ✅ green (06-03) |
| AUT-05 | undo por-doc/por-run; destino sumiu→restaura do CAS | unit | `pytest tests/automation/test_undo.py -x` | ✅ green (06-03) |
| TPL-02 (filtro `field`) | `=,>,<,contém` + coerção Decimal (Pitfall 2) | unit | `pytest tests/automation/test_rules.py -x` | ✅ green (06-02; estendido no 06-07) |

### Novo do REPLAN (Wave 0 a criar)

| Req/Decisão | Behavior | Threat Ref | Test Type | Automated Command | File | Status |
|-------------|----------|------------|-----------|-------------------|------|--------|
| Modelo | AutomationPipeline 1:N PipelineStep 1:N StepFilter; cascade delete-orphan | — | unit | `pytest tests/automation/test_pipeline_model.py -x` | ❌ W0 (06-06) | ⬜ pending |
| Migração 0007 | drop regras + create pipeline; documents/trigger intactos | T-06-01 | unit | `pytest tests/test_migrations.py -x` | ⚠️ atualizar (06-06) | ⬜ pending |
| TPL-02/D-14 | filtros field/source_folder/extension/filename/size/template + and/or | T-06-05 (V5) | unit | `pytest tests/automation/test_pipeline.py -k filter -x` | ❌ W0 (06-07) | ⬜ pending |
| D-12 | pipeline passa por TODAS as etapas cujo filtro casa, em ORDEM; active=False ignorado | — | unit | `pytest tests/automation/test_pipeline.py -k ordering -x` | ❌ W0 (06-07) | ⬜ pending |
| D-13 | dispatch por action_type (move/rename/identify_type/route) | T-06-05 | unit | `pytest tests/automation/test_pipeline.py -k actions -x` | ❌ W0 (06-07) | ⬜ pending |
| Pitfall 8 | [Move,Rename]==[Rename,Move] (materialização única) | — | unit | `pytest tests/automation/test_pipeline.py -k order_independent -x` | ❌ W0 (06-07) | ⬜ pending |
| Pitfall 9 | step Route interrompe o pipeline e NÃO materializa | — | unit | `pytest tests/automation/test_pipeline.py -k route_stops -x` | ❌ W0 (06-07) | ⬜ pending |
| Pitfall 10 | nenhum step casa → mantido na origem (PROCESSANDO, sem transição), não materializa p/ raiz | — | unit | `pytest tests/automation/test_pipeline.py -k no_match -x` | ❌ W0 (06-07) | ⬜ pending |
| D-15 | gate identify_type lê CR existente; NÃO re-cobra IA | — | unit | `pytest tests/automation/test_pipeline.py -k gate -x` | ❌ W0 (06-07) | ⬜ pending |
| AUT-03 | dry-run simula o pipeline inteiro sem tocar disco | — | unit | `pytest tests/automation/test_stage.py -k dry_run -x` | ⚠️ atualizar (06-07) | ⬜ pending |
| AUT-04/T-06-12 | audit `intent` persistido ANTES de materialize_to_dest (write-ahead) | T-06-12 | unit | `pytest tests/automation/test_stage.py -k intent_before_materialize -x` | ⚠️ atualizar (06-07) | ⬜ pending |
| AUT-04/reconcile | crash entre intent/done → reconciliação no startup | T-06-12 | unit | `pytest tests/automation/test_stage.py -k reconcile -x` | ⚠️ atualizar (06-07) | ⬜ pending |
| API | CRUD pipeline/steps/filtros (409/422/404) + dry-run/apply/undo | T-06-05 (V5) | integration | `pytest tests/test_api_automations.py -x` | ⚠️ reescrever (06-07) | ⬜ pending |
| UI | build TS limpo + bundle (construtor pipeline + dry-run) | T-06-14 | build | `cd frontend && npx tsc --noEmit && npm run build` | ⚠️ (06-08) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ atualizar/reescrever · ⚠️ flaky*

---

## Wave 0 Requirements (REPLAN)

**Já satisfeitos (tijolos reusados — não recriar):**
- [x] `tests/automation/test_naming.py` — VERDE (06-02)
- [x] `tests/automation/test_rules.py` — VERDE (06-02; ganha casos dos novos filtros no 06-07, sem regredir os existentes)
- [x] `tests/automation/test_fileops.py` — VERDE (06-03)
- [x] `tests/automation/test_undo.py` — VERDE (06-03)

**Novos/atualizados pelo REPLAN:**
- [ ] `tests/automation/test_pipeline_model.py` — **NOVO** (06-06): cascade delete-orphan, position, FK ondelete
- [ ] `tests/test_migrations.py` — **ATUALIZAR** (06-06): cobrir 0007 (drop regras + create pipeline; trigger trg_documents_updated_at intacto; audit_log.status preservada)
- [ ] `tests/automation/test_pipeline.py` — **NOVO** (06-07): executor puro — filtros D-14, ordem D-12 (incl. active=False ignorado), ações D-13, gate D-15, Pitfalls 8/9/10
- [ ] `tests/automation/test_stage.py` — **ATUALIZAR** (06-07): apply_stage executa o pipeline; dry-run do pipeline inteiro; write-ahead (intent antes de materialize); idempotência por done; reconcile; route não materializa; no_match mantém na origem
- [ ] `tests/test_api_automations.py` — **REESCREVER** (06-07): CRUD aninhado pipeline/steps/filtros (espelha `test_api_templates.py`) + dry-run/apply/undo
- [ ] `tests/automation/conftest.py` — **ESTENDER** (06-06): `pipeline_factory` + `classified_doc_attrs` (file_attrs: ext/size/source_folder_id/original_filename)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Lock de arquivo em uso (WinError 32) | AUT-04/AUT-06 | WSL2/Linux não reproduz fielmente o lock NTFS | No cliente Windows: manter o destino aberto em outro processo e aplicar — operação deve falhar controlada, sem perda, com audit `intent` reconciliável |
| MAX_PATH (260) | AUT-01/AUT-02 | Limite específico do Windows | No Windows: padrão que gere caminho > 260 chars → truncamento/erro controlado (lógica coberta por unit no Linux) |
| Nomes reservados (CON/PRN/NUL…) | AUT-01/D-08 | Reserva específica do Windows | Lista de reservados coberta por unit; confirmar no Windows que destino com nome reservado é sanitizado e o arquivo aparece |
| Construtor de pipeline + dry-run (S1..S6) | AUT-01/02/03/05, TPL-02 | UX visual/funcional (06-08 checkpoint) | Checkpoint humano do 06-08: sequência numerada/encadeada, token com pré-visualização, dry-run sinalizado, aplicar/desfazer reversível, tema claro+escuro, sem visualizador, zero npm novo |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (novos test files do REPLAN listados)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validation strategy updated for pipeline REPLAN (2026-06-17). `wave_0_complete: false` permanece até os novos test files (test_pipeline_model.py / test_pipeline.py + atualizações de stage/api/migrations) serem criados na execução do 06-06/06-07.

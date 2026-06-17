---
phase: 05-confian-a-revis-o-humana-e-quarentena
plan: 01
subsystem: database
tags: [alembic, sqlalchemy, pydantic-settings, confidence, classification, pytest]

# Dependency graph
requires:
  - phase: 04-templates-sub-templates-e-classifica-o
    provides: "ClassificationResult/FilledField (Alembic 0004), classify_stage, validate_field, classify_match_threshold"
provides:
  - "Coluna classification_results.confidence_score (Float nullable, D-01 qualidade de extração)"
  - "Coluna filled_fields.manually_corrected (Boolean NOT NULL default 0, D-08)"
  - "Migração Alembic 0005 (batch_alter_table, sem tocar documents — trigger intacto)"
  - "Função pura compute_confidence(filled_fields, template_fields) -> (score, has_invalid_required) (REV-01/D-04)"
  - "Tunable global review_confidence_threshold (default 0.8, D-03) na config"
  - "4 arquivos de teste Wave 0 (test_confidence preenchido; 3 scaffolds skip para Plans 02/03)"
affects: [05-02 roteamento de estado, 05-03 endpoints de revisão, 05-04 frontend AttentionPage]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Indicador de confiança como função PURA derivada das validações determinísticas (sem IA/DB), testável isolada"
    - "Migração que só adiciona colunas em tabelas não-documents preserva o trigger trg_documents_updated_at (Pitfall 1)"
    - "Scaffolds Wave 0 que coletam/rodam (pytest.mark.skip nos corpos dos planos seguintes) — contrato de teste antecipado"

key-files:
  created:
    - backend/app/classification/confidence.py
    - backend/alembic/versions/0005_confidence_review.py
    - backend/tests/classification/test_confidence.py
    - backend/tests/classification/test_stage_routing.py
    - backend/tests/classification/test_forced_template.py
    - backend/tests/test_api_review.py
  modified:
    - backend/app/models/classification.py
    - backend/app/config.py
    - backend/tests/test_migrations.py

key-decisions:
  - "confidence_score (qualidade de extração, D-01) é coluna distinta de confidence (score do matcher) — não reutilizada"
  - "Score = fração de obrigatórios válidos; has_invalid_required força revisão mesmo com score alto (D-04)"
  - "Sem campos obrigatórios → (1.0, False): nada a revisar por validação determinística"
  - "review_confidence_threshold default 0.8 alinhado à faixa 'Alta ≥80%' do 05-UI-SPEC (A2 a calibrar)"

patterns-established:
  - "compute_confidence: função pura pato-tipada (Protocol) consumível por DB-objects e SimpleNamespace de teste"
  - "Migração de colunas-irmãs espelha a forma da coluna-molde existente (confidence/valid)"

requirements-completed: [REV-01, REV-02]

# Metrics
duration: 6min
completed: 2026-06-17
---

# Phase 5 Plan 01: Fundação Code-and-Config (Confiança/Revisão) Summary

**Score de confiança determinístico (fração de obrigatórios válidos) como função pura, 2 colunas novas via Alembic 0005 sem tocar `documents`, tunable global `review_confidence_threshold` e 4 scaffolds de teste Wave 0.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-17T03:27:05Z
- **Completed:** 2026-06-17T03:33:28Z
- **Tasks:** 2
- **Files modified:** 9 (6 criados, 3 editados)

## Accomplishments

- `ClassificationResult.confidence_score` (Float nullable) e `FilledField.manually_corrected` (Boolean NOT NULL default 0) no schema + migração Alembic 0005 aplicada (`alembic current == 0005`).
- `compute_confidence` puro (sem DB/IA) cobrindo os 6 casos do behavior — fração de obrigatórios válidos + flag `has_invalid_required` (REV-01/D-04).
- Tunable global `review_confidence_threshold` (default 0.8) na config, mesmo padrão de `classify_match_threshold` (REV-02/D-03).
- 4 arquivos de teste Wave 0: `test_confidence` (verde, 6 casos) + 3 scaffolds (`test_stage_routing`, `test_forced_template`, `test_api_review`) que coletam/rodam para os Plans 02/03 preencherem.
- Migração 0005 **não toca `documents`** → trigger `trg_documents_updated_at` confirmado intacto (T-05-01 mitigado).

## Task Commits

1. **Task 1: colunas + compute_confidence puro + tunable** - `4f84a93` (feat)
2. **Task 2: migração 0005 + scaffolds Wave 0** - `f0c3a55` (feat)

_Task 1 era `tdd="true"`: teste e implementação foram entregues juntos no mesmo commit (a função pura já passa os 6 casos no momento do commit)._

## Files Created/Modified

- `backend/app/models/classification.py` - +confidence_score (ClassificationResult), +manually_corrected (FilledField)
- `backend/app/classification/confidence.py` - função pura compute_confidence (Protocol pato-tipado)
- `backend/app/config.py` - +review_confidence_threshold (Field + AliasChoices)
- `backend/alembic/versions/0005_confidence_review.py` - migração das 2 colunas (batch_alter_table, sem documents)
- `backend/tests/classification/test_confidence.py` - 6 casos do behavior (REV-01)
- `backend/tests/classification/test_stage_routing.py` - scaffold roteamento de estado (Plan 02)
- `backend/tests/classification/test_forced_template.py` - scaffold forced_template_id (Plan 02)
- `backend/tests/test_api_review.py` - scaffold dos 4 endpoints de revisão (Plan 03)
- `backend/tests/test_migrations.py` - ajustado para head=0005 (downgrade -1/-2 com a nova revisão)

## Decisions Made

- `confidence_score` é coluna **distinta** de `confidence` (D-01 separa qualidade de extração vs score do matcher) — não houve reuso.
- `compute_confidence` tipada via `Protocol` (pato-tipagem) para aceitar tanto objetos SQLAlchemy quanto `SimpleNamespace` de teste sem acoplar a função ao ORM.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_migrations assumia head=0004; quebrou com 0005 como nova head**
- **Found during:** Task 2 (após aplicar a migração 0005)
- **Issue:** `test_downgrade_um_passo_remove_so_a_fase_4` e `test_downgrade_dois_passos_remove_fase_3` codificavam a semântica de "1 passo de downgrade = remove Fase 4". Com 0005 virando head, `downgrade -1` passa a reverter só as colunas da Fase 5 (Fase 4 permanece) e `downgrade -2` é que remove a Fase 4 — os asserts falhavam.
- **Fix:** Reescritos os dois testes para a nova topologia: `downgrade -1` dropa só `confidence_score`/`manually_corrected` (tabelas 1–4 intactas); `downgrade -2` remove a Fase 4 preservando 1–3. Renomeados para refletir o comportamento.
- **Files modified:** backend/tests/test_migrations.py
- **Verification:** `uv run pytest tests/test_migrations.py -q` → 11 passed; suite completa 256 passed.
- **Committed in:** `f0c3a55` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Correção necessária — a inserção de qualquer migração entre head e os testes de downgrade exige reindexar o que cada passo reverte. Sem scope creep.

## Issues Encountered

- O banco real fica em `~/.processador_documentos/app.db` (derivado de `Settings.effective_database_url`), não na árvore do repo — a checagem `PRAGMA table_info` foi feita resolvendo a URL via `get_settings()` em vez de `glob('**/*.db')`. Confirmadas as 2 colunas e o trigger intacto.

## User Setup Required

None - nenhuma configuração de serviço externo necessária. `REVIEW_CONFIDENCE_THRESHOLD` é opcional (default 0.8).

## Next Phase Readiness

- Contratos prontos para o Plan 02 (roteamento de estado em `classify_stage` consumindo `compute_confidence` + `confidence_score` + `review_confidence_threshold`) e Plan 03 (endpoints de revisão preenchendo os scaffolds).
- Scaffolds Wave 0 com fixtures (`schema_engine`, `client`, respx de conftest) já no lugar — Plans 02/03 só removem os `pytest.mark.skip` e preenchem os corpos.

## Self-Check: PASSED

- FOUND: backend/app/classification/confidence.py
- FOUND: backend/alembic/versions/0005_confidence_review.py
- FOUND: backend/tests/classification/test_confidence.py
- FOUND: backend/tests/classification/test_stage_routing.py
- FOUND: backend/tests/classification/test_forced_template.py
- FOUND: backend/tests/test_api_review.py
- FOUND commit: 4f84a93
- FOUND commit: f0c3a55

---
*Phase: 05-confian-a-revis-o-humana-e-quarentena*
*Completed: 2026-06-17*

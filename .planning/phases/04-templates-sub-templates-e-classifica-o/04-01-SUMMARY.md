---
phase: 04-templates-sub-templates-e-classificacao
plan: 01
subsystem: database
tags: [sqlalchemy, alembic, sqlite, pydantic-settings, python-dateutil, classification, templates]

# Dependency graph
requires:
  - phase: 03-extracao-generica-via-ia-e-medicao-de-tokens
    provides: "Modelo Extraction (forma a espelhar: Mapped/mapped_column, FK CASCADE, UNIQUE p/ idempotência, relationship back_populates) e padrão de tunables openai_extract_* na config"
  - phase: 01-fundacao
    provides: "Base/Alembic versionado (0001), Document.state/last_completed_step, padrão de migração com batch_alter_table"
provides:
  - "4 tabelas novas (templates, template_fields, classification_results, filled_fields) via migração 0004"
  - "Modelos Template + TemplateField (campos tipados D-08, regex D-09, sinais D-02)"
  - "Modelos ClassificationResult (UNIQUE document_id = rede anti double-charge) + FilledField (raw/normalized D-11, valid D-10)"
  - "Tunables de classificação na config (classify_match_threshold, openai_classify_model/temperature/max_output_tokens)"
  - "Scaffolds de teste Wave 0: tests/classification (+ conftest respx de classify) e tests/validation"
affects: [classificacao, validacao, stage, api, frontend]

# Tech tracking
tech-stack:
  added: [python-dateutil==2.9.0.post0]
  patterns:
    - "Tunables de classify espelham o bloco openai_extract_* (Field + AliasChoices, override por env sem deploy)"
    - "ClassificationResult.document_id UNIQUE como rede de banco contra double-charge (espelha Extraction)"
    - "template_id FK SET NULL nullable = quarentena / não-casou (D-03)"
    - "Migração só CRIA tabelas novas; não toca documents → não recria trg_documents_updated_at (mesmo caveat resolvido da 0003)"

key-files:
  created:
    - backend/app/models/template.py
    - backend/app/models/classification.py
    - backend/alembic/versions/0004_templates_classification.py
    - backend/tests/classification/__init__.py
    - backend/tests/classification/conftest.py
    - backend/tests/validation/__init__.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/app/config.py
    - backend/app/models/document.py
    - backend/app/models/__init__.py
    - backend/tests/test_migrations.py

key-decisions:
  - "ClassificationResult.document_id UNIQUE = 1 classificação por bloco = rede de banco contra double-charge (Pitfall 2 / EXT-04), consumida pelo stage no Plan 05"
  - "template_id FK SET NULL nullable: null = quarentena/não-casou (D-03); apagar template não apaga histórico de classificação"
  - "Limiar de classificação é GLOBAL no v1 (classify_match_threshold); por-template fica v2/INT2-05"
  - "openai_classify_model default reusa o literal de extract (gpt-4o-2024-08-06) — uma instância pode definir só um modelo"
  - "TemplateField.field_type default 'texto' (conjunto D-08); regex/hint opcionais (D-09)"
  - "FilledField separa raw_value e normalized_value (D-11) + flag valid/invalid_reason (D-10)"

patterns-established:
  - "Sinais identificadores do template persistidos como JSON Text (signals_json) — consumidos pelo matcher local custo-zero do próximo plano"
  - "conftest de classify reusa o envelope da Responses API e o respx mock de /v1/responses (sem gastar token), espelhando tests/extraction/conftest.py"

requirements-completed: [TPL-01, EXT-04]

# Metrics
duration: 9min
completed: 2026-06-16
---

# Phase 4 Plan 01: Fundação de Templates & Classificação Summary

**4 tabelas novas (templates/template_fields/classification_results/filled_fields) via Alembic 0004, com UNIQUE(document_id) anti double-charge e tunables de classificação lidos da config — base goal-backward de TPL-01 e rede de idempotência de EXT-04**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-16T21:03:07Z
- **Completed:** 2026-06-16
- **Tasks:** 3
- **Files modified:** 12 (6 criados, 6 modificados)

## Accomplishments
- python-dateutil 2.9.0.post0 fixado nas dependencies (build reprodutível no cliente, D-11 normalização de data)
- 4 tunables de classificação na config, com override por env testado (CLASSIFY_MATCH_THRESHOLD=0.7 reflete)
- 4 modelos novos importáveis e registrados em app.models.__all__; ClassificationResult com UNIQUE(document_id) e template_id nullable
- Migração 0004 (down_revision 0003) cria as 4 tabelas; round-trip up/down testado preservando Fases 1/2/3
- Scaffolds de teste Wave 0 prontos: tests/classification (com conftest respx de classify) e tests/validation coletam 0 testes sem erro de import

## Task Commits

Cada tarefa foi commitada atomicamente:

1. **Task 1: python-dateutil + tunables de classificação na config** - `79d5fd9` (chore)
2. **Task 2: 4 modelos novos + relationships reversos + registro** - `ebf6c67` (feat)
3. **Task 3: Migração 0004 + scaffolds de teste Wave 0** - `d438418` (feat)

## Files Created/Modified
- `backend/app/models/template.py` - Template (name UNIQUE, doc_type, signals_json D-02) + TemplateField (field_type D-08, required, regex D-09, hint)
- `backend/app/models/classification.py` - ClassificationResult (document_id UNIQUE, template_id nullable SET NULL, confidence) + FilledField (raw/normalized D-11, valid/invalid_reason D-10)
- `backend/alembic/versions/0004_templates_classification.py` - Migração que cria as 4 tabelas + índices UNIQUE
- `backend/app/config.py` - classify_match_threshold + openai_classify_model/temperature/max_output_tokens
- `backend/app/models/document.py` - reverso 1:1 Document.classification
- `backend/app/models/__init__.py` - registra Template/TemplateField/ClassificationResult/FilledField
- `backend/tests/test_migrations.py` - assertiva das 4 tabelas + UNIQUE + round-trip de downgrade ajustado para 0004
- `backend/tests/classification/conftest.py` - fixtures respx de desempate por IA (match/no-match/fields)
- `backend/pyproject.toml` / `backend/uv.lock` - dependência python-dateutil
- `backend/tests/classification/__init__.py`, `backend/tests/validation/__init__.py` - scaffolds vazios

## Decisões Made
- **Limiar global no v1:** `classify_match_threshold` é um único limiar para todos os templates (por-template adiado para v2/INT2-05, conforme discretion D-03 do plano).
- **Default do modelo de classify:** literal `gpt-4o-2024-08-06` (mesmo valor de extract) em vez de um validador que copie de extract em runtime — mais simples e o resultado observável é idêntico; ainda assim cada um é override-ável por env independentemente.
- **server_default nas colunas booleanas/string:** TemplateField.field_type='texto', required='0', FilledField.valid='1', templates.signals_json='[]' — coerência entre o default do ORM e o default no schema versionado.

## Deviations from Plan

None - plan executed exactly as written.

(Nota: o plano descrevia python-dateutil como "instalado no ambiente mas ausente do arquivo"; na prática não estava instalado no venv. `uv add` cobriu ambos — instalação + registro no pyproject — então a ação do plano permaneceu idêntica, sem desvio de comportamento.)

## Issues Encountered
- Ruff E501 (linha > 100) numa f-string de assert nova em test_migrations.py — resolvido extraindo o conjunto para variável `sobrando` antes do assert. Sem impacto funcional.

## User Setup Required
None - nenhuma configuração de serviço externo necessária. Os tunables têm defaults sensatos; a chave OPENAI_API_KEY já existia desde a Fase 1.

## Next Phase Readiness
- Tabelas e modelos prontos para o Plan de validação (consome TemplateField.regex/required → FilledField.valid/invalid_reason) e o Plan de classificação (matcher local sobre signals_json + desempate por IA escrevendo ClassificationResult).
- conftest de classify pronto para os planos de classificação mockarem a Responses API sem gastar token.
- Sem blockers.

## Self-Check: PASSED

Todos os arquivos criados existem e os 3 commits de tarefa (79d5fd9, ebf6c67, d438418) estão presentes no histórico.

---
*Phase: 04-templates-sub-templates-e-classifica-o*
*Completed: 2026-06-16*

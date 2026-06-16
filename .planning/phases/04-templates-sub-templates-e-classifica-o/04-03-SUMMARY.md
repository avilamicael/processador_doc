---
phase: 04-templates-sub-templates-e-classificacao
plan: 03
subsystem: classificacao
tags: [classification, openai, responses-api, structured-outputs, matcher, filler, pydantic]

# Dependency graph
requires:
  - phase: 04-templates-sub-templates-e-classificacao
    plan: 01
    provides: "Modelos Template/TemplateField (signals_json D-02, name/required), tunables openai_classify_* + classify_match_threshold na config, conftest respx de classify"
  - phase: 03-extracao-generica-via-ia-e-medicao-de-tokens
    provides: "ExtractedField (list-of-pairs strict-safe) reusado pelo MissingFieldsResult; padrão extraction/openai_client (_client/_map_usage/_unwrap/recusa) e router.choose (função pura) espelhados"
provides:
  - "schema.py: DisambiguationResult (matched_template_id int|None = quarentena) + MissingFieldsResult (list[ExtractedField] reusado, strict-safe)"
  - "openai_client.py: disambiguate()/fill_missing_fields() (Responses API + text_format), ClassifyUsage (input->prompt/output->completion), ClassificationRefused"
  - "matcher.py: match_templates() (confiança por sinais + bônus doc_type, PURA) + decide() (política D-03 matched/ambiguous/quarantine)"
  - "filler.py: map_fields() (pares->campos por nome normalizado, missing_required, sem IA)"
affects: [stage, classificacao, validacao]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reuso de ExtractedField (Fase 3) no MissingFieldsResult — nunca redeclara o tipo nem usa dict aberto (Pitfall 1 strict mode)"
    - "Política de desempate (decide) SEPARADA de match_templates — preserva o seam D-03; matcher continua puro e ordenável"
    - "openai_client de classify espelha extraction/openai_client byte-a-byte no estilo (_client/_map_usage/_refusal_reason/_unwrap, segredo só na criação)"

key-files:
  created:
    - backend/app/classification/__init__.py
    - backend/app/classification/schema.py
    - backend/app/classification/openai_client.py
    - backend/app/classification/matcher.py
    - backend/app/classification/filler.py
    - backend/tests/classification/test_matcher.py
    - backend/tests/classification/test_filler.py
  modified: []

key-decisions:
  - "decide(matches, threshold) separada de match_templates: a pontuação é pura/ordenável e a política de roteamento (matched/ambiguous/quarantine) é o ponto extensível — preserva o seam D-03 (não embutido em router.choose)"
  - "Bônus de doc_type = 0.15 (constante) somado à fração de sinais, com confiança limitada a 1.0 — doc_type ajuda no desempate sem dominar a evidência dos sinais"
  - "Margem de ambiguidade = 0.1 entre os dois melhores (ambos acima do piso) → 'ambiguous' (a IA desempata, D-01)"
  - "Filler normaliza nomes com NFKD + casefold + colapso de espaços/underscores (D-05) — casa 'Número Nota' com 'numero nota'/'numero_nota' sem dependência externa"

patterns-established:
  - "Matcher como função pura de módulo (recebe templates já carregados) — sem DB nem IA dentro, espelhando extraction/router.choose"
  - "Schemas de classify guiados por description nos Field (disciplina de prompt) e instructions FIXAS no openai_client (sem few-shot do conteúdo — T-04-06)"

requirements-completed: [TPL-03, EXT-04]

# Metrics
duration: 8min
completed: 2026-06-16
---

# Phase 4 Plan 03: Blocos puros da classificação Summary

**Motor de classificação custo-zero (matcher local por sinais + filler de pares->campos) + os schemas Structured Outputs e o cliente OpenAI das chamadas pagas de desempate/faltantes, todos espelhando os padrões da Fase 3 (list-of-pairs strict-safe, segredo seguro, recusa tratada)**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-06-16
- **Tasks:** 2
- **Files modified:** 7 (7 criados, 0 modificados)

## Accomplishments
- `schema.py`: `DisambiguationResult` com `matched_template_id: int | None` (null = quarentena, D-03) + `MissingFieldsResult` reusando `ExtractedField` da Fase 3 (list-of-pairs strict-safe; sem redeclaração nem dict aberto — Pitfall 1)
- `openai_client.py`: `disambiguate()` e `fill_missing_fields()` via Responses API com `text_format`, `ClassifyUsage` (input→prompt/output→completion), `ClassificationRefused` na recusa (`output_parsed is None`); segredo lido só na criação do cliente
- `matcher.py`: `match_templates()` PURA pontua templates pela fração de sinais presentes (key/full_text, case-insensitive) + bônus de doc_type; `decide()` aplica a política D-03 (matched ≥ limiar / ambiguous na zona cinzenta / quarantine sem sinal) separada do match — preservando o seam
- `filler.py`: `map_fields()` casa pares extraídos → campos por nome normalizado (NFKD+casefold+espaços), lista `missing_required` dos obrigatórios sem par; sem IA, sem validação
- 11 testes verdes (matcher + filler), sem gastar token; matcher/filler provados puros (sem openai/sqlalchemy)

## Task Commits

Cada tarefa foi commitada atomicamente (Task 2 em ciclo TDD RED→GREEN):

1. **Task 1: Schema de classify + cliente OpenAI** - `3daa16f` (feat)
2. **Task 2 (RED): testes de matcher e filler** - `1331f77` (test)
3. **Task 2 (GREEN): matcher + filler** - `4275b92` (feat)

## Files Created/Modified
- `backend/app/classification/__init__.py` - docstring do pacote (peças puras + cliente OpenAI)
- `backend/app/classification/schema.py` - `DisambiguationResult` (nullable) + `MissingFieldsResult` (reuso `ExtractedField`)
- `backend/app/classification/openai_client.py` - `disambiguate`/`fill_missing_fields` (Responses API), `ClassifyUsage`, `ClassificationRefused`
- `backend/app/classification/matcher.py` - `match_templates` (PURA, sinais + bônus) + `decide` (política D-03) + dataclasses `TemplateMatch`/`MatchDecision`
- `backend/app/classification/filler.py` - `map_fields` (pares→campos normalizados) + `FillResult`
- `backend/tests/classification/test_matcher.py` - 7 testes (sinais, doc_type, maior-vence, ambíguo, quarentena)
- `backend/tests/classification/test_filler.py` - 4 testes (mapeamento, case/acento, obrigatório faltante, opcional omitido)

## Decisões Made
- **`decide` separada de `match_templates`:** a pontuação é pura e ordenável; a política de roteamento (matched/ambiguous/quarantine) fica isolada — é o ponto que o stage/Fases futuras estendem sem mexer no scoring, preservando o seam D-03 (não embutido em `router.choose`).
- **Bônus de doc_type = 0.15 (constante de módulo):** somado à fração de sinais e limitado a 1.0 — o palpite de tipo ajuda a desempatar sem sobrepor a evidência dos sinais.
- **Margem de ambiguidade = 0.1:** se os dois melhores estão ambos acima do piso e a diferença é menor que isso → "ambiguous" → a IA desempata (D-01).
- **Normalização do filler:** NFKD + remoção de diacríticos + casefold + colapso de espaços/underscores, sem dependência externa (D-05 pede mapeamento simples).

## Deviations from Plan

None - plan executed exactly as written.

(Nota: o conftest scaffold da Fase 1 trazia `openai_classify_fields_payload` com pares `key/value` sem `confidence`; como `MissingFieldsResult.fields` reusa `ExtractedField` — que exige `confidence` — esse payload precisará de `confidence` quando o stage (Plan seguinte) for testá-lo via respx. Não é desvio deste plano: as funções de `openai_client` foram exercitadas só pelos imports/verificações deste plano; nenhum teste deste plano consome aquele payload. Registrado como aviso para o Plan do stage.)

## Issues Encountered
None - implementação direta espelhando os padrões da Fase 3; todos os testes passaram no primeiro GREEN.

## User Setup Required
None - nenhuma configuração de serviço externo. Os tunables (`classify_match_threshold`, `openai_classify_*`) já existem com defaults desde o Plan 01; a `OPENAI_API_KEY` já existe desde a Fase 1.

## Next Phase Readiness
- Peças prontas para o `classify_stage` (Plan seguinte) compor: matcher local (custo 0) → `decide` (matched/ambiguous/quarantine) → `disambiguate` na zona cinzenta → `map_fields` → `fill_missing_fields` para os obrigatórios faltantes, persistindo `ClassificationResult`/`FilledField` num commit atômico com `Usage(step=classify)`.
- Aviso para o Plan do stage: ao mockar `fill_missing_fields` via respx, incluir `confidence` em cada par do `openai_classify_fields_payload` (o conftest atual omite — `ExtractedField` exige).
- Sem blockers.

## Self-Check: PASSED

Todos os 7 arquivos criados existem e os 3 commits de tarefa (3daa16f, 1331f77, 4275b92) estão presentes no histórico.

---
*Phase: 04-templates-sub-templates-e-classifica-o*
*Completed: 2026-06-16*

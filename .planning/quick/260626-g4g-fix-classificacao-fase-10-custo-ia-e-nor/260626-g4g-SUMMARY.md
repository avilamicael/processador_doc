---
phase: quick-260626-g4g
plan: 01
subsystem: classification
tags: [classification, matcher, ai-fallback, cost-control, tdd, code-review]
requires: []
provides:
  - "Gate do IA-fallback com guardas not called_ai + templates (sem dupla cobrança / sem chamada inútil)"
  - "_condition_matches: needle de texto curto casa RAW casefolded (anti over-match simbólico)"
affects:
  - backend/app/classification/stage.py
  - backend/app/classification/matcher.py
tech-stack:
  added: []
  patterns:
    - "Guardas de custo no gate de IA explícitas no stage (não no matcher.decide), preservando seam D-06"
    - "Needle normalizado curto (<3) → fallback para raw casefolded sobre haystack lowercase-só"
key-files:
  created: []
  modified:
    - backend/app/classification/stage.py
    - backend/app/classification/matcher.py
    - backend/tests/classification/test_stage_ai_fallback.py
    - backend/tests/classification/test_matcher_norm.py
decisions:
  - "WR-04: threshold de needle curto é len(needle) < 3 (não < 2 como no plano) — 'Nº' normaliza para 'no' (len 2) e precisa cair no caminho raw para não over-matchar 'norte'"
metrics:
  tasks: 2
  files_modified: 4
  commits: 2
  duration_min: ~20
  completed: 2026-06-26
---

# Quick Task 260626-g4g: Fix classificação Fase 10 (custo IA + normalização) Summary

Três achados do code-review da Phase 10 no motor de classificação corrigidos com testes
de regressão TDD (RED→GREEN): o IA-fallback deixa de pagar 2x num desempate ambíguo
recusado (WR-01) e de disparar uma chamada paga inútil quando não há templates (WR-03);
o ramo de texto do matcher deixa de over-matchar por símbolos curtos como "R$"/"Nº" que
a normalização reduzia a uma letra/sílaba solta (WR-04).

## What Was Built

### Task 1 — Gate do IA-fallback (WR-01 + WR-03) — commit `7e546f9`

`stage.py` (~264): o gate do IA-fallback ganhou duas guardas adicionais:
`... and not called_ai and templates`.

- `not called_ai` (WR-01): se o ramo "ambiguous" já pagou um desempate e a IA recusou
  (`matched_template_id` segue None), o fallback NÃO re-dispara — antes o mesmo doc
  pagava uma 2ª chamada idêntica. Vai direto para quarentena com o Usage já registrado.
- `templates` (lista vazia = falsy) (WR-03): sem nenhum template cadastrado não há o que
  a IA casar; `disambiguate` contra lista vazia só queimava token retornando null.

Comentário do bloco atualizado para documentar as duas guardas. Ramo "ambiguous",
persistência de Usage e quarentena intocados.

2 testes novos em `test_stage_ai_fallback.py`:
- `test_on_ambiguo_ia_recusa_nao_paga_duas_vezes`: 2 templates ambíguos + IA recusa →
  `call_count == 1`, QUARENTENA, `n_usage == 1`, `called_ai True`.
- `test_on_sem_templates_nao_paga_ia`: zero templates + fallback ON → `call_count == 0`,
  QUARENTENA, `n_usage == 0`.

### Task 2 — Matcher needle curto casa RAW (WR-04) — commit `8d438ab`

`matcher.py` `_condition_matches`, ramo "texto": quando o needle normalizado tem `< 3`
chars, casa o valor RAW casefolded (`value.casefold().strip()`) contra o
`haystack_lower` (lowercase-só, já recebido) em vez do haystack normalizado. Needle
normal (`>= 3`) mantém o comportamento atual com toda a tolerância de
acento/caixa/quebra/pontuação. value vazio → raw "" → fail-closed. Ramo regex e
`_normalize_text`/`_prepare_haystacks` intocados.

6 testes novos em `test_matcher_norm.py`: "R$" não casa "carro rural" (0.0); "Nº" não
casa "documento no campo norte" (0.0); "R$" casa "valor R$ 1.234,00" (1.0); "Nº" casa
"Nº 4567" (1.0); needle normal preserva tolerância ("nota fiscal"/"DANFE" → 1.0); value
vazio → 0.0.

## Deviations from Plan

### 1. [Rule 1 — Bug/correção] WR-04: threshold `len(needle) < 3` em vez de `< 2`

- **Encontrado durante:** Task 2 (escrita do teste de "Nº").
- **Issue:** O plano instruía literalmente `len(needle) < 2` para o caminho raw, mas o
  `<behavior>`/`<success_criteria>` do mesmo plano exigem que "Nº" NÃO over-matche
  "documento no campo norte" (→ 0.0). Verificado empiricamente que `_normalize_text("Nº")`
  produz `"no"` (NFKD expande o ordinal º→o), de comprimento **2**. Com `< 2`, "no" (len 2)
  cairia no caminho normalizado e casaria "documento no campo norte"/"norte" → 1.0,
  contradizendo o comportamento declarado.
- **Fix:** Usar `len(needle) < 3` (captura needles normalizados de 1 e 2 chars). Satisfaz
  todos os exemplos de comportamento do plano; os exemplos são autoritativos sobre a
  constante literal.
- **Impacto:** Nenhum needle de texto dos testes existentes tem normalização < 3 chars
  (o mais curto é "cnpj"=4, "valor"=5, "danfe"=5) — zero regressão na suíte completa.
- **Files modified:** backend/app/classification/matcher.py
- **Commit:** 8d438ab

## Verification

- `backend/tests/classification` (venv): **70 passed** (era 62; +8 novos: 2 stage + 6 matcher).
- `backend/tests/classification/test_stage_ai_fallback.py`: 7 passed (5 existentes + 2 novos).
- `test_matcher_norm.py` + `test_matcher.py` + `test_matcher_groups.py`: 40 passed.
- Suíte backend completa: **523 passed**, 0 falhas (32 warnings de deprecação pré-existentes, fora de escopo).
- `ruff check` nos 4 arquivos tocados: All checks passed.
- Ciclo TDD confirmado por arquivo: RED (WR-01 call_count==2; WR-03 chamada com mock vazio;
  WR-04 over-match 1.0) → GREEN após o fix.

## Commits

- `7e546f9` fix(classification): gate do IA-fallback não paga 2x nem sem templates (WR-01/WR-03)
- `8d438ab` fix(classification): needle de texto curto casa RAW casefolded, não over-matcha (WR-04)

## Known Stubs

Nenhum.

## Self-Check: PASSED

- Arquivos modificados confirmados em disco (stage.py, matcher.py, 2 arquivos de teste).
- Commits confirmados no git log: 7e546f9, 8d438ab.
- SUMMARY.md não-commitado (intencional — o orquestrador commita os docs).

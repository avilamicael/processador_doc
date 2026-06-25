---
phase: 10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova
plan: 04
subsystem: classification
tags: [ia-fallback, config, classify-stage, opt-in, custo]
requires: ["10-01"]
provides:
  - "Setting global classify_ai_fallback_enabled (bool, default False)"
  - "Endpoints GET/PUT /config/ai-fallback (persist_env_setting + cache_clear)"
  - "Ramo de IA-fallback no classify_stage (gated, antes de quarentenar)"
affects:
  - backend/app/config.py
  - backend/app/api/config.py
  - backend/app/classification/stage.py
tech-stack:
  added: []
  patterns:
    - "Toggle global lido de env sem deploy (espelha review-threshold)"
    - "Decisão de chamar IA vive no stage, nunca no matcher.decide (seam D-06)"
key-files:
  created:
    - backend/tests/classification/test_stage_ai_fallback.py
  modified:
    - backend/app/config.py
    - backend/app/api/config.py
    - backend/app/classification/stage.py
decisions:
  - "Fallback reusa disambiguate() contra TODOS os templates (nada casou), contrastando com o desempate que só passa candidatos >= threshold"
  - "Usage(step=classify) sempre persistido na tentativa de fallback, mesmo sem casar (Pitfall 5: a chamada foi paga)"
metrics:
  duration: ~12 min
  completed: 2026-06-25
  tasks: 2
  files: 4
---

# Phase 10 Plan 04: IA-fallback opt-in na classificação Summary

Toggle global `classify_ai_fallback_enabled` (default OFF) que, quando ligado e o matcher local não casa nenhum template, faz o `classify_stage` chamar a IA contra todos os templates antes de quarentenar — reusando `disambiguate`, com custo explícito e Usage persistido mesmo sem casar; seam `matcher.decide` preservado intacto.

## What Was Built

**Task 1 — Setting + endpoints de config (commit b29a60c)**
- `Settings.classify_ai_fallback_enabled: bool = Field(default=False, ...)` em `config.py`, com docstring explicando o custo (cada doc não-casado vira 1 chamada paga quando ON).
- `GET /config/ai-fallback` → `AiFallbackOut(enabled=...)` e `PUT /config/ai-fallback` → `persist_env_setting(_AI_FALLBACK_ENV_KEY, str(body.enabled))` + `get_settings.cache_clear()`, espelhando exatamente o par review-threshold (escrita atômica do `.env`, sem reiniciar o processo). Body Pydantic `bool` → 422 fora do tipo.

**Task 2 — Ramo de IA-fallback no stage + suíte (TDD: RED 692b665, GREEN 061d65d)**
- Ramo `(5.5)` inserido APÓS a decisão do matcher e ANTES do bloco de quarentena, gated por `matched_template_id is None and settings.classify_ai_fallback_enabled and forced_template_id is None`. Chama `disambiguate(_candidates_summary(templates), extraction.full_text)` contra TODOS os templates; seta `called_ai=True`; anexa `Usage(step="classify")`. Se a IA casa um id existente em `by_id`, seta `matched_template_id`/`confidence` e o doc segue o caminho de casamento; se não casa, segue para quarentena com o Usage da tentativa já em `usages` (persistido pelo bloco existente).
- `matcher.decide` e o ramo `forced_template_id` ficaram intactos (seam D-06).
- `test_stage_ai_fallback.py` cobre os 5 casos do `<behavior>`: OFF=quarentena direta (0 chamadas); ON+nada casou+IA casa=segue caminho (1 chamada, Usage); ON+nada casou+IA não casa=quarentena + Usage persistido (Pitfall 5, 1 chamada); ON+forced=fallback não dispara; ON+matcher casou=inalterado.

## Verification

- `pytest tests/classification/test_stage_ai_fallback.py tests/classification/test_stage.py` → 11 passed.
- `pytest tests/classification` → 62 passed.
- `pytest -q` (suíte completa) → 478 passed, 0 falhas (não-regressão geral).
- RED confirmado antes do GREEN: os 2 testes de fallback falharam com `called_ai is False`; os 3 de comportamento-inalterado passaram já no RED.

## TDD Gate Compliance

Task 2 (`tdd="true"`): gate RED (test commit 692b665) → GREEN (feat commit 061d65d) cumprido. REFACTOR não necessário — o ramo espelha o bloco de desempate existente sem duplicação que justifique limpeza.

## Deviations from Plan

None - plano executado exatamente como escrito.

## Self-Check: PASSED

- Arquivos: backend/app/config.py, backend/app/api/config.py, backend/app/classification/stage.py, backend/tests/classification/test_stage_ai_fallback.py — todos FOUND.
- Commits: b29a60c, 692b665, 061d65d — todos FOUND.

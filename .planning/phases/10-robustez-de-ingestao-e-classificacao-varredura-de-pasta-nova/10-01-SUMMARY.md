---
phase: 10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova
plan: 01
subsystem: classification
tags: [matcher, normalizacao, preview, redos, tdd]
requires:
  - "app.classification.matcher.match_templates (06.1-01)"
  - "app.classification.matcher.decide (seam D-03, 06.1-01)"
provides:
  - "matcher._normalize_text (pura, NFKD+lower+pontuação→espaço+colapsa)"
  - "matcher.evaluate_groups (helper público: relatório por-grupo/condição — base do preview, Plano 02 D-09)"
  - "matcher.ConditionReport / matcher.GroupReport (dataclasses de relatório)"
affects:
  - "Plano 10-02 (preview de sinais consome evaluate_groups)"
tech-stack:
  added: []
  patterns:
    - "Bifurcação por modo CEDO em _condition_matches (regex no haystack lowercase-só vs texto no normalizado)"
    - "Normalização simétrica value↔haystack via _normalize_text (Pitfall 2)"
    - "Fonte-única _prepare_haystacks compartilhada por match_templates e evaluate_groups (D-09)"
key-files:
  created:
    - backend/tests/classification/test_matcher_norm.py
  modified:
    - backend/app/classification/matcher.py
decisions:
  - "D-01: NORMALIZAÇÃO (não N-de-M) como mecanismo de tolerância — confiança segue booleana 1.0/0.0"
  - "D-02: normalização simétrica (value E haystack pela MESMA _normalize_text) resolve acento/caixa/quebra/pontuação"
  - "D-03: ramo regex INTACTO — roda contra haystack lowercase-só (não normalizado); ReDoS/timeout/tetos preservados byte-a-byte"
  - "D-04: palavra trocada NÃO resolvida por normalização (tradeoff aceito — fica para a ferramenta de testar sinais)"
  - "D-09: evaluate_groups público reusa _prepare_haystacks do match_templates → agregado idêntico (base do preview)"
metrics:
  duration_min: 9
  completed: 2026-06-25
  tasks: 2
  files: 2
---

# Phase 10 Plano 01: Matcher tolerante por normalização + evaluate_groups Summary

Matcher de sinais ganhou tolerância MECÂNICA via `_normalize_text` (NFKD sem acento + lower + pontuação→espaço + colapsa espaços) aplicada simetricamente a sinal e haystack SÓ no ramo `texto`; o ramo `regex` permanece intacto rodando contra o haystack lowercase-só (ReDoS/timeout/tetos preservados). Expõe o helper público `evaluate_groups` que reusa a mesma preparação de haystack do `match_templates` e devolve relatório por-grupo/condição — fundação do preview de sinais do Plano 02.

## What Was Built

- **`_normalize_text(s)`** — função pura: `unicodedata.normalize("NFKD")` + drop de combinantes (corpo COPIADO de `naming._strip_accents`, NÃO importado — Pitfall 8) + `.lower()` + `_PUNCT_RE`→espaço + `_WS_RE` colapsa + `.strip()`. Documentada como não-logante (V7).
- **Bifurcação por modo em `_condition_matches(cond, haystack_norm, haystack_lower)`** — bifurca CEDO (Pitfall 1): `regex` usa `haystack_lower` (D-03, corpo de ReDoS/timeout/tetos byte-a-byte); `texto`/default usa `needle = _normalize_text(value)` contra `haystack_norm` (simetria D-02), needle vazio → falha fechada.
- **`_prepare_haystacks(full_text)`** — fonte-única que monta os dois haystacks (lowercase-só + normalizado); compartilhada por `match_templates` e `evaluate_groups` para garantir resultado idêntico (D-09).
- **`evaluate_groups(groups, full_text)` PÚBLICO** + dataclasses `ConditionReport(mode, value, matched)` e `GroupReport(matched, conditions)` — relatório por-grupo/condição; `matched` do grupo = E das condições. Consumido pelo preview (Plano 02).
- **Suíte RED→GREEN** `test_matcher_norm.py` cobrindo D-02 (acento/quebra/caixa/pontuação/simetria), D-04 (palavra trocada não casa), D-03 (regex no lowercase-só + ReDoS/teto intactos), D-09 (evaluate_groups + agregado bate com match_templates) e unit de `_normalize_text`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wave 0 — suíte RED de normalização + não-regressão regex | f43a45b | backend/tests/classification/test_matcher_norm.py |
| 2 | GREEN — _normalize_text, bifurcação por modo, evaluate_groups | 9836f9d | backend/app/classification/matcher.py (+ ajuste de teste) |

## Verification

- `tests/classification/test_matcher_norm.py` + `test_matcher_groups.py` + `test_matcher.py`: 34 passed.
- Suíte completa `tests/classification`: **57 passed** (zero regressão D-03; ReDoS/tetos/legado verdes).
- `ruff check` em matcher.py e test_matcher_norm.py: limpo.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Expectativa incorreta no unit de `_normalize_text`**
- **Found during:** Task 2 (verificação GREEN)
- **Issue:** O teste (que eu mesmo escrevi na Task 1) esperava `Nº123` → `n123`. NFKD expande o ordinal `º` para `o` (não é combinante), produzindo `no123`. A implementação está correta; a expectativa do teste estava errada.
- **Fix:** Ajustada a entrada do caso para `N123!` e adicionada nota explicando o comportamento do NFKD com `º`. Sem mudança na implementação.
- **Files modified:** backend/tests/classification/test_matcher_norm.py
- **Commit:** 9836f9d

## TDD Gate Compliance

- RED gate: `test(10-01)` commit f43a45b (suíte falhando por símbolo/comportamento ausente).
- GREEN gate: `feat(10-01)` commit 9836f9d (implementação + suíte verde).
- REFACTOR: não necessário (implementação limpa de primeira; lint verde).

## Threat Surface

Nenhuma superfície nova. T-10-02 (ReDoS) mitigado por não-regressão: ramo regex preservado byte-a-byte com `timeout=_REGEX_TIMEOUT_S` + tetos (testado). T-10-01 (tampering) mitigado: dispatch explícito por etiqueta (nunca `eval`), normalização simétrica, falha-fechada para needle vazio. T-10-IL: `_normalize_text` documentada como não-logante; nenhum log de conteúdo introduzido. Zero dependência nova (só `re`/`unicodedata` stdlib + `regex` já presente) — sem checkpoint de instalação.

## Self-Check: PASSED
- FOUND: backend/app/classification/matcher.py
- FOUND: backend/tests/classification/test_matcher_norm.py
- FOUND commit: f43a45b
- FOUND commit: 9836f9d

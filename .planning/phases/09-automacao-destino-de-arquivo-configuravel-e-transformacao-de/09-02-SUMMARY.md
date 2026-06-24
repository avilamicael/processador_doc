---
phase: 09-automacao-destino-de-arquivo-configuravel-e-transformacao-de
plan: 02
subsystem: automation
tags: [automation, naming, filters, transformation, security, no-eval]
requires:
  - "naming._substitute / resolve_pattern / _fmt_date (Fase 6)"
  - "naming.resolve_dest_folder reescrito (09-01)"
  - "naming.sanitize_component (D-08, passo final por segmento)"
provides:
  - "engine de filtros inline encadeáveis {campo:filtro=arg:filtro} (D-06/D-07)"
  - "conjunto v1: palavras/letras/truncar/maiusc/minusc/sem_acento/substituir/formato/padrao"
  - "_strip_accents (NFKD) + dispatch explícito por filtro (T-09-05, sem eval)"
  - "padrao= suprime o bloqueio D-07 de campo ausente (A3)"
affects:
  - "todo name_pattern (rename) E todo segmento de dest_folder (move/copy) — _substitute é o ponto único"
tech-stack:
  added: []
  patterns:
    - "Parser de pipeline de filtros via split por ':' + dispatch EXPLÍCITO por nome (espelha rules._OPERATORS / V5 — nunca eval/format dinâmico)"
    - "Filtro desconhecido OU int() inválido = INERTE (falha-fechada, não quebra o token)"
    - "padrao= detectado ANTES de _MissingField (A3) — supre o bloqueio de campo ausente"
    - "Retrocompat: spec sem '=' contendo aaaa/mm/dd → _fmt_date legado; senão pipeline"
    - "Ordem D-08: filtros transformam → sanitize_component DEPOIS (por segmento)"
    - "unicodedata.normalize('NFKD') + drop combining para sem_acento (stdlib, sem dep)"
key-files:
  created: []
  modified:
    - backend/app/automation/naming.py
    - backend/tests/automation/test_naming.py
decisions:
  - "[09-02] Engine de filtros inline em _substitute via pipeline split-por-':' + dispatch EXPLÍCITO (_apply_filter), nunca eval (T-09-05). Filtro desconhecido e int() inválido = inerte (falha-fechada amigável)."
  - "[09-02] padrao= resolvido por _has_padrao ANTES de levantar _MissingField (A3 RESOLVED): campo ausente + padrao=X usa X como value; campo presente → padrao é no-op."
  - "[09-02] Atalho legado {data:aaaa-mm} preservado (A1): spec SEM '=' que casa aaaa|mm|dd cai em _fmt_date; o resto vira pipeline. formato= é a forma canônica nova e coexiste."
  - "[09-02] Sanitização permanece a cargo de resolve_pattern/resolve_dest_folder (sanitize_component DEPOIS, D-08); o pipeline NÃO sanitiza — comprovado por test_sanitize_after_filter (substituir=a>/ → '/'→'_')."
  - "[09-02] _TOKEN_RE inalterado: group(2) já captura tudo após o 1º ':' (inclusive ':' internos), então o split no repl basta para a cadeia — sem mudar a regex."
metrics:
  duration: ~8 min
  tasks: 2
  files_modified: 2
  completed: 2026-06-24
---

# Phase 9 Plan 02: Engine de Filtros Inline (Transformação de Valores) Summary

Implementação do ENGINE DE TRANSFORMAÇÃO (backlog item 11 / BL-11): filtros inline encadeáveis no token (`{campo:filtro=arg:filtro}`, D-06) com o conjunto v1 (D-07) — `palavras=N`, `letras=N`/`truncar=N`, `maiusc`, `minusc`, `sem_acento`, `substituir=de>para`, `formato=` (expondo `_fmt_date`) e `padrao=` (default que supre o bloqueio de campo ausente). O dispatch é explícito por nome (nunca `eval`); filtro desconhecido é inerte; a sanitização de chars proibidos do Windows roda DEPOIS dos filtros, por segmento (D-08). Vale tanto para `name_pattern` (rename) quanto para segmentos de `dest_folder` (move/copy), pois ambos passam por `_substitute`.

## What Was Built

- **`_apply_filter(value, f)`** — dispatch EXPLÍCITO por nome de filtro: `palavras=N` (`" ".join(split()[:N])`), `letras=N`/`truncar=N` (`value[:N]`), `maiusc`/`minusc` (caixa), `sem_acento` (`_strip_accents`), `substituir=de>para` (`partition(">")` + `replace`), `formato=spec` (`_fmt_date`; None → `_MissingField`), `padrao=` (no-op aqui, resolvido antes). Filtro desconhecido ou `int()` inválido → **inerte** (devolve o value cru). Nunca `eval`/`exec` (T-09-05).
- **`_apply_filter_pipeline(value, filters)`** — aplica a cadeia em ORDEM (D-06).
- **`_strip_accents(s)`** — `unicodedata.normalize("NFKD")` + drop dos combining (stdlib pura, sem dependência).
- **`_has_padrao(filters)`** — extrai `padrao=X` da cadeia; usado para SUPRIMIR o bloqueio D-07 quando o campo está ausente/vazio (A3).
- **`_substitute.repl` reescrito** — split do `spec` por `:` em filtros; resolve `padrao=` antes de levantar `_MissingField`; mantém o atalho legado `{data:aaaa-mm}` (spec sem `=` casando `aaaa|mm|dd` → `_fmt_date`); senão roda o pipeline. `sanitize_component` continua DEPOIS (caller), preservando D-08.
- **Testes (RED→GREEN):** 16 casos novos cobrindo cada filtro, encadeamento, `padrao=` (ausente e presente), atalho legado, ordem sanitize D-08, filtro desconhecido/inválido inerte, filtro por segmento de pasta, e um guard estrutural `test_no_eval_in_naming_module`.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 (RED) | Testes de filtros inline falhando (conjunto v1 D-07) | a1dfc6f | test_naming.py |
| 2 (GREEN) | Engine de filtros inline (dispatch explícito, sem eval) | 71138a6 | naming.py |

## Deviations from Plan

None — plano executado exatamente como escrito. Sem REFACTOR (implementação já limpa com dispatch explícito; nenhum cleanup necessário). Sem mudança de schema, sem nova dependência (só `unicodedata` da stdlib).

## must_haves — verificação

| Truth | Status |
| ----- | ------ |
| `{fornecedor:palavras=1}` sobre 'IGUACU DIST. DE PROD.' → 'IGUACU' | ✅ test_filter_palavras |
| `{x:letras=8}`/`{x:truncar=8}` truncam a 8; `{x:maiusc}`/`{x:minusc}` mudam caixa | ✅ test_filter_letras/_truncar/_maiusc/_minusc |
| `{x:sem_acento}` sobre 'IGUAÇU AÇÃO' → 'IGUACU ACAO' | ✅ test_filter_sem_acento |
| `{x:substituir=de>para}` substituição literal simples | ✅ test_filter_substituir |
| Campo ausente + `{x:padrao=Geral}` → 'Geral' (não bloqueia) | ✅ test_filter_padrao_default_when_missing |
| `{data:formato=aaaa-mm-dd}` formata; legado `{data:aaaa-mm}` continua | ✅ test_filter_formato_explicit / test_legacy_date_shortcut_still_works |
| Filtros encadeáveis `{x:maiusc:palavras=2}` (pipeline) | ✅ test_filter_chain |
| Sanitização Windows roda DEPOIS dos filtros (D-08) | ✅ test_sanitize_after_filter (`a>/` → `/`→`_`) |
| `{campo}` simples e testes legados intactos (não-regressão) | ✅ test_plain_token_unchanged + 36 naming verdes |
| Filtro desconhecido inerte (nunca eval) | ✅ test_unknown_filter_is_inert / test_no_eval_in_naming_module |

## Threat Model — dispositions aplicadas

- **T-09-05 (Tampering, mitigate):** dispatch EXPLÍCITO por nome literal em `_apply_filter`; filtro desconhecido e `int()` inválido = inerte; `grep eval(\|exec(` em naming.py → vazio; `test_no_eval_in_naming_module` valida estruturalmente. ✅
- **T-09-06 (Tampering, mitigate):** `sanitize_component` roda DEPOIS dos filtros, por segmento (D-08) — `test_sanitize_after_filter` prova que um `/` introduzido por `substituir=a>/` vira `_`. ✅
- **T-09-07 (Info Disclosure, mitigate):** nenhum log de valor/padrão resolvido foi adicionado (V7/V9); helpers documentam "NÃO loga valores". ✅

## Verification

- `cd backend && uv run pytest tests/automation/test_naming.py -q` → **36 passed**.
- `cd backend && uv run pytest tests/automation -q` → **107 passed**, zero regressão.
- `cd backend && uv run pytest -q` (suíte completa) → **460 passed**.
- `grep -n "eval(\|exec(" backend/app/automation/naming.py` → vazio.

## Sem mudança de schema

Confirmado: `name_pattern`/`dest_folder` com filtros inline são apenas strings mais ricas. Nenhum modelo novo, nenhum Alembic, nenhuma dependência externa (só `unicodedata` da stdlib).

## Known Stubs

Nenhum. O engine de filtros v1 está completo e testado. (Regex e mapa de valores ficaram DEFERRED para v2 conforme D-07/CONTEXT.)

## Self-Check: PASSED
- Arquivos modificados existem (naming.py, test_naming.py). ✅
- Commits existem: a1dfc6f (RED), 71138a6 (GREEN). ✅
- Gate TDD: commit `test(...)` (a1dfc6f) precede `feat(...)` (71138a6). ✅

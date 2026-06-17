---
phase: 06-automa-es-de-arquivo-renomear-mover
plan: 02
subsystem: automation-engines
tags: [naming, rules, path-traversal, sanitization, decimal, pure-functions]
requires:
  - "app.config.get_settings (automation_max_component_len)"
provides:
  - "app.automation.naming.resolve_pattern / sanitize_component / resolve_dest_folder"
  - "app.automation.rules.Condition / Rule / evaluate_condition / rule_matches / first_matching_rule"
affects:
  - "app/automation/stage.py (Plan 04 — consome naming+rules para orquestrar apply)"
  - "app/api/automations.py (Plan 04 — CRUD de regras mapeia para Rule/Condition)"
tech-stack:
  added: []
  patterns:
    - "Função pura parse→normalizado-ou-None (espelha validation/dates.py, money.py)"
    - "Dispatch explícito por etiqueta (operador), NUNCA eval (espelha validation/fields.py)"
    - "Confinamento de destino via resolve() + is_relative_to (espelha api/watched_folders.py)"
    - "Coerção numérica via Decimal (espelha validation, T-04-05 — NUNCA float/string lexicográfica)"
key-files:
  created:
    - backend/app/automation/__init__.py
    - backend/app/automation/naming.py
    - backend/app/automation/rules.py
  modified: []
decisions:
  - "API dos módulos seguiu os testes RED (autoridade GREEN), não a nomenclatura tentativa do PLAN"
  - "fields é dict[str, str] (valores normalizados), não dict[str, FilledField] — caller mapeia FilledField→str"
  - "Sanitização em camadas: 9 chars Windows + neutralização de .. + reservados + trailing dot/space + truncamento MAX_PATH"
metrics:
  duration_min: 9
  completed: 2026-06-17
  tasks: 2
  files: 3
---

# Phase 6 Plan 02: Motores Puros (naming + rules) Summary

Dois motores PUROS e determinísticos da fase de automações: `naming.py` resolve padrões `{campo}`/`{campo:fmt}` em nomes/pastas sanitizados e confinados sob a raiz-base (path traversal V4 barrado na fronteira IA→filesystem), e `rules.py` avalia regras condicionais `=,>,<,contém` combinadas por E/OU com coerção numérica via `Decimal`, vencendo a primeira regra que casa por ordem de prioridade — ambos sem IA, sem disco e sem banco, tornando GREEN os 12 testes Wave 0.

## What Was Built

### Task 1 — `naming.py` (AUT-01/AUT-02/D-07/D-08, V4)
- `resolve_pattern(pattern, fields) -> str | None`: substitui tokens e sanitiza o nome final; campo faltante/vazio ou `{data:fmt}` sobre valor não-ISO → `None` (D-07, caller rebaixa para revisão — nunca aplica nome quebrado).
- `sanitize_component(value, max_len=None) -> str`: substitui os 9 chars proibidos do Windows (`< > : " / \ | ? *`) por `_` (isso já mata separadores embutidos — defesa V4 camada 1), neutraliza componentes "só pontos" (`..`/`.` → `_`), remove espaço/ponto finais, prefixa `_` em nomes reservados (CON/PRN/AUX/NUL/COM1-9/LPT1-9, case-insensitive sobre o stem), e trunca ao teto `automation_max_component_len` preservando a extensão (MAX_PATH, Pitfall 5).
- `resolve_dest_folder(pattern, fields, *, base_root) -> Path | None`: resolve e sanitiza cada SEGMENTO individualmente, depois confina via `(base_root / segmentos).resolve().is_relative_to(base_root.resolve())` (V4). Campo faltante ou destino que escaparia → `None`. Não cria pasta no disco (PURO).
- `_fmt_date(iso, spec)`: fatia `YYYY-MM-DD` e substitui `aaaa`/`mm`/`dd` no formato (ex.: `{data:aaaa-mm}` sobre `2026-06-17` → `2026-06`).

### Task 2 — `rules.py` (TPL-02/D-04/D-05, V5)
- `Condition` / `Rule`: dataclasses puras (a forma que o avaliador consome; persistência do Plan 01 é mapeada para elas pelo caller).
- `evaluate_condition(cond, fields) -> bool`: dispatch explícito por operador (NUNCA `eval`); `eq`/`contains` case-insensitive; `gt`/`lt` com coerção numérica obrigatória via `Decimal` quando ambos os lados são numéricos (Pitfall 2 — `Decimal(1500) > Decimal(500)`, não `"1500" > "500"`), fallback string para data ISO/texto; campo ausente → falso (não levanta); operador desconhecido → falso (falha fechada).
- `rule_matches(rule, fields) -> bool`: conjunção `and` (todas) / `or` (qualquer); regra sem condições não casa.
- `first_matching_rule(rules, fields) -> Rule | None`: ordena por `priority`, ignora `active=False`, devolve a primeira que casa (D-05) ou `None`.

## Verification

```
$ pytest tests/automation/test_naming.py tests/automation/test_rules.py -q
............                                                             [100%]
12 passed in 0.08s
```

Gates de aceitação:
- `naming.py`: `def resolve_pattern|sanitize_component|resolve_dest_folder` = 3; `is_relative_to` = 3 (≥1, V4 presente); `mkdir|os.replace` = 0 (módulo puro).
- `rules.py`: `def evaluate_condition|rule_matches|first_matching_rule` = 3; `eval(` = 0 (V5); `Decimal` = 10 (≥1, coerção presente).
- `ruff check` limpo em ambos.

Threat register: T-06-03 (path traversal) mitigado por sanitização + `is_relative_to` (teste `test_folder_traversal_blocked`); T-06-04 (nomes reservados) por `_WIN_RESERVED` (`test_sanitize_reserved_names`); T-06-05 (eval) por dispatch explícito (gate `eval(` == 0); T-06-06 (MAX_PATH) por truncamento.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - API alinhada aos testes RED] Nomenclatura dos símbolos públicos**
- **Found during:** Task 1 e Task 2 (leitura dos arquivos de teste alvo).
- **Issue:** O PLAN descrevia `resolve_folder_pattern`, `evaluate_rules(rules, fields)` e `fields: dict[str, FilledField]`, mas os testes RED autoritativos (`test_naming.py`/`test_rules.py`) chamam `resolve_dest_folder(..., base_root=)`, `sanitize_component(value)` (1 arg), `first_matching_rule`/`rule_matches`/`evaluate_condition`, e `Condition`/`Rule` definidos NO módulo, com `fields: dict[str, str]` (valores já normalizados).
- **Fix:** Implementei exatamente a API que os testes invocam (instrução do executor: tornar os testes GREEN de verdade). Os dois símbolos extras do PLAN não existem; o caller (Plan 04) mapeia `FilledField.normalized_value` → `dict[str, str]` antes de chamar, e seleciona o padrão de nome/pasta via `Rule.name_pattern`/`folder_pattern` resolvidos por `resolve_pattern`/`resolve_dest_folder`.
- **Files modified:** backend/app/automation/naming.py, backend/app/automation/rules.py.
- **Commits:** d585711, ad3a48d.

## Known Stubs

Nenhum. Ambos os módulos são lógica completa e testada; o efeito de disco e a orquestração persistente são responsabilidade declarada dos Plans 03/04 (não stub — separação de camadas por desenho).

## Self-Check: PASSED

- FOUND: backend/app/automation/__init__.py
- FOUND: backend/app/automation/naming.py
- FOUND: backend/app/automation/rules.py
- FOUND commit: d585711 (naming.py)
- FOUND commit: ad3a48d (rules.py)
- 12/12 testes verdes (test_naming.py + test_rules.py)

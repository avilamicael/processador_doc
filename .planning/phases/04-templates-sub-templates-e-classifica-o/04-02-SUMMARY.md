---
phase: 04-templates-sub-templates-e-classificacao
plan: 02
subsystem: validation
tags: [validation, modulo-11, cnpj, cpf, dateutil, decimal, redos, pydantic-types]

# Dependency graph
requires:
  - phase: 04-templates-sub-templates-e-classificacao
    plan: 01
    provides: "python-dateutil fixado nas deps + modelos FilledField (raw_value/normalized_value D-11, valid/invalid_reason D-10) que esta validação alimenta"
  - phase: 03-extracao-generica-via-ia-e-medicao-de-tokens
    provides: "Estilo módulo-função puro (extraction/pdf_io.py, router.choose como seam de despacho por etiqueta) espelhado aqui"
provides:
  - "Pacote validation/ puro (sem DB/IA/HTTP): doc_ids, dates, money, fields"
  - "Módulo 11 CNPJ/CPF PRÓPRIO (is_valid_cnpj/is_valid_cpf) sem dependência externa de DV"
  - "normalize_date dayfirst→ISO (ISO preservado), normalize_money_brl→Decimal, normalize_doc_id→dígitos"
  - "Orquestrador validate_field(*, field_type, raw, required, regex) → FieldValidation (despacho por tipo, marca sem bloquear, bruto+normalizado, regex segura)"
affects: [classificacao, stage, validacao-deterministica-fase7]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "fields.validate_field como seam de despacho por field_type (espelha extraction/router.choose) — Fases 5/7 consomem o mesmo resultado estruturado"
    - "Data: ISO via date.fromisoformat ANTES do dateutil dayfirst (ISO é não-ambíguo; dayfirst corromperia o mês)"
    - "Regex do operador via re.fullmatch sobre valor com teto _MAX_REGEX_LEN=4096 (mitigação ReDoS por desenho — T-04-03)"
    - "Moeda/número via Decimal (NUNCA float); parse falho → None + marca inválido (nunca chuta — T-04-05)"

key-files:
  created:
    - backend/app/validation/doc_ids.py
    - backend/app/validation/dates.py
    - backend/app/validation/money.py
    - backend/app/validation/fields.py
    - backend/tests/validation/test_doc_ids.py
    - backend/tests/validation/test_fields.py
  modified:
    - backend/app/validation/__init__.py

key-decisions:
  - "normalize_date tenta date.fromisoformat primeiro (ISO não-ambíguo) e só então dateutil dayfirst=True — aplicar dayfirst sobre ISO leria YYYY-MM-DD como dia↔mês trocados (bug pego pelo teste, Rule 1)"
  - "FieldValidation é dataclass simples (não Pydantic) — módulo puro sem dependência de validação de schema; o consumidor (Plan 05) mapeia para FilledField"
  - "Booleano reconhece conjunto pt-BR (sim/não/true/false/1/0/s/n/v/f) → normaliza para 'true'/'false'; desconhecido → inválido"
  - "Tipo desconhecido = passthrough (igual a 'texto') — D-08: tipo é só etiqueta opcional, default texto preserva comportamento de hoje"
  - "_MAX_REGEX_LEN=4096: valor acima do teto é recusado ANTES de tocar a engine de regex (mitiga ReDoS V5/T-04-03)"

patterns-established:
  - "Validador determinístico puro reutilizável: a Fase 7 (parsing determinístico) e a Fase 5 (gate de revisão) consomem validate_field sem reescrever lógica"
  - "Parse falho NUNCA chuta um valor: retorna None + invalid_reason, raw_value sempre preservado (D-10/D-11)"

requirements-completed: [EXT-04]

# Metrics
duration: 3min
completed: 2026-06-16
---

# Phase 4 Plan 02: Módulo de Validação Determinística Summary

**Pacote `validation/` puro (Módulo 11 CNPJ/CPF próprio, data dayfirst→ISO, moeda→Decimal) com o orquestrador `validate_field` que despacha por tipo, marca válido/inválido sem bloquear (D-10) e guarda bruto + normalizado (D-11) — o coração determinístico de EXT-04, consumível pela classificação (Plan 05) e pela Fase 7**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-06-16T21:11:24Z
- **Completed:** 2026-06-16
- **Tasks:** 2 (ambas TDD)
- **Files modified:** 7 (6 criados, 1 modificado)

## Accomplishments
- Módulo 11 CNPJ/CPF PRÓPRIO sem dependência externa de DV (CLAUDE.md Decisão Crítica 3): válidos passam, DV errado/repetidos/tamanho errado falham
- `normalize_date` dayfirst→ISO resolvendo a ambiguidade dia↔mês (Pitfall 3); ISO de entrada preservado via `date.fromisoformat`
- `normalize_money_brl` pt-BR → Decimal (NUNCA float — T-04-05); "1.234,56"→"1234.56", "R$ 2.000,00"→"2000.00"
- `validate_field` orquestrador: despacho por field_type (data/moeda/numero/cpf_cnpj/booleano/texto), marca válido/inválido SEM levantar (D-10), preserva bruto + normalizado (D-11)
- Regex do operador via `re.fullmatch` sobre valor com teto de 4096 chars (mitigação ReDoS por desenho — T-04-03)
- Suíte de validação verde: 37 testes (18 doc_ids + 19 fields); ruff limpo; sem float em moeda/número; sem import de lib externa de DV

## Task Commits

Cada tarefa seguiu o ciclo TDD RED→GREEN com commits atômicos:

1. **Task 1 RED: testes falhando de Módulo 11 + parsers** - `f1d4704` (test)
2. **Task 1 GREEN: doc_ids/dates/money** - `ff44390` (feat)
3. **Task 2 RED: testes falhando de validate_field** - `8af3760` (test)
4. **Task 2 GREEN: orquestrador fields.validate_field** - `52915d2` (feat)

## Files Created/Modified
- `backend/app/validation/doc_ids.py` - is_valid_cnpj/is_valid_cpf (Módulo 11 próprio, pesos w1/w2 e 10..2/11..2) + normalize_doc_id (só dígitos)
- `backend/app/validation/dates.py` - normalize_date: ISO via fromisoformat → fallback dateutil dayfirst=True → None
- `backend/app/validation/money.py` - normalize_money_brl: mantém dígitos/`,.-`, remove milhar `.`, troca `,`→`.`, valida via Decimal
- `backend/app/validation/fields.py` - FieldValidation (dataclass) + validate_field (despacho por tipo, required sem levantar, regex fullmatch + teto)
- `backend/app/validation/__init__.py` - docstring do pacote (substitui o scaffold vazio)
- `backend/tests/validation/test_doc_ids.py` - 18 casos pt-BR (CNPJ/CPF válidos/inválidos/repetidos, data dayfirst/ISO/lixo, moeda milhar/símbolo/lixo)
- `backend/tests/validation/test_fields.py` - 19 casos (despacho por tipo, bruto preservado, obrigatório sem levantar, regex fullmatch/teto)

## Decisões Made
- **ISO antes do dayfirst em normalize_date:** o plano descrevia `dtparser.parse(raw, dayfirst=True)` direto, mas isso lê "2026-04-03" como dia↔mês trocados (vira "2026-03-04"). Resolvi tentando `date.fromisoformat` primeiro (ISO é não-ambíguo) e só caindo no dateutil dayfirst para os formatos pt-BR (dd/mm/aaaa). Resultado: ISO preservado E pt-BR dayfirst, ambos corretos.
- **FieldValidation como dataclass (não Pydantic):** mantém o módulo 100% puro/sem dependências de schema; o consumidor (Plan 05 classify_stage) mapeia para o modelo FilledField.
- **Tipo desconhecido = passthrough:** alinhado a D-08 (tipo é etiqueta opcional, default texto) — não inventa validação para tipos fora do conjunto.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] normalize_date corrompia datas ISO sob dayfirst=True**
- **Found during:** Task 1 GREEN (teste `test_date_iso_preservado` falhou)
- **Issue:** A implementação literal do plano (`dtparser.parse(raw, dayfirst=True)`) lia "2026-04-03" como "2026-03-04" — o `dayfirst` força o segundo componente a virar dia mesmo em entrada ISO não-ambígua, corrompendo o mês (exatamente a classe de bug do Pitfall 3 / T-04-05 que o plano queria evitar).
- **Fix:** tentar `date.fromisoformat(s)` primeiro (ISO é não-ambíguo, preserva fielmente) e só então cair no `dtparser.parse(s, dayfirst=True)` para os formatos pt-BR. O contrato externo (dayfirst para dd/mm/aaaa, None em lixo) permanece idêntico.
- **Files modified:** backend/app/validation/dates.py
- **Commit:** ff44390 (incluído no GREEN da Task 1)

(O teste foi escrito na fase RED com a expectativa correta — "2026-04-03" → "2026-04-03" — e foi ele que expôs o bug antes de qualquer integração. TDD funcionando como gate.)

## Issues Encountered
- Ruff: `zip()` sem `strict=` em doc_ids (B905) e organização de imports nos testes — resolvidos (`strict=True` é correto pois slices e pesos têm comprimento igual por construção; imports auto-organizados). Sem impacto funcional.

## User Setup Required
None - módulo puro, sem configuração de serviço externo. python-dateutil já fixado no Plan 04-01.

## Next Phase Readiness
- `validate_field` pronto para o Plan 05 (classify_stage) consumir: aplica validação+normalização por campo do template (TemplateField.field_type/required/regex) → preenche FilledField (raw_value/normalized_value/valid/invalid_reason).
- Reutilizável pela Fase 7 (parsing determinístico) sem reescrever lógica de DV/normalização.
- Sem blockers.

## Self-Check: PASSED

Todos os 7 arquivos criados/modificados existem; os 4 commits de tarefa (f1d4704, ff44390, 8af3760, 52915d2) estão presentes no histórico; suíte de validação 37/37 verde; ruff limpo.

---
*Phase: 04-templates-sub-templates-e-classifica-o*
*Completed: 2026-06-16*

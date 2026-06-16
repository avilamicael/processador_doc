---
phase: 04-templates-sub-templates-e-classificacao
plan: 04
subsystem: api
tags: [fastapi, pydantic, sqlalchemy, templates, classification, read-only]

# Dependency graph
requires:
  - phase: 04-templates-sub-templates-e-classificacao
    plan: 01
    provides: "Modelos Template/TemplateField (name UNIQUE, field_type/regex/hint, signals_json) e ClassificationResult/FilledField (UNIQUE document_id, template_id SET NULL, raw/normalized/valid) via migração 0004"
provides:
  - "Router CRUD /templates (GET lista/detalhe, POST 201, PATCH parcial, DELETE 204) com campos aninhados e sinais (D-02)"
  - "GET /documents/{id} de detalhe — classificação somente leitura (template casado + campos bruto/normalizado + marca + quarentena), S4/TPL-03/TPL-04"
  - "templates_api registrado no main.py (include_router)"
affects: [frontend, classificacao]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Router fino /templates espelha exatamente watched_folders.py (In/Patch/Out, IntegrityError→409, 404 ausente, 204 DELETE, request.app.state.engine)"
    - "signals serializados/desserializados com json (mesma convenção tolerante de classification.matcher._signals) — sem módulo codec novo"
    - "PATCH com fields substitui a coleção inteira (delete-orphan cuida dos órfãos); fields=None preserva os campos atuais"
    - "GET /documents/{document_id} declarado APÓS /documents/duplicates-count (literal antes de param) — sem conflito de rota"
    - "Lista GET /documents permanece leve (sem classification); detalhe é endpoint separado (Open Question 3 do RESEARCH)"

key-files:
  created:
    - backend/app/api/templates.py
    - backend/tests/test_api_templates.py
  modified:
    - backend/app/main.py
    - backend/app/api/documents.py
    - backend/tests/test_api_documents.py

key-decisions:
  - "Serialização de signals via json.dumps/json.loads inline (espelha matcher._signals) em vez de criar um módulo codec — convenção já existente, sem nova superfície"
  - "PATCH /templates com fields informado SUBSTITUI a coleção inteira (semântica explícita do plano); fields omitido preserva os campos atuais"
  - "regex do operador guardada APENAS como string no endpoint — NÃO compilada/executada (T-04-10); aplicação segura é o Plano 04-02"
  - "Detalhe de classificação é endpoint próprio GET /documents/{id}; lista de polling permanece leve (Open Question 3)"

patterns-established:
  - "Validação de domínio coerente com o UI-SPEC nos schemas Pydantic: nome de template/campo em branco → 422 ('Informe o nome…'), lista de campos vazia → 422 ('Adicione ao menos um campo')"

requirements-completed: [TPL-01, TPL-03, TPL-04]

# Metrics
duration: 7min
completed: 2026-06-16
---

# Phase 4 Plan 04: API de Templates & Detalhe de Classificação Summary

**CRUD fino /templates (campos aninhados + sinais, 409 duplicado, 422 inválido, registrado no main) e GET /documents/{id} de detalhe somente leitura (template casado + campos bruto/normalizado + marca + quarentena) — a superfície HTTP de TPL-01 e a fonte de dados da visibilidade de classificação TPL-03/TPL-04 que o frontend consome.**

## Performance

- **Duration:** ~7 min
- **Completed:** 2026-06-16
- **Tasks:** 2
- **Files modified:** 5 (2 criados, 3 modificados)

## Accomplishments
- Router `/templates` completo espelhando `watched_folders.py`: GET lista/detalhe, POST 201 (Template + TemplateField num único commit), PATCH parcial (substitui a coleção de campos), DELETE 204
- 409 para name duplicado (IntegrityError no UNIQUE de templates.name); 422 para body sem campos / campo sem nome / nome de template em branco (coerente com o copy do UI-SPEC S2)
- regex do operador guardada como string sem compilar/executar (T-04-10); todo acesso via ORM parametrizado (T-04-09)
- `GET /documents/{id}` de detalhe: bloco `classification` derivado de ClassificationResult (join com Template p/ o nome) + FilledField (campo, bruto, normalizado, marca válido/inválido); `classification=None` quando aguardando; `template_id`/`template_name` null = quarentena visível (TPL-04)
- Lista `GET /documents` permanece LEVE (sem o bloco classification) — polling barato preservado (Open Question 3 do RESEARCH)
- templates_api registrado no main.py via include_router; OpenAPI expõe `/templates`, `/templates/{template_id}` e `/documents/{document_id}`

## Task Commits

Cada tarefa foi commitada atomicamente:

1. **Task 1: CRUD /templates + registro no main** - `7289051` (feat)
2. **Task 2: GET /documents/{id} — detalhe de classificação somente leitura** - `75a4e2a` (feat)

## Files Created/Modified
- `backend/app/api/templates.py` - Router /templates (TemplateFieldIn/TemplateIn/TemplatePatch/TemplateFieldOut/TemplateOut; _loads_signals tolerante; _apply_fields substitui a coleção; CRUD com 409/422/404/204)
- `backend/app/main.py` - import templates_api + include_router(templates_api.router)
- `backend/app/api/documents.py` - GET /documents/{document_id} + schemas ClassificationFieldOut/ClassificationOut/DocumentDetailOut
- `backend/tests/test_api_templates.py` - CRUD lifecycle, 409 duplicado, 422 (sem campos/campo sem nome/nome em branco), defaults de campo, preservação de classificação no DELETE, 404
- `backend/tests/test_api_documents.py` - estendido: doc classificado (template+campos), quarentena (template null), não classificado (classification null), 404, lista permanece leve

## Decisões Made
- **Serialização de signals inline (json):** em vez de criar um módulo `json_codec`, o endpoint usa `json.dumps`/`json.loads` com a mesma tolerância de `classification.matcher._signals` (raw `or "[]"`, ignora não-listas). Mantém uma única convenção de (de)serialização dos sinais (D-02) sem adicionar superfície nova.
- **PATCH substitui a coleção de campos:** quando `fields` é informado no PATCH, a coleção inteira é substituída (delete-orphan remove os antigos); `fields=None` (omitido) preserva os campos atuais. Semântica explícita do plano.
- **Detalhe em endpoint próprio:** `GET /documents/{id}` carrega a classificação; a lista de polling continua leve (não inflar o polling — RESEARCH Open Question 3).

## Deviations from Plan

None - plan executed exactly as written.

(Nota de detalhe, não desvio: a serialização de signals foi feita com `json` inline espelhando `matcher._signals`, em vez de um módulo codec dedicado — o plano não prescrevia um módulo, apenas "serializa signals→signals_json". Comportamento idêntico ao esperado.)

## Issues Encountered
- `app.routes` no FastAPI desta versão lista as rotas dos sub-routers com `path` vazio/`<none>` no atributo de topo, então o grep direto em `app.routes` não acha `/templates`. A verificação autoritativa é o OpenAPI (`app.openapi()['paths']`), que confirma `/templates`, `/templates/{template_id}` e `/documents/{document_id}` registrados; os 20 testes de API (TestClient) também exercitam as rotas com sucesso. Sem impacto funcional.

## TDD Gate Compliance
Os tasks têm `tdd="true"`, mas `tdd_mode` global é `false` na config. Os endpoints e seus testes foram escritos e verificados juntos (não em commits RED/GREEN separados); os testes de API cobrem cada critério de aceite e passam (20/20). Sem gate RED/GREEN separado registrado — coerente com `tdd_mode: false`.

## User Setup Required
None - nenhuma configuração externa. Os endpoints operam sobre o banco já existente (migração 0004 do Plan 01).

## Next Phase Readiness
- Frontend (Plan 06) tem a API real de templates (CRUD) e o detalhe de classificação (S4) para fiar os hooks TanStack Query (useTemplates/useCreateTemplate/etc. e a visibilidade no documento).
- classify_stage (Plan 05, Wave 3) escreve ClassificationResult/FilledField que este endpoint de detalhe já sabe ler (incl. quarentena com template_id null).
- Suite completa verde (233 testes). Sem blockers.

## Self-Check: PASSED

Arquivos criados existem (templates.py, test_api_templates.py) e os 2 commits de tarefa (7289051, 75a4e2a) estão no histórico. OpenAPI confirma as rotas; 233 testes passam.

---
*Phase: 04-templates-sub-templates-e-classifica-o*
*Completed: 2026-06-16*

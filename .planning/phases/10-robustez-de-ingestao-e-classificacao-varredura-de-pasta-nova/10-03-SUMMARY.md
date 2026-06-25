---
phase: 10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova
plan: 03
subsystem: api/documents
tags: [reprocess, classificacao, quarentena, em_revisao, idempotencia]
requires:
  - "10-01 (matcher/normalização — classify_stage recarrega templates a cada run)"
  - "api/documents.py (_requeue, _build_detail, _folder_path_for, reclassify_document como análogo)"
provides:
  - "POST /documents/{id}/reprocess (single, sem template forçado)"
  - "POST /documents/reprocess (batch por bucket quarentena|em_revisao ou ids)"
  - "_reprocess_one helper (apaga CR + transition PROCESSANDO + requeue classify sem forced)"
affects:
  - "frontend (Plano 10-05) — botões 'reprocessar' / 'reprocessar todos'"
tech-stack:
  added: []
  patterns:
    - "Guard de estado semântico explícito ANTES do transition (allowlist da state machine não basta — PROCESSANDO é alcançável de vários estados)"
    - "Apagar ClassificationResult antes do requeue (idempotência do classify_stage faria no-op)"
    - "Batch numa única sessão; ids inelegíveis/ausentes ignorados (idempotente)"
    - "Rota POST de coleção registrada ANTES de GET /documents/{id} (evita 422 do conversor int)"
key-files:
  created: []
  modified:
    - backend/app/api/documents.py
    - backend/tests/test_api_documents.py
decisions:
  - "Batch aceita XOR bucket|ids (422 se ambos None ou ambos preenchidos)"
  - "Reprocess aceita QUARENTENA E EM_REVISAO; CONCLUIDO/RECEBIDO/FALHA → 409"
  - "Usar HTTP_422_UNPROCESSABLE_CONTENT (constante não-deprecada) no endpoint novo"
metrics:
  duration: ~25min
  completed: 2026-06-25
---

# Phase 10 Plan 03: Reprocess automático (sem template forçado) Summary

Reprocess de documentos em QUARENTENA/EM_REVISAO re-rodando matcher→(IA)→filler com os templates ATUAIS sem forçar template — por-documento e em lote por balde — espelhando `reclassify_document` mas sem `forced_template_id` (D-10/D-11/D-12).

## O que foi entregue

- **`POST /documents/{document_id}/reprocess`** (single, `DocumentDetailOut`): aceita QUARENTENA e EM_REVISAO; apaga o `ClassificationResult` existente (Pitfall 3); `transition(PROCESSANDO)`; re-enfileira `classify` com payload `{content_hash}` SEM `forced_template_id`. Guard semântico → 409 fora dos estados elegíveis (Pitfall 4); 404 se ausente.
- **`POST /documents/reprocess`** (batch, `ReprocessBatchOut`): body `ReprocessBatchIn` com XOR `bucket` ("quarentena"|"em_revisao") OU `ids`. Para `bucket`, resolve ids pelo mesmo filtro de `get_attention`; para `ids`, ignora silenciosamente ausentes e os fora de {QUARENTENA, EM_REVISAO}. Numa única sessão; retorna `{reprocessed: N}`.
- **`_reprocess_one`** helper compartilhado (single + batch): apaga CR → transition PROCESSANDO → requeue classify sem forced.
- Rota de coleção `POST /documents/reprocess` registrada ANTES de `GET /documents/{document_id}` (mesma razão de `/documents/delete` e `/documents/attention` — o conversor `int` daria 422 no path "reprocess").
- Cobertura de API em `test_api_documents.py`: single QUARENTENA (CR apagado + payload sem forced), single EM_REVISAO, CONCLUIDO→409, inexistente→404, batch por bucket (quarentena/em_revisao), batch por ids ignorando inelegíveis (idempotente), body inválido→422.

## must_haves cobertos

- Reprocess sem forçar template, transiciona PROCESSANDO, re-enfileira classify com `{content_hash}` (sem forced) — coberto + assert explícito `"forced_template_id" not in payload`.
- CR apagado antes do requeue (assert: 0 ClassificationResult após reprocess).
- Fora de QUARENTENA/EM_REVISAO → 409 (CONCLUIDO testado, não 500).
- Batch por balde re-enfileira todos os elegíveis, idempotente, retorna contagem.
- `classify_stage` recarrega templates do DB a cada run (herdado de 10-01) — pega edições pós-quarentena.

## Threat model

- **T-10-05 (EoP):** guard semântico explícito `state not in {QUARENTENA, EM_REVISAO}` → 409 antes do transition. Coberto.
- **T-10-05D (DoS):** batch numa só sessão; ids inelegíveis ignorados; requeue UNIQUE-safe via `_requeue`. Coberto.
- **T-10-05I (Info Disclosure):** docstrings + código logam só metadados; nenhum valor/conteúdo logado.
- **T-10-05T (Tampering):** CR apagado antes do requeue (Pitfall 3). Coberto.
- **T-10-SC:** nenhum pacote novo. Confirmado.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Uso de constante 422 não-deprecada**
- **Found during:** Task 2 (warnings no pytest)
- **Issue:** `status.HTTP_422_UNPROCESSABLE_ENTITY` está deprecado nesta versão de Starlette/FastAPI (emite `StarletteDeprecationWarning`).
- **Fix:** trocado por `status.HTTP_422_UNPROCESSABLE_CONTENT` no endpoint batch (constante existe na versão instalada).
- **Files modified:** backend/app/api/documents.py
- **Commit:** e7e3b51
- **Escopo:** só o código novo deste plano. A mesma deprecação em `test_api_automations.py` (pré-existente) ficou fora de escopo.

## Verificação

- `uv run pytest tests/test_api_documents.py -x -q` → 27 passed.
- `uv run pytest -q` (não-regressão completa) → 481 passed, 0 failed.

## Self-Check: PASSED

- FOUND: backend/app/api/documents.py (endpoints `reprocess_document` + `reprocess_documents`)
- FOUND: backend/tests/test_api_documents.py (8 testes de reprocess)
- FOUND commit 38df265 (feat — endpoints)
- FOUND commit e7e3b51 (test + 422 fix)

---
phase: 11-ux-e-visibilidade
plan: 01
subsystem: backend-api
tags: [documents-api, watcher, audit-log, timezone, dedup]
requires:
  - "backend/app/models/audit_log.py (AuditLog write-ahead, Fase 6)"
  - "backend/app/ingest/watcher.py scan_and_enqueue (Fase 2)"
provides:
  - "_as_utc(dt) — datas tz-aware nos *Out de documento (D-13)"
  - "RescanOut.skipped_duplicates + ScanResult (D-04)"
  - "GET /documents/{id}/audit → DocumentAuditOut (D-02)"
affects:
  - "frontend Waves 2+ (toast de rescan, tela de reverter, formatação de datas)"
tech-stack:
  added: []
  patterns:
    - "Helper de serialização único (_as_utc) preferido a field_serializer repetido"
    - "Literal de 3 estados (enqueued/duplicate/skipped) substitui bool no caminho do candidato"
    - "Endpoint read-only com sufixo específico (/audit) — sem string-building de SQL"
key-files:
  created: []
  modified:
    - "backend/app/api/documents.py"
    - "backend/app/ingest/watcher.py"
    - "backend/tests/test_api_documents.py"
    - "backend/tests/test_watcher.py"
decisions:
  - "Marcar naive como UTC (replace), NÃO converter (astimezone): a hora gravada já é UTC"
  - "skipped_duplicates conta SÓ duplicata-de-conteúdo (gate), não já-enfileirado/idempotência"
  - "can_undo = any(status==done), espelhando o critério de undo_document"
metrics:
  duration: "~25min"
  completed: "2026-06-25"
  tasks: 3
  files: 4
---

# Phase 11 Plan 01: Fundação backend (datas tz-aware + dedup visível + audit por documento) Summary

Três correções/exposições de leitura no backend que as Waves de frontend consomem: serialização de `created_at` como UTC tz-aware (item 9/D-13), contagem de duplicatas puladas no `/rescan` (item 3/D-04) e um endpoint `GET /documents/{id}/audit` read-only que alimenta a tela de reverter (item 1/D-02).

## What Was Built

- **Task 1 — `_as_utc` (D-13):** helper único em `documents.py` que marca `datetime` naive como UTC (`replace(tzinfo=UTC)`, sem deslocar a hora) e devolve tz-aware inalterado se já tiver `tzinfo`. Aplicado em `DocumentOut` (lista) e `DocumentDetailOut` (`_build_detail`). Sem migração — tipo de coluna inalterado. Commit `6dea8c7`.
- **Task 2 — `skipped_duplicates` (D-04):** `_stabilize_hash_gate_enqueue` passou de `bool` para um `Literal["enqueued"|"duplicate"|"skipped"]`; `scan_and_enqueue` retorna `ScanResult(enqueued, skipped_duplicates)` (dataclass frozen). Call-site de startup usa `result.enqueued`; `RescanOut` ganhou `skipped_duplicates: int` e `rescan()` desempacota o par. Commit `071a7ca`.
- **Task 3 — `GET /documents/{id}/audit` (D-02):** `AuditEntryOut` + `DocumentAuditOut` (`items` + `can_undo`); rota read-only que faz `select(AuditLog).where(document_id==...).order_by(id.desc())`, 404 via `session.get(Document, ...)` se ausente, `can_undo = any(status=="done")`. `created_at` sai tz-aware via `_as_utc`. Commit `d6ead8a`.

## Verification

- `_as_utc(datetime(2026,6,24,18,4,2)).isoformat()` termina em `+00:00` (hora 18:04 preservada).
- `ScanResult` e `RescanOut.skipped_duplicates` existem; ambos os call-sites de `scan_and_enqueue` atualizados (grep não acha retorno tratado como int).
- `select(AuditLog)` presente em `documents.py`; rota não dispara undo nem escreve.
- `pytest tests/test_api_documents.py -x -q`: 31 passed. Subset `-k audit`: 4 passed. Subset `-k "rescan or scan"`: 5 passed.
- Suíte completa não regride: `pytest -q` → **497 passed** (warnings pré-existentes de SQLite datetime adapter e Starlette 422, fora de escopo).
- `ruff check` limpo nos 4 arquivos tocados.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Caminho do arquivo de teste divergente do plano**
- **Found during:** Tasks 2 e 3 (verificação automatizada referenciava `tests/test_documents_api.py`).
- **Issue:** O plano (`files_modified` e o comando `<automated>` da Task 3) aponta `backend/tests/test_documents_api.py`, mas o arquivo real da suíte é `backend/tests/test_api_documents.py` (convenção `test_api_*` do projeto). Criar o arquivo do plano duplicaria a fixture `client` e quebraria a convenção.
- **Fix:** Adicionei os testes de auditoria e os asserts de `skipped_duplicates` ao arquivo existente `tests/test_api_documents.py`; atualizei `tests/test_watcher.py` ao novo contrato `ScanResult`.
- **Files modified:** `backend/tests/test_api_documents.py`, `backend/tests/test_watcher.py`
- **Commits:** `071a7ca`, `d6ead8a`

**2. [Rule 1 - Regressão induzida] Testes de `test_watcher.py` tratavam o retorno como int**
- **Found during:** Task 2 (após mudar o tipo de retorno de `scan_and_enqueue`).
- **Issue:** `test_scan_*` em `test_watcher.py` assumiam `enqueued = await scan_and_enqueue(...)` como `int` — quebrariam com o novo `ScanResult`.
- **Fix:** Atualizei os 3 sites para `result.enqueued`/`result.skipped_duplicates` e adicionei assert de que o gate de dedup conta `skipped_duplicates == 1` (distinto do já-enfileirado, que é `skipped` e conta 0).
- **Files modified:** `backend/tests/test_watcher.py`
- **Commit:** `071a7ca`

## Semantic note (skipped_duplicates)

`skipped_duplicates` conta **apenas** o ramo do gate de dedup (`IngestedOriginal` já existe → `"duplicate"`). O caso "já enfileirado para (hash, ingest)" (idempotência da fila, antes do worker materializar o `IngestedOriginal`) é `"skipped"` e **não** entra na contagem — coerente com o que o usuário entende por "duplicata ignorada" no toast pós-varredura.

## Known Stubs

Nenhum. Todos os retornos são derivados de dados persistidos (AuditLog/IngestedOriginal); nenhum valor hardcoded flui para a resposta.

## Self-Check: PASSED

- FOUND: backend/app/api/documents.py (modificado)
- FOUND: backend/app/ingest/watcher.py (modificado)
- FOUND: backend/tests/test_api_documents.py (modificado)
- FOUND: backend/tests/test_watcher.py (modificado)
- FOUND commit 6dea8c7 (Task 1)
- FOUND commit 071a7ca (Task 2)
- FOUND commit d6ead8a (Task 3)

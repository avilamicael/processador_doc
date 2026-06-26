---
phase: quick-260626-fot
plan: 01
subsystem: backend/api
tags: [audit, split, bugfix, cosmetic]
requires: []
provides:
  - "GET /documents/{id}/audit filtra registros de materialização de split"
affects:
  - backend/app/api/documents.py
tech-stack:
  added: []
  patterns:
    - "Reuso do filtro de exclusão de split de stage._has_done no endpoint /audit"
key-files:
  created: []
  modified:
    - backend/app/api/documents.py
    - backend/tests/test_api_documents.py
decisions:
  - "Filtro aplicado no endpoint (camada de leitura), sem tocar no frontend nem no modelo — a linha espúria some sozinha quando o /audit para de retornar os registros de split."
metrics:
  duration: ~10 min
  completed: 2026-06-26
requirements: [QUICK-AUDIT-SPLIT]
---

# Quick 260626-fot: Fix audit split-materialize noise Summary

Excluir os `AuditLog` de materialização de split (`details` começando com `split_to_files:`) do endpoint `GET /documents/{id}/audit`, replicando o filtro já em produção em `stage._has_done`, para eliminar a linha "Movido" espúria (origem=destino) da tela "Operações aplicadas" sem mexer no frontend.

## O que foi feito

- **`backend/app/api/documents.py` (`get_document_audit`):**
  - Import: adicionado `or_` (linha 36) e `SPLIT_MATERIALIZE_DETAILS_PREFIX` (linha 41, ordenado como em `stage.py`).
  - `select(AuditLog)` do endpoint ganhou a mesma condição de `stage._has_done`:
    `or_(AuditLog.details.is_(None), ~AuditLog.details.startswith(SPLIT_MATERIALIZE_DETAILS_PREFIX))`.
  - `order_by(AuditLog.id.desc())` e a derivação de `can_undo` ficaram inalterados — passam a operar só sobre as rows reais.
  - Docstring do endpoint atualizada explicando a exclusão (referência ao padrão `_has_done`).
- **`backend/tests/test_api_documents.py`:**
  - Import de `SPLIT_MATERIALIZE_DETAILS_PREFIX`.
  - Teste de regressão `test_audit_excludes_split_materialize_rows`: cria um Document com 2 `AuditLog` status=done — (1) linha de split (`details` com prefixo, origem=destino) e (2) automação real (`details=None`, origem≠destino, `run_id`). Verifica `len(items) == 1` (só a real), `can_undo is True`.

## TDD

- **RED:** o novo teste falhou contra o código atual com `assert 2 == 1` (endpoint retornava as 2 rows).
- **GREEN:** após o filtro, o teste passa e a suíte do arquivo segue verde.
- Commit atômico RED+GREEN (código apenas): `0a2ec3b`.

## Verificação

- `pytest tests/test_api_documents.py -k audit` → **5 passed**.
- `pytest tests/test_api_documents.py` (suíte do arquivo) → **35 passed**.
- `ruff check` nos dois arquivos tocados → **All checks passed!**
- `grep "startswith(SPLIT_MATERIALIZE_DETAILS_PREFIX)" app/api/documents.py` → filtro presente (linha 740).

## Deviations from Plan

- **[Rule 3 - Blocking] Ordem do import ajustada para passar no ruff.** O plano sugeria
  `from app.models.audit_log import AuditLog, SPLIT_MATERIALIZE_DETAILS_PREFIX`, mas o ruff (isort)
  exige a constante antes da classe — convenção já usada em `stage.py:60`. Aplicado
  `from app.models.audit_log import SPLIT_MATERIALIZE_DETAILS_PREFIX, AuditLog` nos dois arquivos.
  Files: `documents.py`, `test_api_documents.py`. Commit: `0a2ec3b`.

Caso contrário, plano executado exatamente como escrito. Frontend, `_has_done` e o modelo não foram tocados.

## Known Stubs

Nenhum.

## Self-Check: PASSED

- FOUND: backend/app/api/documents.py (filtro presente, linha 740)
- FOUND: backend/tests/test_api_documents.py (teste `test_audit_excludes_split_materialize_rows`)
- FOUND commit: 0a2ec3b

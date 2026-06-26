---
phase: quick-260626-fot
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/api/documents.py
  - backend/tests/test_api_documents.py
autonomous: true
requirements: [QUICK-AUDIT-SPLIT]
must_haves:
  truths:
    - "GET /documents/{id}/audit não retorna os AuditLog de materialização de split (details começando com 'split_to_files:')"
    - "Automações reais (details NULL) continuam aparecendo no audit"
    - "can_undo reflete apenas automações reais (linhas de split não contam)"
    - "A tela 'Operações aplicadas' para de exibir a linha 'Movido' espúria (origem=destino) sem mexer no frontend"
  artifacts:
    - path: "backend/app/api/documents.py"
      provides: "get_document_audit com filtro de exclusão de split"
      contains: "SPLIT_MATERIALIZE_DETAILS_PREFIX"
    - path: "backend/tests/test_api_documents.py"
      provides: "teste de regressão para exclusão de split no audit"
      contains: "split_to_files:"
  key_links:
    - from: "backend/app/api/documents.py:get_document_audit"
      to: "app.models.audit_log.SPLIT_MATERIALIZE_DETAILS_PREFIX"
      via: "filtro or_(details IS NULL, NOT details.startswith(prefix))"
      pattern: "startswith\\(SPLIT_MATERIALIZE_DETAILS_PREFIX\\)"
---

<objective>
Corrigir achado cosmético em `GET /documents/{id}/audit`: hoje o endpoint retorna TODOS os
`AuditLog` do documento, incluindo os registros de materialização de split
(`action="apply"`, `details` começando com `SPLIT_MATERIALIZE_DETAILS_PREFIX = "split_to_files:"`).
Isso faz a tela "Operações aplicadas" exibir uma linha "Movido" espúria (origem=destino) para
documentos vindos de pasta com `split_to_files=true`.

FIX: aplicar no `select(AuditLog)` do endpoint o MESMO filtro de exclusão já usado em
`stage._has_done` (linhas 443-452): `or_(AuditLog.details.is_(None), ~AuditLog.details.startswith(SPLIT_MATERIALIZE_DETAILS_PREFIX))`.
Automações reais (details NULL) permanecem; só as linhas de split somem. `can_undo` (derivado das
rows) passa a refletir só automações reais.

Purpose: eliminar ruído na tela de auditoria/reverter sem tocar no frontend — a linha some sozinha
quando o endpoint para de retornar os registros de split.
Output: `documents.py` corrigido + teste de regressão em `test_api_documents.py`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

<interfaces>
<!-- Padrão de exclusão de referência (já em produção) — copiar a forma exata. -->

De backend/app/models/audit_log.py:28:
```python
SPLIT_MATERIALIZE_DETAILS_PREFIX = "split_to_files:"
```

De backend/app/automation/stage.py:443-452 (_has_done — padrão a replicar):
```python
select(AuditLog).where(
    AuditLog.document_id == document_id,
    AuditLog.status == "done",
    or_(
        AuditLog.details.is_(None),
        ~AuditLog.details.startswith(SPLIT_MATERIALIZE_DETAILS_PREFIX),
    ),
)
```

Estado ATUAL do endpoint (backend/app/api/documents.py:728-732 — sem o filtro):
```python
rows = session.scalars(
    select(AuditLog)
    .where(AuditLog.document_id == document_id)
    .order_by(AuditLog.id.desc())
).all()
```

Imports atuais a ajustar:
- documents.py:36 → `from sqlalchemy import delete, func, select`  (falta `or_`)
- documents.py:41 → `from app.models.audit_log import AuditLog`  (falta `SPLIT_MATERIALIZE_DETAILS_PREFIX`)
- test_api_documents.py:24 → `from app.models.audit_log import AuditLog`  (falta `SPLIT_MATERIALIZE_DETAILS_PREFIX`)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Excluir AuditLog de split do endpoint /audit + teste de regressão</name>
  <files>backend/app/api/documents.py, backend/tests/test_api_documents.py</files>
  <behavior>
    - RED primeiro: adicionar `test_audit_excludes_split_materialize_rows` no bloco de testes
      de audit (após a linha 870 de test_api_documents.py). O teste cria um Document e DOIS
      AuditLog status="done": (1) registro de split — `action="apply"`, `details` com o prefixo
      `f"{SPLIT_MATERIALIZE_DETAILS_PREFIX}..."` (ex.: source_path=dest_path para simular a linha
      espúria); (2) automação real — `details=None`, com `source_path`/`dest_path` distintos e
      `run_id`. GET /documents/{id}/audit deve retornar status 200, `len(items) == 1` (SÓ a
      automação real, com o source_path/dest_path dela), e `can_undo is True`. Rodar o teste e
      confirmar que FALHA contra o código atual (hoje retorna 2 itens).
    - GREEN depois: aplicar o filtro no endpoint para o teste passar.
  </behavior>
  <action>
    1. Em backend/tests/test_api_documents.py: adicionar `SPLIT_MATERIALIZE_DETAILS_PREFIX` ao
       import da linha 24 (`from app.models.audit_log import AuditLog, SPLIT_MATERIALIZE_DETAILS_PREFIX`).
       Escrever o teste de regressão descrito em <behavior>, reutilizando o padrão exato dos testes
       de audit existentes (fixture `client`, `get_session(schema_engine)`, `session.flush()` para
       obter `doc.id`, `session.commit()`). Rodar e confirmar RED.
    2. Em backend/app/api/documents.py: adicionar `or_` ao import da linha 36
       (`from sqlalchemy import delete, func, or_, select`) e `SPLIT_MATERIALIZE_DETAILS_PREFIX` ao
       import da linha 41 (`from app.models.audit_log import AuditLog, SPLIT_MATERIALIZE_DETAILS_PREFIX`).
    3. No `select(AuditLog)` de `get_document_audit` (~linha 728), adicionar ao `.where(...)` a mesma
       condição de exclusão usada em `stage._has_done`:
       `or_(AuditLog.details.is_(None), ~AuditLog.details.startswith(SPLIT_MATERIALIZE_DETAILS_PREFIX))`.
       Manter o `order_by(AuditLog.id.desc())` e a derivação de `can_undo` inalterados (passam a operar
       só sobre as rows reais). Atualizar a docstring do endpoint para mencionar que os registros de
       materialização de split são excluídos (referência ao padrão `_has_done`).
    NÃO tocar no frontend. NÃO alterar `_has_done` nem o modelo. Commit atômico (RED+GREEN juntos).
  </action>
  <verify>
    <automated>cd backend && python -m pytest tests/test_api_documents.py -x -q -k "audit"</automated>
  </verify>
  <done>
    O novo teste `test_audit_excludes_split_materialize_rows` passa (1 item retornado, can_undo=true);
    todos os testes de audit existentes continuam passando; `documents.py` importa `or_` e
    `SPLIT_MATERIALIZE_DETAILS_PREFIX` e o `select` do endpoint contém o filtro de exclusão.
  </done>
</task>

</tasks>

<verification>
- `cd backend && python -m pytest tests/test_api_documents.py -q` — toda a suíte do arquivo verde.
- `grep -n "startswith(SPLIT_MATERIALIZE_DETAILS_PREFIX)" backend/app/api/documents.py` — filtro presente no endpoint.
</verification>

<success_criteria>
- GET /documents/{id}/audit não retorna mais registros de split (details com prefixo `split_to_files:`).
- Automações reais (details NULL) continuam aparecendo; `can_undo` reflete só elas.
- Teste de regressão adicionado e verde; suíte existente intacta.
- Frontend não modificado.
</success_criteria>

<output>
Create `.planning/quick/260626-fot-fix-audit-split-materialize/260626-fot-SUMMARY.md` when done
</output>

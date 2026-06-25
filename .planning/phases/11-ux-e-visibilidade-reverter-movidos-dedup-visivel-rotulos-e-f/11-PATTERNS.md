# Phase 11: UX e visibilidade - Pattern Map

**Mapped:** 2026-06-25
**Files analyzed:** 8 (3 backend modified, 1 backend new schema/endpoint, 4 frontend modified)
**Analogs found:** 8 / 8 (todos têm analog no próprio codebase)

Fase é "expor capacidade existente + corrigir apresentação" — quase tudo tem analog
direto e recente no mesmo arquivo. Sem npm novo, sem motor novo (CONTEXT code_context).

---

## File Classification

| Arquivo (modificado/novo) | Role | Data Flow | Analog mais próximo | Match |
|---------------------------|------|-----------|---------------------|-------|
| `backend/app/api/documents.py` — GET audit por doc (item 1, D-02) | route | request-response (read) | `get_document` (mesmo arquivo, l.619-650) + `_build_detail` (l.226-264) | exact |
| `backend/app/api/documents.py` — `RescanOut.skipped_duplicates` (item 3, D-04) | route/schema | request-response | `RescanOut`/`rescan` (mesmo arquivo, l.177-181, 897-904) | exact |
| `backend/app/ingest/watcher.py` — `scan_and_enqueue` retorna skipped (item 3) | service | event-driven/batch | retorno atual de `scan_and_enqueue` (l.215-224, dedup ~l.155) | exact |
| `backend/app/api/documents.py` — tz-aware `created_at` (item 9, D-13) | route/schema | transform (serialização) | `watcher_status.py` (`get_last_scan_at` → `datetime.now(UTC)`) | role-match |
| `frontend/src/lib/api.ts` — `getDocumentAudit` (item 1) | utility (api client) | request-response | `getDocumentDetail` (l.76-78), `postUndo` (l.302) já existe | exact |
| `frontend/src/pages/DocumentsPage.tsx` — botão reverter + origem→destino (item 1) | component | request-response | `DocumentDetailModal` (l.371-524) + hooks de mutation | exact |
| `frontend/src/pages/DocumentsPage.tsx` — toast dedup (item 3, D-05) | component | request-response | `useRescan` (`useDocuments.ts` l.33-42) + footer dup chip (l.302-310) | role-match |
| `frontend/src/pages/DocumentsPage.tsx` / `StatusPill.tsx` — rótulo "pronto" + CTA (item 8, D-10/D-11) | component | transform (derivação) | `resolvePill` (`StatusPill.tsx` l.28-35) | exact |
| `frontend/src/pages/AutomationsPage.tsx` — `<select>` de campo + guard (item 4, D-07/D-08) | component | transform | input free-text (l.822-830) + painel "Campos do template" (l.704-729) + `activeTemplate` (l.449-454) | exact |

---

## Pattern Assignments

### `backend/app/api/documents.py` — NOVO `GET /documents/{id}/audit` (item 1, D-02)

**Role:** route · **Data flow:** request-response (read) · **Analog:** `get_document` + `_build_detail` (mesmo arquivo)

O endpoint novo lê `AuditLog` por `document_id` e devolve origem→destino/status/run_id
para a tela de detalhe alimentar o botão "Reverter". `POST /automations/undo` por
`document_id` JÁ existe (`automations.py:541`) — esta fase só adiciona o GET de leitura.

**Schema Out (espelhar o estilo `DocumentDetailOut`, l.159-168, e os campos do AuditLog):**
```python
class AuditEntryOut(BaseModel):
    """Uma operação aplicada a um documento (origem→destino), lida do AuditLog."""
    id: int
    action: str            # "apply" (move) | "copy"
    status: str            # "done" | "undone" | "undone_from_cas" | "intent"
    source_path: str | None
    dest_path: str | None
    run_id: str | None
    created_at: datetime   # tz-aware (ver item 9 — D-13)

class DocumentAuditOut(BaseModel):
    items: list[AuditEntryOut]
    can_undo: bool         # derivar: existe ao menos um status=="done"
```

**Padrão de rota (copiar de `get_document`, l.619-650 — registrar ANTES de qualquer
`{document_id}` mais genérico já está OK pois o sufixo `/audit` é específico):**
```python
@router.get("/documents/{document_id}/audit", response_model=DocumentAuditOut)
def get_document_audit(request: Request, document_id: int) -> DocumentAuditOut:
    engine = request.app.state.engine
    with get_session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"documento {document_id} não encontrado",
            )
        rows = session.scalars(
            select(AuditLog)
            .where(AuditLog.document_id == document_id)
            .order_by(AuditLog.id.desc())
        ).all()
        ...
```

**Convenções obrigatórias (do docstring do módulo, l.25-28):** NÃO logar valores;
`document_id: int` tipado na rota (sem string-building SQL); 404 quando ausente.
Import novo necessário: `from app.models.audit_log import AuditLog`.

**Fonte dos dados — `AuditLog` (`backend/app/models/audit_log.py`):** colunas
`action`, `status` ("intent"/"done"/"undone"/"undone_from_cas"), `source_path`,
`dest_path`, `run_id`, `content_hash`, `created_at` (já `DateTime(timezone=True)`).
`undo_document` reverte os `status=="done"` (`undo.py:168-183`) — daí `can_undo` =
existe alguma linha `done`.

---

### `backend/app/api/documents.py` — `RescanOut.skipped_duplicates` (item 3, D-04)

**Role:** route/schema · **Analog:** `RescanOut`/`rescan` no mesmo arquivo (l.177-181, 897-904)

**Estado atual:**
```python
class RescanOut(BaseModel):
    enqueued: int

@router.post("/rescan", response_model=RescanOut)
async def rescan(request: Request) -> RescanOut:
    ...
    enqueued = await scan_and_enqueue(engine, paths)
    return RescanOut(enqueued=enqueued)
```

**Mudança:** adicionar `skipped_duplicates: int` ao schema e propagar do `scan_and_enqueue`
(ver próximo item — a função precisa passar a devolver o par). Manter idempotência.

---

### `backend/app/ingest/watcher.py` — `scan_and_enqueue` retorna skipped (item 3)

**Role:** service · **Data flow:** event-driven/batch · **Analog:** o próprio `scan_and_enqueue` (retorno em l.215-224)

O dedup por `content_hash` incrementa `IngestedOriginal.duplicate_hits` e NÃO enfileira
(~l.155). Hoje a função retorna só `enqueued: int`. Para D-04, contar os skips por
duplicata durante a varredura e devolver junto — opção menos invasiva: retornar uma
tupla/dataclass `(enqueued, skipped_duplicates)` (atualizar os 3 chamadores: startup
l.234, `/rescan` em documents.py:903, e o supervisor). `LAST_SCAN_AT = datetime.now(UTC)`
ao final permanece (l.221).

**Atenção:** este arquivo também tem os call-sites de startup; manter o contrato de
retorno consistente nos 3 pontos para não quebrar o supervisor.

---

### `backend/app/api/documents.py` — timestamps tz-aware (item 9, D-13)

**Role:** route/schema · **Data flow:** transform (serialização) · **Analog:** `watcher_status.py`

**Diagnóstico confirmado (causa-raiz):**
- `watcher_status.py` devolve `last_scan_at = watcher.get_last_scan_at()`, que é
  `datetime.now(UTC)` (`watcher.py:221`) — **tz-aware** → Pydantic serializa com offset
  (`...+00:00`/`Z`). Por isso o `/watcher/status` "já está certo".
- `Document.created_at` é `mapped_column(DateTime(timezone=True), server_default=func.now())`
  (`models/document.py:83-85`), MAS o SQLite grava o `func.now()` como string **naive**
  (sem tz); ao ler, vem `datetime` naive → Pydantic serializa **sem offset**
  (`2026-06-24T18:04:02`). O frontend `new Date(iso)` então interpreta como hora LOCAL.

**Alvo (D-13): toda API serializar UTC tz-aware.** O analog correto é o padrão do
`watcher_status` (datetime já carrega `tzinfo=UTC`). Como `created_at` vem naive do
banco, o ponto de correção é **na borda de serialização** — anexar `tzinfo=UTC` a
datetimes naive antes/ao montar os `*Out`. Aplica-se a `DocumentOut.created_at`
(l.81, l.351), `DocumentDetailOut.created_at` (l.167, l.262) e ao `AuditEntryOut.created_at`
do endpoint novo. Padrão a replicar (de `watcher.py:221`):
```python
from datetime import UTC
# datetime naive lido do banco → declarar como UTC (não converter, só marcar):
created_at = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
```
**Discrição do planner (CONTEXT l.47):** decidir entre um validator/serializer reusável
nos schemas vs marcar na montagem. Preferir um único helper para não repetir em cada
`*Out`. NÃO mudar o frontend `formatDate` (paliativo rejeitado, D-13).

---

### `frontend/src/lib/api.ts` — `getDocumentAudit` (item 1)

**Role:** utility (api client) · **Analog:** `getDocumentDetail` (l.76-78), `postUndo` (l.302 — JÁ existe)

```typescript
// Auditoria de um documento (origem→destino/status/run_id — item 1, D-02).
export function getDocumentAudit(id: number): Promise<DocumentAudit> {
  return request<DocumentAudit>(`/documents/${id}/audit`)
}
```
`postUndo({ document_id })` JÁ existe (l.302) — reusar. Adicionar os tipos
`DocumentAudit`/`AuditEntry` em `frontend/src/types.ts` (espelhando `DocumentDetail`,
ver `types.ts` l.114-130 para o estilo de interface). Wrapper `request<T>` (l.45-63)
já trata erro/204 — não reimplementar fetch.

---

### `frontend/src/pages/DocumentsPage.tsx` — reverter + origem→destino (item 1)

**Role:** component · **Analog:** `DocumentDetailModal` (l.371-524)

O modal de detalhe é o ponto de plug (CONTEXT l.99). Adicionar uma seção que busca
`getDocumentAudit(docId)` (via `useQuery`, mesmo padrão de `detailQuery` l.372-375) e,
quando `can_undo`, renderiza origem→destino + botão "Reverter para a origem" que chama
uma mutation sobre `postUndo({ document_id })`.

**Padrão de mutation a criar em `useDocuments.ts` (copiar `useRescan`, l.33-42):**
```typescript
export function useUndoDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => postUndo({ document_id: id }),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ['documents'] })
      qc.invalidateQueries({ queryKey: ['document-detail', id] })
      qc.invalidateQueries({ queryKey: ['document-audit', id] })
    },
  })
}
```
**Convenções (code_context):** valores como TEXTO PURO (sem `dangerouslySetInnerHTML`);
botão segue `btn-primary`; paths em `cell-mono` (ver l.493-494). Reusar o estilo de
botão destrutivo com confirmação do `confirmDelete` (l.322-362) se o undo precisar de
confirmação.

---

### `frontend/src/pages/DocumentsPage.tsx` — toast dedup pós-varredura (item 3, D-05)

**Role:** component · **Analog:** `useRescan` (`useDocuments.ts` l.33-42) + footer dup chip (l.302-310)

`rescan.mutate()` é disparado pelo botão "Forçar varredura" (l.162-170). Hoje o
`postRescan` retorna `{ enqueued }`; após D-04 retorna `{ enqueued, skipped_duplicates }`.
Mostrar toast "X novos enfileirados, Y pulados por já existirem" no `onSuccess` da
mutation (acessível via `rescan.data` ou callback). **Não há lib de toast hoje** — usar
um estado efêmero local + render inline (padrão "code-and-config", sem npm novo; CONTEXT
l.94/code_context). O chip "{N} duplicados ignorados" do footer (l.302-310) mostra o
estilo de mensagem neutra (`var(--text-3)`) a reaproveitar.

Atualizar a assinatura de `postRescan` em `api.ts` (l.80-82) para o novo shape.

---

### `frontend/src/components/StatusPill.tsx` + `DocumentsPage.tsx` — rótulo "pronto" + CTA (item 8, D-10/D-11)

**Role:** component (derivação) · **Analog:** `resolvePill` (`StatusPill.tsx` l.28-35)

`resolvePill` JÁ deriva um rótulo do par `(state, lastCompletedStep)` — o caso
`aguardando_extracao` (l.31-33) é o molde EXATO. Adicionar um ramo para D-10:
```typescript
if (state === 'processando' && lastCompletedStep === 'classificado') {
  return { label: 'Classificado — pronto', token: 'tratado' }  // ou token distinto
}
```
**Tokens travados (code_context):** usar os `--st-*` existentes (`tratado`/`encontrado`/
`leitura`); NÃO inventar token novo nem estado persistido novo (rótulo é DERIVADO).
O backend já expõe `last_completed_step` em `DocumentOut` (documents.py:79, l.349) e o
`StatusPill` já recebe `lastCompletedStep` (DocumentsPage l.280). Confirmar o valor
literal `"classificado"` contra `classification/stage.py:357-364` (constante
`CLASSIFIED_STEP` / `_REOPENED_STEP="classificado"` em `undo.py:49`).

**CTA na lista (D-11):** adicionar botão "Pré-visualizar"/"Aprovar" na linha da tabela
(l.246-286) quando o rótulo for "pronto". Reusar `postApprove`/`postDryRun` (api.ts
l.131, l.286) e o estilo `row-action`/`btn-primary`.

---

### `frontend/src/pages/AutomationsPage.tsx` — `<select>` de campo + guard (item 4, D-07/D-08)

**Role:** component (transform) · **Analog:** input free-text (l.822-830) + painel "Campos do template" (l.704-729) + `activeTemplate` (l.449-454)

**Substituir** o `<input placeholder="nome do campo">` (l.822-830) por um `<select>`
estrito populado com `activeTemplate.fields` (D-07). O `activeTemplate` (l.449-454) já
deriva o template da condição "Tipo de documento"; os campos já são lidos no painel
(l.715-727 `activeTemplate.fields.map(...)`, shape `{name, hint}` — confirmado em
`types.ts:114-130`). Padrão de `<select>` a copiar — o seletor de template logo abaixo
(l.843-856):
```tsx
{isField && (
  activeTemplate ? (
    <select className="select" style={{ width: 168, height: 34 }}
            value={c.field_name}
            onChange={(e) => patchCond(c.key, { field_name: e.target.value })}>
      <option value="">Escolha um campo…</option>
      {activeTemplate.fields.map((f) => (
        <option key={f.id} value={f.name}>{f.name}</option>
      ))}
    </select>
  ) : (
    /* D-08: sem template determinável → bloquear com aviso, SEM fallback de texto */
    <span className="nochip-box" style={{...}}>Escolha um template na condição "Tipo de documento" para comparar um campo.</span>
  )
)}
```
**D-08 (guard):** quando `activeTemplate == null`, a condição "Valor de campo" é
desabilitada/avisada — sem fallback texto livre nem autocomplete global. O padrão
visual de "sem chips" (`nochip-box`, l.676-en l.683 do `renderTokenBar`) é o molde do
aviso. Atualizar `validate` (l.563-589): hoje exige `c.field_name.trim()` (l.569-571);
acrescentar que `field=="field"` exige `activeTemplate` determinável.

---

## Shared Patterns

### API thin-router (backend) — schema In/Out + `get_session` + guards de estado
**Source:** `backend/app/api/documents.py` (todo o arquivo) e `automations.py`
**Apply to:** endpoint GET de audit + mudança no `RescanOut`
- `request.app.state.engine` + `with get_session(engine) as session:` (l.326-327)
- schemas Pydantic `*In`/`*Out` no topo do módulo (l.73-212)
- 404 `HTTPException(status.HTTP_404_NOT_FOUND, ...)`; 409 para pré-condição de estado
- NUNCA logar valores extraídos (docstring l.25-28)

### Serialização de datetime tz-aware
**Source:** `backend/app/api/watcher_status.py` + `backend/app/ingest/watcher.py:221`
**Apply to:** TODOS os `*Out.created_at` (item 9, D-13)
- referência correta: `datetime.now(UTC)` produz offset; datetimes naive do SQLite
  precisam de `.replace(tzinfo=UTC)` na borda de saída.

### Frontend api-client + TanStack mutation
**Source:** `frontend/src/lib/api.ts` (`request<T>` l.45-63) + `frontend/src/hooks/useDocuments.ts`
**Apply to:** `getDocumentAudit`, `useUndoDocument`, toast do rescan
- wrapper `request<T>` único (não reimplementar fetch)
- mutation com `qc.invalidateQueries` no `onSuccess` (l.33-42 e l.46-55)
- `placeholderData: keepPreviousData` + polling 4s para queries de lista (l.11-31)

### Rótulo derivado token-driven (frontend)
**Source:** `frontend/src/components/StatusPill.tsx` (`resolvePill`, l.28-35)
**Apply to:** item 8 (rótulo "pronto")
- derivar de `(state, lastCompletedStep)`; tokens `--st-*` travados; sem estado novo.

### `<select>` estrito + estilo `.select`
**Source:** `frontend/src/pages/AutomationsPage.tsx` (select de template, l.843-856)
**Apply to:** item 4 (seletor de campo)
- `className="select"`, `<option value="">placeholder…</option>` + `.map`.

---

## No Analog Found

Nenhum. Todos os arquivos têm analog direto no codebase (fase de exposição/apresentação).

| Arquivo | Role | Data Flow | Motivo |
|---------|------|-----------|--------|
| — | — | — | — |

---

## Metadata

**Analog search scope:** `backend/app/api/`, `backend/app/automation/`, `backend/app/ingest/`,
`backend/app/models/`, `frontend/src/pages/`, `frontend/src/components/`, `frontend/src/hooks/`,
`frontend/src/lib/`
**Files scanned:** 11 (documents.py, automations.py, watcher_status.py, audit_log.py, undo.py,
watcher.py, document.py, DocumentsPage.tsx, StatusPill.tsx, useDocuments.ts, api.ts, AutomationsPage.tsx)
**Pattern extraction date:** 2026-06-25

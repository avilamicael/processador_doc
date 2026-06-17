# Phase 5: Confiança, Revisão Humana e Quarentena - Pattern Map

**Mapped:** 2026-06-16
**Files analyzed:** 14 (4 backend novos, 5 backend editados, 5 frontend novos/editados)
**Analogs found:** 14 / 14 (todos com analog forte — fase brownfield, composição de primitivas existentes)
**Idioma:** pt-BR

> Esta fase é **code-and-config only** (sem deps novas). Cada arquivo novo/editado tem um analog direto no repositório, lido integralmente. O risco real não é "construir errado" — é **quebrar a atomicidade/idempotência/allowlist** já estabelecidas. Todos os excertos abaixo são para COPIAR a forma exata (commit único, `transition`, `repo.enqueue`, `validate_field`, hooks TanStack Query).

---

## File Classification

| Novo/Modificado | Role | Data Flow | Closest Analog | Match Quality |
|-----------------|------|-----------|----------------|---------------|
| `backend/alembic/versions/0005_confidence_review.py` | migration | batch (schema) | `backend/alembic/versions/0004_templates_classification.py` | exact (migração que NÃO toca `documents`) |
| `backend/app/classification/confidence.py` (NOVO, opcional) | utility (pura) | transform | seção de validação em `stage.py` (passo 8) | role-match (função pura derivada) |
| `backend/app/classification/stage.py` (EDITA) | service | request-response (pipeline) | ele mesmo (passo 6 quarentena via `transition`) | exact (mesmo arquivo, novo ramo) |
| `backend/app/models/classification.py` (EDITA) | model | CRUD | ele mesmo (`confidence: Mapped[float \| None]`) | exact (colunas-irmãs) |
| `backend/app/config.py` (EDITA) | config | — | `config.py` `classify_match_threshold` | exact (tunable-irmão) |
| `backend/app/api/documents.py` (EDITA: 4 endpoints) | controller/route | request-response | `api/documents.py` + `api/templates.py` | exact (routers finos) |
| `backend/app/queue/repo.py` (EDITA: helper requeue) | service (repo) | event-driven (fila) | `repo.requeue_running` | exact (mesmo arquivo) |
| `backend/app/queue/worker.py` (EDITA: `forced_template_id` no payload) | service (worker) | event-driven | `worker._dispatch` ramo CLASSIFY_STEP | exact (mesmo arquivo) |
| `frontend/src/pages/AttentionPage.tsx` (NOVO) | component (page) | request-response (polling) | `pages/DocumentsPage.tsx` + `DocumentDetailModal` | exact (molde de página + modal de campos) |
| `frontend/src/components/ConfidenceBadge.tsx` (NOVO) | component | — | `components/StatusPill.tsx` | role-match (badge token-driven) |
| `frontend/src/hooks/useAttention.ts` (NOVO) | hook | request-response (polling+mutations) | `hooks/useDocuments.ts` + `hooks/useTemplates.ts` | exact (query polling + mutations) |
| `frontend/src/lib/api.ts` (EDITA: 5 funções) | utility (client) | request-response | `lib/api.ts` (`getDocumentDetail`, `updateTemplate`) | exact (mesmo arquivo) |
| `frontend/src/types.ts` (EDITA) | model (types) | — | `types.ts` (`Classification`/`ClassificationField`) | exact (mesmo arquivo) |
| `backend/tests/test_api_review.py` (NOVO) | test | request-response | `backend/tests/test_api_documents.py` | exact (TestClient + schema_engine) |

---

## Pattern Assignments

### `backend/alembic/versions/0005_confidence_review.py` (migration, batch)

**Analog:** `backend/alembic/versions/0004_templates_classification.py`

**CRÍTICO (Pitfall 1):** as DUAS colunas vão em `classification_results` e `filled_fields` — **NUNCA** em `documents`. Migração que toca `documents` força batch recreate no SQLite e **destrói o trigger `trg_documents_updated_at`** (criado na 0002). 0003/0004 documentam explicitamente que evitam isso por não tocar `documents`. Repetir essa garantia.

**Cabeçalho de revisão** (analog linhas 28-32) — encadear `down_revision = '0004'`:
```python
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

**Padrão `batch_alter_table` + `server_default` Boolean** (analog linhas 57-61, 119) — add de coluna nullable + Boolean com `server_default='0'`:
```python
def upgrade() -> None:
    with op.batch_alter_table('classification_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('confidence_score', sa.Float(), nullable=True))
    with op.batch_alter_table('filled_fields', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('manually_corrected', sa.Boolean(), nullable=False, server_default='0')
        )
# NOTA (copiar do docstring 0004 linhas 18-20): nenhuma tabela é `documents`
# → trigger trg_documents_updated_at NÃO afetado (mesma situação da 0003/0004).

def downgrade() -> None:
    with op.batch_alter_table('filled_fields', schema=None) as batch_op:
        batch_op.drop_column('manually_corrected')
    with op.batch_alter_table('classification_results', schema=None) as batch_op:
        batch_op.drop_column('confidence_score')
```

---

### `backend/app/models/classification.py` (model, CRUD) — EDITA

**Analog:** o próprio arquivo — a coluna `confidence` (linha 64) é o molde EXATO da nova coluna.

**Coluna-irmã `confidence_score`** em `ClassificationResult` (espelhar linha 64, `Float` já importado linha 30):
```python
# Score 0.0–1.0 de QUALIDADE DE EXTRAÇÃO (D-01: fração de obrigatórios válidos).
# NÃO confundir com `confidence` (acima) = score do MATCHER/desempate (D-01 separa).
# nullable: quarentena não tem score (sem template = sem campos obrigatórios).
confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
```

**Coluna `manually_corrected`** em `FilledField` (espelhar `valid`, linhas 94-96, `Boolean` já importado linha 26):
```python
# D-08: origem do valor marcada como corrigida manualmente (auditabilidade + base
# do approve). default False (valor veio da IA/documento).
manually_corrected: Mapped[bool] = mapped_column(
    Boolean, default=False, server_default="0", nullable=False
)
```

---

### `backend/app/classification/confidence.py` (utility pura, transform) — NOVO (opcional)

**Analog:** o laço de validação em `stage.py` (passo 8, linhas 285-308) — a fonte de `FilledField.valid` por campo.

Função **PURA** (sem DB/IA) → testável isolada (`tests/classification/test_confidence.py`). Score = fração de OBRIGATÓRIOS válidos (D-01); `has_invalid_required` força revisão mesmo com score alto (D-04). Sem obrigatórios → `(1.0, False)`.

```python
def compute_confidence(filled_fields, template_fields) -> tuple[float, bool]:
    """Retorna (score 0.0-1.0, has_invalid_required). D-01/D-04."""
    required = [f for f in template_fields if f.required]
    if not required:
        return 1.0, False
    valid_by_name = {ff.field_name: ff.valid for ff in filled_fields}
    valid_count = sum(1 for f in required if valid_by_name.get(f.name, False))
    has_invalid = valid_count < len(required)
    return valid_count / len(required), has_invalid
```

---

### `backend/app/classification/stage.py` (service, pipeline) — EDITA

**Analog:** o próprio arquivo. DOIS pontos de extensão; honrar idempotência (linhas 162-173), atomicidade (passo 9, linhas 310-316) e o ramo quarentena (passo 6, linhas 238-252) como molde do roteamento.

**(A) Forçar template (D-09)** — novo parâmetro opcional na assinatura (linhas 131-133) e ramo após idempotência+Extraction; pula matcher/decide/disambiguate:
```python
async def classify_stage(
    session: Session, *, content_hash: str, forced_template_id: int | None = None
) -> ClassifyStageResult:
    ...
    if forced_template_id is not None:
        template = session.get(Template, forced_template_id)
        if template is None:
            raise ValueError("Template forçado inexistente")
        matched_template_id = forced_template_id
        confidence = None  # sem score de matcher quando forçado manualmente
        # vai DIRETO ao passo 7 (filler) — pula matcher/decide/disambiguate
    else:
        # caminho atual (linhas 184-233): matcher.match_templates → decide → ambiguous
        ...
```

**(B) Roteamento de estado (D-01/D-04)** — substituir o passo 9 atual (linhas 310-316) que faz `doc.last_completed_step = CLASSIFIED_STEP` + `session.commit()` direto. Agora ATÔMICO via `transition` (como o ramo quarentena, linha 248). **NUNCA** `session.commit()` manual antes do `transition` (Pitfall 2 — quebra atomicidade):
```python
# (9) Calcular score (puro) e rotear. add já feito (cr+filled_fields+usages);
# transition comita TUDO junto (commit atômico único). NÃO commitar antes.
score, has_invalid_required = compute_confidence(cr.filled_fields, list(template.fields))
cr.confidence_score = score
for u in usages:
    session.add(u)
below_threshold = score < settings.review_confidence_threshold
if has_invalid_required or below_threshold:
    transition(session, doc, DocState.EM_REVISAO, completed_step=CLASSIFIED_STEP)
else:
    # ⚠ SUPERADO pela resolução da Open Q1 (ver abaixo): NÃO usar este ramo.
    # O stage NUNCA transita para CONCLUIDO. Doc que passa permanece
    # PROCESSANDO+classificado (Fase 4): doc.last_completed_step = CLASSIFIED_STEP; session.commit().
    doc.last_completed_step = CLASSIFIED_STEP
    session.commit()
```
> **Open Question 1 (cross-fase) — RESOLVIDA (planejamento Fase 5, 2026-06-16):** auto-CONCLUIDO pularia o ponto de captura da Fase 6 (CONCLUIDO é terminal, sem saídas na allowlist — `states.py` linha 43). **Resolução TRAVADA:** o `classify_stage` NUNCA transita para CONCLUIDO; doc que passa permanece **PROCESSANDO + last_completed_step="classificado"** (comportamento terminal da Fase 4); CONCLUIDO só via `approve` humano (Plan 03-T1). O excerto `transition(CONCLUIDO)` acima foi SUPERADO — **não seguir o ramo CONCLUIDO.** Plan 02-T1 acceptance_criteria tem grep-gate confirmando a ausência de `DocState.CONCLUIDO` em `stage.py`.

**Excerto-molde do commit atômico via `transition`** (ramo quarentena existente, linhas 238-252) — copiar a ORDEM (add → transition, nunca o inverso):
```python
if matched_template_id is None:
    session.add(ClassificationResult(document_id=doc.id, template_id=None, confidence=confidence))
    for u in usages:
        session.add(u)
    transition(session, doc, DocState.QUARENTENA)   # comita TUDO junto (state_machine.py linha 61)
    return ClassifyStageResult(matched=False, template_id=None, called_ai=called_ai)
```

---

### `backend/app/config.py` (config) — EDITA

**Analog:** `classify_match_threshold` (linhas 142-147) — molde EXATO do tunable global com `AliasChoices`.

```python
review_confidence_threshold: float = Field(
    default=0.8,  # ≥80% = "Alta" no 05-UI-SPEC; calibrar (Assumption A2 — confirmar)
    validation_alias=AliasChoices(
        "REVIEW_CONFIDENCE_THRESHOLD", "review_confidence_threshold"
    ),
)
```

---

### `backend/app/api/documents.py` (controller/route, request-response) — EDITA: 4 endpoints

**Analog:** `api/documents.py` (este arquivo, `get_document` linhas 174-248: `request.app.state.engine` + `with get_session`, 404, query do CR) + `api/templates.py` (schemas `In` Pydantic linhas 57-98; `IntegrityError → 409` linhas 219-226).

**Imports a adicionar** (já presentes na maioria — confirmar `transition`, `InvalidTransition`, `repo`, `validate_field`, `compute_confidence`):
```python
from app.pipeline.state_machine import transition
from app.pipeline.states import InvalidTransition
from app.queue import repo
from app.validation.fields import validate_field
```

**Padrão de endpoint de ação** (molde `get_document` linhas 174-211 + guard de allowlist via `transition`). **NUNCA setar `doc.state` direto** — `transition` é o único guard (Anti-Pattern documentado em `worker.py` linhas 84, 322):
```python
@router.post("/documents/{document_id}/approve", response_model=DocumentDetailOut)
def approve_document(request: Request, document_id: int) -> DocumentDetailOut:
    engine = request.app.state.engine
    with get_session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "documento não encontrado")
        cr = session.scalar(select(ClassificationResult).where(
            ClassificationResult.document_id == document_id))
        # GUARD D-07: re-derivar validade ATUAL dos obrigatórios (não confiar no score
        # persistido — Pitfall 4). Bloqueia approve se algum obrigatório inválido.
        if cr is None or _has_invalid_required(cr, session):
            raise HTTPException(status.HTTP_409_CONFLICT,
                "corrija os campos obrigatórios inválidos antes de aprovar")
        try:
            transition(session, doc, DocState.CONCLUIDO)   # allowlist EM_REVISAO→CONCLUIDO
        except InvalidTransition as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        # ... montar e retornar DocumentDetailOut (reusar a lógica de get_document)
```

**Mapeamento dos 4 endpoints:**

| Endpoint | Transição (allowlist `states.py`) | Reenfileira? | Notas |
|----------|-------------------------------------|--------------|-------|
| `POST /documents/{id}/retry` | `FALHA→PROCESSANDO` (states.py L41) | sim — `repo.enqueue`/requeue do step por `last_completed_step` | extraido→classify; aguardando_extracao→extract |
| `POST /documents/{id}/reclassify` | `QUARENTENA→PROCESSANDO` (states.py L39) | sim — classify com `forced_template_id` | Body `{template_id:int}`. **Apagar CR de quarentena ANTES** (Pitfall 3) |
| `PATCH /documents/{id}/fields/{field_name}` | nenhuma (doc fica EM_REVISAO) | não | `validate_field` + `manually_corrected=True` + recalcular `confidence_score` (Pitfall 4). NÃO chama IA (D-08) |
| `POST /documents/{id}/approve` | `EM_REVISAO→CONCLUIDO` (states.py L33) | não | Guard obrigatórios válidos (D-07) |

**Endpoint de patch (D-08, revalida sem IA)** — molde `validate_field` (`validation/fields.py` linhas 64-70) + schema `In` Pydantic (`templates.py` linha 57). Recalcular score no MESMO commit (Pitfall 4):
```python
class FieldPatchIn(BaseModel):
    raw_value: str | None

@router.patch("/documents/{document_id}/fields/{field_name}", response_model=DocumentDetailOut)
def patch_field(request: Request, document_id: int, field_name: str, body: FieldPatchIn):
    engine = request.app.state.engine
    with get_session(engine) as session:
        cr = session.scalar(select(ClassificationResult).where(
            ClassificationResult.document_id == document_id))
        if cr is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "classificação não encontrada")
        ff = session.scalar(select(FilledField).where(
            FilledField.classification_result_id == cr.id,
            FilledField.field_name == field_name))
        if ff is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "campo não encontrado")
        tf = _template_field(session, cr.template_id, field_name)   # join Template→TemplateField
        v = validate_field(field_type=tf.field_type, raw=body.raw_value,
                           required=tf.required, regex=tf.regex)
        ff.raw_value, ff.normalized_value = v.raw_value, v.normalized_value
        ff.valid, ff.invalid_reason = v.valid, v.invalid_reason
        ff.manually_corrected = True
        cr.confidence_score, _ = compute_confidence(cr.filled_fields, _template_fields(session, cr.template_id))
        session.commit()
        # ... retornar detalhe
```

**Reclassify — apagar CR antes (Pitfall 3)** + reenfileirar com `forced_template_id`:
```python
# Idempotência (stage.py linhas 162-173) faz no-op se o CR existir → APAGAR primeiro.
session.delete(cr)                       # cascade delete-orphan limpa FilledFields
transition(session, doc, DocState.PROCESSANDO)
repo.requeue_step(session, content_hash=doc.content_hash, step="classify",
                  payload=json.dumps({"content_hash": doc.content_hash,
                                      "forced_template_id": body.template_id}))
```

---

### `backend/app/queue/repo.py` (service/repo, fila) — EDITA: novo helper

**Analog:** `repo.requeue_running` (linhas 185-200) — molde EXATO de `UPDATE jobs ... WHERE` + commit + rowcount. Resolve Open Question 2 (UNIQUE `(original_hash, step)` impede re-`enqueue`): em vez de inserir novo job, **resetar o existente** para `pending`.

```python
def requeue_step(session: Session, *, content_hash: str, step: str, payload: str) -> int:
    """Reseta o job (content_hash, step) existente para pending + atualiza payload.

    Reusa a linha (mantém a UNIQUE uq_jobs_hash_step) — para retry/reclassify, onde
    o job antigo já está 'done' e um novo enqueue seria no-op. Análogo a requeue_running.
    """
    result = session.execute(
        text(
            "UPDATE jobs SET status='pending', payload=:payload, next_run_at=:now, "
            "attempts=0, updated_at=CURRENT_TIMESTAMP "
            "WHERE original_hash=:hash AND step=:step"
        ),
        {"payload": payload, "now": _utcnow(), "hash": content_hash, "step": step},
    )
    session.commit()
    return result.rowcount
```
> Se nenhuma linha for resetada (job nunca existiu), cair para `repo.enqueue`. Confirmar no plano que o sweep idempotente (`worker._sweep_pending`) não re-cria o job antes do reset.

---

### `backend/app/queue/worker.py` (service/worker, event-driven) — EDITA

**Analog:** `worker._dispatch` ramo CLASSIFY_STEP (linhas 158-164). Ler `forced_template_id` do payload e passar ao `classify_stage`:
```python
elif step == CLASSIFY_STEP:
    with get_session(engine) as session:
        forced = json.loads(payload).get("forced_template_id")  # None no caminho normal
        await classify_stage(session, content_hash=original_hash, forced_template_id=forced)
```
> O payload normal de classify (`worker.py` linha 327) é `{"content_hash": ...}` → `.get` retorna `None` → caminho atual intacto.

---

### `frontend/src/types.ts` (model/types) — EDITA

**Analog:** `Classification`/`ClassificationField` (linhas 137-163). Estender com os 2 campos novos:
```typescript
export interface ClassificationField {
  field_name: string
  raw_value: string | null
  normalized_value: string | null
  valid: boolean
  invalid_reason: string | null
  manually_corrected: boolean   // NOVO (D-08)
}
export interface Classification {
  template_id: number | null
  template_name: string | null
  confidence: number | null
  confidence_score: number | null   // NOVO (D-02; 0-1, UI multiplica por 100)
  fields: ClassificationField[]
}
```

---

### `frontend/src/lib/api.ts` (utility/client, request-response) — EDITA: 5 funções

**Analog:** `getDocumentDetail` (linhas 64-66, GET tipado por path) + `updateTemplate` (linhas 109-114, PATCH com JSON body). O helper `request<T>` (linhas 33-51) já lança `ApiError` em `!res.ok` — reusar.
```typescript
export function getAttention(): Promise<AttentionList> {
  return request<AttentionList>('/documents/attention')   // endpoint dedicado (Open Q3)
}
export function postRetry(id: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/retry`, { method: 'POST' })
}
export function postReclassify(id: number, templateId: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/reclassify`, {
    method: 'POST', body: JSON.stringify({ template_id: templateId }),
  })
}
export function patchField(id: number, fieldName: string, rawValue: string | null): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/fields/${encodeURIComponent(fieldName)}`, {
    method: 'PATCH', body: JSON.stringify({ raw_value: rawValue }),
  })
}
export function postApprove(id: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/approve`, { method: 'POST' })
}
```

---

### `frontend/src/hooks/useAttention.ts` (hook, polling+mutations) — NOVO

**Analog:** `useDocuments` (linhas 13-21, query com `refetchInterval`/`refetchIntervalInBackground:false`/`keepPreviousData`) + `useTemplates`/`useRescan` (mutations com `invalidateQueries` em `onSuccess`).
```typescript
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getAttention, patchField, postApprove, postReclassify, postRetry } from '../lib/api'

const ATTENTION_KEY = ['attention'] as const

export function useAttentionDocuments() {
  return useQuery({
    queryKey: ATTENTION_KEY,
    queryFn: getAttention,
    refetchInterval: 4000,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,
  })
}
export function useApproveDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => postApprove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ATTENTION_KEY })
      qc.invalidateQueries({ queryKey: ['documents'] })   // some da lista geral também
    },
  })
}
// useRetryDocument, useReclassifyDocument, usePatchField — mesmo molde (invalidam ['attention'])
```

---

### `frontend/src/components/ConfidenceBadge.tsx` (component) — NOVO

**Analog:** `StatusPill.tsx` (linhas 19-51) — mapa estático estado→token + render `<span className="pill" style={{ color: var(--st-X), background: var(--st-X-bg) }}>`. Mapear faixa de score → rótulo/token (05-UI-SPEC §Color, D-02). Score numérico em mono. **NÃO usar accent** (reservado a CTAs).
```typescript
// score 0-1 → {pct, label, token}. Faixas PRESCRITAS (05-UI-SPEC):
//   ≥0.80 Alta/tratado(verde) | 0.50-0.79 Média/leitura(âmbar) | <0.50 Baixa/erro(vermelho)
const pct = Math.round(score * 100)
const { label, token } = score >= 0.8 ? { label: 'Alta', token: 'tratado' }
  : score >= 0.5 ? { label: 'Média', token: 'leitura' }
  : { label: 'Baixa', token: 'erro' }
return (
  <span className="badge" style={{ color: `var(--st-${token})`, background: `var(--st-${token}-bg)` }}>
    <span style={{ fontFamily: 'var(--font-mono)' }}>{pct}%</span> · {label}
  </span>
)
```
> Reutilizável em S4 (AttentionPage) E no `DocumentDetailModal` existente (05-UI-SPEC §Component Inventory).

---

### `frontend/src/pages/AttentionPage.tsx` (component/page, polling) — NOVO

**Analog:** `DocumentsPage.tsx` — molde de página completo. Reusar SEM alteração: `.card`, `.stat-grid`/`.stat-card` (contagem por balde), `.chips`/`.chip`/`.chip.active` (alternar baldes), `table.docs`/`.cell-mono`, `StatusPill`, e os 3 estados de tela.

**Estados de tela** (DocumentsPage linhas 91-93) — copiar a derivação exata:
```typescript
const isInitialLoading = query.isLoading && !data
const isError = query.isError && !data
const isEmpty = !isInitialLoading && !isError && /* nada nos 3 baldes */
```

**Empty/error state centralizado** (linhas 183-216) — copiar o bloco `padding: '48px 24px'` + heading 15/700 + `.btn-primary` "Tentar novamente" com `Icon name="refresh"`. Empty heading da fase: **"Tudo em dia"** (05-UI-SPEC).

**Chips de balde com contagem** (linhas 121-132):
```tsx
<div className="chips">
  {buckets.map((b) => (
    <button key={b.key} className={active === b.key ? 'chip active' : 'chip'} onClick={() => setActive(b.key)}>
      <span>{b.label}</span><span className="chip-count">{b.count}</span>
    </button>
  ))}
</div>
```

**Tabela de campos editáveis (S4)** — molde `DocumentDetailModal` tabela campo→valor→normalizado→marca (linhas 397-445). Para campos inválidos, trocar o `<td>` de valor por `<input className="search-input">` (mono) com `aria-label="Corrigir valor de {campo}"`; manter o badge `válido`/`inválido` com `title={f.invalid_reason}` (linhas 422-436). Valores como **texto puro** (sem `dangerouslySetInnerHTML`).

**Badge inválido (copiar token-driven, linhas 426-435):**
```tsx
{f.valid
  ? <span className="badge badge-ok">válido</span>
  : <span className="badge" style={{ color: 'var(--st-erro)', background: 'var(--st-erro-bg)' }}
      title={f.invalid_reason ?? undefined}>inválido</span>}
```

**CTA "Aprovar documento"** `.btn-primary` `disabled` enquanto algum obrigatório inválido (D-07; hint 05-UI-SPEC). Select "Atribuir template" (S3) `disabled` o botão "Reclassificar" até escolher template.

---

### `backend/tests/test_api_review.py` (test, request-response) — NOVO

**Analog:** `backend/tests/test_api_documents.py` (fixture `client` sobre `schema_engine` linhas 35-43; `app.state.engine` sobrescrito; `_seed` helper linhas 46-48; `test_detail_classified_document` linha 177).

**Fixture molde** (test_api_documents linhas 35-43):
```python
@pytest.fixture
def client(schema_engine: Engine) -> Iterator[TestClient]:
    previous = app.state.engine
    app.state.engine = schema_engine
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.state.engine = previous
```

**Cobertura (05-RESEARCH Test Map):** patch revalida + `manually_corrected` + **sem-IA** (`respx call_count==0`); approve 409 com obrigatório inválido → 200 após correção; retry de doc não-FALHA → 409; reclassify apaga CR + reenfileira (não no-op). Mock OpenAI via `respx` (`tests/classification/conftest.py`).

---

## Shared Patterns

### Guard de transição de estado (allowlist)
**Source:** `backend/app/pipeline/state_machine.py` `transition` (linhas 24-63) + `states.py` `TRANSITIONS` (linhas 19-43)
**Apply to:** TODOS os 4 endpoints de ação E o roteamento do `stage.py`
**Regra:** NUNCA `doc.state = X` direto. SEMPRE `transition(session, doc, DocState.Y)` — valida contra `TRANSITIONS`, faz `rollback` em par inválido, comita em par válido. Endpoint converte `InvalidTransition`→`HTTPException(409)`. Transições da fase já na allowlist: `PROCESSANDO→{EM_REVISAO,CONCLUIDO}`, `EM_REVISAO→CONCLUIDO`, `QUARENTENA→PROCESSANDO`, `FALHA→PROCESSANDO`.

### Revalidação determinística sem IA (D-08)
**Source:** `backend/app/validation/fields.py` `validate_field` (linhas 64-151)
**Apply to:** endpoint de patch de campo
**Regra:** reusar EXATAMENTE — cobre data/moeda/numero/cpf_cnpj(Módulo 11)/booleano/regex-com-teto-ReDoS (`_MAX_REGEX_LEN` linha 29). NÃO duplicar lógica, NÃO chamar OpenAI (teste prova `call_count==0`).

### Commit atômico único (sem commit antes do transition)
**Source:** `backend/app/classification/stage.py` ramo quarentena (linhas 238-252) + `state_machine.transition` (comita internamente, linha 61)
**Apply to:** roteamento de estado no `stage.py`; patch de campo
**Regra (Pitfall 2):** `session.add(...)` de tudo ANTES; `transition` comita o conjunto. NUNCA `session.commit()` manual antes do `transition`.

### Reenfileiramento idempotente
**Source:** `backend/app/queue/repo.py` `enqueue` (linhas 43-77, no-op em UNIQUE) + `requeue_running` (linhas 185-200, molde do novo `requeue_step`)
**Apply to:** retry e reclassify
**Regra (Pitfall 3):** apagar o CR de quarentena ANTES de reenfileirar (senão a idempotência do `stage.py` linhas 162-173 faz no-op). UNIQUE `(original_hash, step)` impede `enqueue` novo → usar `requeue_step` (reset para pending).

### Polling sem flicker + invalidação (frontend)
**Source:** `frontend/src/hooks/useDocuments.ts` (linhas 13-21) + `useRescan` (linhas 33-42)
**Apply to:** todos os hooks de `useAttention.ts`
**Regra:** query com `refetchInterval:4000` + `refetchIntervalInBackground:false` + `placeholderData:keepPreviousData`; mutations com `invalidateQueries(['attention'])` (e `['documents']`) em `onSuccess`. Fonte de verdade = API, sem otimismo que mascare falha.

### Segurança — Information Disclosure / XSS
**Source:** `api/documents.py` docstring (linhas 25-27) + `DocumentDetailModal` (texto puro)
**Apply to:** endpoints e UI da fase
**Regra:** valores extraídos (CNPJ/CPF) SÓ no corpo da resposta, NUNCA em log (T-04-11). React renderiza valores como texto puro — proibido `dangerouslySetInnerHTML` (T-04-12). `document_id`/`template_id` tipados `int`; `field_name` em `where(... == field_name)` parametrizado (nunca concatenado).

---

## No Analog Found

Nenhum. Todos os 14 arquivos têm analog forte no repositório — fase brownfield de composição de primitivas. As 3 decisões abertas (Open Questions) NÃO são lacunas de pattern, são decisões de planejamento/produto:

| Questão | Tipo | Onde resolver |
|---------|------|---------------|
| Auto-CONCLUIDO no stage vs estado pré-Fase-6 (CONCLUIDO é terminal) | arquitetura cross-fase | planejamento/discuss |
| `GET /documents/attention` dedicado vs filtro em `GET /documents` (N+1, Pitfall 5) | design de API | planejamento |
| Default `review_confidence_threshold=0.8` (A2) | produto | confirmar com usuário |

---

## Metadata

**Analog search scope:** `backend/alembic/versions/`, `backend/app/{classification,api,queue,models,pipeline,validation}/`, `backend/app/config.py`, `backend/tests/`, `frontend/src/{pages,hooks,lib,components}/`, `frontend/src/types.ts`
**Files scanned (lidos integralmente):** 0004 migration, stage.py, fields.py, documents.py, templates.py, classification.py (model), worker.py, repo.py, state_machine.py, config.py (tunable), states.py, useDocuments.ts, useTemplates.ts, api.ts, StatusPill.tsx, types.ts, DocumentsPage.tsx (página + DocumentDetailModal), test_api_documents.py (fixtures)
**Pattern extraction date:** 2026-06-16

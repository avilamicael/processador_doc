# Phase 6: Automações de Arquivo (Renomear/Mover) - Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 17 (12 backend novos/modificados + 5 frontend novos/modificados) + 8 arquivos de teste
**Analogs found:** 17 / 17 (todos com análogo no codebase — zero greenfield real)

> Esta fase é orquestração de ativos JÁ construídos e testados (CAS, máquina de
> estados, worker, validação, API fina). NÃO inventar — copiar a forma exata dos
> análogos abaixo. Nenhuma dependência nova (stdlib + libs do projeto, conforme
> 06-RESEARCH §Standard Stack).

---

## File Classification

### Backend

| Novo/Modificado | Role | Data Flow | Análogo mais próximo | Qualidade |
|-----------------|------|-----------|----------------------|-----------|
| `app/automation/rules.py` (novo) | utility (avaliador puro) | transform | `app/validation/fields.py` (`validate_field` dispatch por tipo) + `app/classification/matcher.py` | role-match (puro determinístico) |
| `app/automation/naming.py` (novo) | utility (resolução de tokens) | transform | `app/validation/dates.py` + `app/validation/money.py` (puros, parse→normalizado-ou-None) | role-match |
| `app/automation/fileops.py` (novo) | utility (operação física) | file-I/O | `app/storage/cas.py` (`store`: temp + os.replace atômico) | exact (file-I/O atômico) |
| `app/automation/stage.py` (novo) | service (orquestração+persist.) | request-response / batch | `app/classification/stage.py` (`classify_stage`: idempotência + commit atômico único + transition) | exact |
| `app/automation/undo.py` (novo) | service (reversão) | file-I/O / transform | `app/automation/fileops.py` (irmão) + `app/storage/cas.py` (`read_bytes`) | role-match |
| `app/automation/__init__.py` (novo) | package init | — | `app/classification/__init__.py` | exact |
| `app/models/audit_log.py` (modificar) | model | CRUD | `app/models/classification.py` (FK + colunas + relationship) | exact |
| `app/models/automation_rule.py` (novo) | model | CRUD | `app/models/template.py` (`Template` 1:N `TemplateField` cascade delete-orphan) | exact |
| `app/api/automations.py` (novo) | controller (route) | request-response / CRUD | `app/api/templates.py` (In/Patch/Out, 409/422/404/204, 1:N aninhado) + `app/api/documents.py` (ações POST: approve/retry/reclassify) | exact |
| `app/alembic/versions/0006_*.py` (novo) | migration | — | `alembic/versions/0004_templates_classification.py` (create_table) + `0005_confidence_review.py` (batch add_column) | exact |
| `app/queue/worker.py` (modificar) | service (dispatch) | event-driven | o próprio `worker.py` (`_dispatch` bifurca por step; `enqueue_pending_classifications` sweep) | exact (auto-análogo) |
| `app/models/__init__.py` (modificar) | package init | — | o próprio (registrar `AutomationRule` em `__all__`) | exact |
| `app/main.py` (modificar) | config | — | o próprio (`app.include_router(automations_api.router)`) | exact |

### Frontend

| Novo/Modificado | Role | Data Flow | Análogo mais próximo | Qualidade |
|-----------------|------|-----------|----------------------|-----------|
| `src/pages/AutomationsPage.tsx` (reescrever — é mock) | component (page) | request-response | `src/pages/TemplatesPage.tsx` (substituiu mock por superfície API: form inline, loading/erro/vazio, confirmRemove) | exact |
| `src/pages/DryRunPage.tsx` (novo — S4) | component (page) | request-response | `src/pages/DocumentsPage.tsx` (`table.docs`, checkbox lote, estados de tela) | exact |
| `src/hooks/useAutomations.ts` (novo) | hook | request-response | `src/hooks/useTemplates.ts` (query + 3 mutations invalidando key) + `src/hooks/useDocuments.ts` (polling) | exact |
| `src/lib/api.ts` (modificar) | utility (client) | request-response | o próprio (`request<T>` + funções `getTemplates`/`postApprove`) | exact (auto-análogo) |
| `src/types.ts` (modificar) | utility (types) | — | o próprio (`TemplateCreate`/`TemplatePatch`/`FieldType`) | exact |
| `src/components/Icon.tsx` (modificar) | component | — | o próprio (adicionar `undo`/`alert`/`arrowUp`/`arrowDown` no mesmo estilo de stroke) | exact |

---

## Pattern Assignments

### `app/automation/stage.py` (service, orquestração + persist. atômico)

**Análogo:** `app/classification/stage.py` (LER NA ÍNTEGRA antes de planejar — é o molde exato)

**Forma da função + idempotência por checagem prévia** (stage.py:132-174):
```python
async def classify_stage(session: Session, *, content_hash: str, ...) -> ClassifyStageResult:
    doc = session.scalar(select(Document).where(Document.content_hash == content_hash))
    if doc is None:
        raise ValueError("Document inexistente para content_hash informado")  # worker re-tenta
    # IDEMPOTÊNCIA: registro existente → no-op SEM re-executar (não re-mover arquivo)
    existing = session.scalar(select(ClassificationResult).where(ClassificationResult.document_id == doc.id))
    if existing is not None:
        return ClassifyStageResult(..., called_ai=False)
```
> Para `apply_stage`: a checagem de idempotência é `AuditLog(status="done")` já existente para o doc → no-op (NÃO re-move). Espelha o `existing is not None` acima. (06-RESEARCH Pattern 1.)

**Commit atômico ÚNICO via `transition` — NUNCA commit manual antes** (stage.py:341-364):
```python
if has_invalid_required or below_threshold:
    # NUNCA session.commit() antes do transition — o transition comita TUDO junto
    transition(session, doc, DocState.EM_REVISAO, completed_step=CLASSIFIED_STEP)
    return ...
# caminho "passou": marcador em memória + 1 commit
doc.last_completed_step = CLASSIFIED_STEP
session.commit()
```
> **Atenção crítica (stage.py:341-346 / 06-RESEARCH Anti-Patterns):** NUNCA `session.commit()` manual antes de um `transition` — o `transition` comita CR/audit/estado juntos; commitar antes quebra a atomicidade. Para D-07 (campo faltante): `transition(session, doc, DocState.EM_REVISAO)` exatamente como acima.

**Não vazar conteúdo em log** (stage.py:34, 366-372): logar só metadados (`doc.id`, paths, ids) — NUNCA valores de campo/full_text. Ver Shared Pattern "Logging".

---

### `app/automation/fileops.py` (utility, file-I/O atômico)

**Análogo:** `app/storage/cas.py` (`store`, linhas 64-122)

**`os.replace` atômico same-volume + temp staging no MESMO diretório do destino** (cas.py:103-113):
```python
final_path.parent.mkdir(parents=True, exist_ok=True)
staged_tmp = final_path.parent / cleanup_target.name   # tmp e destino no mesmo dir → rename atômico
os.replace(cleanup_target, staged_tmp)
os.replace(staged_tmp, final_path)
```
> Para AUT-06 cross-device, a `safe_move` adiciona o ramo EXDEV (06-RESEARCH Pattern 3): `try os.replace → except OSError if errno==EXDEV → copy→fsync→verifica-hash→remove`. **Materialização do CAS (D-11):** o destino é escrito a partir de `cas.read_bytes(content_hash)` (cas.py:125-127), não movendo o original. Verificar o hash pós-escrita reusa o MESMO `hashlib.sha256` do CAS.

**Hashing por streaming em chunks (reusar, não reinventar)** (cas.py:37, 77, 89-92):
```python
_CHUNK_SIZE = 64 * 1024
hasher = hashlib.sha256()
while chunk := fin.read(_CHUNK_SIZE):
    hasher.update(chunk)
```
> Verificação pós-cópia cross-device (AUT-06) e detecção idêntico/diferente na colisão (D-09/D-10) usam este hashing. `ingest/hashing.py` é a outra fonte do mesmo SHA-256.

**Anti-colisão a MONTANTE (resolução de nome), não no replace** (06-RESEARCH Pitfall 1 + Code Example "resolve_collision"): o destino livre (`_1`/`_2`, D-09) ou o skip de duplicata (D-10) é resolvido ANTES de chamar `safe_move`. `os.replace` SOBRESCREVE por design — defesa extra com `O_CREAT|O_EXCL`/`exists()`.

**Limpeza defensiva no `finally`** (cas.py:114-122): o `cleanup_target` aponta SEMPRE só para o temporário desta chamada, zerado assim que consumido por `os.replace`. O `finally` JAMAIS pode remover o blob/arquivo final — defesa contra perda irreversível (CLAUDE.md "nunca pode causar perda").

---

### `app/automation/naming.py` (utility, transform puro)

**Análogo:** `app/validation/dates.py` + `app/validation/money.py` (funções puras, parse→normalizado-ou-`None`)

**Disciplina parse-falho → `None` (nunca chuta)** (dates.py:28-38, money.py:22-31):
```python
def normalize_date(raw: str) -> str | None:
    if not raw or not raw.strip():
        return None
    try:
        return date.fromisoformat(s).isoformat()   # ISO YYYY-MM-DD, lexicograficamente ordenável
    except ValueError:
        ...
        return None
```
> `naming.resolve_pattern` devolve `None` quando um token referencia campo faltante/inválido (D-07 → caller faz `transition(EM_REVISAO)`). `normalize_date` devolve ISO `YYYY-MM-DD` — base para `{data:aaaa-mm}` (fatiar `y, m, d = iso.split("-")`). `normalize_money_brl` devolve string Decimal-comparável. Reuso direto (06-RESEARCH Code Examples). Sanitização dos 9 chars Windows + nomes reservados (Pitfall 4) + MAX_PATH (Pitfall 5) é hand-roll documentado (06-RESEARCH §Don't Hand-Roll).

---

### `app/automation/rules.py` (utility, avaliador puro — TPL-02)

**Análogo:** `app/validation/fields.py` (`validate_field`, dispatch por etiqueta) + reuso de `dates.py`/`money.py`

**Dispatch explícito por operador (NUNCA `eval`)** (fields.py:99-123 mostra o estilo de dispatch por `field_type`):
```python
if field_type == "data":
    normalized = normalize_date(raw)
elif field_type == "moeda":
    normalized = normalize_money_brl(raw)
elif field_type == "numero":
    normalized = _normalize_numero(raw)   # str(Decimal(...)) — NUNCA float
```
> O avaliador de regras despacha por OPERADOR (`=`/`>`/`<`/`contém`) com o MESMO estilo. **Coerção numérica obrigatória** (06-RESEARCH Pitfall 2): `>`/`<` de moeda/numero → `Decimal`; data → comparar ISO `YYYY-MM-DD` (já ordenável). Comparar como string inverte 500 vs 3000. Primeira regra que casa vence (D-05). Teto `_MAX_REGEX_LEN = 4096` (fields.py:29) reusado se houver operador regex (V5/ReDoS).

---

### `app/automation/undo.py` (service, reversão — AUT-05)

**Análogo:** `app/automation/fileops.py` (irmão) + `app/storage/cas.py` `read_bytes` (cas.py:125-127)

**Rede final de recuperação via CAS** (cas.py:125-127):
```python
def read_bytes(content_hash: str) -> bytes:
    return path_for(content_hash).read_bytes()
```
> Undo checa integridade do destino por hash; bate → reverte dst→origem; destino sumiu/mudou → restaura `cas.read_bytes(content_hash)` para a origem e marca `status="undone_from_cas"` (06-RESEARCH Open Q2 / Claude's Discretion). Por-doc e por-run: filtrar `AuditLog` por `document_id` ou `run_id`. NUNCA perda; falha controlada.

---

### `app/api/automations.py` (controller, CRUD + ações)

**Análogo PRIMÁRIO:** `app/api/templates.py` (1:N aninhado, In/Patch/Out, 409/422/404/204)
**Análogo de AÇÕES:** `app/api/documents.py` (POST approve/retry/reclassify com guard de estado + reenqueue)

**Estrutura In/Patch/Out + engine via `request.app.state`** (templates.py:127-156, 207-228):
```python
router = APIRouter(prefix="/templates", tags=["templates"])

@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(request: Request, body: TemplateIn) -> TemplateOut:
    engine = request.app.state.engine
    with get_session(engine) as session:
        ...
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, ...) from exc
```

**Coleção filha substituída inteira no PATCH (delete-orphan)** (templates.py:170-181, 248-249): `_apply_fields` substitui `template.fields = [...]`. Para regras: as `RuleCondition`s da regra seguem o mesmo padrão (substituir coleção no PATCH).

**Ações POST com guard de estado + reenqueue** (documents.py:475-510, 624-652):
```python
@router.post("/documents/{document_id}/approve", response_model=DocumentDetailOut)
def approve_document(request: Request, document_id: int) -> DocumentDetailOut:
    ...
    try:
        transition(session, doc, DocState.CONCLUIDO)
    except InvalidTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
```
> `POST /dry-run`, `POST /apply` (por-doc e por-lote, D-03), `POST /undo` seguem este molde: guard semântico de estado → ação → 409 em transição inválida. Reenqueue do step `apply` reusa o helper `_requeue` (documents.py:462-472 → `repo.requeue_step`/`repo.enqueue`). NÃO logar valores extraídos (documents.py:25-27).

---

### `app/models/audit_log.py` (model — ESTENDER)

**Análogo:** `app/models/classification.py` (FK ondelete, colunas Text/String, nullable, relationship)

**Estado atual mínimo** (audit_log.py:20-35): `id`, `document_id` (FK SET NULL nullable), `action`, `details` (Text), `created_at`, `document` relationship.

**Colunas a adicionar (migração 0006 — 06-RESEARCH Code Example "Extensão do AuditLog"):** `status` (String, server_default `"done"`), `source_path` (Text), `dest_path` (Text), `run_id` (String, AUT-05 batch), `content_hash` (String(64), undo via CAS). Seguir o estilo de colunas de `classification.py:82-108` (Mapped + mapped_column + server_default).

---

### `app/models/automation_rule.py` (novo model)

**Análogo:** `app/models/template.py` (`Template` 1:N `TemplateField`)

**Pai com relationship cascade delete-orphan** (template.py:30-56):
```python
class Template(Base):
    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True, unique=True, nullable=False)
    fields: Mapped[list["TemplateField"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )
```

**Filha com FK ondelete CASCADE** (template.py:59-82):
```python
class TemplateField(Base):
    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True, nullable=False
    )
```
> `AutomationRule` (priority, action/padrão nome+pasta, active) 1:N `RuleCondition` (campo, operador, valor, conjunção E/OU) com o MESMO cascade. D-05: coluna `priority` ordenável; primeira-que-casa-vence. Registrar em `models/__init__.py` (`__all__`).

---

### `app/alembic/versions/0006_automations.py` (migration)

**Análogo:** `0004_templates_classification.py` (create_table) + `0005_confidence_review.py` (batch add_column)

**create_table com FK ondelete + índices** (0004:37-104):
```python
op.create_table('templates', sa.Column('id', sa.Integer(), nullable=False), ...)
with op.batch_alter_table('templates', schema=None) as batch_op:
    batch_op.create_index(batch_op.f('ix_templates_name'), ['name'], unique=True)
```

**add_column em tabela existente via batch** (0005:34-48):
```python
with op.batch_alter_table('classification_results', schema=None) as batch_op:
    batch_op.add_column(sa.Column('confidence_score', sa.Float(), nullable=True))
```
> **CAVEAT TRAVADO (0004:18-20, 0005:16-19):** estender SÓ `audit_log` (batch add_column) e CRIAR as tabelas de regra. NÃO fazer `batch_alter_table('documents')` — preservar intacto o trigger `trg_documents_updated_at` (criado na 0002). `revision='0006'`, `down_revision='0005'`. `downgrade` dropa na ordem inversa (filhas antes das pais).

---

### `app/queue/worker.py` (MODIFICAR — novo step `apply`)

**Análogo:** o próprio `worker.py` (auto-análogo)

**Bifurcação por step em `_dispatch` — coroutine vs to_thread** (worker.py:154-182):
```python
if step == EXTRACT_STEP:
    with get_session(engine) as session:
        await extract_stage(session, content_hash=original_hash)
elif step == CLASSIFY_STEP:
    forced = json.loads(payload).get("forced_template_id")
    with get_session(engine) as session:
        await classify_stage(session, content_hash=original_hash, forced_template_id=forced)
else:
    await asyncio.to_thread(_process_job_blocking, engine, ...)
```
> Adicionar `elif step == APPLY_STEP:` chamando `apply_stage`. Fileops é IO-bound mas síncrono — se `apply_stage` for `def` (não async), despachar via `asyncio.to_thread`; se for coroutine, `await` direto. Definir conforme o desenho do stage. Cada caminho abre SUA própria sessão.

**Sweep idempotente de captura de docs prontos** (worker.py:302-342):
```python
def enqueue_pending_classifications(session: Session) -> int:
    docs = session.scalars(
        select(Document).where(
            Document.state == DocState.PROCESSANDO,
            Document.last_completed_step == EXTRACTED_STEP,
            ~Document.content_hash.in_(select(Document.content_hash).join(ClassificationResult)),
        )
    ).all()
    for doc in docs:
        repo.enqueue(session, original_hash=doc.content_hash, step=CLASSIFY_STEP, payload=...)
```
> Para auto-aplica (D-01 / 06-RESEARCH Open Q3): novo `enqueue_pending_applications` pega docs `PROCESSANDO + last_completed_step="classificado"` de ALTA confiança (score ≥ `review_confidence_threshold`) sem `AuditLog(status="done")`. Adicionar a chamada em `_sweep_pending` (worker.py:345-369). Idempotente por UNIQUE(content_hash, step).

**Routing de FALHA por step** (worker.py:185-194): adicionar `APPLY_STEP` ao ramo `_fail_document_for_content_hash`. **NUNCA setar `document.state` direto — sempre `transition`** (worker.py:84, 101).

**Lock de arquivo Windows como FALHA retryável** (06-RESEARCH Pitfall 6): `PermissionError`/`OSError` (WinError 32) sobe ao worker → `schedule_retry` (worker.py:234-255), sem corromper. O write-ahead deixa o estado reconciliável.

---

### `src/pages/AutomationsPage.tsx` (REESCREVER — hoje é mock) + `src/pages/DryRunPage.tsx`

**Análogo de S1/S2/S3 (reescrita do mock):** `src/pages/TemplatesPage.tsx`
**Análogo de S4 (dry-run table):** `src/pages/DocumentsPage.tsx`

**Hooks + estados de tela (loading/erro/vazio)** (TemplatesPage.tsx:54-71):
```typescript
const templatesQuery = useTemplates()
const isInitialLoading = templatesQuery.isLoading && !templatesQuery.data
const isError = templatesQuery.isError && !templatesQuery.data
const isEmpty = !isInitialLoading && !isError && templates.length === 0
```

**Form inline com linhas de condição (`select` + `select` + input)** (TemplatesPage.tsx:232-282): cada campo é um card `padding:14` com `select className="select"` + input `search-input`. Para S2: linha de condição = `select` campo + `select` operador (`= > < contém`) + input valor + combinador E/OU. Reordenação ↑/↓ com `row-action` + `aria-label`+`title` (06-UI-SPEC §Visuals).

**Diálogo de confirmação (molde S6 undo)** (TemplatesPage.tsx:457-499): overlay `position:fixed inset:0` + card `padding:22` + 2 CTAs. Para S6 (undo): NUNCA linguagem destrutiva vermelha — comunicar reversibilidade (06-UI-SPEC Copywriting).

**Tabela dry-run (S4)** — DocumentsPage.tsx:74-88 (filtro + seleção `allIds`/`allSel`) e `table.docs` com checkbox por linha + por lote (D-03). Colunas origem→destino em `var(--font-mono)`; badge de colisão (`--st-leitura` âmbar D-09 / `--st-encontrado` azul D-10 / `--st-erro` vermelho D-07). CTA "Aplicar automações" só após preview carregar.

---

### `src/hooks/useAutomations.ts` + `src/lib/api.ts` + `src/types.ts`

**Análogo:** `src/hooks/useTemplates.ts` (CRUD) + `src/hooks/useDocuments.ts` (polling)

**Query + mutations invalidando a key** (useTemplates.ts:16-48):
```typescript
const TEMPLATES_KEY = ['templates'] as const
export function useTemplates() {
  return useQuery({ queryKey: TEMPLATES_KEY, queryFn: getTemplates })
}
export function useCreateTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TemplateCreate) => createTemplate(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: TEMPLATES_KEY }),
  })
}
```
> `useAutomations` para CRUD de regras (invalida `['automations']`). Dry-run/apply/undo são mutations que invalidam `['documents']` + `['automations']`. Polling do dry-run reusa o padrão `useDocuments` (refetchInterval 4000, `keepPreviousData`, `refetchIntervalInBackground:false`).

**Client tipado `request<T>` lançando em erro** (api.ts:35-53): reusar tal-qual; adicionar `getAutomationRules`/`createAutomationRule`/`updateAutomationRule`/`deleteAutomationRule`/`postDryRun`/`postApply`/`postUndo`. 204 sem corpo já tratado (api.ts:51).

---

## Shared Patterns

### Persistência atômica (commit único / transition comita junto)
**Source:** `app/pipeline/state_machine.py` (`transition`, linhas 24-63) + `app/classification/stage.py:341-364`
**Apply to:** `automation/stage.py`, `automation/undo.py`, todos os endpoints de ação em `api/automations.py`
```python
def transition(session, document, to_state, completed_step=None) -> Document:
    if not is_valid_transition(from_state, to_state):
        session.rollback()
        raise InvalidTransition(from_state, to_state)  # estado intacto (D-06)
    document.state = to_state
    if completed_step is not None:
        document.last_completed_step = completed_step
    session.commit()   # comita estado + tudo pendente JUNTO
    session.refresh(document)
    return document
```
Allowlist relevante (states.py:25-43): `PROCESSANDO → {EM_REVISAO, CONCLUIDO, QUARENTENA, FALHA}`; `EM_REVISAO → {... CONCLUIDO ...}`. **CONCLUIDO é terminal (sem saídas)** — 06-RESEARCH Open Q3: definir no plan se o `apply` roda ANTES da transição final a CONCLUIDO. NUNCA inventar auto-laço PROCESSANDO→PROCESSANDO.

### Audit write-ahead (intent → executa → done)
**Source:** 06-RESEARCH Pattern 2 (novo) + idempotência de `stage.py:163-174`
**Apply to:** `automation/stage.py`, `automation/fileops.py`
`AuditLog(status="intent", source_path, dest_path, run_id, content_hash)` + `session.commit()` ANTES de tocar o disco; após `safe_move`, atualizar para `status="done"` + transition num commit. Crash no meio = `intent` órfão reconciliável no startup (espelha `repo.requeue_running`, repo.py:218-233 + worker.py:379-382).

### Reenqueue idempotente de step
**Source:** `app/api/documents.py:462-472` (`_requeue`) + `app/queue/repo.py` (`enqueue`/`requeue_step`)
**Apply to:** `api/automations.py` (apply por-doc/lote), sweep do worker
```python
def _requeue(session, *, content_hash, step, payload):
    rows = repo.requeue_step(session, content_hash=content_hash, step=step, payload=json.dumps(payload))
    if rows == 0:
        repo.enqueue(session, original_hash=content_hash, step=step, payload=json.dumps(payload))
```
UNIQUE `uq_jobs_hash_step` é a barreira de idempotência; `enqueue` é no-op (retorna `None`) quando já existe (repo.py:70-77).

### Logging (não vazar conteúdo)
**Source:** `app/classification/stage.py:34` + `app/api/documents.py:25-27`
**Apply to:** TODOS os módulos da fase
Logar só metadados (`doc.id`, paths, ids, run_id, status). NUNCA valores de campo/full_text/conteúdo do documento (V7/V9, 06-RESEARCH Security Domain). O `AuditLog` guarda paths (necessário ao undo) mas não conteúdo de campos sensíveis.

### Confinamento de destino (path traversal V4)
**Source:** `app/api/watched_folders.py:43-81` (`_normalize_path` + `resolve()` + `is_symlink()` check)
**Apply to:** `automation/naming.py` (resolução de destino)
06-RESEARCH Security Domain V4: o destino resolvido de tokens `{campo}` (valores da IA, não-confiáveis) DEVE ser confinado sob raiz-base via `resolved.is_relative_to(base)`; sanitização remove `\ /` mas confirmar confinamento por `resolve()` + checagem de prefixo. Não seguir symlinks no destino (`is_symlink()`, padrão watched_folders.py:65).

### Estados de cor/status no frontend (tokens travados)
**Source:** `src/components/StatusPill.tsx` (`STATE_PILL` record) + 06-UI-SPEC §Color
**Apply to:** `AutomationsPage.tsx`, `DryRunPage.tsx`
Reusar `StatusPill state="concluido"` (verde `--st-tratado`) para aplicado; `.badge` âmbar (`--st-leitura`) colisão D-09; azul (`--st-encontrado`) duplicata D-10; vermelho (`--st-erro`) bloqueio D-07/falha. NUNCA hex hardcoded — sempre `var(--st-*)`.

---

## No Analog Found

Nenhum arquivo sem análogo. Toda peça desta fase tem um molde direto no codebase
(06-RESEARCH "Key insight": cada peça de segurança já está construída — o valor é
orquestrá-las). As únicas LÓGICAS genuinamente novas (sem arquivo-irmão idêntico)
têm forma derivada de análogos puros:

| Lógica nova | Padrão derivado de | Observação |
|-------------|--------------------|------------|
| Ramo cross-device EXDEV (AUT-06) | `cas.py` os.replace + 06-RESEARCH Pattern 3 | Padrão de código completo no research; testar EXDEV com temp dirs no Linux (Windows-only marcado p/ verificação manual) |
| Avaliador de condições E/OU com precedência (D-05) | `validation/fields.py` dispatch + `matcher.decide` | Combinação E/OU é lógica nova, mas o dispatch por operador espelha o por-`field_type` |
| Reconciliação de `intent` órfão no startup | `repo.requeue_running` + `worker` sweep | Espelha resume de jobs running; aplicar a `AuditLog(status="intent")` |

---

## Metadata

**Analog search scope:** `backend/app/{automation,classification,storage,api,models,queue,validation,pipeline}/`, `backend/alembic/versions/`, `frontend/src/{pages,hooks,lib,components}/`
**Files scanned:** ~30 (12 backend lidos na íntegra + 6 frontend + 2 migrações + worker/repo/config)
**Pattern extraction date:** 2026-06-17
**Dependências novas:** nenhuma (stdlib + libs já instaladas — confirmado 06-RESEARCH §Standard Stack e 06-UI-SPEC §Registry Safety)

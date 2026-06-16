# Phase 4: Templates, Sub-templates e Classificação - Pattern Map

**Mapped:** 2026-06-16
**Files analyzed:** 21 (15 backend + 6 frontend) novos/modificados
**Analogs found:** 18 / 21 (3 sem análogo direto — módulos de validação determinística)

> **Insight central (confirmado pela pesquisa):** ~90% desta fase é **espelhamento** da fundação das Fases 1–3, já no repositório. O código genuinamente novo sem análogo é: (a) o matcher local por sinais (D-02), (b) o módulo de validação determinística (Módulo 11 + parsers pt-BR), e (c) o construtor de template na UI. Todo o resto copia padrões existentes 1-para-1.

---

## File Classification

| Novo/Modificado | Role | Data Flow | Análogo mais próximo | Qualidade |
|-----------------|------|-----------|----------------------|-----------|
| `backend/app/models/template.py` (Template + TemplateField) | model | CRUD | `backend/app/models/extraction.py` + `document.py` | exact |
| `backend/app/models/classification.py` (ClassificationResult + FilledField) | model | CRUD | `backend/app/models/extraction.py` + `usage.py` | exact |
| `backend/app/models/__init__.py` (registrar novos modelos) | model-registry | — | `backend/app/models/__init__.py` (atual) | exact |
| `backend/alembic/versions/0004_*.py` | migration | — | `backend/alembic/versions/0003_extractions.py` | exact |
| `backend/app/classification/stage.py` (`classify_stage`) | service | event-driven (stage) | `backend/app/extraction/stage.py` | exact |
| `backend/app/classification/schema.py` (desempate + faltantes) | schema | request-response (IA) | `backend/app/extraction/schema.py` | exact |
| `backend/app/classification/matcher.py` (sinais locais D-02) | service | transform (puro) | `backend/app/extraction/router.py` (estilo) | role-match |
| `backend/app/classification/filler.py` (mapeia pares→campos D-05) | service | transform (puro) | `backend/app/extraction/stage.py` (`_fields_to_json`) | partial |
| `backend/app/classification/openai_client.py` (ou reuso) | service | request-response (IA) | `backend/app/extraction/openai_client.py` | exact |
| `backend/app/validation/doc_ids.py` (Módulo 11 CNPJ/CPF) | utility | transform (puro) | — (sem análogo; estilo `pdf_io`/módulo-função) | no-analog |
| `backend/app/validation/dates.py` (dateutil dayfirst→ISO) | utility | transform (puro) | — (estilo módulo-função) | no-analog |
| `backend/app/validation/money.py` (pt-BR→Decimal) | utility | transform (puro) | — (estilo módulo-função) | no-analog |
| `backend/app/validation/fields.py` (orquestra por tipo D-09/D-11) | service | transform (puro) | `backend/app/extraction/router.py` (estilo seam) | role-match |
| `backend/app/queue/worker.py` (add `step="classify"` + sweep) | service | event-driven (queue) | `backend/app/queue/worker.py` (atual: `extract`) | exact (estende) |
| `backend/app/api/templates.py` (CRUD) | route | CRUD | `backend/app/api/watched_folders.py` | exact |
| `backend/app/api/documents.py` (estender `GET /documents/{id}` S4) | route | request-response | `backend/app/api/documents.py` (atual) | exact (estende) |
| `backend/app/config.py` (limiar classificação + `openai_classify_*`) | config | — | `backend/app/config.py` (`openai_extract_*`) | exact (estende) |
| `backend/app/main.py` (registrar router templates) | config | — | `backend/app/main.py` (atual) | exact (estende) |
| `frontend/src/hooks/useTemplates.ts` | hook | CRUD | `frontend/src/hooks/useWatchedFolders.ts` | exact |
| `frontend/src/lib/api.ts` (+ funções de template) | utility | request-response | `frontend/src/lib/api.ts` (atual) | exact (estende) |
| `frontend/src/types.ts` (substituir `Template` mock pela forma real) | types | — | `frontend/src/types.ts` (`Folder`/`FolderCreate`/`FolderPatch`) | exact |
| `frontend/src/pages/TemplatesPage.tsx` (substitui mock) | component | CRUD | `frontend/src/pages/ConfigPage.tsx` (`PastasTab`) | exact |
| `frontend/src/pages/DocumentsPage.tsx` (estender S4 leitura) | component | request-response | `frontend/src/pages/ConfigPage.tsx` (estados loading/erro/vazio) | role-match |

---

## Shared Patterns

> Os padrões abaixo são transversais e devem ser aplicados em TODOS os arquivos da role indicada. O planner deve referenciar estes excertos em cada plano.

### Stage atômico idempotente (não cobrar IA duas vezes)
**Source:** `backend/app/extraction/stage.py` linhas 74-185
**Apply to:** `classification/stage.py`
**Regra dura (Pitfall 2 — double-charge):** checar o registro existente ANTES de qualquer chamada paga; um único `session.commit()` ao final; erro propaga ao worker (sem try/catch no stage); avançar SÓ o marcador interno em memória (NUNCA `mark_step`, que comita sozinho; NUNCA `transition(PROCESSANDO→PROCESSANDO)`).

```python
# linhas 97-111 — localiza o bloco + idempotência (no-op se já existe registro)
doc = session.scalar(select(Document).where(Document.content_hash == content_hash))
if doc is None:
    raise ValueError("Document inexistente para content_hash informado")
existing = session.scalar(select(Extraction).where(Extraction.document_id == doc.id))
if existing is not None:
    return ExtractStageResult(route=existing.route, called_ai=False)  # NÃO re-cobra

# linhas 151-176 — PERSISTÊNCIA ATÔMICA: registro + Usage + marcador num único commit
session.add(Extraction(document_id=doc.id, ...))
session.add(Usage(document_id=doc.id, step=USAGE_STEP, prompt_tokens=..., completion_tokens=...))
doc.last_completed_step = EXTRACTED_STEP   # marcador interno EM MEMÓRIA (D-07)
session.commit()                            # ÚNICO commit; crash antes daqui = rollback total
```
Para a Fase 4: `EXTRACTED_STEP="extraido"` → `CLASSIFIED_STEP="classificado"` (D-04); `USAGE_STEP="extract"` → `"classify"` (USE-02); a idempotência usa `ClassificationResult` (UNIQUE document_id) no lugar de `Extraction`.

### Schema Structured Outputs list-of-pairs (NUNCA dict aberto)
**Source:** `backend/app/extraction/schema.py` linhas 19-60
**Apply to:** `classification/schema.py` (desempate D-01 + campos faltantes D-06)
**Regra dura (Pitfall 1 — strict mode):** chaves variáveis viram DADOS (`key`/`value`), nunca forma do schema; campos opcionais → `nullable` (`int | None`); `description` em cada Field guia o modelo.

```python
# linhas 19-33 — par dado→valor como objeto fixo (reusar para os faltantes D-06)
class ExtractedField(BaseModel):
    key: str = Field(description="Nome do dado, ex.: 'cnpj_emitente', 'valor_total'")
    value: str = Field(description="Valor lido, como aparece no documento (sem normalizar)")
    confidence: float = Field(description="0.0-1.0: confiança na leitura deste campo")
```
Para o desempate (D-01), modelar (ver `04-RESEARCH.md` Pattern 2): `matched_template_id: int | None` (null = nenhum casa → quarentena) + `confidence: float` + `reason: str`. Para os faltantes (D-06): `fields: list[ExtractedField]`.

### Cliente OpenAI: Responses API + usage + recusa
**Source:** `backend/app/extraction/openai_client.py` linhas 68-134
**Apply to:** `classification/openai_client.py` (ou reusar funções deste módulo — A4 da pesquisa)
**Pontos load-bearing:** `.get_secret_value()` SÓ no ponto de criação do cliente (CFM 5); `output_parsed is None` = recusa → levanta exceção (sem retry aqui — backoff é da fila); mapear `usage.input_tokens→prompt_tokens`, `usage.output_tokens→completion_tokens`.

```python
# linhas 68-81 — segredo nunca logado + mapeamento de usage
def _client() -> AsyncOpenAI:
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    return AsyncOpenAI(api_key=api_key)

def _map_usage(response) -> ExtractionUsage:
    usage = response.usage
    return ExtractionUsage(prompt_tokens=usage.input_tokens, completion_tokens=usage.output_tokens)

# linhas 121-133 — chamada Responses API + Structured Outputs (text_format Pydantic)
response = await client.responses.parse(
    model=settings.openai_extract_model,
    instructions=SYSTEM_INSTRUCTIONS,     # system prompt FIXO, sem few-shot
    input=[{"role": "user", "content": [{"type": "input_text", "text": native_text}]}],
    text_format=ExtractionResult,
    temperature=settings.openai_extract_temperature,
    max_output_tokens=settings.openai_extract_max_output_tokens,
)
return _unwrap(response), _map_usage(response)
```

### Quarentena via state machine (nunca setar state direto)
**Source:** `backend/app/pipeline/state_machine.py` linhas 24-63 + `states.py` linhas 19-44
**Apply to:** `classification/stage.py` (TPL-04 — nenhum template casa)
A aresta `PROCESSANDO → QUARENTENA` JÁ está na allowlist (`states.py` linha 28). Usar `transition(session, doc, DocState.QUARENTENA)`. NÃO setar `document.state` direto. Para "classificado" (D-04), o estado de topo NÃO muda (continua PROCESSANDO) — avançar só `last_completed_step` em memória + commit no stage (não `transition`, não `mark_step`).

### Log sem vazar conteúdo (V7/V8)
**Source:** `backend/app/extraction/stage.py` linhas 178-184; `openai_client.py` linhas 107-114
**Apply to:** todos os stages/clients da fase
Logar SÓ metadados (`document_id`, `template_id`, `route`, `doc_type_guess`, motivo de recusa). NUNCA `full_text`, `fields`, valores extraídos nem a chave.

---

## Pattern Assignments

### `backend/app/models/template.py` + `classification.py` (model, CRUD)

**Análogo:** `backend/app/models/extraction.py` (linhas 17-57) — colunas `Mapped`/`mapped_column`, FK `ondelete="CASCADE"`, UNIQUE para idempotência, `relationship` com `back_populates`, `created_at` com `server_default=func.now()`, schema só via Alembic.

```python
# extraction.py linhas 34-56 — forma a espelhar para os 4 novos modelos
class Extraction(Base):
    __tablename__ = "extractions"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True, unique=True, nullable=False,   # UNIQUE = idempotência
    )
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)   # list-of-pairs serializado
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    document: Mapped["Document"] = relationship(back_populates="extraction")
```

- `ClassificationResult` deve ter `UNIQUE(document_id)` (Pitfall 2: 1 classificação por bloco) + FK nullable `template_id` (null = quarentena) + relação com `Extraction`/`Document` (D-07: preserva a Extraction bruta).
- Sinais identificadores (D-02) e validações por campo (D-09) persistidos como JSON/colunas no `TemplateField` (A3 da pesquisa); `Text` serializado segue o padrão de `fields_json`.
- **Lembrete `Document` (document.py linhas 92-104):** ao adicionar `relationship` reverso para os novos modelos, espelhar o `extraction: Mapped["Extraction | None"]` (1:1, `uselist=False`, `cascade="all, delete-orphan"`).
- **Registrar em `models/__init__.py`** (linhas 8-29): importar + adicionar ao `__all__`, senão o autogenerate do Alembic e os testes de schema não veem o modelo.

---

### `backend/alembic/versions/0004_*.py` (migration)

**Análogo:** `backend/alembic/versions/0003_extractions.py` (linhas 25-63)

```python
# linhas 25-27 — encadeamento de revisão (0003 é o predecessor → next 0004)
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'

# linhas 33-55 — create_table + UNIQUE index via batch_alter_table
op.create_table('extractions', sa.Column('id', sa.Integer(), nullable=False), ...,
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'))
with op.batch_alter_table('extractions', schema=None) as batch_op:
    batch_op.create_index(batch_op.f('ix_extractions_document_id'), ['document_id'], unique=True)
```
- `revision='0004'`, `down_revision='0003'`. Criar as 3-4 tabelas novas (templates, template_fields, classification_results, filled_fields).
- **Caveat herdado (linhas 14-16):** como a 0004 só CRIA tabelas e NÃO toca `documents`, NÃO recria o trigger `trg_documents_updated_at` (mesmo caso resolvido da 0003).

---

### `backend/app/classification/stage.py` (`classify_stage`)

**Análogo:** `backend/app/extraction/stage.py` (arquivo inteiro, 74-191). Ver "Stage atômico idempotente" em Shared Patterns. Fluxo específico da Fase 4 (`04-RESEARCH.md` diagrama linhas 163-175): checa `ClassificationResult` existente → lê `Extraction` do bloco → matcher local → (talvez IA desempate) → quarentena OU mapeia pares→campos → (talvez IA faltantes) → valida/normaliza → commit único (`ClassificationResult` + `FilledField`s + `Usage(step="classify")` + marcador `"classificado"`).

`_fields_to_json` (stage.py linhas 188-191) é o padrão de serialização list-of-pairs → JSON para persistir.

---

### `backend/app/classification/matcher.py` (sinais locais D-02) — role-match

**Análogo de ESTILO:** `backend/app/extraction/router.py` (linhas 22-43) — função de módulo única, pura, mínima, sem DB nem OpenAI, sem classe. O matcher é puro sobre `Extraction.fields_json`/`full_text`/`doc_type_guess` e devolve confiança por template.

```python
# router.py linhas 22-42 — forma do seam: função pura, decide e retorna, sem efeitos
def choose(blob: bytes) -> str:
    blob_type = pdf_io.detect_blob_type(blob)
    if blob_type in ("jpeg", "png"):
        return "vision"
    min_chars = get_settings().openai_extract_min_chars_per_page
    _text, route = pdf_io.extract_text_and_decide(blob, min_chars_per_page=min_chars)
    return route
```
Formato do sinal (discretion D-02, recomendação `04-RESEARCH.md` Open Question 2): lista de termos/chaves cuja presença em `fields_json.key` OU `full_text` (case-insensitive) pontua; confiança = fração presente. **NÃO embutir a classificação em `router.choose`** (Anti-Pattern / Critical Failure Mode 4 — mata o seam D-03).

---

### `backend/app/validation/{doc_ids,dates,money,fields}.py` — NO ANALOG (módulo novo)

**Sem análogo direto no codebase.** Espelhar o **estilo de módulo-função** de `extraction/pdf_io.py` / `extraction/router.py` (funções puras de módulo, sem classe). Código de referência pronto em `04-RESEARCH.md` linhas 313-353 (Módulo 11 CNPJ, `normalize_date` dayfirst, `normalize_money_brl` Decimal).

**Regras duras (Pitfall 3):**
- `dateutil.parser.parse(s, dayfirst=True)` SEMPRE (defaults en-US trocam dia↔mês).
- Moeda: `Decimal`, NUNCA `float`; remover `.` (milhar), trocar `,`→`.`.
- DV CNPJ/CPF: algoritmo Módulo 11 próprio (CLAUDE.md PROÍBE dep externa).
- Sempre guardar bruto + normalizado (D-11); parse falho → marca inválido (D-10), nunca chuta.
- `fields.py` orquestra por tipo de campo — estilo seam de `router.py` (despacho por etiqueta de tipo: texto/número/data/moeda/CPF-CNPJ/booleano).
- **ReDoS (V5):** regex do operador via `re.fullmatch` sobre input já limitado em tamanho; não compilar em loop quente sem cache.

---

### `backend/app/queue/worker.py` (estender com `step="classify"`)

**Análogo:** o PRÓPRIO arquivo (`worker.py`) — o padrão `extract` já está pronto; replicar para `classify`.

```python
# linhas 47-49 — adicionar a constante do step
EXTRACT_STEP = "extract"   # + CLASSIFY_STEP = "classify"

# linhas 136-159 (_dispatch) — adicionar ramo classify (coroutine, await direto, NÃO to_thread)
if step == EXTRACT_STEP:
    with get_session(engine) as session:
        await extract_stage(session, content_hash=original_hash)
# + elif step == CLASSIFY_STEP: await classify_stage(session, content_hash=original_hash)

# linhas 162-171 (_fail_for_step) — rotear a FALHA por content_hash (igual a extract)

# linhas 239-276 (enqueue_pending_extractions) — espelhar enqueue_pending_classifications:
#   Documents com last_completed_step=="extraido" e SEM ClassificationResult → enfileira classify
#   Idempotente por UNIQUE(content_hash, step) na tabela jobs (cobre os LEGADOS — sweep no startup)
```
**Anti-pattern (Pitfall 4):** NÃO enfileirar `classify` de dentro do `extract_stage` (quebra o commit único — `repo.enqueue` comita por si). Usar o sweep idempotente no startup (linhas 291-296) + gatilho fora do commit. **`repo.py` não muda** — `enqueue` já aceita `step` arbitrário (linha 47).

---

### `backend/app/api/templates.py` (CRUD)

**Análogo:** `backend/app/api/watched_folders.py` (linhas 40-200) — router fino, `*In`/`*Patch`/`*Out` Pydantic, `from_attributes`, 404/409/422, `IntegrityError`→409, `request.app.state.engine` + `get_session`.

```python
# linhas 40, 84-124 — router + esquemas In/Patch/Out (from_attributes para o Out)
router = APIRouter(prefix="/watched-folders", tags=["watched-folders"])
class WatchedFolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; path: str; ...

# linhas 135-156 — POST com IntegrityError→409
@router.post("", response_model=WatchedFolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(request: Request, body: WatchedFolderIn) -> WatchedFolder:
    ...
    try: session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, ...) from exc

# linhas 159-200 — PATCH parcial (404 se não acha) + DELETE 204
```
- Prefix `/templates`. Body de criação aninha a lista de campos (cada um com tipo/validações/sinais).
- **Registrar em `main.py`** (linhas 25-26, 78-79): `from app.api import templates as templates_api` + `app.include_router(templates_api.router)`.

---

### `backend/app/api/documents.py` (estender — `GET /documents/{id}` para S4)

**Análogo:** o PRÓPRIO arquivo (linhas 34-111). Recomendação `04-RESEARCH.md` Open Question 3: criar `GET /documents/{id}` de DETALHE (não inflar a lista do polling) retornando template casado + campos (bruto/normalizado) + marca válido/inválido + estado quarentena. Espelhar `DocumentOut` (linhas 34-42) e o padrão de join (linhas 75-88). Somente leitura (S4 é Fase 5 quem resolve).

---

### `backend/app/config.py` (estender)

**Análogo:** o bloco `openai_extract_*` (linhas 88-132) — `Field(default=..., validation_alias=AliasChoices(...))`, lido de env sem deploy. Adicionar: limiar de classificação GLOBAL (discretion D-03, default tunável) + `openai_classify_model`/temperatura se a chamada de classificação precisar de modelo próprio (default = reusar `openai_extract_model`). Documentar o default do limiar como os `queue_*`/`openai_extract_*`.

---

### Frontend

#### `frontend/src/hooks/useTemplates.ts`
**Análogo:** `frontend/src/hooks/useWatchedFolders.ts` (arquivo inteiro, 16-48) — 1-para-1.
```typescript
// linhas 16-48 — queryKey constante + invalidate em onSuccess
const FOLDERS_KEY = ['watched-folders'] as const
export function useWatchedFolders() { return useQuery({ queryKey: FOLDERS_KEY, queryFn: getWatchedFolders }) }
export function useCreateFolder() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (body) => createWatchedFolder(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: FOLDERS_KEY }) })
}
// useUpdate / useDelete idem (PATCH/DELETE)
```
→ `TEMPLATES_KEY = ['templates']`; `useTemplates`/`useCreateTemplate`/`useUpdateTemplate`/`useDeleteTemplate`.

#### `frontend/src/lib/api.ts` (estender)
**Análogo:** as funções `*WatchedFolder` (linhas 63-87). O wrapper `request<T>` (linhas 29-47), `ApiError`, e o tratamento 204 já existem e são reusados — só adicionar `getTemplates`/`createTemplate`/`updateTemplate`/`deleteTemplate` apontando para `/templates`.

#### `frontend/src/types.ts` (substituir mock)
**Análogo:** `Folder`/`FolderCreate`/`FolderPatch` (linhas 42-63). Substituir o `Template` MOCK (linhas 82-88) pela forma real da API (id, name, type, fields[], sinais), espelhando o trio In/Patch/Out do backend.

#### `frontend/src/pages/TemplatesPage.tsx` (substitui mock)
**Análogos:**
- **Grid de cards** (S1): o PRÓPRIO `TemplatesPage.tsx` atual (linhas 4-45) tem a estética travada (`.sec-head`, `.btn-primary`, `.tpl-grid`, `.tpl-card`, `.tpl-icon`, `.tpl-name`, `.tags`/`.tag`) — manter as classes, trocar `TEMPLATES` mock por `useTemplates()`.
- **Form inline + modal destrutivo + estados loading/erro/vazio** (S2/S3): `ConfigPage.tsx` `PastasTab` (linhas 61-310) é o molde EXATO — form `FormState` controlado (linhas 59-119), labels `fontSize:12/fontWeight:600/var(--text-2)` (linhas 145, 155), erro inline em `var(--st-erro)` (linhas 171-173), botões com estado "Salvando…" (linhas 178-184), e o modal de confirmação `confirmRemove` (linhas 267-307).

```tsx
// ConfigPage.tsx linhas 88-111 — submitForm: valida → create OU update → onSuccess fecha
const submitForm = () => {
  if (!form) return
  const path = form.path.trim()
  if (!path) { setFormError('Informe o caminho da pasta.'); return }
  if (form.id == null) createFolder.mutate({...}, { onSuccess: closeForm, onError })
  else updateFolder.mutate({...}, { onSuccess: closeForm, onError })
}
```
**Copy/labels/tokens TRAVADOS:** seguir `04-UI-SPEC.md` ao pé da letra — CTAs contextuais "Salvar template"/"Descartar template"/"Manter template" (NÃO "Cancelar"), pesos só 600/700, cores só via `var(--…)`, ícones do `Icon` próprio. Tipo de campo = `select` com Texto/Número/Data/Moeda/CPF-CNPJ/Booleano; obrigatório = `Switch` existente.

#### `frontend/src/pages/DocumentsPage.tsx` (estender — S4 leitura)
**Análogo:** estados loading/erro/vazio do `PastasTab` (ConfigPage.tsx linhas 209-234). S4 é SOMENTE LEITURA: badge do template casado + tabela campo→valor(bruto)→normalizado + marca válido/inválido (`--st-tratado`/`--st-erro`) + pílula "Quarentena" (`StatusPill` já mapeia `quarentena→leitura` — NÃO alterar). Valores em `var(--font-mono)`.

---

## No Analog Found

| Arquivo | Role | Data Flow | Motivo |
|---------|------|-----------|--------|
| `backend/app/validation/doc_ids.py` | utility | transform | Validação determinística Módulo 11 — nova; código de referência em `04-RESEARCH.md` linhas 313-329. Estilo módulo-função (`pdf_io`). Reutilizável (Fase 7 também usa) |
| `backend/app/validation/dates.py` | utility | transform | Parser de data pt-BR (dateutil dayfirst) — novo; ref `04-RESEARCH.md` linhas 331-340 |
| `backend/app/validation/money.py` | utility | transform | Parser de moeda pt-BR (Decimal) — novo; ref `04-RESEARCH.md` linhas 342-353 |

> `matcher.py` e `filler.py` não estão aqui porque têm análogo de ESTILO forte (`router.py` / `_fields_to_json`), mesmo sendo lógica nova.

## Metadata

**Análogos lidos:** `extraction/stage.py`, `extraction/schema.py`, `extraction/openai_client.py`, `extraction/router.py`, `models/extraction.py`, `models/usage.py`, `models/document.py`, `models/__init__.py`, `queue/worker.py`, `queue/repo.py`, `api/watched_folders.py`, `api/documents.py`, `alembic/versions/0003_extractions.py`, `pipeline/states.py`, `pipeline/state_machine.py`, `config.py`, `main.py`, `frontend/src/hooks/useWatchedFolders.ts`, `frontend/src/lib/api.ts`, `frontend/src/types.ts`, `frontend/src/pages/TemplatesPage.tsx`, `frontend/src/pages/ConfigPage.tsx`
**Escopo de busca:** `backend/app/{models,extraction,classification,validation,queue,api,pipeline}`, `backend/alembic/versions`, `frontend/src/{hooks,lib,pages,components}`
**Arquivos escaneados:** ~40 (todos os fontes .py/.ts/.tsx)
**Data de extração:** 2026-06-16

# Phase 3: Extração Genérica via IA e Medição de Tokens - Pattern Map

**Mapped:** 2026-06-16
**Files analyzed:** 11 (8 novos, 3 modificados, + pyproject)
**Analogs found:** 11 / 11 (todos com análogo direto na própria base Fases 1–2)

> Esta fase é **aditiva sobre um pipeline maduro**. Quase tudo que o executor precisa já existe e foi testado nas Fases 1–2 — o trabalho é **estender padrões existentes**, não inventar. Cada novo arquivo abaixo tem um análogo concreto com `arquivo:linha` para copiar. Os três genuinamente novos (cliente OpenAI, `extract_stage`, modelo `Extraction`) ainda espelham análogos de forma/estrutura.

---

## File Classification

| Novo/Modificado | Role | Data Flow | Análogo mais próximo | Qualidade |
|-----------------|------|-----------|----------------------|-----------|
| `backend/app/extraction/router.py` (NOVO) | service/seam (D-03) | transform/request-response | `backend/app/storage/cas.py` (camada de funções de módulo atrás de interface) | role-match |
| `backend/app/extraction/openai_client.py` (NOVO) | service (cliente externo) | request-response (async) | `backend/app/storage/cas.py` (funções de módulo) + construção de `Settings`/`SecretStr` em `config.py` | role-match |
| `backend/app/extraction/schema.py` (NOVO) | model (Pydantic, não-DB) | transform | AI-SPEC §4b.1 (definição completa) — sem análogo Pydantic-de-IA no repo | partial (usar AI-SPEC) |
| `backend/app/extraction/pdf_io.py` (NOVO) | utility (PyMuPDF) | file-I/O / transform | `backend/app/ingest/splitter.py` (lib de PDF isolada) + `cas.read_bytes` | role-match |
| `backend/app/extraction/stage.py` / `extract_stage` (NOVO) | service (estágio de pipeline) | event-driven (job) / orquestração | `backend/app/pipeline/ingest_stage.py` (`process_ingest`) | **exact** |
| `backend/app/models/extraction.py` (NOVO) | model (SQLAlchemy) | CRUD | `backend/app/models/usage.py` + `audit_log.py` (FK→documents, mesmo cabeçalho) | **exact** |
| `backend/alembic/versions/0003_*.py` (NOVO) | migration | DDL | `backend/alembic/versions/0002_ingestion.py` | **exact** |
| `backend/app/queue/worker.py` (MOD) | service (worker) | event-driven dispatch | o próprio `_run_once` / `_process_job_blocking` (bifurcar por `step`) | self |
| `backend/app/pipeline/ingest_stage.py` (MOD) ou sweep | service | event-driven enqueue | `repo.enqueue` chamado em `watcher.py:144` | role-match |
| `backend/app/config.py` (MOD) | config | — | os tunables `queue_*` já em `config.py:71-86` | **exact** |
| `backend/app/models/__init__.py` (MOD) | registro de modelos | — | o próprio `__init__.py` (adicionar `Extraction` ao import + `__all__`) | self |
| `backend/pyproject.toml` (MOD) | config/deps | — | o próprio `[project.dependencies]` / `[dependency-groups].dev` | self |

---

## Pattern Assignments

### `backend/app/pipeline/stage.py` → `extract_stage` (service, event-driven) — O ARQUIVO CENTRAL

**Análogo:** `backend/app/pipeline/ingest_stage.py` (`process_ingest`). Espelhar **forma, docstring-discipline, atomicidade e isolamento sem HTTP**. Diferença-chave: `extract_stage` é **`async def`** (o `process_ingest` é sync).

**Cabeçalho/contrato isolável** (`ingest_stage.py:1-29, 62-97`): docstring rico explicando garantias (idempotência, atomicidade, estado terminal), `@dataclass(frozen=True)` para o resultado, assinatura `(session, *, ...)` keyword-only, retorno tipado. Copiar esse estilo.

**Ler o bloco do CAS por hash** (mesmo padrão que `ingest_stage.py:120` usa `cas.store`; aqui é leitura):
```python
from app.storage import cas
pdf_bytes = cas.read_bytes(doc.content_hash)   # cas.py:125
```

**Idempotência de resume — checar antes de trabalhar** (espelha `ingest_stage.py:153-160`, que faz `select(Document).where(content_hash==...)` antes de recriar). Aqui: checar `Extraction` existente para o `document_id` ANTES de chamar a IA (evita cobrança dupla, Pitfall 3 do RESEARCH):
```python
already = session.scalar(select(Extraction).where(Extraction.document_id == doc.id))
if already is not None:
    return  # no-op: já extraído, não re-chamar a IA
```

**Commit atômico único, ANTES de `mark_done`** (espelha `ingest_stage.py:174-177` — um único `session.commit()` ao final; "crash antes daqui = rollback total"). Persistir `Extraction` + `Usage` + avançar marcador no **mesmo commit**.

> **CORREÇÃO CRÍTICA sobre estado (divergência AI-SPEC × código real, RESEARCH A4).** O AI-SPEC §4 mostra `transition(... to_state=PROCESSANDO, completed_step="extraido")`. Isso **QUEBRA**: `PROCESSANDO → PROCESSANDO` NÃO está na allowlist (`states.py:25-30`) e `transition` levanta `InvalidTransition` + `rollback` (`state_machine.py:48-55`, docstring linhas 41-44 explicita "PROCESSANDO → PROCESSANDO NÃO estão na allowlist"). **Use `mark_step` no caminho de sucesso:**
> ```python
> from app.pipeline.state_machine import mark_step   # state_machine.py:66
> mark_step(session, doc, "extraido")   # mantém state=PROCESSANDO, atualiza marcador (D-07)
> ```
> ⚠️ Mas `mark_step` faz seu **próprio `session.commit()`** (`state_machine.py:73-75`). Para manter o commit ÚNICO atômico (Pitfall 3), o executor deve: ou (a) gravar `Extraction`+`Usage` na sessão e setar `doc.last_completed_step="extraido"` em memória, comitando tudo de uma vez (mesma técnica que `ingest_stage.py:162-177` usa ao setar `doc.state`/`last_completed_step` em memória e comitar no fim — NÃO via `transition`), ou (b) aceitar `mark_step` como o commit final. Preferir (a) para alinhar à atomicidade do CR-02.

**Caminho de FALHA é via `transition`** (allowlist `PROCESSANDO → FALHA` existe, `states.py:25-30`) — mas isso é feito pelo **worker** ao esgotar retries, exatamente como `_fail_documents_for_original` já faz (`worker.py:65-95`), NÃO dentro do `extract_stage`. O `extract_stage` apenas **levanta** em falha/recusa; o worker captura e roteia (ver dispatch abaixo).

**Sub-armadilha CPU-bound dentro de async** (RESEARCH Pattern 1): só a parte PyMuPDF (`get_text`/`get_pixmap`) vai em `await asyncio.to_thread(...)` de DENTRO do `extract_stage`; a chamada OpenAI fica `await` direto no loop. Mesma razão pela qual o worker hoje usa `to_thread` para o split (`worker.py:115-122`).

---

### `backend/app/queue/worker.py` (MODIFICADO — bifurcar dispatch por `step`)

**Análogo:** o próprio `_run_once` (`worker.py:98-141`). Hoje despacha incondicionalmente via `asyncio.to_thread(_process_job_blocking, ...)` (`worker.py:117-122`).

**Ponto exato de mudança** — após `claim_next` (`worker.py:104-108`), bifurcar por `row.step` (a `Row` já traz `step`, retornado pelo `RETURNING` em `repo.py:111`):
```python
# worker.py — DENTRO do try, no lugar do to_thread atual (linhas 115-122)
if row.step == "ingest":
    await asyncio.to_thread(_process_job_blocking, engine, original_hash=original_hash, payload=row.payload)
elif row.step == "extract":
    # extract_stage é async → roda no loop do worker. NUNCA to_thread (Pitfall 1),
    # NUNCA asyncio.run (já estamos num loop). content_hash do bloco == row.original_hash.
    await _process_extract(engine, content_hash=original_hash, payload=row.payload)
```

**Reusar TODO o esqueleto de erro/retry intacto** (`worker.py:123-141`): o mesmo `except Exception → schedule_retry → (se esgotou) _fail_documents_for_original → mark_done`. Recusa da IA (`output_parsed is None`) deve **levantar** (ex.: `ExtractionRefused`) para cair nesse mesmo caminho — D-08. NÃO reimplementar retry no `extract_stage`.

> ⚠️ **Reaproveitamento de `_fail_documents_for_original`** (`worker.py:65-95`): ele busca Documents por `original_hash` do **original** (`origin_original_id`). Para o job de extract, `original_hash` É o `content_hash` do bloco (Pitfall 2). Então o caminho de FALHA da extração precisa de uma variante que ache o `Document` por `content_hash` (`select(Document).where(Document.content_hash == content_hash)`) e use o mesmo `transition(session, doc, DocState.FALHA)` (`worker.py:87`, allowlist `PROCESSANDO→FALHA`).

**Cada thread/coroutine usa SUA própria sessão** (`worker.py:55, 72, 104, 125, 139` — `with get_session(engine) as session:`). Manter.

---

### `backend/app/extraction/pdf_io.py` (utility, file-I/O) — PyMuPDF

**Análogo:** `backend/app/ingest/splitter.py` (lib de PDF — pikepdf — isolada num módulo de funções; não lido aqui mas referenciado por `ingest_stage.py:42`). Padrão a copiar: **módulo de funções puras** que recebe `bytes`/`Path` e devolve dados, sem tocar DB nem HTTP — igual a `cas.py` (funções de módulo, sem classe, `cas.py:24`).

**Import** (do AI-SPEC §3, confirmado RESEARCH linha 112): `import fitz` (NÃO `import pymupdf`).

**Heurística texto-vs-visão** (RESEARCH Pattern 2, esqueleto):
```python
import fitz
def extract_text_and_decide(pdf_bytes: bytes, min_chars_per_page: int) -> tuple[str, str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts = [page.get_text() for page in doc]
    total = sum(len(t.strip()) for t in texts)
    return "\n".join(texts), ("native_text" if total >= min_chars_per_page * doc.page_count else "vision")
```

> ⚠️ **Detecção PDF vs imagem por magic bytes** (RESEARCH Pitfall 5 / Open Question 2): a Fase 2 ingere imagem como 1 bloco de bytes crus (`ingest_stage.py:137-138`), e o CAS guarda só o hash (`cas.py:125`, sem extensão). `fitz.open(filetype="pdf")` falha em JPG/PNG. Detectar no `pdf_io`/`stage`: `%PDF-` → PDF; `\xFF\xD8` → JPEG; `\x89PNG` → PNG. Imagem → caminho visão direto (a imagem já é a página). **Decisão de planejamento.**

---

### `backend/app/extraction/openai_client.py` (service, request-response async)

**Análogo de forma:** `cas.py` (funções de módulo atrás de interface, `cas.py:24`). **Análogo de construção de cliente com segredo:** `config.py` — a chave é `SecretStr` (`config.py:55`), e o módulo "nada loga nem retorna o valor da chave" (`config.py:11`).

**Padrão de segredo a copiar** (Critical Failure Mode 5):
```python
from app.config import get_settings
client = AsyncOpenAI(api_key=get_settings().openai_api_key.get_secret_value())
# .get_secret_value() SÓ aqui, no ponto de criação. Nunca logar a chave nem o conteúdo.
```

**Sintaxe Responses API + `_unwrap` + recusa** — completa no AI-SPEC §3 (`responses.parse`, `text_format=ExtractionResult`, `output_parsed is None` → `raise ExtractionRefused`). NÃO duplicar aqui.

**Mapeamento de tokens** (RESEARCH Code Examples linhas 314-327): a Responses API expõe `usage.input_tokens`/`output_tokens`, mas o modelo `Usage` usa `prompt_tokens`/`completion_tokens` (`usage.py:30-31`). Mapear `input→prompt`, `output→completion`. Documentar.

---

### `backend/app/extraction/router.py` (service/seam — D-03, o ponto de costura)

**Análogo:** `cas.py` (`cas.py:24`) e `repo.py` (`repo.py:20-24`) — **funções de módulo formando uma fronteira única de acesso**, estilo explicitamente citado em `repo.py:20` ("Funções de módulo, estilo `cas.py`/`state_machine.py`, sem classe"). O router é a interface que Fases 4/7 estendem (D-03): default v1 = "decide native_text vs vision, sempre IA". Manter mínimo e plugável.

```python
def choose(blob: bytes) -> str:   # "native_text" | "vision"
    # v1: heurística de pdf_io. Fases 4/7 plugam aqui o atalho local (custo 0).
    ...
```

---

### `backend/app/models/extraction.py` (model, CRUD)

**Análogo:** `backend/app/models/usage.py` (FK→documents com `ondelete=CASCADE`, `index`, `created_at` com `server_default=func.now()`, relationship recíproca, docstring explicando o papel na fase). Copiar **estrutura exata do cabeçalho e dos campos**.

**Esqueleto** (campos exatos = Claude's Discretion, guiado por AI-SPEC §4b.1 / RESEARCH linhas 341-357):
```python
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.storage.db import Base

class Extraction(Base):
    __tablename__ = "extractions"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, unique=True, nullable=False
    )  # UNIQUE = 1 extração por bloco = idempotência (não re-extrair / não re-cobrar)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)      # list[ExtractedField] serializado
    full_text: Mapped[str] = mapped_column(Text, nullable=False)        # texto nativo (D-06)
    doc_type_guess: Mapped[str] = mapped_column(String, nullable=False)
    doc_type_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    route: Mapped[str] = mapped_column(String, nullable=False)          # "native_text"|"vision" (métrica D-04)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

**Padrão de `Mapped`/`mapped_column`**: idêntico a `usage.py:25-34` e `document.py:36-89`. Para `FK` com docstring de motivação, ver `document.py:66-73`.

> **OBRIGATÓRIO: registrar em `app/models/__init__.py`** (`__init__.py:8-27`) — adicionar `from app.models.extraction import Extraction` e incluir `"Extraction"` no `__all__`. O docstring do `__init__.py:1-6` avisa: o autogenerate do Alembic depende disso. **Relationship recíproca opcional** em `Document` (espelharia `document.py:94-96` `usages`/`pages`).

---

### `backend/alembic/versions/0003_*.py` (migration)

**Análogo:** `backend/alembic/versions/0002_ingestion.py`. Copiar: cabeçalho de revisão (`0002:24-28` → `revision='0003'`, `down_revision='0002'`), `op.create_table` + `op.batch_alter_table` para índices (`0002:74-92`), padrão de FK (`ForeignKeyConstraint([...], ondelete=...)`, `0002:67`).

```python
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
```

```python
op.create_table('extractions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('fields_json', sa.Text(), nullable=False),
    sa.Column('full_text', sa.Text(), nullable=False),
    sa.Column('doc_type_guess', sa.String(), nullable=False),
    sa.Column('doc_type_confidence', sa.Float(), nullable=False),
    sa.Column('route', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
)
with op.batch_alter_table('extractions', schema=None) as batch_op:
    batch_op.create_index(batch_op.f('ix_extractions_document_id'), ['document_id'], unique=True)  # UNIQUE
```

> ⚠️ **Trigger CAVEAT do 0002 NÃO se aplica** se a migração 0003 só CRIAR `extractions` e **não tocar `documents`**. O `batch_alter_table('documents')` é que derrubava `trg_documents_updated_at` (`0002:94-107`). Se 0003 não alterar `documents`, NÃO precisa recriar o trigger. Só replicar o bloco `_TRG_DROP`/`_TRG_CREATE` (`0002:33-39, 105-107`) SE optar por adicionar coluna em `documents` (não recomendado — texto nativo vai em `Extraction.full_text`).

---

### `backend/app/config.py` (MODIFICADO — tunables OPENAI_EXTRACT_*)

**Análogo:** os tunables `queue_*` já existentes (`config.py:71-86`) — **copiar o padrão exato** `Field(default=..., validation_alias=AliasChoices("UPPER", "lower"))`. A chave OpenAI já existe (`config.py:55`, `openai_api_key: SecretStr | None`).

```python
# config.py — adicionar junto aos queue_* (mesmo padrão AliasChoices)
openai_extract_model: str = Field(
    default="gpt-4o-2024-08-06",   # CONFIRMAR vigente na conta; suporta visão + Structured Outputs
    validation_alias=AliasChoices("OPENAI_EXTRACT_MODEL", "openai_extract_model"),
)
openai_extract_temperature: float = Field(
    default=0.0, validation_alias=AliasChoices("OPENAI_EXTRACT_TEMPERATURE", "openai_extract_temperature"),
)
openai_extract_max_output_tokens: int = Field(
    default=4096, validation_alias=AliasChoices("OPENAI_EXTRACT_MAX_OUTPUT_TOKENS", "openai_extract_max_output_tokens"),
)
openai_extract_image_detail: str = Field(
    default="high", validation_alias=AliasChoices("OPENAI_EXTRACT_IMAGE_DETAIL", "openai_extract_image_detail"),
)
openai_extract_min_chars_per_page: int = Field(
    default=..., validation_alias=AliasChoices("OPENAI_EXTRACT_MIN_CHARS_PER_PAGE", "openai_extract_min_chars_per_page"),
)
```

---

### Enfileiramento do job `extract` (MOD `ingest_stage.py` OU novo sweep)

**Análogo:** `repo.enqueue` chamado em `watcher.py:137-150` — monta `payload = json.dumps({...})` e chama `repo.enqueue(session, original_hash=..., step="...", payload=payload)`.

**Chave de idempotência (Pitfall 2 / RESEARCH A1):** usar o `content_hash` do **bloco** como `original_hash` do job de extract (o campo chama-se `original_hash` mas semanticamente é "identidade de conteúdo deste trabalho"). `(block.content_hash, "extract")` é único — a UNIQUE `uq_jobs_hash_step` (`job.py:41-43`) já garante idempotência sem mudar o schema.

```python
payload = json.dumps({"content_hash": block_hash})
repo.enqueue(session, original_hash=block_hash, step="extract", payload=payload)   # watcher.py:144 pattern
```

> ⚠️ **Open Question 1 (decisão de planejamento):** `repo.enqueue` faz seu PRÓPRIO `session.commit()` (`repo.py:71`), o que quebraria o commit único atômico do `ingest_stage` (`ingest_stage.py:177`). Duas saídas limpas: (a) enfileirar APÓS o commit do ingest, num passo idempotente separado; ou (b) **sweep no startup do worker** — análogo a `repo.requeue_running` (`repo.py:185-200`) / `run_worker:151-154` — que pega Documents em `aguardando_extracao` (`ingest_stage.py:53`, `AWAITING_EXTRACTION_STEP`) sem job de extract e os enfileira. O sweep cobre também Documents legados da Fase 2 (RESEARCH Runtime State Inventory). **Recomendação RESEARCH: sweep idempotente.**

---

### `backend/pyproject.toml` (MODIFICADO — deps)

**Análogo:** o próprio `[project.dependencies]` (`pyproject.toml:7-16`, já lista `pikepdf==10.8.0` com pin exato) e `[dependency-groups].dev` (`pyproject.toml:18-24`).
- Adicionar a `dependencies`: `"openai==2.41.*"`, `"PyMuPDF==1.27.*"`.
- Adicionar a `dev`: `"respx"` (mock OpenAI, CI sem token).
- Via `uv add "openai==2.41.*" "PyMuPDF==1.27.*"` e `uv add --group dev respx`.

---

## Shared Patterns (cross-cutting — aplicam a vários arquivos)

### Sessão por unidade de trabalho
**Source:** `worker.py:55, 104, 125, 139`; `watcher.py:125`
**Apply to:** `extract_stage`, worker dispatch, sweep.
Sempre `with get_session(engine) as session:`. Sessões SQLAlchemy não cruzam threads (`worker.py:43-49` docstring). Cada thread/coroutine abre a sua.

### Atomicidade: commit único, trabalho ANTES de `mark_done`
**Source:** `ingest_stage.py:174-177` (um `session.commit()` no fim; "crash antes daqui = rollback total")
**Apply to:** `extract_stage` (Extraction + Usage + marcador num só commit, ANTES de `repo.mark_done` em `worker.py:139-141`). Evita cobrança dupla (Pitfall 3).

### Estado só via `state_machine`, nunca `doc.state` direto
**Source:** `state_machine.py:24-76`; `worker.py:65-95` (`_fail_documents_for_original` usa `transition`, "nunca seta `document.state` direto — Anti-Pattern", `worker.py:13-14`)
**Apply to:** `extract_stage` (sucesso → `mark_step("extraido")`, `state_machine.py:66`), worker (FALHA → `transition(... DocState.FALHA)`, `worker.py:87`). **NÃO usar `transition` para PROCESSANDO→PROCESSANDO** (não está na allowlist, `states.py:25-30`).

### Segredo nunca logado
**Source:** `config.py:11` (chave `SecretStr`, "nada aqui loga nem retorna o valor"), `config.py:55`
**Apply to:** `openai_client.py` (`.get_secret_value()` só no ponto de criação), todo log da fase (logar `document_id`/caminho/`doc_type_guess`/motivo de recusa — nunca chave nem `full_text`/`fields`). Critical Failure Mode 5.

### Idempotência por checagem prévia de existência
**Source:** `ingest_stage.py:153-160` (`select(Document).where(content_hash==...)` antes de recriar)
**Apply to:** `extract_stage` (checar `Extraction` por `document_id` antes de chamar a IA) + UNIQUE `(content_hash, "extract")` na fila (`job.py:41-43`).

### Funções de módulo atrás de interface (sem classe)
**Source:** `cas.py:24`, `repo.py:20` ("Funções de módulo, estilo `cas.py`/`state_machine.py`, sem classe")
**Apply to:** `router.py`, `openai_client.py`, `pdf_io.py`.

### Tunables de env via `Field(default, validation_alias=AliasChoices(...))`
**Source:** `config.py:71-86` (`queue_*`)
**Apply to:** todos os `OPENAI_EXTRACT_*`.

### Migração: `create_table` + `batch_alter_table` para índices; cabeçalho de revisão encadeado
**Source:** `0002_ingestion.py:42-92`; cuidado de trigger `0002:94-107` (só se tocar `documents`)
**Apply to:** `0003_*.py`.

### Modelo de registro obrigatório
**Source:** `models/__init__.py:1-27` (todo modelo no import + `__all__` para o autogenerate do Alembic)
**Apply to:** registrar `Extraction`.

---

## No Analog Found

| File | Role | Data Flow | Reason / Fonte a usar |
|------|------|-----------|------------------------|
| `backend/app/extraction/schema.py` (`ExtractionResult`/`ExtractedField`) | model Pydantic-de-IA | transform | Não há Pydantic-de-IA / Structured Outputs no repo (todos os Pydantic atuais são `Settings`). **Usar AI-SPEC §4b.1** (definição completa, com a restrição strict-mode: list-of-pairs, NÃO `dict` aberto). |
| Construção `AsyncOpenAI` + `responses.parse` + `_unwrap` | service externo async | request-response | Primeira integração OpenAI do projeto. **Usar AI-SPEC §3** (sintaxe completa). Forma do módulo copia `cas.py`; o segredo copia `config.py`. |
| `tests/extraction/` (conftest + fixtures respx) | test | — | Diretório novo (RESEARCH Wave 0). Sem teste de IA mockada no repo ainda. Usar `respx` + padrão pytest-asyncio já em `pyproject.toml:43-45` (`asyncio_mode="auto"`). |

---

## Metadata

**Analog search scope:** `backend/app/` (extraction[ausente], pipeline, queue, models, storage, config, ingest), `backend/alembic/versions/`, `backend/pyproject.toml`
**Files scanned (lidos linha a linha):** ingest_stage.py, worker.py, repo.py, state_machine.py, states.py, usage.py, document.py, page.py, audit_log.py, enums.py, job.py, config.py, cas.py, watcher.py, models/__init__.py, 0001_initial.py (parcial), 0002_ingestion.py, pyproject.toml
**Pattern extraction date:** 2026-06-16

# Phase 2: Ingestão e Fila Assíncrona - Research

**Researched:** 2026-06-15
**Domain:** Hot-folder ingestion + in-process SQLite-backed durable job queue + PDF page splitting (single-tenant, Windows-first, FastAPI)
**Confidence:** HIGH (stack versions verified on PyPI; queue/watcher/split patterns verified against official docs + existing Phase-1 substrate. One MEDIUM area: the in-process SQLite queue has no canonical library — the pattern below is assembled from documented SQLite/SQLAlchemy primitives.)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Ingestão no v1 é **exclusivamente por pasta monitorada (hot folder)**. Sem upload manual (ING-01 removido) e sem lote CLI (ING-03 removido).
- **D-02:** **Múltiplas pastas monitoradas**, configuradas **pela UI** — não por arquivo de config. Cada pasta: caminho + **regra de separação própria** (qtd. de páginas por bloco). Persistir config no banco.
- **D-03:** Após ingestão (cópia ao CAS), o **original permanece na pasta** (não move/remove). Dedup por hash evita reprocessar nos rescans. Usuário limpa a pasta manualmente.
- **D-04:** Evento do watcher é só **gatilho de candidatura**. Arquivo só é enfileirado após **estabilizar** (size/mtime parados por uma janela). **Janela de estabilização configurável (global)** com padrão sensível embutido.
- **D-05:** Regra de separação é **por pasta**: "tudo que cair nesta pasta é separado a cada N páginas". Aplica-se a PDFs multi-página.
- **D-06:** **Cada bloco vira um Document independente** — próprio conteúdo (novo PDF), próprio hash SHA-256, próprio estado, próprio percurso. Ex.: PDF de 10 páginas em pasta "separar a cada 1" → 10 Documents.
- **D-07:** O **arquivo original inteiro** continua armazenado no CAS (rede de segurança), além dos blocos. Imagens (JPG/PNG) são página única — viram 1 Document, sem separação.
- **D-08:** Dedup **global e para sempre, por conteúdo** (mesmo hash SHA-256 visto em qualquer pasta a qualquer momento = duplicata).
- **D-09:** Dedup deve ser checado no **hash do arquivo ORIGINAL (antes de separar)**, para que rescans não re-separem o documento. Implicação de schema: hoje `content_hash` único existe em `documents` (os blocos); é preciso um gate/registro do hash do **original** (pré-split) distinto do hash dos blocos.
- **D-10:** Ao detectar duplicata: **ignora sem reprocessar/cobrar, mas com visibilidade na UI** — contador/indicador de "duplicados ignorados" + registro em log/auditoria. Não polui a lista principal.
- **D-11:** Fila **in-process, persistida em SQLite, sem broker externo**. Worker em background com **retry + backoff**, **idempotência por hash + etapa**. Reusa máquina de estados + `last_completed_step` da Fase 1.
- **D-12:** UI da Fase 2: (1) gerenciador de pastas monitoradas; (2) lista de documentos com estado (polling); (3) contador de duplicados ignorados. Sem tela de upload.

### Claude's Discretion
- Estrutura concreta da(s) tabela(s) de fila/jobs e da config de pastas; algoritmo de polling/backoff; nº máximo de tentativas antes de `FALHA`; concorrência do worker.
- Lib do watcher (preferência: **watchfiles** sobre watchdog) e mecanismo de detecção de estabilidade no Windows.
- Lib de split de PDF (sugestão: **pikepdf** MPL; atentar AGPL do PyMuPDF — relevante a partir da Fase 3).
- Como o gate de dedup do **original pré-split** (D-09) é modelado no schema atual.
- Onde, na máquina de estados, o documento "para" ao fim da Fase 2 (aguardando extração) — **não** marcar `CONCLUIDO`.
- Tratamento de extensão não suportada na pasta: no v1, ignorar silenciosamente (quarentena é Fase 5).
- Valor padrão da janela de estabilização (D-04) e padrão de separação por pasta (sugestão: "não separar").

### Deferred Ideas (OUT OF SCOPE)
- **Upload manual pela interface (ING-01)** — v2 (ING2-01). Não pesquisar/planejar.
- **Lote por linha de comando / backfill (ING-03)** — v2 (ING2-02). Não pesquisar/planejar.
- **Mover original para subpasta "processados"** — descartado no v1 (D-03 mantém o original no lugar).
- **Janela de estabilização por pasta** e **threshold por pasta** — v1 mantém estabilização global (D-04).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ING-02 | Processa automaticamente arquivos em pasta(s) monitorada(s) só após estarem estáveis; múltiplas pastas configuráveis pela UI | §Watcher + Estabilização (watchfiles `awatch` + quiescência size/mtime + lock-test Windows); §Pasta config no DB; §FastAPI lifespan integration |
| ING-04 | Aceita PDF e imagens comuns (JPG, PNG) | §Page Splitter (PDF via pikepdf; imagem = 1 Document, sem split — D-07); §Extension allowlist (ignorar silenciosamente o resto) |
| ING-05 | Separa multi-página em blocos por qtd. configurada por pasta; cada bloco = documento independente | §Page Splitter (pikepdf `Pdf.new()` + `pages.extend` por janelas de N páginas → novo PDF por bloco) |
| ING-06 | Deduplica por hash, evita reprocessar e cobrar o mesmo arquivo duas vezes | §Dedup Gate (hash do original pré-split + `documents.content_hash` único dos blocos); §Idempotência de job |
| PROC-02 | Fila assíncrona, worker em background, retry e backoff | §In-Process SQLite Queue (tabela `jobs`, claim atômico sob WAL, retry/backoff exponencial+jitter, dead-letter→FALHA) |
| PROC-03 | Fila idempotente (chave por hash + etapa), impede reexecução e cobrança dupla | §Idempotência (job key = original_hash + step; resume via `last_completed_step`; dedup gate; reusa `transition`/`mark_step`) |
</phase_requirements>

## Summary

Esta fase adiciona três subsistemas ao substrato já pronto da Fase 1 (CAS por SHA-256, máquina de estados, modelos SQLAlchemy + Alembic, FastAPI com lifespan): (1) um **watcher de hot-folder** que detecta candidatos e só os promove após estabilização; (2) uma **fila durável in-process persistida em SQLite** com um worker assíncrono que faz retry/backoff e é idempotente por hash+etapa; (3) um **page splitter** que quebra PDFs multi-página em blocos, cada bloco virando um Document independente. Tudo roda **no mesmo processo do FastAPI**, subido pelo `lifespan` já existente — sem broker externo, alinhado ao constraint Windows/single-tenant.

A decisão de schema mais importante é o **gate de dedup pré-split (D-09)**: o `documents.content_hash` único de hoje refere-se aos **blocos**, mas o dedup precisa acontecer no **hash do arquivo original antes de separar**, senão cada rescan da pasta (onde o original permanece — D-03) re-separa o mesmo arquivo. A recomendação é uma **nova tabela `ingested_originals`** (uma linha por hash de original já visto), checada antes de qualquer split, mais um vínculo bloco→original. Isto não viola o schema atual e entra por migração Alembic versionada (D-10).

A área de menor confiança consagrada é a **fila SQLite in-process** (sem lib madura — confirmado em STATE.md Blockers). O padrão recomendado é uma tabela `jobs(status, attempts, next_run_at, ...)` com **claim atômico via `UPDATE ... WHERE id IN (SELECT ... LIMIT 1) RETURNING`** (SQLite ≥ 3.35 suporta RETURNING) ou um `UPDATE` condicional por status, executado sob o `busy_timeout`/WAL já configurados. Como há **um único writer** (o worker), a contenção do SQLite deixa de ser problema.

**Primary recommendation:** `watchfiles.awatch` (event→candidato) + estabilização por quiescência (size/mtime) com lock-test no Windows → tabela `jobs` SQLite com claim atômico e backoff exponencial+jitter → `pikepdf` (MPL-2.0) para split por N páginas gerando novos PDFs → cada bloco passa por `cas.store` e vira um `Document`; dedup gate por hash do original numa nova tabela `ingested_originals`; tudo orquestrado por uma `asyncio.Task` subida no `lifespan` do FastAPI, com a etapa de split/IO pesada despachada para um thread (`asyncio.to_thread`) para não bloquear o event loop. O documento termina a Fase 2 num **estado/marcador "aguardando extração"** — sem `CONCLUIDO`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Detectar arquivos novos na pasta | Worker/Backend (filesystem watcher) | — | Filesystem do cliente é monitorado pelo processo backend; nenhuma responsabilidade no browser |
| Estabilização (não processar arquivo parcial) | Worker/Backend | — | Quiescência size/mtime + lock-test são operações de FS locais |
| Fila durável + retry/backoff | Database/Storage (tabela `jobs`) + Worker (loop) | — | Estado da fila persiste no SQLite (sobrevive a crash); o worker é o executor |
| Dedup por hash | Database/Storage (`content_hash` único + `ingested_originals`) + Worker (cálculo) | — | A unicidade é imposta no DB; o hash é calculado no worker via `cas.store` |
| Split de páginas | Worker/Backend (pikepdf, CPU-bound) | — | Manipulação de PDF é local e CPU-bound; isolar do event loop |
| Config de pastas monitoradas (CRUD) | Database/Storage (nova tabela) + API (rotas finas) + Frontend (UI) | — | UI grava no DB via API; o watcher lê do DB |
| Lista de documentos + contador de duplicados | API (read-only) + Frontend (polling) | Database (fonte de verdade) | UI reflete o DB por polling (TanStack Query); nunca dona do estado |
| Avançar estado do documento | Worker/Backend (reusa `transition`/`mark_step`) | Database | Pattern 1 (Document as State Machine) — já implementado na Fase 1 |

## Standard Stack

### Core (novos nesta fase)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **watchfiles** | 1.2.0 | Hot-folder watcher (event → candidato a ingestão) | `[VERIFIED: PyPI]` MIT, baseado em Rust (`notify`), async-native (`awatch`), mantido pela equipe pydantic/uvicorn. Já é a preferência do projeto sobre `watchdog` (CLAUDE.md "What NOT to Use"). Suporta múltiplos paths e `stop_event` para shutdown limpo. |
| **pikepdf** | 10.8.0 | Split de PDF por N páginas → novos PDFs (blocos) | `[VERIFIED: PyPI + slopcheck OK]` Licença **MPL-2.0** (permissiva — `[CITED: github.com/pikepdf/pikepdf]`), powered by qpdf. **Evita a AGPL do PyMuPDF** para a operação de split (a flag de licença AGPL do projeto é assim contornada nesta fase). `Pdf.new()` + `dst.pages.extend(src.pages[a:b])` + `save()` é a API canônica de split. |

### Supporting (já no projeto / stdlib)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **SQLAlchemy** | 2.0.51 | Tabelas `jobs`, `watched_folders`, `ingested_originals`; claim de job | `[VERIFIED: venv]` Já instalado; toda persistência passa por aqui (não acoplar SQL cru — CLAUDE.md) |
| **alembic** | 1.18.4 | Migração das novas tabelas | `[VERIFIED: venv]` Schema só evolui por migração versionada (D-10). `render_as_batch=True` já configurado no `env.py`. |
| **hashlib (stdlib)** | — | SHA-256 do original pré-split | `[VERIFIED]` Já usado pelo CAS; o gate de dedup precisa do hash do original **antes** de `cas.store` (ver §Dedup Gate) |
| **asyncio (stdlib)** | — | Worker loop + watcher como `asyncio.Task` no lifespan | `[VERIFIED]` FastAPI/uvicorn já rodam num event loop; `awatch` é async; `asyncio.to_thread` isola split CPU-bound |
| **FastAPI** | 0.137.1 | Rotas CRUD de pastas + lista de documentos + lifespan que sobe watcher/worker | `[VERIFIED: venv]` Lifespan já existe em `main.py` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| watchfiles | watchdog | `[CITED: CLAUDE.md]` watchdog é sync, menos confiável em redes/NFS, emite múltiplos `modified` durante escrita. Explicitamente em "What NOT to Use". |
| pikepdf (split) | PyMuPDF / pypdf | PyMuPDF é **AGPL-3.0** (impeditivo para produto vendido — flag do projeto). pypdf (6.13.2, BSD) é alternativa permissiva válida porém com reparo/robustez inferior a qpdf. **Usar pikepdf.** |
| pikepdf (split) | pypdfium2 5.10.1 | `[VERIFIED: PyPI]` BSD/Apache; ótimo para **render** página→imagem (relevante na Fase 3, onde a AGPL do PyMuPDF morde de novo), mas não é a ferramenta de split. Anotar para a Fase 3. |
| Fila SQLite in-process | arq + Redis | `[CITED: CLAUDE.md]` arq exige broker externo — viola constraint Windows/single-tenant. arq é a opção do **modo servidor** (futuro), atrás da mesma interface `enqueue`/`process`. |
| Fila SQLite in-process | FastAPI BackgroundTasks | `[CITED: ARCHITECTURE.md Anti-Pattern 1]` BackgroundTasks roda no mesmo request, sem durabilidade nem retry — perde trabalho num crash. Inaceitável para idempotência (PROC-03). |

**Installation:**
```bash
# Backend (com uv, dentro de backend/)
uv add watchfiles==1.2.0 pikepdf==10.8.0
```
*(SQLAlchemy, Alembic, FastAPI, Pydantic já estão no `pyproject.toml` e instalados no venv.)*

**Version verification (executada nesta sessão):**
- `watchfiles` 1.2.0 — MIT — uploaded 2026-05-18 — requires_python >=3.10 `[VERIFIED: PyPI]`
- `pikepdf` 10.8.0 — MPL-2.0 — uploaded 2026-06-08 — requires_python >=3.10 `[VERIFIED: PyPI]`
- `pypdfium2` 5.10.1 (alternativa de render p/ Fase 3) — BSD-3/Apache-2.0 — uploaded 2026-06-15 `[VERIFIED: PyPI]`
- venv atual: Python 3.12.13, fastapi 0.137.1, sqlalchemy 2.0.51, alembic 1.18.4, pydantic 2.13.4 `[VERIFIED: venv]`

## Package Legitimacy Audit

> slopcheck 0.6.1 instalado e executado (`scan requirements.txt`) nesta sessão. Ambos os pacotes novos passaram.

| Package | Registry | Age | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-------------|-----------|-------------|
| watchfiles | pypi | latest 1.2.0 (2026-05-18); projeto maduro (equipe pydantic) | github.com/samuelcolvin/watchfiles | [OK] | Approved |
| pikepdf | pypi | latest 10.8.0 (2026-06-08); projeto maduro (qpdf binding) | github.com/pikepdf/pikepdf | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
  ┌─────────────────────────── FastAPI process (uvicorn, 1 event loop) ───────────────────────────┐
  │                                                                                                │
  │  lifespan startup:  engine (WAL) ─→ spawn asyncio.Task(watcher)  + asyncio.Task(worker loop)   │
  │                                                                                                │
  │   pasta(s) do cliente                                                                          │
  │   ┌───────────────┐   FS event (added/modified)                                               │
  │   │ C:\Entrada\…  │ ───────────────────────────►  WATCHER (watchfiles.awatch, múltiplos paths) │
  │   └───────────────┘                                      │                                     │
  │        ▲ original permanece (D-03)                       │ marca candidato                     │
  │        │                                                 ▼                                     │
  │        │                                   STABILIZER (quiescência size/mtime + lock-test)     │
  │        │                                                 │ estável                             │
  │        │                                                 ▼                                     │
  │        │                            hash(original)  ─→  DEDUP GATE (ingested_originals)         │
  │        │                                                 │           │ já visto                │
  │        │                                                 │ novo      ▼                         │
  │        │                                                 ▼      contador "duplicados ignorados"│
  │        │                                          INSERT job(status=pending, original_hash)    │
  │        │                                                 │                                     │
  │        │   ┌──── DB (SQLite WAL) ────────────────────────┼───────────────────────┐            │
  │        │   │  jobs · watched_folders · ingested_originals │ documents · pages · …  │            │
  │        │   └─────────────────────────────────────────────┼───────────────────────┘            │
  │        │                                                  │ claim atômico (1 writer)           │
  │        │                                                  ▼                                     │
  │        │                      WORKER LOOP (poll → claim → run → backoff/retry)                 │
  │        │                                                  │                                     │
  │        │           cas.store(original) ─→ SPLIT (pikepdf, via asyncio.to_thread)               │
  │        │                                                  │ N blocos                            │
  │        └──────────────────────────────────────────────── │ (cópia, nunca move o original)     │
  │                                  por bloco: cas.store(bloco) → Document(content_hash=bloco)    │
  │                                            transition(RECEBIDO→PROCESSANDO)                     │
  │                                            mark_step("ingested")  ── "aguardando extração"     │
  │                                                  │                                              │
  │   API (rotas finas)  ◄───── lê estado/contadores │   FRONTEND React (polling TanStack Query)   │
  │   /watched-folders CRUD · /documents (list) · /documents/duplicates-count · /rescan            │
  └────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/app/
├── ingest/                      # NOVO — fronteira de ingestão (isolável, sem HTTP)
│   ├── watcher.py               # watchfiles.awatch sobre paths do DB; emite candidatos
│   ├── stabilizer.py            # quiescência size/mtime + lock-test Windows
│   └── splitter.py              # pikepdf: PDF → N blocos (novos PDFs em bytes/temp)
├── queue/                       # NOVO — fila durável in-process (atrás de interface)
│   ├── models.py? (ou em models/) # tabela jobs
│   ├── repo.py                  # enqueue / claim atômico / mark_done / mark_retry / mark_failed
│   └── worker.py                # loop async: poll → claim → process → backoff
├── pipeline/
│   ├── ingest_stage.py          # NOVO — orquestra: dedup gate → store original → split → criar Documents
│   ├── state_machine.py         # (Fase 1 — reusar transition/mark_step)
│   └── states.py                # (Fase 1 — TRANSITIONS)
├── models/
│   ├── watched_folder.py        # NOVO — caminho + páginas/bloco + ativa
│   ├── ingested_original.py     # NOVO — gate de dedup pré-split (D-09)
│   ├── job.py                   # NOVO — fila
│   ├── document.py page.py …    # (Fase 1)
├── api/                         # NOVO (API fina; Fase 1 não tinha api/)
│   ├── watched_folders.py       # CRUD (D-12 peça 1)
│   └── documents.py             # list + duplicates-count + rescan (D-12 peças 2 e 3)
├── config.py                    # + stabilization_window_seconds (D-04, global)
└── main.py                      # lifespan: subir watcher + worker como asyncio.Task
```
**Rationale:** segue o padrão estabelecido na Fase 1 — "camada atrás de interface única" (db, CAS). `queue/repo.py` é a interface `enqueue`/`claim` que permite trocar para arq/Redis no modo servidor sem tocar no resto (STACK.md §5). `ingest/` e `pipeline/ingest_stage.py` não conhecem HTTP. API fina (D-12 / ARCHITECTURE.md).

### Pattern 1: In-Process Durable SQLite Queue (claim atômico sob WAL)
**What:** Uma tabela `jobs` persiste o trabalho pendente. Um único worker faz polling, faz **claim atômico** de um job, processa, e marca done/retry/failed. Persistência sobrevive a crash (durabilidade — PROC-02).
**When to use:** Modo padrão single-tenant sem Redis (D-11). É **o** padrão desta fase.

Esquema sugerido para `jobs`:
```python
# models/job.py — esboço
class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Idempotência (PROC-03): chave única por (hash do original, etapa).
    # UNIQUE evita enfileirar o mesmo trabalho duas vezes (rescan → mesmo original).
    original_hash: Mapped[str] = mapped_column(String(64), index=True)
    step: Mapped[str] = mapped_column(String, default="ingest")
    payload: Mapped[str] = mapped_column(Text)          # JSON: source_path, folder_id, pages_per_block
    status: Mapped[str] = mapped_column(String, default="pending", index=True)  # pending|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at / updated_at ...
    # __table_args__ = (UniqueConstraint("original_hash", "step", name="uq_jobs_hash_step"),)
```

**Claim atômico (a parte crítica).** SQLite ≥ 3.35 suporta `UPDATE ... RETURNING`. Com **um único writer** e `busy_timeout` já configurado (5000ms — db.py), o claim é uma única instrução atômica:
```python
# repo.py — claim de UM job devido agora (pseudo via SQLAlchemy text/core)
# Source: SQLite UPDATE...RETURNING (sqlite.org/lang_update.html), one-writer model.
row = session.execute(text("""
    UPDATE jobs
       SET status='running', attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP
     WHERE id = (
        SELECT id FROM jobs
         WHERE status='pending' AND next_run_at <= CURRENT_TIMESTAMP
         ORDER BY next_run_at
         LIMIT 1
     )
    RETURNING id, original_hash, step, payload, attempts, max_attempts
""")).first()
session.commit()
```
- **Por que é seguro:** o worker é o **único writer** (D-11/STACK.md §1). Não há corrida de dois consumidores. O `UPDATE ... WHERE id=(SELECT ...)` é uma transação única; mesmo que a API leia concorrentemente (WAL permite readers), nenhuma escrita compete. Se no futuro houver 2 workers, o mesmo statement continua correto porque o `UPDATE` condicional só "ganha" uma vez por linha.
- **Resume após crash:** ao subir, o worker faz `UPDATE jobs SET status='pending' WHERE status='running'` (re-fila jobs que estavam em execução quando o processo morreu). A idempotência (abaixo) garante que reprocessar não duplica.

### Pattern 2: Backoff Exponencial com Jitter + Dead-Letter → FALHA
**What:** Falha de processamento agenda novo `next_run_at = now + base * 2^attempts + jitter`; ao exceder `max_attempts`, marca o job `failed` **e** o documento `FALHA` (via `transition`).
**When to use:** Toda falha transitória (PROC-02). Evita tempestade de retries.
```python
# Source: padrão de domínio (PITFALLS.md Pitfall 6: backoff exponencial + jitter)
import random
def schedule_retry(job):
    if job.attempts >= job.max_attempts:
        job.status = "failed"           # dead-letter; NÃO some (vai p/ FALHA no doc)
        return
    delay = min(BASE_SECONDS * (2 ** job.attempts), MAX_BACKOFF_SECONDS)
    delay += random.uniform(0, delay * 0.25)   # jitter
    job.status = "pending"
    job.next_run_at = utcnow() + timedelta(seconds=delay)
```

### Pattern 3: Dedup Gate Pré-Split (D-09) — nova tabela `ingested_originals`
**What:** Antes de qualquer split, calcula-se o SHA-256 do **arquivo original** e checa-se contra `ingested_originals`. Se já existe → duplicata (incrementa contador, NÃO re-separa, NÃO cria jobs/blocos). Se novo → registra o original e prossegue.
**Why:** `documents.content_hash` é único nos **blocos** (D-06), não no original. Sem um gate separado, todo rescan (original permanece — D-03) recalcularia split e tentaria criar blocos de novo. (O `UNIQUE` em `documents.content_hash` *pegaria* o bloco duplicado via IntegrityError, mas isso é caro, re-faz o split e não dá visibilidade limpa — o gate pré-split é o correto.)
```python
# models/ingested_original.py — esboço
class IngestedOriginal(Base):
    __tablename__ = "ingested_originals"
    id: Mapped[int] = mapped_column(primary_key=True)
    original_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # gate D-09
    original_filename: Mapped[str] = mapped_column(String)
    source_folder_id: Mapped[int | None] = mapped_column(ForeignKey("watched_folders.id"))
    block_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_hits: Mapped[int] = mapped_column(Integer, default=0)  # quantas vezes reaparecido (D-10)
    created_at ...
# Vínculo bloco→original: adicionar coluna nullable em documents:
#   documents.origin_original_id  FK → ingested_originals.id   (rastreia o original-fonte do bloco)
```
**Contador de duplicados ignorados (D-10/D-12):** pode ser derivado como `SUM(duplicate_hits)` ou um contador agregado simples; a UI lê via endpoint dedicado (`/documents/duplicates-count`).

### Pattern 4: Estabilização por Quiescência + Lock-Test (Windows)
**What:** O evento do watcher é só candidatura (D-04 / PITFALLS Pitfall 1). Só enfileira após `size` e `mtime` ficarem estáveis por uma janela configurável (global), **e** o arquivo poder ser aberto sem lock do gravador.
**When to use:** Sempre antes de hash/split (Pitfall 1 é existencial). 
```python
# Source: PITFALLS.md Pitfall 1 (quiescência size/mtime) + Windows lock semantics
async def wait_stable(path: Path, window_s: float, poll_s: float = 1.0) -> bool:
    last = None
    stable_for = 0.0
    while stable_for < window_s:
        try:
            st = path.stat()
        except FileNotFoundError:
            return False                       # removido enquanto estabilizava
        sig = (st.st_size, st.st_mtime_ns)
        if sig == last:
            stable_for += poll_s
        else:
            stable_for = 0.0
            last = sig
        await asyncio.sleep(poll_s)
    # Lock-test Windows: abrir em modo que falha se outro processo ainda escreve.
    try:
        with path.open("rb"):                  # no Windows, open falha se exclusivo p/ escrita
            pass
    except (PermissionError, OSError):
        return False
    return True
```
**Nota Windows (NTFS):** `mtime` pode ter granularidade grosseira; combinar size+mtime+lock-test é mais robusto que mtime sozinho. A janela padrão (D-04) deve ser sensível a cópias lentas em rede — recomendar default **~3–5s** com 2+ polls estáveis.

### Pattern 5: Page Splitter com pikepdf (D-05/D-06/D-07)
**What:** PDF de M páginas + regra "N páginas/bloco" → `ceil(M/N)` novos PDFs. Cada novo PDF é `cas.store`-ado e vira um Document. "Não separar" (default sugerido) = 1 bloco = o PDF inteiro. Imagem (JPG/PNG) = nunca split, 1 Document (D-07).
```python
# Source: pikepdf docs (pikepdf.readthedocs.io/en/latest/topics/pages.html) — VERIFIED API
import pikepdf
def split_pdf(src_path: Path, pages_per_block: int | None) -> list[bytes]:
    blocks: list[bytes] = []
    with pikepdf.Pdf.open(src_path) as src:       # Pdf.open aceita path e file-like
        n = len(src.pages)
        step = n if not pages_per_block else pages_per_block   # None/0 = "não separar"
        for start in range(0, n, step):
            dst = pikepdf.Pdf.new()
            dst.pages.extend(src.pages[start:start + step])
            buf = io.BytesIO()
            dst.save(buf)                          # save aceita path ou stream
            blocks.append(buf.getvalue())
    return blocks
```
- pikepdf é **CPU/IO-bound** → rodar via `await asyncio.to_thread(split_pdf, ...)` no worker para não bloquear o event loop (PITFALLS Performance Trap: não bloquear loop; ARCHITECTURE Scaling §2).
- Para criar o bloco no CAS a partir de bytes: ou escrever num temp e usar `cas.store(temp_path)` (assinatura atual aceita `Path`), **ou** estender o CAS com um `store_bytes(data)`. **Decisão de planejamento:** o `cas.store` atual recebe `Path`; o caminho de menor risco é escrever cada bloco num arquivo temporário (mesmo volume da pasta de dados) e chamar `cas.store(temp)`. Avaliar adicionar `store_bytes` se quiser evitar o temp.

### Pattern 6: FastAPI Lifespan sobe Watcher + Worker (mesmo processo)
**What:** O `lifespan` já existente (`main.py`) cria as `asyncio.Task` do watcher e do worker no startup e as cancela no shutdown. Sem processo separado, sem broker.
```python
# Source: FastAPI lifespan (já em main.py) + asyncio.create_task / TaskGroup pattern
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings(); ensure_data_dir(settings)
    engine = create_db_engine(settings.effective_database_url)
    app.state.engine = engine
    stop = asyncio.Event()
    watcher_task = asyncio.create_task(run_watcher(engine, stop))
    worker_task  = asyncio.create_task(run_worker(engine, stop))
    try:
        yield
    finally:
        stop.set()                                  # watchfiles.awatch(stop_event=stop) encerra
        for t in (watcher_task, worker_task):
            t.cancel()
        await asyncio.gather(watcher_task, worker_task, return_exceptions=True)
        engine.dispose()
```
- `watchfiles.awatch(*paths, stop_event=stop)` — `[CITED: watchfiles.helpmanual.io]` aceita múltiplos paths e um `stop_event` (objeto com `is_set()`; `anyio.Event`/`asyncio` compatível) para shutdown limpo.
- **Reconfiguração de pastas (D-02):** quando a UI adiciona/remove pasta, o conjunto de paths muda. `awatch` recebe os paths na chamada; para refletir mudanças, reiniciar o `awatch` (cancelar e recriar a task com a nova lista lida do DB) ou rodar um supervisor que reescaneia o DB periodicamente. **Decisão de planejamento.**
- **Cuidado com multi-worker uvicorn:** em produção single-tenant usar **1 worker uvicorn** (CLAUDE.md já diz "1 worker basta; concorrência vem do async"). Com >1 worker uvicorn, cada processo subiria seu próprio watcher/worker → duplicação. Manter `--workers 1`.

### Anti-Patterns to Avoid
- **Processar no handler HTTP / BackgroundTasks** — sem durabilidade/retry (ARCHITECTURE Anti-Pattern 1). Usar a tabela `jobs`.
- **Confiar no primeiro evento do watcher como "arquivo pronto"** — PITFALLS Pitfall 1. Sempre estabilizar.
- **Calcular hash sobre arquivo parcial** — quebra dedup (Pitfall 1/4). Hash só após estabilização.
- **Bloquear o event loop com split de PDF grande** — usar `asyncio.to_thread` (Performance Trap).
- **`create_all` para as novas tabelas** — schema só por Alembic (D-10).
- **Auto-laço de estado** — `transition` não permite X→X (state_machine.py docstring). O worker checa o estado atual antes de pedir transição.
- **Rodar uvicorn com `--workers N>1`** — duplicaria watcher/worker. Manter 1.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detecção de arquivos novos na pasta | Loop manual de `os.listdir` + diff | `watchfiles.awatch` | `[VERIFIED]` Eventos nativos (notify/ReadDirectoryChangesW), async, multi-path, confiável em rede |
| Split de PDF / reparo | Manipular bytes do PDF | `pikepdf` (qpdf) | `[VERIFIED]` Lida com PDFs malformados, xref, objetos compartilhados — hand-roll quebra em PDFs reais |
| Hash + cópia atômica ao storage | Reimplementar | `cas.store` (Fase 1) | `[VERIFIED]` Já existe: streaming, atômico (`os.replace`), idempotente, preserva original |
| Transição de estado | Setar `document.state` direto | `transition`/`mark_step` (Fase 1) | `[VERIFIED]` Allowlist + rollback sem corromper |
| Migração de schema | `create_all` / SQL manual | Alembic (`env.py` já wired) | `[VERIFIED]` `render_as_batch` p/ SQLite; base da atualização segura (DIST-05) |
| Backoff/jitter | Sleep fixo | Fórmula exponencial+jitter (Pattern 2) | `[CITED: PITFALLS]` Sleep fixo causa tempestade de retries |

**Key insight:** quase toda a "infra difícil" já está pronta (CAS atômico, máquina de estados, DB/WAL, Alembic). Esta fase é **costura**: watcher → estabilização → dedup gate → fila → split → criar Documents. O único componente sem lib consagrada é a fila SQLite — mas ela é construída sobre primitivas SQLite/SQLAlchemy bem documentadas.

## Runtime State Inventory

> Esta fase é majoritariamente greenfield (cria tabelas e módulos novos), mas adiciona estado runtime persistente. Inventário do que passa a existir e do que precisa de migração de dados:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data (novo) | Tabelas `jobs`, `watched_folders`, `ingested_originals`; coluna nova `documents.origin_original_id` | Migração Alembic versionada (nova revisão sobre `0001`); nenhum dado legado a converter (Fase 1 não tem documentos em produção) |
| Live service config | Watcher lê a lista de pastas do DB (não de arquivo). Mudança de pasta na UI precisa propagar ao `awatch` em execução | Decisão de planejamento: reiniciar a task `awatch` ou supervisor que relê o DB |
| OS-registered state | Nenhum. O watcher vive dentro do processo FastAPI (asyncio.Task), não há serviço/tarefa do SO registrada nesta fase | None — verificado: lifespan sobe/derruba as tasks; nenhum systemd/Task Scheduler/pm2 |
| Secrets/env vars | Novo: `stabilization_window_seconds` (e talvez `queue_poll_interval`, `queue_max_attempts`) em `config.py` via env/.env | Adicionar campos a `Settings`; sem segredos novos |
| Build artifacts | Novas dependências `watchfiles`, `pikepdf` no `pyproject.toml`/lockfile | `uv add`; lockfile reproduzível (uv) — reinstalar no destino |

**Nada encontrado em:** dados legados para migrar (Fase 1 está vazia em produção); registros do SO; segredos novos.

## Common Pitfalls

### Pitfall 1: Processar arquivo parcialmente escrito (race com a cópia)
**What goes wrong:** Watcher dispara durante a cópia; hash sobre conteúdo parcial quebra dedup; split de PDF truncado.
**Why it happens:** `awatch` emite `modified` várias vezes durante a escrita; não há evento portável de "terminou".
**How to avoid:** Estabilização por quiescência (Pattern 4) + lock-test no Windows. Hash só após estável.
**Warning signs:** Hashes diferentes para o "mesmo" arquivo entre runs; PDFs que falham parsing intermitentemente.
`[CITED: PITFALLS.md Pitfall 1]`

### Pitfall 2: Rescan re-separa o mesmo original (dedup no nível errado)
**What goes wrong:** Dedup só no hash dos blocos → cada rescan (original permanece, D-03) recalcula o split e tenta recriar Documents.
**Why it happens:** `documents.content_hash` único é dos **blocos**, não do original (D-06/D-09).
**How to avoid:** Gate pré-split em `ingested_originals` (Pattern 3). Checar hash do original **antes** de fazer split/store dos blocos.
**Warning signs:** Custo de split repetido; IntegrityError no `content_hash` dos blocos a cada rescan; contador de duplicados não bate.

### Pitfall 3: Cobrança/trabalho duplicado após crash (idempotência fraca)
**What goes wrong:** Worker reprocessa job após crash → re-split, re-cria Documents, (na Fase 3) re-chama OpenAI.
**Why it happens:** Sem chave de idempotência (hash+etapa) e sem checagem de estado antes de agir.
**How to avoid:** `UNIQUE(original_hash, step)` na tabela `jobs`; resume re-fila `running`→`pending`; o gate pré-split + `content_hash` único dos blocos tornam a re-criação um no-op idempotente; reusar `last_completed_step`.
**Warning signs:** Documentos duplicados após restart; jobs presos em `running`.
`[CITED: PITFALLS.md Pitfall 6 / PROC-03]`

### Pitfall 4: Event loop bloqueado por split de PDF grande
**What goes wrong:** `pikepdf` síncrono num PDF de centenas de páginas trava o loop → API/health/polling congelam.
**Why it happens:** Worker e API compartilham o mesmo event loop (mesmo processo).
**How to avoid:** `await asyncio.to_thread(split_fn, ...)` para o trabalho CPU-bound; processar página/bloco a bloco.
**Warning signs:** `/health` lento durante ingestão de lote; UI polling trava.
`[CITED: ARCHITECTURE.md Scaling §2 / PITFALLS Performance Traps]`

### Pitfall 5: Múltiplos workers uvicorn duplicam o watcher
**What goes wrong:** `uvicorn --workers 2` → 2 processos, cada um com seu watcher+worker → arquivos processados/enfileirados em dobro.
**Why it happens:** Lifespan roda por processo.
**How to avoid:** Single-tenant usa **1 worker uvicorn** (CLAUDE.md). Documentar/forçar. Se algum dia precisar N workers, o watcher/worker deve virar processo único separado.
**Warning signs:** Jobs duplicados; dois logs de "watcher iniciado".

### Pitfall 6: Marcar `CONCLUIDO` cedo demais
**What goes wrong:** Worker marca o Document `CONCLUIDO` ao fim do split — mas extração (Fase 3) ainda não rodou.
**Why it happens:** `PROCESSANDO→CONCLUIDO` está na allowlist (states.py).
**How to avoid:** Document fica em **`PROCESSANDO`** com `last_completed_step` indicando "ingerido/separado, aguardando extração" (D-04 do CONTEXT / Integration Points). **Não** chamar `transition(..., CONCLUIDO)`. A UI mapeia esse estado para "Aguardando extração" (UI-SPEC).
**Warning signs:** Documentos verdes "Concluído" sem nenhum dado extraído.
`[CITED: 02-CONTEXT.md Integration Points + 02-UI-SPEC.md]`

## Code Examples

Os exemplos canônicos verificados estão inline nas seções Pattern 1–6 acima (claim atômico SQLite, backoff+jitter, dedup gate, estabilização, split pikepdf, lifespan). Fontes:
- Claim/RETURNING: `[CITED: sqlite.org/lang_update.html]` (UPDATE...RETURNING, SQLite ≥3.35)
- pikepdf split: `[CITED: pikepdf.readthedocs.io/en/latest/topics/pages.html]` (`Pdf.new`/`pages.extend`/`save`)
- watchfiles: `[CITED: watchfiles.helpmanual.io/api/watch]` (`awatch`, `Change` enum, multi-path, `stop_event`, Windows timeouts)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `watchdog` (sync, polling) | `watchfiles` (Rust/notify, async) | maduro 2023+ | Mais confiável em rede/NFS; async-native — combina com FastAPI |
| `PyPDF2` | `pikepdf` (qpdf) / `pypdf` | PyPDF2 deprecado | Reparo/split robusto; pikepdf MPL evita AGPL do PyMuPDF |
| `SELECT ... FOR UPDATE` (Postgres) p/ claim | `UPDATE ... RETURNING` (SQLite ≥3.35) com 1 writer | SQLite 3.35 (2021) | Claim atômico simples sem lib de fila; viável in-process |

**Deprecated/outdated:**
- `watchdog` — explicitamente em "What NOT to Use" (CLAUDE.md). Não usar.
- `PyPDF2` — deprecado (fundido em pypdf). Não usar.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | SQLite no ambiente alvo é ≥ 3.35 (suporta `UPDATE ... RETURNING`) | Pattern 1 | Baixo — Python 3.12 traz SQLite recente; se não, usar `UPDATE` condicional + `SELECT` em transação (mesmo writer único). Validar `sqlite3.sqlite_version` no planejamento. |
| A2 | Default da janela de estabilização ~3–5s é sensível | Pattern 4 / D-04 | Médio — redes lentas/arquivos enormes podem precisar mais. É configurável (global), então ajustável sem deploy. Confirmar default com usuário. |
| A3 | 1 worker uvicorn é o modo de execução padrão | Pattern 6 / Pitfall 5 | Médio — se a operação subir com >1 worker, duplica. CLAUDE.md já indica 1 worker; documentar como requisito. |
| A4 | Escrever bloco em temp + `cas.store(temp)` é aceitável vs. estender CAS com `store_bytes` | Pattern 5 | Baixo — ambos funcionam; decisão de design no planejamento. |
| A5 | Reconfigurar pastas reinicia a task `awatch` (vs. supervisor com re-scan) | Pattern 6 | Baixo — ambos viáveis; afeta latência de "pasta nova passa a ser monitorada". Decisão de planejamento. |
| A6 | Default de separação por pasta = "não separar" (1 bloco) | Pattern 5 / D-05 discretion | Baixo — é a sugestão explícita do CONTEXT; confirma comportamento de PDF multi-página sem regra. |

## Open Questions

1. **Coluna de vínculo bloco→original**
   - What we know: precisa rastrear de qual original cada bloco veio (D-09 + auditoria/undo futuro).
   - What's unclear: `documents.origin_original_id` FK nullable vs. tabela de junção.
   - Recommendation: coluna FK nullable em `documents` (mais simples; 1 bloco tem exatamente 1 original). Migração Alembic.

2. **Extensão não suportada na pasta (ING-04)**
   - What we know: PDF/JPG/PNG aceitos; resto ignorado silenciosamente no v1 (quarentena é Fase 5 — discretion).
   - What's unclear: registrar em log/auditoria o arquivo ignorado?
   - Recommendation: log leve (debug) sem criar Document; não enfileirar. Quarentena fica para Fase 5.

3. **Como o "Forçar varredura" (UI-SPEC) dispara um rescan**
   - What we know: a UI tem botão "Forçar varredura" (`.btn-primary`).
   - What's unclear: endpoint que reescaneia as pastas e re-emite candidatos (útil para arquivos colocados enquanto o watcher estava parado).
   - Recommendation: endpoint `POST /rescan` que lista os arquivos das pastas ativas e os passa pelo mesmo caminho (estabilização → dedup gate → enqueue). Idempotente por dedup.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | runtime | ✓ | 3.12.13 (venv) | — |
| SQLite | fila + DB | ✓ (embutido no Python) | confirmar ≥3.35 p/ RETURNING (A1) | `UPDATE` condicional sem RETURNING (1 writer) |
| watchfiles | watcher | ✗ (a instalar) | 1.2.0 | nenhum aceitável (watchdog vetado) |
| pikepdf | split | ✗ (a instalar) | 10.8.0 | pypdf 6.13.2 (BSD) se pikepdf falhar no Windows |
| FastAPI / SQLAlchemy / Alembic / Pydantic | tudo | ✓ | 0.137.1 / 2.0.51 / 1.18.4 / 2.13.4 | — |

**Missing dependencies with no fallback:** watchfiles (mas é trivial `uv add`; watchdog está vetado por política).
**Missing dependencies with fallback:** pikepdf (fallback pypdf, ambos têm wheels Windows). SQLite RETURNING (fallback statement condicional).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode=auto) |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths=["tests"]`) |
| Quick run command | `cd backend && .venv/bin/python -m pytest tests/ -x -q` |
| Full suite command | `cd backend && .venv/bin/python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ING-02 | Arquivo só enfileira após estabilizar (size/mtime parados) | unit | `pytest tests/test_stabilizer.py -x` | ❌ Wave 0 |
| ING-02 | Watcher detecta arquivo novo e cria candidato | integration | `pytest tests/test_watcher.py -x` | ❌ Wave 0 |
| ING-04 | PDF/JPG/PNG aceitos; outras extensões ignoradas | unit | `pytest tests/test_ingest_stage.py::test_extension_allowlist -x` | ❌ Wave 0 |
| ING-05 | PDF M páginas + N/bloco → ceil(M/N) Documents | unit | `pytest tests/test_splitter.py -x` | ❌ Wave 0 |
| ING-05 | "Não separar" → 1 Document = PDF inteiro; imagem → 1 Document | unit | `pytest tests/test_splitter.py::test_no_split -x` | ❌ Wave 0 |
| ING-06 | Mesmo original (rescan) não re-separa nem cria Documents | unit | `pytest tests/test_dedup_gate.py -x` | ❌ Wave 0 |
| PROC-02 | Job claim atômico; falha agenda retry com backoff; N falhas → FALHA | unit | `pytest tests/test_queue.py -x` | ❌ Wave 0 |
| PROC-02 | Resume após crash re-fila jobs `running`→`pending` | unit | `pytest tests/test_queue.py::test_resume_on_startup -x` | ❌ Wave 0 |
| PROC-03 | Reprocessar mesmo job (hash+etapa) é no-op idempotente | unit | `pytest tests/test_queue.py::test_idempotent -x` | ❌ Wave 0 |
| PROC-03/D-06 | Worker termina em PROCESSANDO+step "aguardando extração", nunca CONCLUIDO | unit | `pytest tests/test_ingest_stage.py::test_terminal_state -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && .venv/bin/python -m pytest tests/ -x -q`
- **Per wave merge:** full suite
- **Phase gate:** full suite verde antes de `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_stabilizer.py` — ING-02 (quiescência; usar `tmp_path` + escrita incremental)
- [ ] `tests/test_watcher.py` — ING-02 (awatch sobre `tmp_path`; pode precisar marcar como integração)
- [ ] `tests/test_splitter.py` — ING-05 (fixtures: PDF multi-página gerado com pikepdf; assert nº de blocos)
- [ ] `tests/test_dedup_gate.py` — ING-06 (mesmo conteúdo 2x → 1 ingestão + contador)
- [ ] `tests/test_queue.py` — PROC-02/03 (claim, backoff, resume, idempotência; usa fixture `engine` existente)
- [ ] `tests/test_ingest_stage.py` — ING-04/D-06 (allowlist de extensão; estado terminal)
- [ ] Fixtures: PDF de exemplo multi-página em `tests/` (gerar via pikepdf no conftest, não commitar binário grande)
- [ ] Framework install: `uv add watchfiles==1.2.0 pikepdf==10.8.0` (e dev já tem pytest/pytest-asyncio)

*(Infra de teste existente — `conftest.py` com fixtures `sqlite_url`/`engine` — cobre a parte de DB; faltam os arquivos acima específicos da Fase 2.)*

## Security Domain

> `security_enforcement: true`, ASVS level 1 no config.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Fase 2 não adiciona auth; app single-tenant bind local (Fase 8/deploy) |
| V3 Session Management | no | Sem sessões nesta fase |
| V4 Access Control | no (parcial) | Endpoints de config são locais single-tenant; auth é tema de deploy |
| V5 Input Validation | **yes** | Caminho de pasta (UI) e nomes de arquivo são entrada não-confiável — validar/sanear |
| V6 Cryptography | no | SHA-256 já é só para endereçamento de conteúdo (não segurança) — sem novo uso cripto |
| V12 Files & Resources | **yes** | Manipulação de arquivos da pasta do cliente; path traversal, leitura de arquivo controlada pelo usuário |

### Known Threat Patterns for {watcher + folder config + PDF split}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal no caminho da pasta monitorada (UI grava `..\..\Windows`) | Elevation / Information Disclosure | Validar/normalizar o caminho (`Path.resolve()`); rejeitar ou confinar; no v1 a pasta é escolha do operador local, mas validar formato e existência |
| Caminho de pasta aponta para diretório do sistema → watcher lê arquivos sensíveis | Information Disclosure | Allowlist de extensões (só PDF/JPG/PNG entram no pipeline); ignorar o resto (ING-04) reduz superfície |
| PDF malicioso/malformado trava o splitter (DoS) | Denial of Service | pikepdf (qpdf) é robusto a PDFs malformados; envolver split em try/except → job vai p/ retry e depois FALHA, não derruba o worker |
| Nome de arquivo com chars de controle/PUA usado em path do CAS | Tampering | CAS endereça por **hash**, não por nome — nome do arquivo nunca compõe o caminho de storage (mitigado pela Fase 1). `original_filename` é só metadado exibido (escapar na UI) |
| Job payload (JSON) com caminho injetado | Tampering | Payload é gerado internamente (não vem do browser); validar `source_path` está sob uma pasta monitorada conhecida antes de abrir |
| Zip-bomb / PDF com milhares de páginas → explosão de Documents/CAS | Denial of Service | Considerar limite de páginas/blocos por original (config); split via `to_thread` não bloqueia; monitorar `block_count` |

**Nota:** a sanitização de path traversal dos **templates de nome/destino** (PITFALLS Security) é da **Fase 6** (automações), não desta. Aqui a entrada de risco é o **caminho da pasta monitorada** (V5/V12).

## Sources

### Primary (HIGH confidence)
- PyPI JSON API (pypi.org/pypi/<pkg>/json) — watchfiles 1.2.0 (MIT, 2026-05-18), pikepdf 10.8.0 (MPL-2.0, 2026-06-08), pypdfium2 5.10.1 (BSD/Apache, 2026-06-15), pypdf 6.13.2 — `[VERIFIED]`
- venv local (`backend/.venv/bin/python`) — Python 3.12.13; fastapi 0.137.1, sqlalchemy 2.0.51, alembic 1.18.4, pydantic 2.13.4 — `[VERIFIED]`
- slopcheck 0.6.1 `scan` — watchfiles [OK], pikepdf [OK] (pypi) — `[VERIFIED]`
- Código Fase 1 lido: `cas.py`, `state_machine.py`, `states.py`, `document.py`, `page.py`, `enums.py`, `db.py`, `config.py`, `main.py`, `alembic/env.py`, `0001_initial.py`, `conftest.py` — `[VERIFIED]`
- pikepdf docs — pikepdf.readthedocs.io/en/latest/topics/pages.html (`Pdf.new`/`pages.extend`/`save`) — `[CITED]`
- watchfiles docs — watchfiles.helpmanual.io/api/watch (`awatch`, `Change`, multi-path, `stop_event`, Windows timeout) — `[CITED]`
- github.com/pikepdf/pikepdf README — licença MPL-2.0 — `[CITED]`

### Secondary (MEDIUM confidence)
- `.planning/research/{STACK,ARCHITECTURE,PITFALLS}.md` — stack/patterns/pitfalls do projeto — `[CITED]`
- `02-CONTEXT.md`, `02-UI-SPEC.md`, `REQUIREMENTS.md`, `STATE.md`, `CLAUDE.md` — decisões e constraints — `[CITED]`
- SQLite `UPDATE ... RETURNING` (≥3.35) — sqlite.org/lang_update.html — `[ASSUMED versão do ambiente, A1]`

### Tertiary (LOW confidence)
- Defaults numéricos (janela de estabilização ~3–5s, max_attempts 5, poll interval) — heurística; confirmar no planejamento/com usuário (A2)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versões e licenças verificadas em PyPI; slopcheck OK; substrato Fase 1 lido diretamente.
- Architecture (watcher/split/lifespan): HIGH — APIs verificadas em docs oficiais; integração com lifespan existente confirmada no código.
- Fila SQLite in-process: MEDIUM — sem lib consagrada (confirmado em STATE.md); padrão montado de primitivas documentadas (UPDATE...RETURNING, 1 writer, WAL já configurado). Validar `sqlite_version` ≥3.35 (A1).
- Pitfalls: HIGH — derivados de PITFALLS.md do projeto + código real.
- Security: MEDIUM — ASVS L1; foco em V5/V12 (path da pasta, PDF malformado).

**Research date:** 2026-06-15
**Valid until:** 2026-07-15 (stack estável; reverificar pikepdf/watchfiles se a fase começar após ~30 dias)

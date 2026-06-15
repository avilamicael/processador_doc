# Architecture Research

**Domain:** Intelligent Document Processing (IDP) — pipeline de documentos fiscais BR, single-tenant, FastAPI + React + worker assíncrono local
**Researched:** 2026-06-15
**Confidence:** HIGH (estrutura de pipeline IDP, fila async, structured outputs verificados em múltiplas fontes oficiais/independentes; MEDIUM para detalhes de reversibilidade de arquivo, baseados em princípios gerais + analogia)

## Standard Architecture

O domínio IDP converge para um pipeline de **etapas sequenciais que estreitam a ambiguidade e elevam a confiança** a cada passo (ingestão → classificação → extração → validação → roteamento). Para este projeto, a arquitetura recomendada é um **monólito modular FastAPI** com um **worker assíncrono no mesmo host**, onde cada documento é uma **entidade com máquina de estados explícita** e cada etapa do pipeline é um módulo desacoplável que lê/escreve estado num banco local.

A peça central NÃO é a API HTTP — é o **pipeline orientado a estado**. A API e a UI são apenas duas formas de injetar trabalho (upload, hot folder) e de inspecionar/intervir (revisão, dry-run, desfazer). Isso mantém o sistema testável etapa-a-etapa e permite reprocessar a partir de qualquer estado.

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React SPA)                           │
│  Upload · Construtor de Templates · Fila de Revisão · Dry-run/Undo     │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTP/JSON + polling/SSE de progresso
┌───────────────────────────────┴──────────────────────────────────────┐
│                      FASTAPI (processo web — I/O only)                 │
│  Rotas: ingest · documents · templates · review · automations · usage │
│  Responsabilidade: validar, enfileirar job, ler estado. NÃO processa.  │
└───────┬──────────────────────────────────────────┬────────────────────┘
        │ enfileira job (enqueue)                   │ lê estado
        ▼                                           ▼
┌───────────────────────┐              ┌────────────────────────────────┐
│   QUEUE (Redis/arq)   │              │   STATE STORE (SQLite/Postgres) │
│   jobs + retry + dedup│◄────────────►│   documents, pages, extractions,│
└───────┬───────────────┘              │   templates, audit_log, usage   │
        │ pega job                     └────────────────┬───────────────┘
        ▼                                                │ lê/escreve
┌──────────────────────────────────────────────────────┴────────────────┐
│                  WORKER (mesmo host — processo separado)                │
│  ┌────────┐ ┌──────┐ ┌───────┐ ┌──────────┐ ┌───────────┐ ┌──────────┐ │
│  │INGEST/ │→│SPLIT │→│ROUTER │→│EXTRACTION│→│CLASSIFY + │→│AUTOMATION│ │
│  │DEDUP   │ │PAGES │ │       │ │(det/txt/ │ │VALIDATE   │ │(rename/  │ │
│  │(hash)  │ │      │ │       │ │ AI)      │ │           │ │ move)    │ │
│  └────────┘ └──────┘ └───┬───┘ └────┬─────┘ └─────┬─────┘ └────┬─────┘ │
└──────────────────────────│──────────│─────────────│────────────│───────┘
                           │          │             │            │
                  parser   │   OpenAI │      threshold baixo →    │ dry-run
                  boleto/  │   API    │      QUARENTENA/REVISÃO   │ + undo log
                  NF-e     ▼   (vision/structured)                ▼
              ┌────────────────────┐                    ┌──────────────────┐
              │  BLOB STORE local  │                    │  FILESYSTEM do    │
              │  (CAS por hash)    │                    │  cliente (saída)  │
              └────────────────────┘                    └──────────────────┘
```

### Component Responsibilities

| Componente | Responsabilidade (o que possui) | Implementação típica |
|-----------|---------------------------------|----------------------|
| **API (FastAPI)** | Endpoint HTTP; valida entrada, enfileira jobs, lê estado/progresso. Não executa processamento pesado. | Routers async, Pydantic v2, dependência de DB session |
| **Hot folder watcher** | Detecta novos arquivos numa pasta monitorada e enfileira job de ingestão | `watchdog` (observer) no processo worker ou serviço próprio |
| **Queue + Worker** | Executa cada etapa em background com retry/backoff; concorrência controlada; idempotência por job key | `arq` + Redis (recomendado) |
| **Ingest/Dedup** | Calcula hash do conteúdo; rejeita/marca duplicatas; copia para blob store (CAS) | `hashlib.sha256`, store por hash |
| **Page Splitter** | Separa PDF multipágina em N páginas/grupos configuráveis | `pypdf`/`pikepdf` |
| **Extraction Router** | Decide a rota por documento: determinística → texto nativo → IA. Owner da política de custo | Regras + detecção de texto (`pdfplumber`/`PyMuPDF`) |
| **Deterministic parsers** | Boleto (linha digitável/código de barras) e NF-e (chave 44 díg./XML) sem IA | parsing + dígito verificador (mód. 10/11) |
| **AI Extractor** | OCR + extração estruturada via OpenAI structured outputs (JSON Schema) | `openai` SDK, `response_format` json_schema, vision |
| **Classifier** | Atribui documento a template/sub-template (campos + score de confiança) | regras + IA p/ contexto |
| **Validator** | Valida campos (CNPJ, data, valor) e gera score; abaixo do threshold → quarentena | Pydantic + validators de domínio BR |
| **Automation Engine** | Executa renomear/mover com dry-run, log de undo, anti-colisão | filesystem + tabela `audit_log` |
| **State Store** | Verdade única do estado de cada documento, extrações, templates, audit, usage | SQLite (default) / Postgres (servidor) |
| **Usage Meter** | Registra tokens/chamadas por etapa e por documento p/ cobrança | hook na resposta OpenAI (`usage` field) |

## Recommended Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, lifespan, mount static (React build)
│   ├── api/                 # Camada HTTP — fina, sem lógica de pipeline
│   │   ├── ingest.py        # upload, registrar hot folder, batch
│   │   ├── documents.py     # listar/ver estado, reprocessar
│   │   ├── templates.py     # CRUD templates e sub-templates
│   │   ├── review.py        # fila de revisão, corrigir campos, aprovar
│   │   ├── automations.py   # dry-run, aplicar, desfazer
│   │   └── usage.py         # relatório de tokens/uso
│   ├── pipeline/            # NÚCLEO — cada etapa é um módulo puro/testável
│   │   ├── stages/
│   │   │   ├── ingest.py    # hash, dedup, persistir no CAS
│   │   │   ├── split.py     # separação de páginas
│   │   │   ├── router.py    # política determinístico→texto→IA
│   │   │   ├── extract_deterministic.py  # boleto, NF-e
│   │   │   ├── extract_text.py           # texto nativo PDF
│   │   │   ├── extract_ai.py             # OpenAI structured outputs
│   │   │   ├── classify.py  # template matching + confiança
│   │   │   ├── validate.py  # validators BR + threshold quarentena
│   │   │   └── automation.py # rename/move + undo log
│   │   ├── orchestrator.py  # avança o documento pela máquina de estados
│   │   └── states.py        # enum de estados + transições válidas
│   ├── workers/
│   │   ├── tasks.py         # funções arq (enqueue targets)
│   │   ├── settings.py      # config arq (concorrência, retry)
│   │   └── watcher.py       # watchdog da hot folder
│   ├── domain/              # modelos de domínio (templates, regras de automação)
│   │   ├── templates.py     # schema extensível de template/sub-template
│   │   └── automation_rules.py # regras extensíveis (rename/move hoje; futuro)
│   ├── integrations/
│   │   └── openai_client.py # wrapper: structured outputs + captura de usage
│   ├── storage/
│   │   ├── blobs.py         # CAS por hash (entrada imutável)
│   │   └── db.py            # SQLAlchemy/SQLModel, migrações
│   ├── models/              # tabelas: Document, Page, Extraction, AuditLog, Usage
│   └── config.py            # settings (OPENAI_API_KEY, paths, thresholds)
├── alembic/                 # migrações de schema
└── tests/                   # testes por etapa (fixtures de documento real)

frontend/                    # React SPA (build servido pelo FastAPI em prod)
```

### Structure Rationale

- **`pipeline/stages/`:** cada etapa é uma função pura `(input_state) -> output_state` sem conhecer HTTP nem a fila. Permite testar uma NF-e real isoladamente, reprocessar a partir de qualquer estado e adicionar etapas futuras sem tocar nas vizinhas. Esta é a fronteira mais importante do sistema.
- **`api/` fina:** a API só valida, enfileira e lê. Toda regra de negócio vive em `pipeline/` e `domain/`. Isso evita o anti-padrão de "lógica na rota" e mantém a UI/CLI/hot-folder como entradas intercambiáveis.
- **`domain/` separado de `pipeline/`:** templates e regras de automação são *dados configuráveis pelo cliente*, não código. Modelá-los como dados (schema versionado) é o que torna o sistema extensível para e-mail/WhatsApp/API no futuro sem deploy.
- **`integrations/openai_client.py` único:** centraliza captura de tokens (cobrança), retry de rate limit e o que sai da máquina (gancho LGPD). Nenhuma etapa chama a OpenAI direto.
- **`storage/blobs.py` como CAS:** o arquivo de entrada é imutável e endereçado por hash; as automações operam em cópias/saídas, nunca destroem o original. Base da reversibilidade.

## Architectural Patterns

### Pattern 1: Document as a State Machine (etapas desacopláveis)

**What:** Cada documento tem um campo `state` com transições explícitas. O orquestrador avança o documento uma etapa por vez, persistindo o estado entre cada uma.

**When to use:** Sempre neste projeto — é o eixo da arquitetura. Permite quarentena, retry, reprocessamento e auditoria.

**Trade-offs:** Mais cerimônia que processamento inline (precisa persistir entre etapas), mas é o que torna o pipeline confiável, observável e recuperável após crash. Para documentos fiscais isso não é negociável.

**Estados sugeridos:**
```
RECEIVED → DEDUPED → SPLIT → ROUTED → EXTRACTED → CLASSIFIED
        → VALIDATED → (AUTO) PENDING_AUTOMATION → APPLIED
                    → (low confidence / sem template) QUARANTINED
                    → (revisão humana) IN_REVIEW → VALIDATED (volta)
        → FAILED (erro após retries — nunca some, vai p/ quarentena)
```

```python
# states.py
class DocState(str, Enum):
    RECEIVED = "received"; DEDUPED = "deduped"; SPLIT = "split"
    ROUTED = "routed"; EXTRACTED = "extracted"; CLASSIFIED = "classified"
    VALIDATED = "validated"; PENDING_AUTOMATION = "pending_automation"
    APPLIED = "applied"; IN_REVIEW = "in_review"
    QUARANTINED = "quarantined"; FAILED = "failed"

TRANSITIONS: dict[DocState, set[DocState]] = {
    DocState.VALIDATED: {DocState.PENDING_AUTOMATION, DocState.QUARANTINED, DocState.IN_REVIEW},
    # ...transição inválida = bug, não dado corrompido
}
```

### Pattern 2: Confidence-Threshold Routing com Human-in-the-Loop

**What:** Após validação, se o score de confiança < threshold (ou falta template, ou validação de campo falha), o documento vai para `QUARANTINED`/`IN_REVIEW` em vez de aplicar automações. A UI permite corrigir e re-validar.

**When to use:** É um requisito de v1 (revisão humana, quarentena). Padrão padrão em todo IDP de produção (AWS Bedrock IDP, Azure usam exatamente isto).

**Trade-offs:** Exige UI de revisão e modelagem de "callback" (documento espera ação humana). O custo é justificado: documentos fiscais errados aplicados às cegas causam perda de arquivos do cliente.

### Pattern 3: Tiered Extraction (cost-aware routing)

**What:** Router decide a rota mais barata que funciona, nesta ordem:
1. **Determinístico** — boleto (linha digitável/código de barras 44 pos.) e NF-e (chave 44 díg. / XML): custo zero, 100% preciso.
2. **Texto nativo** — se o PDF tem camada de texto extraível: custo zero.
3. **IA (OpenAI vision + structured outputs)** — só imagens/PDFs escaneados ou campos que sobraram.

**When to use:** Núcleo da estratégia de custo do produto (cobrança por token). Minimizar IA = minimizar custo do cliente = vantagem do produto.

**Trade-offs:** Mais lógica de roteamento e mais código de parsing determinístico para manter. Vale muito: cada documento que evita a IA economiza dinheiro real do cliente e elimina risco LGPD.

```python
def route(doc) -> Route:
    if (b := try_parse_boleto(doc)) or (n := try_parse_nfe(doc)):
        return Route.DETERMINISTIC          # custo zero
    if has_native_text(doc):
        return Route.NATIVE_TEXT            # custo zero
    return Route.AI                         # OpenAI, mede tokens
```

### Pattern 4: Reversible Operations via Write-Ahead Audit Log

**What:** Antes de qualquer rename/move, grava no `audit_log` a operação planejada (origem, destino, hash). Dry-run = calcular o plano e mostrá-lo SEM executar. Undo = ler o log e reverter na ordem inversa. Anti-colisão: nunca sobrescrever destino existente.

**When to use:** Toda operação que toca arquivos do cliente (requisito de integridade/v1).

**Trade-offs:** O original sempre preservado no CAS torna o undo seguro mesmo se o log corromper. Princípio retirado de transactional file systems: registrar a intenção *antes* de agir.

## Data Flow

### Request Flow (ingestão até automação)

```
[Upload / Hot folder / CLI batch]
    ↓
[API valida] → [enfileira job arq] → retorna 202 + document_id
                    ↓
              [Worker pega job]
                    ↓
   ingest(hash, dedup→CAS) → split(páginas) → route()
                    ↓
   ┌── determinístico (boleto/NF-e) ──┐
   ├── texto nativo PDF ──────────────┤→ extract → classify(template)
   └── OpenAI (vision+json_schema) ───┘            ↓
                                              validate(campos BR)
                                                    ↓
                          score ≥ threshold ──→ PENDING_AUTOMATION
                          score < threshold  ──→ QUARANTINED / IN_REVIEW
                                                    ↓
                          [dry-run preview na UI] → [aplicar]
                                                    ↓
                          audit_log (write-ahead) → rename/move
```

### State / Progress Management

```
[State Store = DB]  ← única fonte de verdade do estado de cada documento
       ↑ escreve cada transição          ↓ lê estado/progresso
   [Worker/etapas]                    [API] → [React] (polling ou SSE)
```
A UI React NÃO mantém estado de pipeline — ela reflete o DB. Progresso de lote = contar documentos por estado. Isso evita dessincronização e sobrevive a reload/crash.

### Key Data Flows

1. **Dedup por conteúdo:** hash SHA-256 do arquivo na ingestão → se já existe, marca duplicata e NÃO reprocessa/cobra. CAS garante que arquivos idênticos ocupem espaço uma vez.
2. **Idempotência de job:** job key derivada do hash + etapa. Retry após falha/crash não duplica trabalho nem chamadas à OpenAI (evita cobrança dupla).
3. **Medição de uso:** cada chamada OpenAI retorna `usage` (prompt/completion tokens) → gravado em `usage` ligado ao document_id e à etapa → relatório de cobrança.
4. **Reversão:** `audit_log` registra cada rename/move com origem/destino/hash → undo percorre em ordem inversa; original intacto no CAS como rede de segurança.

## Scaling Considerations

Single-tenant: "escala" aqui = tamanho do lote e throughput num host, não número de usuários.

| Escala | Ajustes de arquitetura |
|--------|------------------------|
| Uso leve (até ~centenas de docs/dia) | SQLite + arq + Redis num só host. Monólito modular. Suficiente. |
| Lotes grandes / servidor dedicado | Trocar SQLite → Postgres; aumentar concorrência do worker arq (jobs I/O-bound, OpenAI é a espera dominante). |
| Throughput pesado contínuo | Múltiplos processos worker no mesmo host lendo a mesma fila Redis; ainda single-tenant. CPU-bound (PDF/imagem) pode usar pool de processos. |

### Scaling Priorities

1. **Primeiro gargalo: rate limit / latência da OpenAI.** É I/O-bound — `arq` async roda muitos jobs concorrentes num worker. Mitigar com backoff exponencial e fila; medir tokens para o cliente dosar.
2. **Segundo gargalo: CPU de split/render de PDF e imagem.** Isolar etapas CPU-bound num pool de processos separado das etapas I/O-bound, para não bloquear o event loop.

## Anti-Patterns

### Anti-Pattern 1: Processar inline na rota HTTP (sem fila)

**What people do:** Chamar OpenAI/processar o PDF dentro do handler da requisição de upload.
**Why it's wrong:** Timeout de HTTP em lotes grandes; sem retry; um crash perde o trabalho; rate limit da OpenAI derruba requisições do usuário. `BackgroundTasks` do FastAPI roda no mesmo processo e não dá durabilidade/retry.
**Do this instead:** API só enfileira (retorna 202 + id); worker `arq` processa com retry e idempotência. Progresso via polling/SSE lendo o DB.

### Anti-Pattern 2: Pipeline como uma função monolítica gigante

**What people do:** Uma função `process_document()` que faz ingestão→IA→automação de ponta a ponta sem persistir estado intermediário.
**Why it's wrong:** Impossível reprocessar de um ponto, impossível inserir revisão humana no meio, crash perde tudo, testar uma etapa exige rodar todas. Mata a extensibilidade futura (e-mail/WhatsApp).
**Do this instead:** Etapas desacopladas com estado persistido entre cada uma (Pattern 1). Cada etapa lê estado, faz uma coisa, escreve estado.

### Anti-Pattern 3: Aplicar automações sem reversibilidade

**What people do:** `os.rename()` direto assim que a IA extrai os campos.
**Why it's wrong:** IA pode errar; mover/renomear sem log/undo perde o arquivo do cliente — falha catastrófica de confiança para dados fiscais.
**Do this instead:** Dry-run obrigatório, write-ahead audit log, original imutável no CAS, undo, anti-colisão (nunca sobrescrever). Confiança é requisito de v1.

### Anti-Pattern 4: Hardcodar templates/regras como código

**What people do:** Tipos de documento e regras de rename/move embutidos em `if/elif` no código.
**Why it's wrong:** Cliente precisa criar templates pelo app; cada novo emissor exigiria deploy. Bloqueia automações futuras (API/e-mail/WhatsApp).
**Do this instead:** Templates e regras de automação como **dados versionados no DB** com um schema extensível; o motor interpreta os dados. Regra de automação = `{tipo, params}` para suportar novos tipos sem mudar o core.

### Anti-Pattern 5: Mandar tudo para a IA

**What people do:** Enviar todo PDF para a OpenAI por simplicidade.
**Why it's wrong:** Custo de token desnecessário (o cliente paga), risco LGPD (dado fiscal sensível saindo da máquina), mais lento, e perde precisão onde parsing determinístico seria 100%.
**Do this instead:** Tiered extraction (Pattern 3): determinístico → texto nativo → IA só no resto.

## Integration Points

### External Services

| Serviço | Padrão de integração | Notas |
|---------|----------------------|-------|
| **OpenAI API** | Cliente único em `integrations/`; `response_format: json_schema` (structured outputs) + entrada vision para escaneados | Capturar `usage.prompt_tokens`/`completion_tokens` por chamada (cobrança). Chave por instância via env/config. Structured outputs garante JSON válido conforme o template. Backoff em rate limit (429). |
| **Filesystem do cliente** | Hot folder (watchdog) na entrada; rename/move com audit log na saída | Operações reversíveis e anti-colisão. Original preservado no CAS. |
| **Redis** | Broker da fila arq (mesmo host) | Dependência operacional única do worker; baixíssimo overhead. |

### Internal Boundaries

| Fronteira | Comunicação | Notas |
|-----------|-------------|-------|
| API ↔ Worker | Fila (enqueue job), não chamada direta | API nunca processa; desacopla durabilidade do request HTTP |
| Worker ↔ State Store | Leitura/escrita direta (DB) | DB é a fonte de verdade do estado; transição persistida por etapa |
| Etapa ↔ Etapa | Via estado no DB (orquestrador), não chamada direta | Permite reprocessar, inserir revisão, testar isolado |
| Pipeline ↔ OpenAI | Só via `integrations/openai_client.py` | Ponto único p/ tokens, retry e controle LGPD do que sai |
| UI ↔ Estado | API read-only + polling/SSE | UI reflete o DB; nunca dona do estado de pipeline |

## Suggested Build Order (dependências entre componentes)

A ordem deriva das dependências reais — cada fase entrega algo testável e desbloqueia a próxima.

1. **Fundação de estado + storage.** Modelos `Document`/`Page`/`AuditLog`/`Usage`, máquina de estados, CAS por hash, DB/migrações. Tudo depende disto.
2. **Ingestão + dedup.** Upload manual + hash + dedup → documento entra em `RECEIVED/DEDUPED`. Entrada mais simples primeiro; hot folder e CLI depois (mesma porta de entrada).
3. **Fila + worker (arq/Redis) + orquestrador.** Tira o processamento da rota HTTP cedo — refatorar depois é caro. Mesmo com etapas vazias, valida o esqueleto async/retry/idempotência.
4. **Split de páginas.** Etapa isolada, dependência baixa, necessária antes da extração por página.
5. **Extração determinística (boleto/NF-e) + texto nativo.** Custo zero, alto valor, testável sem chave OpenAI. Estabelece o contrato de saída estruturada antes de plugar a IA.
6. **Extração via OpenAI (structured outputs + vision) + medição de tokens.** Encaixa na rota da IA reusando o contrato da etapa 5. Medição junto desde o início (cobrança).
7. **Templates/sub-templates + classificação.** Depende do schema de extração existir. Construtor no app + matching. Modelar como dados extensíveis aqui.
8. **Validação + threshold + quarentena/revisão.** Depende de extração e classificação produzirem campos e score. Habilita human-in-the-loop.
9. **Automação (rename/move) + dry-run + audit log + undo.** Última etapa do pipeline; depende de campos validados e confiáveis. Reversibilidade desde o primeiro commit desta fase.
10. **Hot folder + CLI batch + relatório de uso + empacotamento single-tenant.** Entradas adicionais e operação; reusam tudo abaixo.

**Implicação chave:** a fila/worker (passo 3) deve vir ANTES das etapas pesadas de extração — introduzir async depois força reescrever toda a orquestração. E reversibilidade (passo 9) é parte da definição de pronto da automação, não um extra posterior.

## Sources

- AWS — [Architecting an IDP pipeline with generative AI](https://aws.amazon.com/blogs/machine-learning/from-pdfs-to-insights-architecting-an-intelligent-document-processing-pipeline-with-aws-generative-ai-services/) (HIGH — fases canônicas do pipeline IDP)
- AWS — [Scalable IDP using Amazon Bedrock](https://aws.amazon.com/blogs/machine-learning/scalable-intelligent-document-processing-using-amazon-bedrock/) (HIGH — state machine, Map para páginas, quarentena, callback de revisão humana)
- Azure Architecture Center — [Extract and Map Information from Unstructured Content](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/multi-modal-content-processing) (HIGH — confidence-threshold routing, human-in-the-loop)
- arXiv — [Operationalizing Document AI: A Microservice Architecture for OCR and LLM Pipelines](https://arxiv.org/html/2605.18818v1) (MEDIUM — separação de etapas em produção)
- [FastAPI Background Tasks: Celery vs ARQ vs RQ (2026)](https://medium.com/@rameshkannanyt0078/fastapi-background-tasks-celery-vs-arq-vs-rq-2026-benchmarks-decision-guide-f99598aa21eb) e [Why arq/RQ over Celery for LLM Workloads](https://dangquan1402.github.io/llm-engineering-notes/2026/04/02/lightweight-task-queues-for-llm-apps.html) (MEDIUM — arq recomendado para I/O-bound LLM em FastAPI single-host)
- OpenAI — [Introducing Structured Outputs in the API](https://openai.com/index/introducing-structured-outputs-in-the-api/) e [Structured model outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs) (HIGH — json_schema compatível com vision, campo usage)
- Redis — [Idempotency cost-saving patterns for LLM apps](https://redis.io/blog/what-is-idempotency-in-redis/) e [Content-addressable storage (Wikipedia)](https://en.wikipedia.org/wiki/Content-addressable_storage) (HIGH — dedup por hash, idempotência, CAS)
- USPTO — [Transactional file system patents](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7257595) (MEDIUM — write-ahead log para reversibilidade)
- GitHub — [mrmgomes/boleto-utils](https://github.com/mrmgomes/boleto-utils), [Trust-Code/python-boleto](https://github.com/Trust-Code/python-boleto), [Webmania — chave de acesso NF-e](https://webmania.com.br/blog/entenda-como-funciona-a-chave-de-acesso-da-nf-e/) (MEDIUM — parsing determinístico boleto 44 pos. / NF-e 44 díg. mód.11)

---
*Architecture research for: IDP pipeline de documentos fiscais BR, single-tenant FastAPI + React*
*Researched: 2026-06-15*

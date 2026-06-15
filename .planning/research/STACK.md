# Stack Research

**Domain:** Aplicação web single-tenant para processamento/organização de documentos fiscais brasileiros (NF-e, boletos), com extração híbrida local + OpenAI
**Researched:** 2026-06-15
**Confidence:** HIGH (versões verificadas em docs/PyPI/npm oficiais; única área MEDIUM/LOW é parsing de boleto em Python — ver seção dedicada)

## Resumo Prescritivo (TL;DR)

| Camada | Escolha | Confiança |
|--------|---------|-----------|
| Backend framework | FastAPI 0.137.x + Uvicorn | HIGH |
| Validação/schemas | Pydantic 2.13.x | HIGH |
| PDF texto nativo + split | PyMuPDF (fitz) 1.27.x | HIGH |
| PDF manipulação robusta (split/repair) | pikepdf 10.x | HIGH |
| Tabelas/layout (fallback) | pdfplumber 0.11.x | MEDIUM |
| OCR local opcional | pytesseract 0.3.13 + Tesseract (por-bra) | MEDIUM |
| IA / OCR-visão | openai 2.41.x via **Responses API** + Structured Outputs | HIGH |
| NF-e (XML) | nfelib 2.5.x | HIGH |
| Chave NF-e / CNPJ (validação) | algoritmo determinístico próprio (Módulo 11 / Módulo 11 CNPJ) | HIGH |
| Boleto (linha digitável/código de barras) | **parser determinístico próprio** (Módulo 10/11) | MEDIUM |
| Watcher de pasta | watchfiles 1.2.x | HIGH |
| Fila/worker | **arq 0.28** (Redis) *ou* **SQLite-backed in-process** (ver variantes) | MEDIUM |
| Banco | **SQLite (WAL)** como padrão; Postgres opcional para modo servidor | HIGH |
| ORM + migrações | SQLAlchemy 2.0 (+ SQLModel 0.0.38 opcional) + Alembic 1.18.x | HIGH |
| Frontend | React 19.2 + Vite 8 + TypeScript | HIGH |
| Data-fetching | TanStack Query 5.101 | HIGH |
| Empacotamento server/local | Docker Compose (padrão) | HIGH |
| Futuro desktop | Tauri v2 + sidecar PyInstaller | MEDIUM |

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | 3.12 (3.11–3.13 ok) | Runtime do backend | 3.12 é o sweet-spot 2025/26: wheels prontas para PyMuPDF/pikepdf/pydantic-core, performance melhor que 3.11. Evitar 3.14 por imaturidade de wheels em algumas libs nativas. |
| **FastAPI** | 0.137.1 | API HTTP + serve o frontend buildado | Async nativo (essencial para chamadas OpenAI concorrentes), validação via Pydantic, OpenAPI grátis, mesmo binário roda em localhost ou servidor — atende ao requisito "mesmo código local ou servidor". |
| **Uvicorn** | 0.40.x (com `[standard]`) | ASGI server | Servidor de produção padrão para FastAPI; suporta reload em dev e workers em produção. Em single-tenant 1 worker basta; concorrência vem do async. |
| **Pydantic** | 2.13.4 | Modelos de extração, validação de campos (CNPJ, data, valor) e schema da IA | É a mesma camada usada pela OpenAI SDK para gerar/validar JSON Schema dos Structured Outputs — um modelo Pydantic serve simultaneamente como contrato da IA e validação determinística. |
| **PyMuPDF (fitz)** | 1.27.2.x | Extração de texto nativo, render de página→imagem para a IA, detecção "tem texto vs escaneado" | Mais rápido e mais preciso na extração de texto que pdfminer/pdfplumber; faz render para PNG/JPEG (necessário para mandar páginas como imagem à OpenAI). Licença AGPL — **ver "What NOT to Use" para implicação comercial**. |
| **OpenAI Python SDK** | 2.41.1 | Extração via IA (visão) com saída estruturada e contagem de tokens | SDK oficial. Usar **Responses API** (`client.responses.parse`) — recomendação oficial da OpenAI para projetos novos. `usage` no retorno dá tokens para a cobrança por consumo. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pikepdf** | 10.8.0 | Split de PDF por N páginas, merge, reparo de PDFs malformados | Use para a feature "separar páginas por quantidade configurável" e para sanear PDFs corrompidos antes de processar. Licença MPL-2.0 (permissiva) — preferível ao split do PyMuPDF onde a AGPL incomodar. |
| **pdfplumber** | 0.11.10 | Extração de tabelas e layout posicional | Fallback quando PyMuPDF não dá estrutura suficiente (ex.: tabelas de itens de NF). Não é o extrator principal — é mais lento. |
| **nfelib** | 2.5.2 | Ler/validar XML de NF-e (e CT-e, NFS-e, MDF-e) | Quando o input é o **XML** da NF-e (não o DANFE em PDF). Bindings gerados dos XSDs oficiais da Fazenda, licença MIT. Extração 100% determinística e gratuita. |
| **watchfiles** | 1.2.0 | Hot folder / pasta monitorada | Watcher da pasta de ingestão. Mantido pela equipe do pydantic/uvicorn, baseado em Rust (notify), async-friendly, mais confiável que `watchdog` em redes/NFS. |
| **arq** | 0.28.0 | Fila assíncrona + retry para lotes e rate limit OpenAI | Quando o cliente roda em **modo servidor** com Redis disponível. asyncio-nativo (combina com FastAPI/OpenAI async), retry e backoff embutidos. *Atenção: projeto em "maintenance mode" — ver alternativas.* |
| **httpx** | 0.28.x | Cliente HTTP async (já é dependência da OpenAI SDK) | Para automações futuras (webhooks) e healthchecks. |
| **python-dateutil** | 2.9.x | Parsing/normalização de datas extraídas | Normalizar datas heterogêneas (dd/mm/aaaa, ISO, etc.) dos documentos. |
| **pytesseract** | 0.3.13 | OCR local opcional (offline, sem custo OpenAI) | **Opcional.** Para clientes sensíveis a LGPD que querem reduzir o que sai da máquina, ou pré-OCR barato antes da IA. Requer binário Tesseract + traineddata `por`. Qualidade inferior à visão da OpenAI em documentos ruins. |
| **alembic** | 1.18.4 | Migrações de schema do banco | Toda mudança de schema entre versões do produto instalado no cliente. Crítico para upgrades sem perda de dados. |
| **SQLAlchemy** | 2.0.x | ORM / camada de banco | Abstrai SQLite↔Postgres com o mesmo código (atende ao requisito local↔servidor). API 2.0 async disponível. |
| **SQLModel** | 0.0.38 | Wrapper Pydantic+SQLAlchemy (opcional) | Se quiser modelos únicos servindo de tabela e de schema API. Opcional — SQLAlchemy puro é mais maduro; SQLModel ainda 0.0.x. |

### Frontend

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| **React** | 19.2.7 | UI (construtor de templates, revisão humana, dry-run) | Requisito do projeto. v19 estável. |
| **Vite** | 8.0.16 | Build tool / dev server | Padrão de fato 2026 para React (Create React App está morto). Build estático servido pelo FastAPI em produção (single-origin, sem CORS). Requer Node ≥20.19 ou ≥22.12. |
| **TypeScript** | 5.x | Tipagem | Compartilhar tipos dos modelos Pydantic via geração de cliente OpenAPI. |
| **TanStack Query** | 5.101.0 | Data-fetching/cache, polling de fila e status | Polling do status de processamento, invalidação após ações (dry-run→aplicar). |
| **openapi-typescript** + **openapi-fetch** | latest | Cliente tipado gerado do OpenAPI do FastAPI | Mantém frontend e backend em sincronia de tipos sem escrever fetch manual. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **uv** | Gerenciador de pacotes/venv Python | Substitui pip/poetry; resolução rápida, lockfile reprodutível — crítico para builds de distribuição idênticos no cliente. |
| **ruff** | Lint + format Python | Substitui flake8+black+isort. |
| **pytest** + **pytest-asyncio** | Testes | Testar parsers determinísticos (boleto/NF-e) com casos reais é a maior alavanca de confiança. |
| **respx** / **openai mock** | Mockar OpenAI nos testes | Não gastar tokens em CI; testar retry/rate-limit. |
| **PyInstaller** | Empacotar backend num executável | Necessário só no caminho futuro Tauri (sidecar). |

## Installation

```bash
# Backend (com uv)
uv add fastapi==0.137.1 "uvicorn[standard]" pydantic==2.13.4 \
       pymupdf==1.27.2.3 pikepdf==10.8.0 pdfplumber==0.11.10 \
       openai==2.41.1 nfelib==2.5.2 watchfiles==1.2.0 \
       sqlalchemy==2.0.* alembic==1.18.4 python-dateutil httpx

# Fila (modo servidor com Redis)
uv add arq==0.28.0

# OCR local opcional (requer binário Tesseract + traineddata 'por' no SO)
uv add pytesseract==0.3.13 pillow

# Dev
uv add --dev pytest pytest-asyncio respx ruff

# Frontend
npm create vite@latest frontend -- --template react-ts
npm install @tanstack/react-query@5.101.0
npm install -D openapi-typescript openapi-fetch
```

---

## Decisões Críticas (atenção especial)

### 1. SQLite vs Postgres — **SQLite (WAL) como padrão**

**Recomendação: SQLite por padrão; Postgres como opção de configuração para modo servidor.** Confiança: HIGH.

| Critério | SQLite | Postgres |
|----------|--------|----------|
| Instalação no cliente | Zero (embutido no Python) | Requer serviço/container extra |
| Single-tenant, 1 instância | Ideal | Overkill |
| Concorrência de escrita | Limitada (1 writer) — mas com WAL e fila serializando escritas é suficiente | Alta |
| Backup | Copiar 1 arquivo | pg_dump/serviço |
| Modo servidor multi-worker pesado | Frágil sob escrita concorrente alta | Ideal |

**Por quê SQLite ganha aqui:** o produto é single-tenant, instalado na máquina do cliente, com **um worker serializando o processamento** via fila. A contenção de escrita do SQLite deixa de ser problema quando há um único writer (o worker). Habilitar `PRAGMA journal_mode=WAL` e `busy_timeout` resolve leituras concorrentes da API web. "Banco = 1 arquivo" simplifica backup, dedup por hash e o requisito de "nunca perder dados". Usar SQLAlchemy + Alembic mantém a porta aberta para Postgres trocando só a connection string — recomende isto desde o dia 1 para não acoplar a SQLite.

**Quando trocar para Postgres:** cliente roda em servidor com múltiplos usuários simultâneos revisando documentos e alto volume de escrita concorrente. Tornar configurável via `DATABASE_URL`.

### 2. Parsing de boleto em Python — **parser determinístico próprio** (NÃO há lib madura)

**Recomendação: implementar parser próprio do código de barras (44 dígitos) e linha digitável (47/48 dígitos) com validação Módulo 10/11.** Confiança: MEDIUM (algoritmo HIGH; ausência de lib pronta confirmada).

**Achado importante:** as bibliotecas Python de "boleto" no PyPI (`python-boleto`/pyboleto, `iqnus-boleto`) são para **gerar/emitir** boletos, não para fazer parsing/validação de um boleto recebido. A melhor referência de parsing (`@mrmgomes/boleto-utils`) é **JavaScript-only** (npm), não existe em Python. `pyzbar` (0.1.9, último release 2022) lê o **código de barras visual** de uma imagem mas não interpreta os campos.

**Estratégia prescritiva:**
1. **Se há texto/imagem com a linha digitável** → parser determinístico próprio: separar os 5 campos, validar DV de cada campo (Módulo 10), validar DV geral do código de barras (Módulo 11), extrair fator de vencimento (→ data, base 1997/2000-2025) e valor (últimos 10 dígitos / 100). Tratar boleto de arrecadação/convênio (inicia com "8", usa Módulo 10 ou 11 conforme 3º dígito).
2. **Se o boleto é imagem com código de barras Interleaved 2of5** → `pyzbar` para extrair os 44 dígitos, depois o parser acima. Portar a lógica testada do `boleto-utils` JS é caminho de baixo risco.
3. **Cobrir com testes** usando boletos reais — esta é a feature onde "determinístico = custo zero + 100% preciso" se concretiza.

### 3. NF-e — **nfelib para XML; algoritmo próprio para chave de acesso**

**Recomendação:** Confiança: HIGH.
- **Input XML de NF-e** → `nfelib` 2.5.2 (MIT, bindings dos XSDs oficiais). Extração completa e determinística.
- **Apenas a chave de 44 dígitos** (ex.: extraída do DANFE em PDF/imagem) → validar o DV (44º dígito) com **Módulo 11** próprio e fatiar os campos (UF, AAMM, CNPJ emitente, modelo, série, número, tipo emissão, código numérico). Trivial e sem dependência.
- Validar **CNPJ** com algoritmo de dígito verificador próprio (Módulo 11 de CNPJ). Não vale dependência externa para isso.

### 4. OpenAI — **Responses API + Structured Outputs**, não Chat Completions/JSON mode

**Recomendação: `client.responses.parse(model=..., input=..., text_format=MeuModeloPydantic)`.** Confiança: HIGH.

- A **Responses API** (lançada em março/2025) é a recomendação oficial da OpenAI para projetos novos; em testes internos a OpenAI reporta melhor custo/latência vs Chat Completions. Suporta texto + imagem (visão) + saída estruturada num só endpoint.
- **Structured Outputs** (schema garantido) > "JSON mode" — a OpenAI recomenda sempre usar Structured Outputs quando possível. Em Responses usa-se `text.format`/`text_format`; em Chat Completions seria `response_format`.
- Passar um modelo **Pydantic** como `text_format` faz o SDK gerar o JSON Schema, validar a resposta e devolver objeto tipado — o mesmo modelo vira sua validação determinística de campos. Encaixe perfeito com o requisito "saída estruturada por template + validações (CNPJ, data, valor)".
- **Visão:** mandar a página renderizada (PyMuPDF → PNG/JPEG) como `input_image`. Para PDFs nativos também há `input_file`, mas para escaneados o caminho imagem é o mais previsível.
- **Cobrança por tokens:** ler `response.usage` (input/output tokens) em cada chamada e persistir por chave/documento. É a base da medição de consumo exigida.
- **Modelo:** usar família `gpt-4o`/sucessor com visão e Structured Outputs (confirmar o modelo vigente na conta no momento da implementação — modelos giram rápido).

### 5. Fila/worker — depende do modo de distribuição

**Recomendação: arq (Redis) no modo servidor; fila in-process baseada em SQLite no modo "instala-e-roda" sem Redis.** Confiança: MEDIUM.

O dilema é que **arq, dramatiq e celery todos exigem um broker (Redis/RabbitMQ)** — o que adiciona uma dependência de infraestrutura que contradiz o ideal "cliente instala numa máquina e roda". Opções:

- **Modo servidor / Docker Compose:** `arq` + Redis. asyncio-nativo (combina com OpenAI async), retry/backoff embutidos. (arq está em "maintenance mode" mas estável; dramatiq 2.1 é a alternativa mais ativa se preferir, porém é sync-first.)
- **Modo "máquina do cliente" sem Redis:** fila persistida na **própria tabela SQLite** consumida por um worker `asyncio` dentro do mesmo processo (ou processo irmão) — sem broker externo. Implementação modesta: tabela `jobs(status, attempts, next_retry_at, ...)`, polling com backoff, respeitando rate limit da OpenAI. Mantém o "double-click and run".

Projetar a camada de fila atrás de uma interface (`enqueue`/`process`) para trocar o backend sem mexer no resto.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Responses API | Chat Completions API | Só se precisar de feature legada específica ainda não portada para Responses. Para projeto novo, Responses. |
| SQLite (WAL) | Postgres | Modo servidor multiusuário com escrita concorrente alta. |
| arq | dramatiq 2.1 | Se preferir worker sync robusto e maturidade ativa; aceita o broker. |
| arq / fila SQLite | Celery 5.6 | Ecossistema gigante já existente. Pesado demais e sync-first para single-tenant. |
| PyMuPDF (extração) | pdfplumber | Quando precisa de tabelas/posições; mais lento, usar como fallback. |
| OpenAI visão | pytesseract (Tesseract) | Cliente LGPD-sensível querendo OCR offline, ou pré-OCR barato. Qualidade menor em scans ruins. |
| Vite + React | Next.js | Só se precisar SSR/SEO — irrelevante para app interno single-tenant. Vite é mais simples de servir pelo FastAPI. |
| SQLAlchemy puro | SQLModel | Se quiser um modelo único API+DB e aceitar lib 0.0.x. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Create React App** | Descontinuado, sem manutenção, build lento | Vite 8 |
| **`watchdog`** | Polling/eventos menos confiáveis em redes/NFS, API sync | `watchfiles` (Rust/notify, async) |
| **OpenAI "JSON mode" (`response_format: json_object`)** | Não garante o schema; pode faltar campos | **Structured Outputs** (schema garantido) |
| **`pyboleto`/`python-boleto`/`iqnus-boleto` para parsing** | São para **gerar** boletos, não para ler/validar boletos recebidos | Parser determinístico próprio (Módulo 10/11) |
| **`PyPDF2`** | Deprecado (fundido em `pypdf`); reparo e split frágeis | `pikepdf` (qpdf) para split/repair; PyMuPDF para texto |
| **Electron (para o futuro desktop)** | Pesado; e não atende ao caso "servidor" | Docker no servidor; Tauri v2 se/quando desktop |
| **Chamar OpenAI síncrono em loop no request** | Bloqueia, estoura rate limit, sem retry | Fila/worker async com backoff |
| **Acoplar SQL direto ao SQLite** | Trava migração para Postgres | SQLAlchemy + Alembic desde o dia 1 |
| **PyMuPDF sem atentar à licença** | AGPL-3.0: produto **vendido** pode exigir licença comercial da Artifex | Avaliar licença comercial PyMuPDF, OU usar pikepdf (MPL) + pdfium/pypdfium2 para render onde a AGPL for impeditiva |

> **Flag de licenciamento (importante para produto vendido):** PyMuPDF é **AGPL-3.0**. Como o app é **vendido** a clientes, confirme com jurídico se precisa da **licença comercial** da Artifex. Alternativa permissiva: `pypdfium2` (Apache/BSD via PDFium) para render página→imagem e `pdfplumber`/`pdfminer.six` (MIT) para texto, mantendo o stack 100% permissivo. nfelib (MIT) e pikepdf (MPL-2.0) já são seguros.

## Stack Patterns by Variant

**Se distribuição = "máquina do cliente, double-click":**
- SQLite (WAL) + fila in-process SQLite (sem Redis)
- Futuro: Tauri v2 + backend FastAPI empacotado com PyInstaller como **sidecar**; frontend Vite buildado embutido
- Porque: zero dependências de infraestrutura externa

**Se distribuição = "servidor do cliente":**
- Docker Compose: container app (FastAPI+Uvicorn) + container Redis (+ Postgres opcional)
- arq como worker em container separado
- Porque: escala, múltiplos revisores humanos, robustez de escrita

**Se cliente LGPD-sensível (minimizar dados à OpenAI):**
- Roteamento agressivo: texto nativo (PyMuPDF) → parser determinístico (boleto/NF-e/chave) → pytesseract local → só então OpenAI
- Logar/explicar exatamente o que sai da máquina (já é objetivo de evolução do projeto)

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| SQLModel 0.0.38 | SQLAlchemy >=2.0.14,<2.1 ; Pydantic >=2.11 | Se usar SQLModel, fixar SQLAlchemy <2.1. |
| openai 2.41.x | Pydantic 2.x | SDK usa Pydantic 2; modelos de `text_format` devem ser Pydantic v2. |
| Vite 8 | Node >=20.19 ou >=22.12 | Build do frontend exige Node recente. |
| PyMuPDF 1.27.x | Python 3.10–3.14 | Wheels prontas; preferir 3.12 em produção. |
| watchfiles 1.2 | Python 3.10–3.15 | — |
| arq 0.28 | Redis >=4.2 | Broker obrigatório. |
| Tauri v2 sidecar | PyInstaller (executável único) | Backend empacotado e declarado como `externalBin`. |

## Sources

- `/openai/openai-python` (Context7/ctx7) — `.responses.parse` / `.chat.completions.parse`, Structured Outputs com Pydantic — HIGH
- https://developers.openai.com/api/docs/guides/structured-outputs & /migrate-to-responses & blog/responses-api — Responses API é o padrão recomendado; usar Structured Outputs over JSON mode — HIGH
- PyPI JSON API (pypi.org/pypi/<pkg>/json) — versões: openai 2.41.1, fastapi 0.137.1, pydantic 2.13.4, PyMuPDF 1.27.2.3, pikepdf 10.8.0, pdfplumber 0.11.10, sqlmodel 0.0.38, alembic 1.18.4, watchfiles 1.2.0, arq 0.28.0, dramatiq 2.1.0, celery 5.6.3, pytesseract 0.3.13, nfelib 2.5.2 — HIGH
- npm registry (registry.npmjs.org) — react 19.2.7, vite 8.0.16, @tanstack/react-query 5.101.0 — HIGH
- github.com/akretion/nfelib + pypi nfelib — leitura/validação de XML NF-e, licença MIT — HIGH
- github.com/mrmgomes/boleto-utils — confirmado **JavaScript-only (npm), não há equivalente Python mantido** — MEDIUM
- pypi pyzbar 0.1.9 (último release 2022) — leitura de código de barras visual, não interpreta campos — MEDIUM
- v2.tauri.app/develop/sidecar + templates tauri-fastapi-sidecar (GitHub) — padrão Tauri v2 + PyInstaller sidecar — MEDIUM
- Algoritmos Módulo 10/11 (boleto), Módulo 11 (chave NF-e e CNPJ) — domínio público, especificação FEBRABAN/Receita — HIGH

---
*Stack research for: processamento/organização de documentos fiscais (single-tenant)*
*Researched: 2026-06-15*

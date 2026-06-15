<!-- GSD:project-start source:PROJECT.md -->

## Project

**Processador de Documentos**

Aplicação web (FastAPI + React, web-first) vendida como produto para empresas que recebem muitos documentos de **tipos variados** (cada cliente tem seus próprios tipos — notas fiscais e boletos são apenas exemplos). O cliente roda na própria máquina ou servidor (majoritariamente **Windows**) e configura, pelo app, **templates** por tipo de documento e **sub-templates por cliente/emissor**, com os campos a extrair e as automações desejadas. O sistema ingere os documentos, separa páginas quando necessário, lê os dados (texto nativo de PDF localmente; imagens e PDFs escaneados via IA da OpenAI), classifica cada documento contra os templates e executa automações — inicialmente **renomear e mover** arquivos com base nos dados extraídos. O motor é **genérico** (qualquer tipo de documento via template + IA); parsing determinístico de tipos conhecidos é otimização, não o foco.

**Core Value:** Transformar uma pilha de documentos heterogêneos (PDFs e imagens) em arquivos **classificados, nomeados e organizados corretamente de forma automática e confiável** — sem o usuário perder arquivos nem confiar cegamente na IA.

### Constraints

- **Plataforma primária**: **Windows** — a maioria das instalações roda em Windows; empacotamento, watcher de pasta e operações de arquivo (NTFS, atomicidade, cross-device) devem ser testados e confiáveis nele primeiro
- **Tech stack**: Backend Python/FastAPI + frontend React (web-first) — alinhado à familiaridade com Python e ao requisito de rodar local ou em servidor
- **Distribuição**: O mesmo código deve rodar em `localhost` (máquina do cliente Windows) **ou** em servidor — evita travar em modelo desktop; empacotamento desktop (preferência Tauri sobre Electron) fica como evolução. Preferir **fila in-process (SQLite)** ao invés de Redis no modo padrão, para não exigir broker externo no Windows
- **Domínio genérico**: O motor não pode ser acoplado a tipos fiscais específicos — qualquer tipo de documento deve ser suportado via template + IA; parsing determinístico de tipos conhecidos é um módulo opcional/plugável
- **Dependência externa**: Parte de IA exige internet e chave OpenAI válida por instância
- **Provedor de IA**: OpenAI (ChatGPT) — definido pelo usuário
- **Segurança/LGPD**: Documentos fiscais são sensíveis; minimizar e tornar explícito o que sai da máquina para a OpenAI
- **Integridade de arquivos**: Operações que movem/renomeiam arquivos do cliente devem ser reversíveis e nunca podem causar perda (quarentena + dry-run + log/desfazer)

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

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

# Backend (com uv)

# Fila (modo servidor com Redis)

# OCR local opcional (requer binário Tesseract + traineddata 'por' no SO)

# Dev

# Frontend

## Decisões Críticas (atenção especial)

### 1. SQLite vs Postgres — **SQLite (WAL) como padrão**

| Critério | SQLite | Postgres |
|----------|--------|----------|
| Instalação no cliente | Zero (embutido no Python) | Requer serviço/container extra |
| Single-tenant, 1 instância | Ideal | Overkill |
| Concorrência de escrita | Limitada (1 writer) — mas com WAL e fila serializando escritas é suficiente | Alta |
| Backup | Copiar 1 arquivo | pg_dump/serviço |
| Modo servidor multi-worker pesado | Frágil sob escrita concorrente alta | Ideal |

### 2. Parsing de boleto em Python — **parser determinístico próprio** (NÃO há lib madura)

### 3. NF-e — **nfelib para XML; algoritmo próprio para chave de acesso**

- **Input XML de NF-e** → `nfelib` 2.5.2 (MIT, bindings dos XSDs oficiais). Extração completa e determinística.
- **Apenas a chave de 44 dígitos** (ex.: extraída do DANFE em PDF/imagem) → validar o DV (44º dígito) com **Módulo 11** próprio e fatiar os campos (UF, AAMM, CNPJ emitente, modelo, série, número, tipo emissão, código numérico). Trivial e sem dependência.
- Validar **CNPJ** com algoritmo de dígito verificador próprio (Módulo 11 de CNPJ). Não vale dependência externa para isso.

### 4. OpenAI — **Responses API + Structured Outputs**, não Chat Completions/JSON mode

- A **Responses API** (lançada em março/2025) é a recomendação oficial da OpenAI para projetos novos; em testes internos a OpenAI reporta melhor custo/latência vs Chat Completions. Suporta texto + imagem (visão) + saída estruturada num só endpoint.
- **Structured Outputs** (schema garantido) > "JSON mode" — a OpenAI recomenda sempre usar Structured Outputs quando possível. Em Responses usa-se `text.format`/`text_format`; em Chat Completions seria `response_format`.
- Passar um modelo **Pydantic** como `text_format` faz o SDK gerar o JSON Schema, validar a resposta e devolver objeto tipado — o mesmo modelo vira sua validação determinística de campos. Encaixe perfeito com o requisito "saída estruturada por template + validações (CNPJ, data, valor)".
- **Visão:** mandar a página renderizada (PyMuPDF → PNG/JPEG) como `input_image`. Para PDFs nativos também há `input_file`, mas para escaneados o caminho imagem é o mais previsível.
- **Cobrança por tokens:** ler `response.usage` (input/output tokens) em cada chamada e persistir por chave/documento. É a base da medição de consumo exigida.
- **Modelo:** usar família `gpt-4o`/sucessor com visão e Structured Outputs (confirmar o modelo vigente na conta no momento da implementação — modelos giram rápido).

### 5. Fila/worker — depende do modo de distribuição

- **Modo servidor / Docker Compose:** `arq` + Redis. asyncio-nativo (combina com OpenAI async), retry/backoff embutidos. (arq está em "maintenance mode" mas estável; dramatiq 2.1 é a alternativa mais ativa se preferir, porém é sync-first.)
- **Modo "máquina do cliente" sem Redis:** fila persistida na **própria tabela SQLite** consumida por um worker `asyncio` dentro do mesmo processo (ou processo irmão) — sem broker externo. Implementação modesta: tabela `jobs(status, attempts, next_retry_at, ...)`, polling com backoff, respeitando rate limit da OpenAI. Mantém o "double-click and run".

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

## Stack Patterns by Variant

- SQLite (WAL) + fila in-process SQLite (sem Redis)
- Futuro: Tauri v2 + backend FastAPI empacotado com PyInstaller como **sidecar**; frontend Vite buildado embutido
- Porque: zero dependências de infraestrutura externa
- Docker Compose: container app (FastAPI+Uvicorn) + container Redis (+ Postgres opcional)
- arq como worker em container separado
- Porque: escala, múltiplos revisores humanos, robustez de escrita
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

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

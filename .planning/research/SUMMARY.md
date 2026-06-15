# Project Research Summary

**Project:** Processador de Documentos
**Domain:** Intelligent Document Processing (IDP) — documentos fiscais brasileiros (NF-e, boletos), single-tenant, on-premise
**Researched:** 2026-06-15
**Confidence:** HIGH (stack e arquitetura verificados em fontes oficiais; parsing determinístico BR HIGH; fila/worker MEDIUM)

## Executive Summary

Este produto é um IDP (Intelligent Document Processing) single-tenant voltado ao mercado brasileiro, com diferencial na combinação de parsing determinístico fiscal (NF-e e boleto a custo zero) com extração por IA da OpenAI somente onde necessário, e automações de arquivo reversíveis como entrega principal. A abordagem prescrita pela pesquisa converge em uma única direção: um monólito modular FastAPI com worker assíncrono e banco SQLite, onde cada documento percorre uma máquina de estados explícita do recebimento até a automação — nunca processamento inline na rota HTTP e nunca operação de arquivo sem log de reversão. O template de documento é um schema de campos (form editor), não um editor de zonas visuais, o que elimina uma classe inteira de complexidade de UI e torna o produto mais robusto a variações de layout entre emissores.

A recomendação é construir em camadas que entreguem valor testável e desbloqueiem a camada seguinte: fundação de estado e storage primeiro, depois extração determinística (zero custo de IA, validável sem chave OpenAI), depois extração por IA com medição de tokens, depois templates e classificação, depois o loop de revisão humana, e por último a automação de rename/move com dry-run e undo. A fase de fila/worker async deve vir antes de qualquer extração pesada — introduzi-la depois exige reescrever a orquestração inteira.

Os riscos mais críticos são todos operacionais, não técnicos: processamento de arquivo parcialmente escrito (hash errado, extração de lixo), move/rename sem proteção de colisão (perda irrecuperável de arquivo do cliente), e deduplicação furada combinada com fila sem idempotência (cobrança dupla na conta OpenAI do cliente). Esses três itens devem ser prevenidos na primeira versão de cada subsistema, não adicionados depois. Confiança no produto — revisão humana, dry-run, quarentena, log/undo — é requisito de v1, não polimento.

## Key Findings

### Recommended Stack

O backend é Python 3.12 + FastAPI 0.137 + Pydantic 2.13, servindo o build React estático em produção (single-origin, sem CORS). Para PDF: PyMuPDF 1.27 para extração de texto nativo e render de página para imagem; pikepdf 10.8 para split/repair (licença MPL-2.0, mais segura para produto vendido do que a AGPL do PyMuPDF). A OpenAI SDK 2.41 deve ser usada via Responses API (`client.responses.parse`) com Structured Outputs e modelo Pydantic como `text_format` — não JSON mode, que não garante schema. SQLite em WAL mode é o banco padrão (single-tenant + 1 writer serializado pela fila = sem contenção); Alembic é obrigatório desde o dia 1 para migrações seguras entre versões do produto instalado. A fila tem duas variantes: `arq` 0.28 + Redis para modo servidor; fila in-process em SQLite para "máquina do cliente sem dependências". Frontend: React 19 + Vite 8 + TypeScript + TanStack Query 5.

**Alerta de licença:** PyMuPDF é AGPL-3.0; para produto vendido, confirmar necessidade de licença comercial da Artifex ou substituir render por `pypdfium2` (Apache/BSD).

**Core technologies:**
- FastAPI 0.137 + Uvicorn: framework async, validação Pydantic, mesmo binário local ou servidor
- Pydantic 2.13: modelos de extração + contrato do Structured Output da IA — uma camada serve os dois
- PyMuPDF 1.27: extração de texto nativo + render página para imagem (verificar licença AGPL)
- pikepdf 10.8: split de PDF por N páginas e reparo de PDFs malformados (MPL-2.0)
- OpenAI SDK 2.41 via Responses API + Structured Outputs: extração estruturada com garantia de schema e medição de tokens
- nfelib 2.5 (MIT): parsing completo de XML de NF-e sem IA
- Parser determinístico próprio (boleto + chave NF-e): Módulo 10/11, sem dependência externa madura em Python
- watchfiles 1.2: hot folder watcher (Rust/notify, async-friendly)
- SQLite WAL + SQLAlchemy 2.0 + Alembic 1.18: banco padrão + ORM abstractable + migrações entre versões
- arq 0.28 / fila SQLite in-process: worker async com retry (Redis em servidor; in-process em cliente)
- React 19 + Vite 8 + TanStack Query 5: SPA servida pelo FastAPI, polling de status

### Expected Features

**Must have (table stakes):**
- Ingestão multi-formato (PDF + imagens) via hot folder, upload manual e CLI batch
- Extração híbrida: texto nativo local -> parsing determinístico fiscal -> IA somente no restante
- Parsing determinístico de NF-e (XML/chave 44 dígitos) e boleto (linha digitável/código de barras) com validação de DV
- Validação de campos (CNPJ, data, valor, checksum de chave/linha digitável)
- Construtor de templates schema-first (declarar campos e tipos, sem editor de zonas visuais)
- Sub-templates por emissor keyed no CNPJ
- Classificação automática (determinística primeiro, IA como fallback, "sem template" -> quarentena)
- Score de confiança + threshold configurável
- Fila de revisão humana com visualizador lado-a-lado + campos editáveis
- Rename + move com string de tokens dos campos extraídos
- Dry-run / preview obrigatório antes de qualquer operação de arquivo
- Log de auditoria + undo (write-ahead, reversível por documento e por lote)
- Quarentena para documentos sem template ou com falha
- Dedup por hash SHA-256 (também como chave de idempotência da fila)
- Fila assíncrona com retry e backoff para lotes e rate limit da OpenAI
- Medição de tokens/chamadas por documento com idempotência (sem cobrança dupla)

**Should have (differentiators):**
- Parsing determinístico BR antes da IA: moat competitivo vs. IDP genéricos estrangeiros — custo zero, precisão 100% nos documentos mais comuns
- Roteamento de custo explícito (determinístico -> texto nativo -> IA): menor custo de token do cliente como argumento de venda
- Single-tenant / roda na máquina do cliente: postura LGPD-friendly vs. SaaS cloud
- Hot folder "set and forget": automação transparente
- Divisão configurável de páginas por documento
- Transparência do que foi enviado à OpenAI (registro por documento: processado local vs. enviado à IA)
- Correções da revisão humana alimentando hints por sub-template (LLM few-shot barato vs. retraining)

**Defer (v2+):**
- Automações além de rename/move (e-mail, WhatsApp, API/ERP)
- Empacotamento desktop (Tauri v2 + sidecar PyInstaller)
- Provedores de IA alternativos / modelos on-prem
- Parsers determinísticos para outros tipos fiscais (NFS-e, etc.)
- Thresholds de confiança por template (em vez de só global)
- Export estruturado para CSV/Excel

### Architecture Approach

A arquitetura é um monólito modular FastAPI com um worker assíncrono no mesmo host, onde o documento é uma entidade com máquina de estados explícita (RECEIVED -> DEDUPED -> SPLIT -> ROUTED -> EXTRACTED -> CLASSIFIED -> VALIDATED -> PENDING_AUTOMATION -> APPLIED, com estados laterais IN_REVIEW / QUARANTINED / FAILED). A API é uma camada fina que valida, enfileira e lê estado — não processa. Todo o processamento vive em `pipeline/stages/`, onde cada etapa é uma função pura `(state_in) -> state_out` sem conhecer HTTP nem a fila. O arquivo de entrada é imutável no CAS (content-addressable store por hash); automações operam nas saídas, nunca destroem o original. Um único módulo `integrations/openai_client.py` é o ponto de entrada para a OpenAI, centralizando captura de tokens, retry de rate limit e controle do que sai da máquina.

**Major components:**
1. API (FastAPI) — camada fina HTTP: valida, enfileira, lê estado; nunca processa
2. Worker assíncrono (arq/Redis ou fila SQLite) — executa etapas do pipeline com retry/idempotência
3. Pipeline/stages — etapas desacopladas e testáveis: ingest, split, router, extract_deterministic, extract_text, extract_ai, classify, validate, automation
4. State Store (SQLite/Postgres) — fonte única de verdade: Document, Page, Extraction, AuditLog, Usage
5. Blob Store / CAS — arquivos de entrada imutáveis endereçados por hash; base da reversibilidade
6. Automation Engine — rename/move com dry-run, write-ahead audit log, anti-colisão e undo
7. OpenAI client wrapper — único ponto de chamada à IA: structured outputs, captura de tokens, retry em 429
8. Hot folder watcher (watchfiles) — detecta novos arquivos com estabilização por quiescência antes de enfileirar

### Critical Pitfalls

1. **Arquivo parcialmente escrito no watcher** — nunca processar no primeiro evento de inotify; implementar estabilização por quiescência (size+mtime estáveis por N segundos) e calcular hash somente após estabilização. Usar staging com rename atômico para ingestão via upload/CLI.

2. **Move/rename sem proteção de colisão** — checar existência do destino antes de mover; nunca shutil.move sem decisão explícita de conflito; move cross-device = copy+fsync+verify+delete (não atômico); write-ahead audit log antes de agir; dry-run mostra colisões em vermelho. Um arquivo sobrescrito sem proteção é irrecuperável.

3. **Confiar no JSON estruturado da IA como dado correto** — Structured Outputs garante formato, não veracidade. Validar todos os campos por algoritmos determinísticos (DV de CNPJ, chave NF-e, linha digitável de boleto, faixas de data/valor). Qualquer falha -> revisão humana obrigatória antes de qualquer automação.

4. **Fila sem idempotência -> cobrança dupla e operações repetidas** — chave de job derivada do hash + etapa; máquina de estados persistida impede reexecução de etapa já completada; backoff exponencial com jitter em 429; dead-letter para falhas permanentes (nunca somem).

5. **Mandar tudo para a IA (sem roteamento determinístico-primeiro)** — custo de token desnecessário, risco LGPD. A cascata determinístico -> texto nativo -> IA não é uma otimização posterior; é a proposta de valor central. Cada documento resolvido localmente economiza dinheiro real do cliente.

## Implications for Roadmap

A arquitetura converge para uma ordem de construção clara: cada fase entrega um sistema testável e desbloqueia a seguinte. Fila/worker async deve vir antes de extração pesada. Reversibilidade (dry-run + undo + quarentena) deve ser parte da definição de pronto da fase de automação, não um extra posterior.

### Phase 1: Fundacao de Estado e Storage

**Rationale:** Tudo o mais depende disso. Os modelos de domínio, a máquina de estados, o CAS por hash e as migrações Alembic devem existir antes de qualquer feature. É a base que torna o pipeline testável etapa a etapa.
**Delivers:** Esquema de banco (Document, Page, Extraction, AuditLog, Usage), máquina de estados com transições explícitas, CAS por hash SHA-256, Alembic configurado, configuração de app (DATABASE_URL, OPENAI_API_KEY, paths).
**Addresses:** Requisito de "nunca perder dados"; base para dedup e idempotência.
**Avoids:** Anti-pattern de pipeline monolítico sem estado persistido; impossibilidade de reprocessar a partir de um ponto.

### Phase 2: Ingestao e Fila Assincrona

**Rationale:** Ingestão (upload manual primeiro, hot folder depois) + fila/worker devem ser estabelecidos juntos e antes das etapas pesadas. Introduzir async depois exige reescrever a orquestração inteira. Com etapas de pipeline ainda vazias, já é possível validar o esqueleto de retry/idempotência.
**Delivers:** Upload manual de PDF/imagem, hash + dedup, armazenamento no CAS, enfileiramento no arq/Redis (ou fila SQLite in-process), worker orquestrador com retry/backoff, polling de status na API. Hot folder com estabilização por quiescência + CLI batch.
**Addresses:** Ingestão via pasta monitorada, upload manual, lote CLI; dedup por hash; fila assíncrona com retry.
**Avoids:** Pitfall de arquivo parcialmente escrito (estabilização obrigatória no watcher); pitfall de fila sem idempotência (job key = hash + etapa).

### Phase 3: Extracao Deterministica BR

**Rationale:** Custo zero, precisão 100%, testável sem chave OpenAI. Estabelece o contrato de saída estruturada (campos tipados + score de confiança) que a extração por IA vai reutilizar. É o diferencial competitivo mais forte e deve vir antes da IA.
**Delivers:** Extração de texto nativo de PDF (PyMuPDF), parser de NF-e (nfelib para XML; algoritmo próprio para chave 44 dígitos com Módulo 11), parser de boleto (linha digitável 47/48 dígitos com Módulo 10/11 + fator de vencimento + decode de barras via pyzbar), validadores de CNPJ/DV, roteador de extração.
**Addresses:** Extração sem IA de boleto/NF-e; validação de campos BR; roteamento local-primeiro.
**Avoids:** Pitfall de parsing BR ingênuo (validar todos os DVs, preferir XML ao DANFE); pitfall de custo de tokens (não mandar para a IA o que pode ser resolvido local).

### Phase 4: Extracao por IA e Medicao de Tokens

**Rationale:** Encaixa na rota de extração reusando o contrato da Phase 3. Medição de tokens deve ser implementada junto desde o início — retrofitar depois é arriscado para a cobrança por consumo.
**Delivers:** Integração OpenAI via Responses API + Structured Outputs com modelo Pydantic como text_format, render de página PDF para imagem (PyMuPDF), extração de imagens/PDFs escaneados, captura de usage.prompt_tokens + usage.completion_tokens por chamada gravada na tabela Usage, modelo de confiança por campo/caminho de extração.
**Uses:** openai 2.41 (Responses API), PyMuPDF render, Pydantic models.
**Avoids:** Pitfall de custo descontrolado (só rota para IA o que sobrou após determinístico + texto nativo); pitfall de cobrança dupla (idempotência por hash + etapa).

### Phase 5: Templates, Sub-templates e Classificacao

**Rationale:** Depende do schema de extração existir (Phases 3 e 4). O construtor de templates é um form editor de campos, não um canvas visual — decisão arquitetural que deve ser protegida. Templates são dados no banco, não código.
**Delivers:** CRUD de templates (nome, tipo de documento, lista de campos com tipo/validação/hint) via API + UI React, sub-templates por emissor keyed no CNPJ, classificação automática (determinística primeiro, IA fallback com lista de templates disponíveis, "none" -> quarentena), threshold de confiança configurável.
**Addresses:** Construtor de templates no app; sub-templates por cliente/emissor; classificação automática.
**Avoids:** Anti-pattern de templates hardcodados como código; anti-pattern de canvas/editor zonal de coordenadas.

### Phase 6: Validacao, Revisao Humana e Quarentena

**Rationale:** Depende de extração e classificação produzirem campos e score. O gate de confiança determinístico (DV de CNPJ, chave, linha digitável) deve existir antes de qualquer automação ser ligada.
**Delivers:** Validação pós-extração com gate determinístico (CNPJ, chave NF-e, linha digitável, data, valor), roteamento para IN_REVIEW (abaixo do threshold ou falha de validação) ou QUARANTINED (sem template), fila de revisão na UI com visualizador lado-a-lado (doc + campos editáveis), aprovação/rejeição com re-validação, quarentena visível com motivo e ação de resolver.
**Addresses:** Revisão humana com baixa confiança; quarentena; threshold de confiança.
**Avoids:** Pitfall de alucinação sem gate (JSON válido != dado correto); UX pitfall de quarentena que parece sumiço.

### Phase 7: Automacao Rename/Move com Dry-run, Undo e Auditoria

**Rationale:** Última etapa do pipeline; depende de campos validados e confiáveis da Phase 6. Reversibilidade é parte da definição de pronto desta fase, não um extra posterior. Um arquivo sobrescrito sem proteção é irrecuperável.
**Delivers:** Motor de automação com linguagem de tokens de campo nos templates de nome/pasta (ex.: {cliente}_{numero_nota}_{data}.pdf), dry-run/preview com diff de pares origem->destino e sinalização de colisões, write-ahead audit log (gravar intenção ANTES de agir), execução com anti-colisão (sufixo _2 ou quarentena de conflito), undo por documento e por lote/execução, move seguro cross-device (copy+fsync+verify+delete).
**Addresses:** Renomear e mover arquivos; dry-run/preview; log de auditoria + desfazer; never lose a file.
**Avoids:** Pitfall de move destrutivo/colisão; pitfall de log gravado após a ação; anti-pattern de os.rename direto pós-IA.

### Phase 8: Operacao, Distribuicao e Documentacao

**Rationale:** Entradas adicionais (hot folder consolidado, CLI batch), relatório de uso, empacotamento e documentação — tudo reutiliza o pipeline. Migração segura entre versões (Alembic já configurado desde a Phase 1) e guias de instalação/atualização são entregáveis de primeira classe para um produto instalado pelo cliente.
**Delivers:** Hot folder estabilizado (watchfiles + quiescência), CLI batch, relatório de uso/tokens por período na UI, empacotamento Docker Compose (app + Redis), verificação de versão visível, guia de instalação, guia de atualização segura, documentação de uso com exemplos, guia de operação/troubleshooting.
**Addresses:** Todos os requisitos de distribuição, atualização e documentação.
**Avoids:** Migração insegura entre versões; perda de templates/config em update.

### Phase Ordering Rationale

- Phases 1-2 constroem o esqueleto que torna tudo testável e resiliente: estado + storage + fila async. Sem isso, extração pesada vira spaghetti.
- Phases 3-4 avançam do mais barato para o mais caro: determinístico BR (custo zero, testável sem API key) antes da IA. Isso também valida o contrato de saída estruturada antes de plugar a OpenAI.
- Phase 5 depende do contrato de extração existir; classificar contra templates que não existem é impossível.
- Phase 6 é o gate antes da automação: nenhum arquivo do cliente pode ser tocado sem ter passado por validação determinística e/ou revisão humana.
- Phase 7 é a última etapa do pipeline propositalmente: é a mais destrutiva e deve ser construída sobre garantias sólidas das fases anteriores.
- Phase 8 opera sobre o pipeline completo; hot folder e CLI são entradas adicionais, não uma camada nova.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Extracao Deterministica BR):** Parser de boleto próprio em Python não tem lib madura; deve-se portar lógica de boleto-utils (JavaScript) e cobrir com testes de boletos reais. Boleto de arrecadação/convênio (prefixo "8") é um sub-caso que precisa de fixtures reais.
- **Phase 4 (IA + Tokens):** Modelo OpenAI vigente com visão + Structured Outputs muda rapidamente; confirmar o modelo disponível na conta no momento da implementação. Otimização de payload de visão (tiles, resolução mínima legível) merece pesquisa pontual.
- **Phase 6 (Revisao Humana):** UI de visualizador lado-a-lado (doc renderizado + campos editáveis) é a feature de maior custo de frontend; pesquisar bibliotecas de PDF viewer para React (react-pdf/pdf.js) antes de estimar.
- **Phase 7 (Automacao):** Avaliar se mini-linguagem de tokens simples basta ou se Jinja2-lite é mais segura; sanitização de path traversal em valores extraídos por IA.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Fundacao):** SQLAlchemy + Alembic + SQLite WAL são bem documentados; máquina de estados em Python é trivial.
- **Phase 2 (Ingestao + Fila):** arq + Redis tem documentação oficial completa; fila SQLite in-process é polling simples de tabela.
- **Phase 5 (Templates + Classificacao):** CRUD de dados no FastAPI + schema-first template builder são padrões comuns; sem novidade técnica relevante.
- **Phase 8 (Operacao):** Docker Compose, Alembic migrations e documentação técnica são padrões conhecidos.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versões verificadas em PyPI/npm oficial; Responses API, Structured Outputs verificadas em docs oficiais OpenAI; SQLite WAL + arq validados em benchmarks recentes. Única área MEDIUM: fila in-process SQLite (padrão funcional sem lib consagrada). Alerta AGPL PyMuPDF verificado. |
| Features | MEDIUM-HIGH | Padrões IDP verificados em múltiplas fontes independentes; especificações BR (chave NF-e, linha digitável) HIGH por serem padrões determinísticos FEBRABAN/SEFAZ. Detalhes de pricing/features de competidores LOW por falta de divulgação pública. |
| Architecture | HIGH | Pipeline IDP com state machine verificado em fontes canônicas (AWS Bedrock IDP, Azure Architecture Center); padrões de fila async, CAS por hash e write-ahead log são estabelecidos. MEDIUM para reversibilidade de arquivo (princípios gerais + analogia com transactional filesystems). |
| Pitfalls | HIGH | Comportamento de inotify/watchdog verificado em issues e docs oficiais; retenção de dados OpenAI verificada em platform.openai.com; algoritmos BR (Módulo 10/11, estrutura da chave NF-e) verificados em fontes FEBRABAN/SEFAZ/TecnoSpeed. |

**Overall confidence:** HIGH

### Gaps to Address

- **Boleto parser Python:** Não há biblioteca Python madura para parsing de boleto recebido. Implementar do zero portando lógica de mrmgomes/boleto-utils (JavaScript). Cobrir com fixtures de boletos reais de múltiplos emissores, incluindo boleto de arrecadação/convênio (prefixo "8") — único jeito de validar.
- **Licença PyMuPDF (AGPL-3.0):** Produto vendido pode exigir licença comercial da Artifex. Resolver antes de iniciar a Phase 3; se optar por stack 100% permissiva, substituir por pypdfium2 (Apache/BSD) para render + pdfplumber/pdfminer.six (MIT) para texto nativo.
- **Modelo OpenAI com visão + Structured Outputs:** Modelos giram rápido; confirmar o modelo vigente e os limites de contexto/visão no momento da Phase 4. Testar custo real por tipo de documento com a conta do cliente antes de estabelecer preços de consumo.
- **Modelo de confiança para extração via IA:** A OpenAI não expõe score de confiança por campo para extração de visão. O sistema precisa de um modelo próprio baseado em validação determinística pós-extração (campo passou/falhou DV/formato/cross-check) em vez de auto-reporte da IA.
- **Variante de fila sem Redis:** Fila in-process baseada em SQLite não tem biblioteca consagrada. Avaliar se polling de tabela próprio é o caminho mais simples para o caso "double-click and run".
- **UI de PDF viewer (Phase 6):** react-pdf (pdf.js) deve ser avaliado antes da estimativa de esforço da fila de revisão humana.

## Sources

### Primary (HIGH confidence)

- OpenAI platform docs (platform.openai.com) — Responses API, Structured Outputs, data retention (30 dias), Zero Data Retention via enterprise
- PyPI JSON API — versões: fastapi 0.137.1, pydantic 2.13.4, openai 2.41.1, pymupdf 1.27.2.3, pikepdf 10.8.0, alembic 1.18.4, watchfiles 1.2.0, arq 0.28.0, nfelib 2.5.2
- npm registry — react 19.2.7, vite 8.0.16, @tanstack/react-query 5.101.0
- AWS Machine Learning Blog — Architecting an IDP pipeline with generative AI (fases canônicas do pipeline IDP)
- AWS Machine Learning Blog — Scalable IDP using Amazon Bedrock (state machine, quarentena, callback de revisão humana)
- Azure Architecture Center — Extract and Map Information from Unstructured Content (confidence-threshold routing, HITL)
- TecnoSpeed blog — composição da chave de acesso NF-e 44 dígitos / DV módulo 11
- FocusNFE blog — estrutura da chave de acesso NF-e (UF/AAMM/CNPJ/modelo/série/número/DV)
- SEFAZ / nfelib — XSDs oficiais da NF-e; nfelib bindings (github.com/akretion/nfelib)

### Secondary (MEDIUM confidence)

- Docsumo, Klippa DocHorizon, Rossum, Unstract, Parseur — padrões de HITL, schema-first template builder, confidence thresholds
- GitHub: mrmgomes/boleto-utils — parsing determinístico de boleto (JavaScript, confirmado sem equivalente Python)
- Efí (sejaefi.com.br) — estrutura da linha digitável 47 dígitos / DV módulo 10 e 11 / fator de vencimento
- arXiv 2605.18818 — separação de etapas em pipeline IDP em produção
- FastAPI Background Tasks benchmarks (Medium/2026) — arq recomendado para I/O-bound LLM em FastAPI single-host
- Alan Engineering (Medium) — validar pós-extração e rotear para revisão com erro estruturado, não só "baixa confiança"
- Tauri v2 docs — sidecar PyInstaller (padrão documentado, poucos casos em produção com FastAPI)

### Tertiary (LOW confidence)

- Detalhes de pricing e feature sets de Klippa/Docsumo/Rossum — não publicados; análise baseada em páginas de marketing
- Implementação da fila SQLite in-process — padrão funcional inferido a partir de princípios de polling de tabela; sem referência de implementação canônica

---
*Research completed: 2026-06-15*
*Ready for roadmap: yes*

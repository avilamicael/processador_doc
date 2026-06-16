# Processador de Documentos

## What This Is

Aplicação web (FastAPI + React, web-first) vendida como produto para empresas que recebem muitos documentos de **tipos variados** (cada cliente tem seus próprios tipos — notas fiscais e boletos são apenas exemplos). O cliente roda na própria máquina ou servidor (majoritariamente **Windows**) e configura, pelo app, **templates** por tipo de documento e **sub-templates por cliente/emissor**, com os campos a extrair e as automações desejadas. O sistema ingere os documentos, separa páginas quando necessário, lê os dados (texto nativo de PDF localmente; imagens e PDFs escaneados via IA da OpenAI), classifica cada documento contra os templates e executa automações — inicialmente **renomear e mover** arquivos com base nos dados extraídos. O motor é **genérico** (qualquer tipo de documento via template + IA); parsing determinístico de tipos conhecidos é otimização, não o foco.

## Core Value

Transformar uma pilha de documentos heterogêneos (PDFs e imagens) em arquivos **classificados, nomeados e organizados corretamente de forma automática e confiável** — sem o usuário perder arquivos nem confiar cegamente na IA.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

**Ingestão & Processamento — validados na Fase 2 (2026-06-16)**
- [x] Ingerir documentos via **pasta(s) monitorada(s)** processada(s) automaticamente após o arquivo estabilizar — configuráveis pela interface (ING-02)
- [x] Aceitar **PDF e imagens** (allowlist de extensão) (ING-04)
- [x] **Separar páginas** por quantidade configurável por pasta — cada bloco vira um documento independente (ING-05)
- [x] **Deduplicar por hash** — não reprocessa nem cobra o mesmo arquivo duas vezes, idempotente mesmo após retry/crash (ING-06, PROC-03)
- [x] **Fila assíncrona com retry/backoff** (worker in-process SQLite, claim atômico) (PROC-02)

**Leitura/Extração & Medição — validados na Fase 3 (2026-06-16)**
- [x] Extrair **texto nativo de PDF localmente** (sem custo de IA quando o PDF tem texto), com heurística texto-vs-visão (EXT-01)
- [x] Extrair dados de **imagens e PDFs escaneados via IA da OpenAI** (Responses API + visão) (EXT-01)
- [x] **Extração genérica via IA para qualquer tipo de documento** — schema `ExtractionResult` strict-safe (list-of-pairs), Structured Outputs; *binding por template fica na Fase 4* (EXT-02)
- [x] **Medição de uso por tokens** por documento (`Usage(step="extract")` no mesmo commit atômico da extração — não cobra duas vezes) (USE-02)
- _Roteamento determinístico de tipos conhecidos (boleto/NF-e) e revisão por confiança permanecem nas Fases 7 e 5._

### Active

<!-- Current scope. Building toward these (v1). Hypotheses until shipped. -->

**Ingestão**
- [ ] Ingerir documentos via **pasta(s) monitorada(s)** (hot folder) processada(s) automaticamente — **único caminho de ingestão no v1**; configuráveis pela interface
- [ ] Aceitar **PDF e imagens** como formatos de entrada
- [ ] **Separar páginas** por quantidade configurável **por pasta** (cada bloco vira um documento independente)
- [ ] **Deduplicar por hash** para não reprocessar/cobrar o mesmo arquivo duas vezes
- _(v2)_ ~~Upload manual na interface~~ e ~~lote/linha de comando~~ — removidos do v1 em 2026-06-15 (ingestão folder-only)

**Leitura/Extração**
- [x] Extrair **texto nativo de PDF localmente** (sem custo de IA quando o PDF tem texto) — _Fase 3_
- [x] Extrair dados de **imagens e PDFs escaneados via IA da OpenAI** (OCR + contexto) — _Fase 3_
- [x] **Extração genérica via IA para qualquer tipo de documento** (caminho principal; _binding por template na Fase 4_) — _Fase 3_
- [~] Roteamento de extração: determinístico (quando aplicável) → texto nativo local → IA — _seam pronto na Fase 3; ramo determinístico na Fase 7_
- [~] **Saída estruturada (JSON Schema)** da IA — _schema genérico pronto na Fase 3; conforme template + validações configuráveis na Fase 4/5_
- [ ] **(Otimização) Parsing determinístico de tipos conhecidos** (ex.: boleto via linha digitável, NF-e via chave/XML) para reduzir custo de IA quando o cliente tiver esses tipos

**Templates & Classificação**
- [ ] **Construtor de templates no app**: o cliente cria templates por tipo de documento (NF, boleto, etc.)
- [ ] **Sub-templates por cliente/emissor** com regras e automações próprias
- [ ] Definir, por template, os **campos a extrair**
- [ ] **Classificar** automaticamente cada documento contra os templates/sub-templates (usando IA para contexto)

**Automações (v1)**
- [ ] **Renomear** arquivos usando os campos extraídos (ex.: `{cliente}_{numero_nota}_{data}.pdf`)
- [ ] **Mover** arquivos para pastas com base nos campos (ex.: `NotasFiscais/{cliente}/{ano-mes}/`)

**Confiança & Controle**
- [ ] **Revisão humana** quando a IA tem baixa confiança: conferir/corrigir campos antes de aplicar automações
- [ ] **Dry-run / pré-visualização** das automações antes de aplicar de verdade
- [ ] **Quarentena**: documentos sem template ou com falha vão para revisão manual (nunca somem)
- [ ] **Log de auditoria + desfazer** das ações aplicadas a cada documento

**Processamento**
- [ ] **Fila assíncrona com retry** (worker em background) para lotes grandes e rate limit/erros da OpenAI

**IA & Cobrança**
- [ ] **Chave OpenAI por cliente** (provisionada pelo fornecedor); o cliente é responsável pelo consumo
- [x] **Medição de uso por tokens / chamadas de API** para apoiar a cobrança por consumo — _Fase 3_

**Distribuição & Atualização**
- [ ] **Versionamento de releases** do produto (instalável por cliente, com versão visível)
- [ ] **Mecanismo de atualização**: o fornecedor publica novas versões e os clientes atualizam o sistema
- [ ] **Migração segura entre versões**: atualizar não pode quebrar nem perder templates, configurações e dados do cliente

**Documentação (entregável de primeira classe)**
- [ ] **Guia de instalação** (rodar em máquina local ou servidor, configurar a chave OpenAI)
- [ ] **Guia de atualização** (como aplicar updates publicados pelo fornecedor sem perder dados)
- [ ] **Documentação de uso / experiência do usuário** (criar templates, revisar, aplicar automações) com **exemplos de "como fazer"**
- [ ] **Guia de operação/administração** (pasta monitorada, backup dos dados, troubleshooting)

### Out of Scope

<!-- Explicit boundaries with reasoning. -->

- **Multiusuário / contas / login / SaaS multi-tenant** — produto é single-tenant, cada cliente roda a própria instância; isolamento vem por instância, não por tenant
- **Proxy/gateway central de IA** — descartado: cada instância usa a própria chave OpenAI provisionada; sem componente cloud obrigatório no v1
- **App desktop (Electron/Tauri) no v1** — web-first; empacotamento desktop fica como porta aberta para o futuro sem reescrever o app
- **Automações além de renomear/mover no v1** — chamar API, enviar por e-mail/WhatsApp ficam para depois
- **Billing/faturamento embutido no app** — cobrança é feita por fora, com base no uso medido por chave

## Context

- **Modelo de negócio:** app único vendido a clientes; cada cliente instala e gerencia no próprio computador ou servidor (single-tenant). Cobrança baseada no consumo de IA (tokens/uso da API), com uma chave OpenAI por cliente provisionada pelo fornecedor — se o cliente usa mais, paga mais.
- **Domínio:** documentos fiscais brasileiros (NF-e, boletos). Boletos têm linha digitável/código de barras e NF-e tem chave de acesso de 44 dígitos / XML — parsing determinístico evita custo de IA e é 100% preciso onde aplicável.
- **Sensibilidade dos dados:** documentos fiscais são dados sensíveis (LGPD). O que é enviado à OpenAI deve ser controlável/explicável — marcado como objetivo de evolução.
- **Stack pretendida:** Python no backend (FastAPI), React no frontend; ecossistema Python maduro para manipulação de PDF/imagem e integração OpenAI.
- **Decisão de provedor de IA:** OpenAI (ChatGPT) — escolha explícita do usuário para OCR e processamento de contexto.

## Constraints

- **Plataforma primária**: **Windows** — a maioria das instalações roda em Windows; empacotamento, watcher de pasta e operações de arquivo (NTFS, atomicidade, cross-device) devem ser testados e confiáveis nele primeiro
- **Tech stack**: Backend Python/FastAPI + frontend React (web-first) — alinhado à familiaridade com Python e ao requisito de rodar local ou em servidor
- **Distribuição**: O mesmo código deve rodar em `localhost` (máquina do cliente Windows) **ou** em servidor — evita travar em modelo desktop; empacotamento desktop (preferência Tauri sobre Electron) fica como evolução. Preferir **fila in-process (SQLite)** ao invés de Redis no modo padrão, para não exigir broker externo no Windows
- **Domínio genérico**: O motor não pode ser acoplado a tipos fiscais específicos — qualquer tipo de documento deve ser suportado via template + IA; parsing determinístico de tipos conhecidos é um módulo opcional/plugável
- **Dependência externa**: Parte de IA exige internet e chave OpenAI válida por instância
- **Provedor de IA**: OpenAI (ChatGPT) — definido pelo usuário
- **Segurança/LGPD**: Documentos fiscais são sensíveis; minimizar e tornar explícito o que sai da máquina para a OpenAI
- **Integridade de arquivos**: Operações que movem/renomeiam arquivos do cliente devem ser reversíveis e nunca podem causar perda (quarentena + dry-run + log/desfazer)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Web-first (FastAPI + React) em vez de Electron | Mesmo código serve "máquina do cliente" e "servidor"; Electron travaria o caso servidor | — Pending |
| Empacotamento desktop adiado (preferir Tauri se vier) | Mais leve que Electron; só se houver demanda por "instala e abre" | — Pending |
| Provedor de IA: OpenAI/ChatGPT | Escolha explícita do usuário | — Pending |
| OCR híbrido: texto nativo local → IA só no que sobra | Reduz custo de tokens e mantém precisão | — Pending |
| Motor genérico para qualquer tipo de documento (não acoplado a fiscal) | Clientes têm tipos variados; NF-e/boleto são exemplos | — Pending |
| Parsing determinístico de tipos conhecidos como módulo opcional/plugável | Linha digitável/chave são exatos e custo zero, mas não podem ser o eixo do produto | — Pending |
| Windows como plataforma primária; fila in-process (SQLite) em vez de Redis no modo padrão | Maioria das instalações é Windows; evita broker externo difícil de operar lá | — Pending |
| Chave OpenAI por cliente (sem proxy central) | Cliente arca com o próprio consumo; elimina componente cloud obrigatório | — Pending |
| Medição de uso por tokens, não por "documento" | Sistema também processa contexto, não só extração; tokens refletem o custo real | — Pending |
| Single-tenant (sem multiusuário/SaaS no v1) | Produto vendido como app único instalado por cliente | — Pending |
| Confiança como requisito de v1 (revisão, dry-run, quarentena, log/desfazer) | Documentos fiscais + mover arquivos do cliente exigem que nada se perca e nada seja aplicado às cegas | — Pending |
| Documentação tratada como entregável de v1 (instalação, atualização, uso/exemplos, operação) | Produto vendido e instalado por cliente exige docs claras de instalar/usar/atualizar | — Pending |
| Atualizações publicadas pelo fornecedor com migração segura de dados | Cliente roda a própria instância; updates não podem quebrar templates/config/dados | — Pending |
| Ingestão folder-only no v1 (sem upload manual nem CLI) | Usuário trabalha por pastas; cada pasta tem sua regra de separação; upload/CLI viram v2 | — Pending (Phase 2 discuss, 2026-06-15) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-16 — Phase 3 complete: motor de extração genérica via IA (Responses API + Structured Outputs), texto nativo local e medição de tokens por documento (EXT-01/02, USE-02 validados; CR-01 aceito p/ v1). Próxima: Phase 4 (templates, sub-templates e classificação).*

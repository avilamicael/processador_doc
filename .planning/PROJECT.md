# Processador de Documentos

## What This Is

Aplicação web (FastAPI + React, web-first) vendida como produto para empresas que recebem muitos documentos — notas fiscais, boletos e similares. O cliente roda na própria máquina ou servidor e configura, pelo app, **templates** por tipo de documento e **sub-templates por cliente/emissor**, com os campos a extrair e as automações desejadas. O sistema ingere os documentos, separa páginas quando necessário, lê os dados (texto nativo de PDF localmente; imagens e PDFs escaneados via IA da OpenAI), classifica cada documento contra os templates e executa automações — inicialmente **renomear e mover** arquivos com base nos dados extraídos.

## Core Value

Transformar uma pilha de documentos heterogêneos (PDFs e imagens) em arquivos **classificados, nomeados e organizados corretamente de forma automática e confiável** — sem o usuário perder arquivos nem confiar cegamente na IA.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these (v1). Hypotheses until shipped. -->

**Ingestão**
- [ ] Ingerir documentos via **pasta monitorada** (hot folder) processada automaticamente
- [ ] Ingerir documentos via **upload manual** na interface
- [ ] Ingerir documentos via **lote/linha de comando** apontando para uma pasta
- [ ] Aceitar **PDF e imagens** como formatos de entrada
- [ ] **Separar páginas** por quantidade configurável pelo usuário quando o documento tem mais de uma página
- [ ] **Deduplicar por hash** para não reprocessar/cobrar o mesmo arquivo duas vezes

**Leitura/Extração**
- [ ] Extrair **texto nativo de PDF localmente** (sem custo de IA quando o PDF tem texto)
- [ ] Extrair dados de **imagens e PDFs escaneados via IA da OpenAI** (OCR + contexto)
- [ ] Ler **boleto e NF-e sem IA** quando possível: parsing determinístico de linha digitável/código de barras e chave de acesso/XML de NF-e
- [ ] Roteamento de extração: local primeiro, IA só onde necessário
- [ ] **Saída estruturada (JSON Schema)** da IA conforme o template + validações de campo (CNPJ, data, valor)

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
- [ ] **Medição de uso por tokens / chamadas de API** para apoiar a cobrança por consumo

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

- **Tech stack**: Backend Python/FastAPI + frontend React (web-first) — alinhado à familiaridade com Python e ao requisito de rodar local ou em servidor
- **Distribuição**: O mesmo código deve rodar em `localhost` (máquina do cliente) **ou** em servidor — evita travar em modelo desktop; empacotamento desktop (preferência Tauri sobre Electron) fica como evolução
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
| Parsing determinístico de boleto/NF-e antes da IA | Linha digitável/código de barras e chave/XML são exatos e custo zero | — Pending |
| Chave OpenAI por cliente (sem proxy central) | Cliente arca com o próprio consumo; elimina componente cloud obrigatório | — Pending |
| Medição de uso por tokens, não por "documento" | Sistema também processa contexto, não só extração; tokens refletem o custo real | — Pending |
| Single-tenant (sem multiusuário/SaaS no v1) | Produto vendido como app único instalado por cliente | — Pending |
| Confiança como requisito de v1 (revisão, dry-run, quarentena, log/desfazer) | Documentos fiscais + mover arquivos do cliente exigem que nada se perca e nada seja aplicado às cegas | — Pending |

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
*Last updated: 2026-06-15 after initialization*

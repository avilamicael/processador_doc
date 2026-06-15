# Roadmap: Processador de Documentos

## Overview

O produto transforma pilhas de documentos heterogêneos (PDFs e imagens, de tipos variados) em arquivos classificados, nomeados e organizados de forma automática e confiável, single-tenant, rodando primariamente em Windows. A jornada começa pela fundação que torna tudo seguro e testável — máquina de estados persistida, armazenamento imutável por hash (CAS) e migrações desde o dia 1 — sobre a qual se monta a ingestão multi-entrada com fila assíncrona idempotente in-process. Em seguida vem o núcleo do motor: extração **genérica via IA** dirigida pelo template, com medição de tokens para a cobrança por consumo. Sobre esse contrato de extração constroem-se os templates/sub-templates e a classificação, depois o gate de confiança com revisão humana e quarentena, e só então as automações de arquivo (renomear/mover) com dry-run, log de auditoria write-ahead e undo. O parsing determinístico de tipos conhecidos entra depois, como módulo opcional/plugável de otimização de custo (não como eixo do produto). A jornada fecha com distribuição, atualização segura entre versões e a documentação de primeira classe (instalação, atualização, uso e operação).

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Fundação de Estado e Storage** - Máquina de estados persistida, CAS por hash, migrações Alembic e base Windows single-tenant (completed 2026-06-15)
- [ ] **Phase 2: Ingestão e Fila Assíncrona** - Upload/hot folder/CLI, dedup por hash e fila in-process idempotente com retry
- [ ] **Phase 3: Extração Genérica via IA e Medição de Tokens** - Núcleo do motor: extração por IA dirigida pelo template (qualquer tipo) + texto nativo + medição de uso
- [ ] **Phase 4: Templates, Sub-templates e Classificação** - Construtor schema-first de templates e classificação automática contra eles
- [ ] **Phase 5: Confiança, Revisão Humana e Quarentena** - Score de confiança determinístico, limiar, fila de revisão lado-a-lado e quarentena visível
- [ ] **Phase 6: Automações de Arquivo (Renomear/Mover)** - Renomear/mover por tokens com dry-run, audit log write-ahead, anti-colisão e undo
- [ ] **Phase 7: Módulo Determinístico Opcional e Roteamento de Custo** - Parsing plugável de tipos conhecidos (boleto/NF-e) e cascata determinístico→nativo→IA
- [ ] **Phase 8: Distribuição, Atualização e Documentação** - Releases versionadas, update com migração segura e guias de instalação/atualização/uso/operação

## Phase Details

### Phase 1: Fundação de Estado e Storage

**Goal**: Existe uma fundação que garante que nenhum dado se perde — modelos de domínio, máquina de estados explícita, armazenamento imutável por hash e migrações seguras — rodando confiavelmente em Windows.
**Depends on**: Nothing (first phase)
**Requirements**: PROC-01, DIST-01, DIST-02, USE-01
**Success Criteria** (what must be TRUE):

  1. Cada documento tem um estado persistido e só transita por transições explícitas válidas (transição inválida falha, não corrompe dado)
  2. Um arquivo ingerido é armazenado de forma imutável endereçado por hash (CAS) e pode ser recuperado mesmo após qualquer automação posterior
  3. O sistema sobe e opera em Windows no modo padrão sem broker externo e sem dependências de infraestrutura adicionais
  4. A chave OpenAI por instância é configurável e lida da configuração da aplicação (sem proxy central)
  5. O schema do banco evolui via migração versionada (Alembic) sem recriar o banco

**Plans**: 4 plans
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Scaffold backend + config (data dir %ProgramData%, chave OpenAI) + engine SQLite WAL atrás de interface

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Modelos de domínio (Document/Page/AuditLog/Usage) + Alembic desde o dia 1 (migração 0001)
- [x] 01-03-PLAN.md — CAS imutável por hash SHA-256 dentro da pasta de dados (copia o original, recuperável)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-04-PLAN.md — Máquina de estados explícita (transições válidas; inválida falha sem corromper) + marcador interno de etapa

### Phase 2: Ingestão e Fila Assíncrona

**Goal**: O usuário consegue colocar documentos no sistema por três caminhos (upload, pasta monitorada, lote CLI) e cada documento entra numa fila assíncrona idempotente que nunca reprocessa nem cobra duas vezes o mesmo arquivo.
**Depends on**: Phase 1
**Requirements**: ING-01, ING-02, ING-03, ING-04, ING-05, ING-06, PROC-02, PROC-03
**Success Criteria** (what must be TRUE):

  1. O usuário consegue enviar PDFs e imagens (JPG/PNG) por upload manual na interface e vê o documento entrar na fila
  2. Arquivos colocados na pasta monitorada são processados automaticamente apenas após estarem estáveis (arquivo parcialmente escrito não é processado)
  3. O usuário consegue processar uma pasta inteira em lote pela linha de comando
  4. Um documento multi-página é separado em blocos pela quantidade de páginas configurada pelo usuário
  5. Enviar o mesmo arquivo duas vezes é detectado por hash e não gera reprocessamento nem cobrança dupla, mesmo após retry/crash da fila

**Plans**: TBD
**UI hint**: yes

### Phase 3: Extração Genérica via IA e Medição de Tokens

**Goal**: O sistema extrai, para qualquer tipo de documento, os campos definidos no template usando a IA da OpenAI (caminho principal), aproveitando texto nativo local quando disponível, e mede o consumo de tokens por documento para a cobrança.
**Depends on**: Phase 2
**Requirements**: EXT-01, EXT-02, EXT-04
**Success Criteria** (what must be TRUE):

  1. O sistema extrai os campos pedidos de um documento de qualquer tipo (incluindo imagens e PDFs escaneados) via IA dirigida pela definição de campos do template
  2. A IA retorna os dados em formato estruturado conforme um JSON Schema derivado do template, e validações de campo configuráveis são aplicadas ao resultado
  3. Quando o PDF já tem texto nativo, o sistema extrai esse texto localmente sem custo de IA
  4. Cada chamada à IA registra os tokens consumidos (prompt + completion) ligados ao documento, disponíveis para apoiar a cobrança por consumo

**Plans**: TBD

### Phase 4: Templates, Sub-templates e Classificação

**Goal**: O usuário consegue criar, no app, templates schema-first por tipo de documento e sub-templates por cliente/emissor, e o sistema classifica automaticamente cada documento contra eles — mandando para quarentena o que não casa.
**Depends on**: Phase 3
**Requirements**: TPL-01, TPL-02, TPL-03, TPL-04
**Success Criteria** (what must be TRUE):

  1. O usuário cria um template declarando campos (nome, tipo, validação, dica) por um editor schema-first, sem desenhar zonas visuais
  2. O usuário cria sub-templates por cliente/emissor com campos e automações próprias
  3. Cada documento é classificado automaticamente contra os templates disponíveis (usando IA para contexto)
  4. Um documento que não casa com nenhum template vai para quarentena e nunca some

**Plans**: TBD
**UI hint**: yes

### Phase 5: Confiança, Revisão Humana e Quarentena

**Goal**: O usuário nunca confia cegamente na IA — documentos com baixa confiança ou que falham validação param numa fila de revisão com o documento ao lado dos campos editáveis, e a quarentena é visível e resolúvel.
**Depends on**: Phase 4
**Requirements**: REV-01, REV-02, REV-03, REV-04, REV-05
**Success Criteria** (what must be TRUE):

  1. O sistema calcula um indicador de confiança por documento baseado em validação determinística pós-extração (não apenas no auto-relato da IA)
  2. O usuário define um limiar de confiança que decide o que vai para revisão manual
  3. Documentos abaixo do limiar ou que falham validação aparecem numa fila de revisão com visualizador do documento lado-a-lado com campos editáveis
  4. O usuário consegue aprovar/corrigir os campos antes de qualquer automação ser aplicada
  5. A quarentena é visível, mostra o motivo de cada documento e permite resolver/reprocessar

**Plans**: TBD
**UI hint**: yes

### Phase 6: Automações de Arquivo (Renomear/Mover)

**Goal**: O sistema renomeia e move arquivos do cliente com base nos campos extraídos de forma reversível e segura — dry-run obrigatório, log de auditoria antes de agir, proteção contra colisão e undo — de modo que nenhum arquivo jamais se perde.
**Depends on**: Phase 5
**Requirements**: AUT-01, AUT-02, AUT-03, AUT-04, AUT-05, AUT-06
**Success Criteria** (what must be TRUE):

  1. O usuário define padrões de renomeação e de pasta de destino usando os campos extraídos (ex.: `{cliente}_{numero}_{data}.pdf`, `Documentos/{cliente}/{ano-mes}/`)
  2. Antes de aplicar, o sistema mostra um dry-run/preview com pares origem→destino e colisões sinalizadas
  3. O sistema registra a intenção em log de auditoria ANTES de agir e nunca sobrescreve um destino existente silenciosamente
  4. O usuário consegue desfazer operações por documento e por lote/execução
  5. Mover entre discos diferentes é seguro (copia, verifica e só então remove a origem)

**Plans**: TBD
**UI hint**: yes

### Phase 7: Módulo Determinístico Opcional e Roteamento de Custo

**Goal**: Para clientes que recebem tipos conhecidos (boleto, NF-e), um módulo opcional/plugável extrai esses dados sem IA, e o roteador passa a escolher a rota mais barata (determinístico → texto nativo → IA), reduzindo o custo de tokens do cliente.
**Depends on**: Phase 6
**Requirements**: EXT-03, EXT-05
**Success Criteria** (what must be TRUE):

  1. Com o módulo habilitado, boletos são lidos pela linha digitável/código de barras e NF-e pela chave de 44 dígitos/XML, sem chamar a IA, com validação de dígito verificador
  2. O roteador resolve cada documento na ordem determinístico (quando aplicável) → texto nativo local → IA, mandando à IA só o que não foi resolvido localmente
  3. Com o módulo desabilitado, o motor continua funcionando integralmente pela extração genérica via IA (o determinístico é otimização, não dependência)
  4. Documentos resolvidos localmente não geram consumo de tokens (refletido na medição de uso)

**Plans**: TBD

### Phase 8: Distribuição, Atualização e Documentação

**Goal**: O fornecedor publica versões do produto e o cliente consegue atualizar sua instância sem perder templates, configurações ou dados, com documentação clara para instalar, atualizar, usar e operar.
**Depends on**: Phase 7
**Requirements**: DIST-03, DIST-04, DIST-05, DOC-01, DOC-02, DOC-03, DOC-04
**Success Criteria** (what must be TRUE):

  1. O produto exibe uma versão visível e o fornecedor consegue publicar releases versionadas
  2. O cliente consegue atualizar a instância para uma nova versão publicada pelo fornecedor
  3. A atualização migra dados com segurança (Alembic) preservando templates, configurações e dados do cliente
  4. Existe guia de instalação (Windows local ou servidor, configurar chave OpenAI) e guia de atualização sem perda de dados
  5. Existe documentação de uso com exemplos de "como fazer" (criar templates, revisar, aplicar automações) e guia de operação/administração (pasta monitorada, backup, troubleshooting)

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Fundação de Estado e Storage | 4/4 | Complete   | 2026-06-15 |
| 2. Ingestão e Fila Assíncrona | 0/TBD | Not started | - |
| 3. Extração Genérica via IA e Medição de Tokens | 0/TBD | Not started | - |
| 4. Templates, Sub-templates e Classificação | 0/TBD | Not started | - |
| 5. Confiança, Revisão Humana e Quarentena | 0/TBD | Not started | - |
| 6. Automações de Arquivo (Renomear/Mover) | 0/TBD | Not started | - |
| 7. Módulo Determinístico Opcional e Roteamento de Custo | 0/TBD | Not started | - |
| 8. Distribuição, Atualização e Documentação | 0/TBD | Not started | - |

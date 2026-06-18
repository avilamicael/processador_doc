# Roadmap: Processador de Documentos

## Overview

O produto transforma pilhas de documentos heterogêneos (PDFs e imagens, de tipos variados) em arquivos classificados, nomeados e organizados de forma automática e confiável, single-tenant, rodando primariamente em Windows. A jornada começa pela fundação que torna tudo seguro e testável — máquina de estados persistida, armazenamento imutável por hash (CAS) e migrações desde o dia 1 — sobre a qual se monta a ingestão multi-entrada com fila assíncrona idempotente. Em seguida vem o núcleo do motor: extração **genérica via IA** dirigida pelo template, com medição de tokens para a cobrança por consumo. Sobre esse contrato de extração constroem-se os templates/sub-templates e a classificação, depois o gate de confiança com revisão humana e quarentena, e só então as automações de arquivo (renomear/mover) com dry-run, log de auditoria write-ahead e undo. O parsing determinístico de tipos conhecidos entra depois, como módulo opcional/plugável de otimização de custo (não como eixo do produto). A jornada fecha com distribuição, atualização segura entre versões e a documentação de primeira classe (instalação, atualização, uso e operação).

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Fundação de Estado e Storage** - Máquina de estados persistida, CAS por hash, migrações Alembic e base Windows single-tenant (completed 2026-06-15)
- [x] **Phase 2: Ingestão e Fila Assíncrona** - Pasta(s) monitorada(s) com separação por pasta, dedup por hash e fila in-process idempotente com retry (completed 2026-06-16)
- [x] **Phase 3: Extração Genérica via IA e Medição de Tokens** - Núcleo do motor: extração por IA dirigida pelo template (qualquer tipo) + texto nativo + medição de uso (completed 2026-06-16)
- [x] **Phase 4: Templates, Sub-templates e Classificação** - Construtor schema-first de templates e classificação automática contra eles (completed 2026-06-16)
- [x] **Phase 5: Confiança, Revisão Humana e Quarentena** - Score de confiança determinístico, limiar, fila de revisão lado-a-lado e quarentena visível (completed 2026-06-17)
- [x] **Phase 6: Automações de Arquivo (Renomear/Mover)** - Renomear/mover por tokens com dry-run, audit log write-ahead, anti-colisão e undo (modelo final Condições→Ações; verificado por testes 2026-06-18, 1 item de verificação ao vivo pendente)
- [x] **Phase 6.2: Ação de Automação Copiar** (INSERTED) - Ação Copiar nas automações (copia ao destino deixando o original); Cortar/split por template adiado para v2 (completed 2026-06-18)
- [ ] **Phase 7: Módulo Determinístico Opcional e Roteamento de Custo** - Parsing plugável de tipos conhecidos (boleto/NF-e) e cascata determinístico→nativo→IA — **ADIADA** (otimização opcional; revisitar após medir custo real de tokens em uso)
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

**Goal**: O usuário configura, pela interface, uma ou mais pastas monitoradas (cada uma com sua regra de separação de páginas) e cada arquivo colocado nelas entra numa fila assíncrona idempotente que nunca reprocessa nem cobra duas vezes o mesmo arquivo. Ingestão é exclusivamente por pasta monitorada no v1.
**Depends on**: Phase 1
**Requirements**: ING-02, ING-04, ING-05, ING-06, PROC-02, PROC-03
**Success Criteria** (what must be TRUE):

  1. O usuário configura pela interface uma ou mais pastas monitoradas (caminho + páginas por bloco) e vê os documentos entrando na fila com seu estado
  2. Arquivos colocados na pasta monitorada são processados automaticamente apenas após estarem estáveis (arquivo parcialmente escrito não é processado)
  3. Um documento multi-página é separado em blocos pela quantidade de páginas configurada na pasta, e cada bloco vira um documento independente no pipeline
  4. Enviar o mesmo arquivo duas vezes é detectado por hash e não gera reprocessamento nem cobrança dupla, mesmo após retry/crash da fila (com visibilidade de duplicados ignorados na interface)

**Note de escopo (2026-06-15)**: ING-01 (upload manual) e ING-03 (lote CLI) removidos do v1 → v2. Ingestão folder-only. Ver `phases/02-ingest-o-e-fila-ass-ncrona/02-CONTEXT.md`.

**Plans**: 8 plans (5 do modelo de regra-única; 06-01/06-04/06-05 ficam como histórico — REPLAN para PIPELINE adicionou 06-06/06-07/06-08)
**UI hint**: yes
Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Schema da fila/dedup/pastas (3 tabelas + origin_original_id) via Alembic 0002 + deps (watchfiles/pikepdf) + esqueletos Wave 0

**Wave 2** *(blocked on Wave 1)*

- [x] 02-02-PLAN.md — Utilidades de ingestão: estabilizador (quiescência+lock-test) + separador de PDF (pikepdf) + config de janela global

**Wave 3** *(blocked on Wave 2)*

- [x] 02-03-PLAN.md — Núcleo idempotente: fila SQLite (claim atômico/backoff/resume) + worker + ingest_stage (dedup gate + estado terminal "aguardando extração")

**Wave 4** *(blocked on Wave 3)*

- [x] 02-04-PLAN.md — Watcher (awatch→estabiliza→gate→enqueue) + lifespan (watcher+worker) + API fina (CRUD pastas, lista docs, duplicados, rescan)

**Wave 5** *(blocked on Wave 4)*

- [x] 02-05-PLAN.md — Frontend: TanStack Query + hooks/cliente + telas Documentos (polling) e Pastas monitoradas (CRUD) + verificação visual

### Phase 3: Extração Genérica via IA e Medição de Tokens

**Goal**: O sistema extrai, para qualquer tipo de documento (incluindo imagens e PDFs escaneados), os dados que encontrar via IA da OpenAI de forma **genérica** (não dirigida por template), aproveitando texto nativo local quando disponível, e mede o consumo de tokens por documento para a cobrança.
**Depends on**: Phase 2
**Requirements**: EXT-01, EXT-02, USE-02
**Success Criteria** (what must be TRUE):

  1. O sistema extrai os dados de um documento de qualquer tipo (incluindo imagens e PDFs escaneados) via IA, devolvendo pares `dado→valor`, o texto integral e um palpite de tipo de documento
  2. A IA retorna os dados em formato estruturado conforme um JSON Schema **genérico** (Structured Outputs), persistido junto com o texto nativo como base para os templates/classificação da Fase 4
  3. Quando o PDF já tem texto nativo, o sistema extrai esse texto localmente sem custo de IA
  4. Cada chamada à IA registra os tokens consumidos (prompt + completion) ligados ao documento, disponíveis para apoiar a cobrança por consumo

**Nota de escopo (2026-06-16, discuss-phase)**: **EXT-04** (JSON Schema **derivado do template** + **validações de campo configuráveis**) foi re-escopado da Fase 3 → **Fase 4** — depende de campos de template, que não existem na hora da extração genérica. O critério de sucesso 2 foi ajustado de "schema derivado do template + validações" para "schema genérico estruturado". Análogo ao re-escopo ING-01/ING-03 da Fase 2. Ver `phases/03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens/03-CONTEXT.md` `<domain>`/`<deferred>`.

**Plans**: 4 plans
Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Fundação: deps (openai/PyMuPDF/respx) + tunables de extração + schema genérico ExtractionResult + modelo Extraction (Alembic 0003) + scaffold de testes respx

**Wave 2** *(blocked on Wave 1)*

- [x] 03-02-PLAN.md — Primitivas: pdf_io (texto nativo/render/magic bytes) + router (seam D-03) + openai_client (Responses API + Structured Outputs + recusa + tokens)

**Wave 3** *(blocked on Wave 2)*

- [x] 03-03-PLAN.md — extract_stage async idempotente (commit atômico: Extraction + full_text + Usage + marcador "extraido"); testes de tokens/estado/idempotência

**Wave 4** *(blocked on Wave 3)*

- [x] 03-04-PLAN.md — Wiring na fila: dispatch por step (extract no loop, ingest em thread) + FALHA por content_hash + sweep idempotente de enqueue de extract

### Phase 4: Templates, Sub-templates e Classificação

**Goal**: O usuário consegue criar, no app, templates schema-first por tipo de documento, e o sistema classifica automaticamente cada documento contra eles — preenchendo e validando os campos do template e mandando para quarentena o que não casa.
**Depends on**: Phase 3
**Requirements**: TPL-01, TPL-03, TPL-04, EXT-04
**Success Criteria** (what must be TRUE):

  1. O usuário cria um template declarando campos (nome, tipo, validação, dica) por um editor schema-first, sem desenhar zonas visuais
  2. Cada documento é classificado automaticamente contra os templates disponíveis (híbrido: regras por sinais declarados → IA para desempate)
  3. Um documento que não casa com nenhum template vai para quarentena e nunca some
  4. A IA retorna dados em formato estruturado conforme um JSON Schema **derivado do template**, com validações de campo configuráveis aplicadas ao resultado (EXT-04, re-escopado da Fase 3 em 2026-06-16)

**Nota de escopo (2026-06-16):** sub-templates (TPL-02) re-escopados para a Fase 6 como **regras condicionais de automação** — o que variava entre "sub-templates" não era a extração/campos e sim qual automação aplicar (ver `phases/04-templates-sub-templates-e-classifica-o/04-CONTEXT.md`).

**Plans**: 6 plans
**UI hint**: yes
Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Fundação: deps (python-dateutil) + tunables de classify + 4 modelos (template/campo/resultado/campo-preenchido) + Alembic 0004 + scaffolds Wave 0

**Wave 2** *(blocked on Wave 1)*

- [x] 04-02-PLAN.md — Módulo de validação determinística reutilizável (Módulo 11 CNPJ/CPF próprio + parsers pt-BR data/moeda + validate_field bruto/normalizado)
- [x] 04-03-PLAN.md — Blocos de classificação: schema list-of-pairs (desempate/faltantes) + matcher local por sinais + filler de campos + cliente OpenAI
- [x] 04-04-PLAN.md — API fina: CRUD /templates + GET /documents/{id} de detalhe (classificação somente leitura) + registro no main

**Wave 3** *(blocked on Wave 2)*

- [x] 04-05-PLAN.md — classify_stage async idempotente atômico (matcher→IA→filler→IA→validação, quarentena, Usage) + fiação na fila (step=classify + sweep de legados)

**Wave 4** *(blocked on Wave 3)*

- [x] 04-06-PLAN.md — Frontend: tipos/api/hooks + TemplatesPage real (S1/S2/S3) substituindo o mock + DocumentsPage S4 (classificação somente leitura) + verificação visual

### Phase 5: Confiança, Revisão Humana e Quarentena

**Goal**: O usuário nunca confia cegamente na IA — documentos com baixa confiança ou que falham validação param numa visão de triagem na web ("Precisam de atenção") que mostra o motivo e os campos editáveis, e a quarentena é visível e resolúvel. A web é gestão/triagem (corrige o **dado** que a automação usará); o arquivo em si é manuseado no Windows Explorer — sem visualizador de documento na web.
**Depends on**: Phase 4
**Requirements**: REV-01, REV-02, REV-03, REV-04, REV-05
**Success Criteria** (what must be TRUE):

  1. O sistema calcula um indicador de confiança por documento baseado em validação determinística pós-extração (não apenas no auto-relato da IA)
  2. O usuário define um limiar de confiança (global, na config) que decide o que vai para revisão manual
  3. Documentos abaixo do limiar OU com campo obrigatório inválido/faltante aparecem numa visão de triagem na web que mostra o motivo e os valores dos campos editáveis — sem visualizador de documento na web
  4. O usuário consegue aprovar/corrigir os valores dos campos na web antes de qualquer automação (aprovar → CONCLUIDO; correção marcada como manual)
  5. A quarentena é visível, mostra o motivo de cada documento e permite resolver (atribuir template + reclassificar) / reprocessar

**Nota de escopo (2026-06-16):** modelo "web ativa, leve" — uma visão única "Precisam de atenção" com 3 baldes (FALHA → tentar de novo; QUARENTENA → atribuir template + reclassificar; EM_REVISAO → corrigir campos + aprovar). Visualizador de documento na web removido por decisão de visão (web = gestão; arquivos via Windows Explorer). Ver `phases/05-confian-a-revis-o-humana-e-quarentena/05-CONTEXT.md`.

**Plans**: 4 plans
Plans:
**Wave 1**

- [x] 05-01-PLAN.md — Fundação: colunas confidence_score/manually_corrected (Alembic 0005) + tunable do limiar + função pura compute_confidence + scaffolds Wave 0

**Wave 2** *(blocked on Wave 1)*

- [x] 05-02-PLAN.md — classify_stage: cálculo+persistência do score, roteamento EM_REVISAO vs PROCESSANDO+classificado (sem auto-CONCLUIDO), forced_template_id + repo.requeue_step + worker payload

**Wave 3** *(blocked on Wave 2)*

- [x] 05-03-PLAN.md — API de triagem: endpoints retry/reclassify/patch/approve (allowlist como guard) + GET /documents/attention (3 baldes) + GET/PUT limiar global

**Wave 4** *(blocked on Wave 3)*

- [x] 05-04-PLAN.md — Frontend: AttentionPage (3 baldes + ações) + ConfidenceBadge + hooks/api/types + S6 na Config + navegação + verificação visual

**UI hint**: yes

### Phase 6: Automações de Arquivo (Renomear/Mover)

**Goal**: O sistema renomeia e move arquivos do cliente com base nos campos extraídos de forma reversível e segura — dry-run obrigatório, log de auditoria antes de agir, proteção contra colisão e undo — de modo que nenhum arquivo jamais se perde. Inclui **regras condicionais de tratativa** por tipo/cliente/valor (ex.: nota fiscal do cliente Y → pasta Documentos; holerite > R$ 3.000 → pasta análise) que decidem qual automação aplicar.
**Depends on**: Phase 5
**Requirements**: AUT-01, AUT-02, AUT-03, AUT-04, AUT-05, AUT-06, TPL-02
**Success Criteria** (what must be TRUE):

  1. O usuário define padrões de renomeação e de pasta de destino usando os campos extraídos (ex.: `{cliente}_{numero}_{data}.pdf`, `Documentos/{cliente}/{ano-mes}/`)
  2. Antes de aplicar, o sistema mostra um dry-run/preview com pares origem→destino e colisões sinalizadas
  3. O sistema registra a intenção em log de auditoria ANTES de agir e nunca sobrescreve um destino existente silenciosamente
  4. O usuário consegue desfazer operações por documento e por lote/execução
  5. Mover entre discos diferentes é seguro (copia, verifica e só então remove a origem)
  6. O usuário define **regras condicionais de tratativa** (condição sobre os campos extraídos → qual automação aplicar), permitindo tratativas diferentes para o mesmo tipo de documento por cliente/emissor/valor (TPL-02, re-escopado da Fase 4 em 2026-06-16)

**Nota de implementação do critério 5 (2026-06-17, planning):** D-11 redefine a mecânica de "copia, verifica e só então remove a origem" como **materializa do CAS → verifica o hash do destino → remove o arquivo original da pasta de origem**. O "copia" é a materialização do conteúdo imutável do CAS (não um move do original), o "verifica" é a conferência do SHA-256 do destino, e o "remove a origem" é o unlink do original na pasta monitorada SOMENTE após a verificação passar. O CAS preserva o conteúdo para sempre (rede final do undo), então a remoção nunca causa perda. O critério 5 é cumprido integralmente — não há redução de escopo.

**Plans**: 5 plans
**UI hint**: yes
Plans:
**Wave 1**

- [x] 06-01-PLAN.md — Fundação: estender AuditLog (write-ahead+undo) + modelos AutomationRule/RuleCondition + Alembic 0006 + tunables + scaffolds Wave 0

**Wave 2** *(blocked on Wave 1)*

- [x] 06-02-PLAN.md — Motores puros: naming (tokens→caminho sanitizado+confinado, bloqueio→revisão) + rules (regras condicionais primeira-que-casa-vence)
- [x] 06-03-PLAN.md — Operação física: fileops (materializa do CAS+anti-colisão+verifica hash) + undo (reversão por-doc/run com fallback CAS)

**Wave 3** *(blocked on Wave 2)*

- [x] 06-04-PLAN.md — Orquestração: apply_stage (write-ahead idempotente+reconcile) + worker (step apply+sweep auto-aplica) + API /automations + approve dispara apply

**Wave 4** *(blocked on Wave 3)*

- [x] 06-05-PLAN.md — Frontend: tipos/api/hooks + Automações real (S1/S2/S3) + Dry-run (S4) + Aplicar/Desfazer (S5/S6) + verificação visual

> **REPLAN (2026-06-17) — modelo de PIPELINE (D-12..D-16).** As automações deixaram de ser "regra única" e viraram um pipeline ordenado de etapas componíveis. 06-02 (naming) e 06-03 (fileops/undo) são REUSADOS como ações atômicas (não replanejados). 06-01/06-04/06-05 ficam como histórico do modelo antigo. Os planos abaixo reescrevem modelo de dados + executor + API + frontend.

**Wave 1 (REPLAN)**

- [x] 06-06-PLAN.md — Modelo de dados do PIPELINE: AutomationPipeline 1:N PipelineStep 1:N StepFilter (substitui automation_rules/rule_conditions) + Alembic 0007 forward-only (documents/audit_log intactos) + scaffolds de teste do modelo

**Wave 2 (REPLAN)** *(blocked on 06-06)*

- [x] 06-07-PLAN.md — Executor PURO do pipeline (run_pipeline, materialização única) + filtros de entrada (D-14) + apply_stage/dry_run reescritos + API CRUD de pipeline/steps/filtros + ajuste do worker (reusa naming/fileops/undo)

**Wave 3 (REPLAN)** *(blocked on 06-07)*

- [x] 06-08-PLAN.md — Frontend construtor de pipeline (S1 lista ordenada/encadeada + S2 editor de etapa + S3 token com pré-visualização) + Dry-run (S4) + Aplicar/Desfazer (S5/S6) + verificação visual (sem visualizador; zero npm novo)

> **REFINO PÓS-PLANO (06-09..06-12, 2026-06-18).** Após 06-08, o modelo de automações evoluiu para o **modelo final "Condições→Ações"** (D-23..D-26): 06-09 (refinamentos D-17/D-18/D-21/D-22), 06-10 (construtor conforme mockup), 06-11 (remodelagem Condições→Ações + migração 0008 substituindo pipeline/steps/filters por automations/conditions/actions), 06-12 (reescrita do frontend). Ver `06-VERIFICATION.md`.

### Phase 06.1: Redesign de Templates e Classificação por Sinais (E/OU + Regex) (INSERTED)

**Goal:** A tela de criação/edição de Template comunica explicitamente o pipeline (Passo 1 reconhecer o tipo SEM IA por sinais; Passo 2 extrair campos COM IA) e o motor de classificação por sinais evolui de "fração de termos literais" para **grupos booleanos E/OU de condições texto|regex**, persistidos como JSON estruturado na coluna existente e avaliados com segurança (ReDoS) — preservando o seam `decide()`, o roteamento de quarentena/revisão e a ponte campo→token das automações.
**Requirements**: D-T0..D-T9 (decisões do CONTEXT — sem REQ-IDs formais; cobertura por decision-coverage gate)
**Depends on:** Phase 6
**Plans:** 4/4 plans complete
**UI hint**: yes

Plans:
**Wave 1**

- [x] 06.1-01-PLAN.md — Matcher booleano de grupos E/OU texto|regex (tetos ReDoS, parser forward-compatible, doc_type bonus removido, `decide()` preservado) + suite RED→GREEN (D-T1/D-T2)

**Wave 2** *(blocked on 06.1-01)*

- [x] 06.1-02-PLAN.md — API/modelo de templates no schema de grupos (Pydantic `Literal` mode, serialização forward-compatible, regex string-only T-04-10, doc_type dormente) + testes de integração (D-T2/D-T5/D-T9)

**Wave 3** *(blocked on 06.1-02)*

- [x] 06.1-03-PLAN.md — Frontend: reescrita de TemplatesPage conforme mockup (grupos E/OU, campos densos + ⚙ Avançado, tooltips ⓘ hover, sem doc_type) + tipos/cliente + token `--tip-shadow` + gate de build (D-T0/D-T3/D-T4/D-T6/D-T7/D-T8/D-T9)

**Gap closure** *(CR-01 + WR-01, do VERIFICATION/REVIEW)*

- [x] 06.1-04-PLAN.md — Fechar ReDoS real (timeout via lib `regex` + falha-fechada) e falha-fechada de `decide()` com threshold ≤ 0; docstring corrigida; testes reforçados (D-T1/D-T2)

### Phase 06.2: Ação de Automação Copiar (INSERTED)

**Goal:** Adicionar a ação **Copiar** ao modelo Condições→Ações da Fase 6, mantendo Mover e Renomear sem regressão. Copiar materializa o arquivo no destino e **deixa o original na origem** (não remove) — mais seguro que Mover, atende ao objetivo do usuário de "não perder o documento". Reusa a infraestrutura da Fase 6 (`fileops.materialize_to_dest`, anti-colisão, audit write-ahead, undo, dry-run).
**Requirements**: estende AUT-* (sem REQ-IDs formais novos; cobertura por decision-coverage do CONTEXT, como a 06.1)
**Depends on:** Phase 6
**Success Criteria** (rascunho — refinar no discuss-phase):

  1. O usuário adiciona a ação **Copiar** (com pasta de destino, tokens de campo) a uma automação e, após aplicar, o arquivo aparece no destino E o original permanece na origem
  2. Mover e Renomear continuam funcionando sem regressão
  3. Dry-run, audit log write-ahead, anti-colisão e undo cobrem a ação Copiar (nenhum arquivo se perde)

**Escopo (decisão 2026-06-18, discuss-phase):** a Fase 6.2 cobre **somente a ação Copiar**. A ação **Cortar / split por template foi ADIADA para a v2** — a separação por pasta monitorada (`pages_per_block`) já existe e o split dirigido por template (re-entrada de pedaços no pipeline vs. saída de arquivo; onde a regra de corte mora) precisa de mais reflexão. Ver memória de projeto `automacoes-acoes-copiar-cortar`.

**Plans:** 3/3 plans complete
Plans:
**Wave 1**

- [x] 06.2-01-PLAN.md — Executor PURO multi-saída: AutomationPlan carrega N cópias planejadas + alvo de move; ramo `copy` espelha `move` (resolução/bloqueio) sem mutar o alvo; docstring de modelo (sem migração)

**Wave 2** *(blocked on 06.2-01)*

- [x] 06.2-02-PLAN.md — Orquestração física: apply_stage materializa cada cópia do CAS (write-ahead por cópia, anti-colisão, SEM remove_original) antes do move; undo de cópia (apaga a cópia, nunca toca o original); API valida `copy` + dry-run por saída

**Wave 3** *(blocked on 06.2-02)*

- [x] 06.2-03-PLAN.md — Frontend: ActionType/DryRunRow + opção "Copiar" no editor (nota "o original permanece") + badge "Copiado — original mantido" no dry-run + verificação visual ao vivo

### Phase 7: Módulo Determinístico Opcional e Roteamento de Custo

**Goal**: Para clientes que recebem tipos conhecidos (boleto, NF-e), um módulo opcional/plugável extrai esses dados sem IA, e o roteador passa a escolher a rota mais barata (determinístico → texto nativo → IA), reduzindo o custo de tokens do cliente.
**Depends on**: Phase 6
**Requirements**: EXT-03, EXT-05
**Success Criteria** (what must be TRUE):

  1. Com o módulo habilitado, boletos são lidos pela linha digitável/código de barras e NF-e pela chave de 44 dígitos/XML, sem chamar a IA, com validação de dígito verificador
  2. O roteador resolve cada documento na ordem determinístico (quando aplicável) → texto nativo local → IA, mandando à IA só o que não foi resolvido localmente
  3. Com o módulo desabilitado, o motor continua funcionando integralmente pela extração genérica via IA (o determinístico é otimização, não dependência)
  4. Documentos resolvidos localmente não geram consumo de tokens (refletido na medição de uso)

**Status (2026-06-18, discuss-phase): ADIADA por decisão do usuário.** O motor com IA já está funcional de ponta a ponta (Fases 1–6.1) e a Fase 7 é **pura otimização de custo** — não altera o que o usuário vê e, por design do roadmap, é "otimização, não dependência" (com o módulo desligado, o estado de hoje continua válido — SC3). Decisão: **deixar rodar 100% pela IA primeiro, medir o custo real de tokens em uso, e só então decidir se os parsers determinísticos (boleto via linha digitável/Módulo 10-11; NF-e via chave de 44 dígitos/Módulo 11) valem o esforço.** Gatilho para revisitar: custo de tokens observado na prática justificar a economia em boleto/NF-e. Nenhuma decisão de implementação foi capturada (sem CONTEXT.md) — as 4 áreas de decisão (escopo & entrada NF-e XML vs. só chave do DANFE; posição na cascata determinístico→nativo→IA via seam `router.choose`/D-03; gatilho da detecção e fallback de DV; toggle global vs. por-tipo + reflexo de custo-zero na medição `Usage`) ficam abertas para o discuss-phase futuro. Assets prontos para reuso quando revisitada: `backend/app/extraction/router.py` (seam D-03), `backend/app/validation/doc_ids.py` (Módulo 11 CNPJ/CPF próprio), `backend/app/models/usage.py` (medição por `step`).

**Plans**: TBD (adiada)

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
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 6.1 → 6.2 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Fundação de Estado e Storage | 4/4 | Complete    | 2026-06-15 |
| 2. Ingestão e Fila Assíncrona | 5/5 | Complete    | 2026-06-16 |
| 3. Extração Genérica via IA e Medição de Tokens | 4/4 | Complete    | 2026-06-16 |
| 4. Templates, Sub-templates e Classificação | 6/6 | Complete   | 2026-06-16 |
| 5. Confiança, Revisão Humana e Quarentena | 4/4 | Complete   | 2026-06-17 |
| 6. Automações de Arquivo (Renomear/Mover) | 8/8 (+06-09..06-12 refino) | Complete (test-verified) | 2026-06-18 |
| 6.1. Redesign de Templates e Classificação por Sinais | 4/4 | Complete    | 2026-06-18 |
| 6.2. Ação de Automação Copiar | 3/3 | Complete   | 2026-06-18 |
| 7. Módulo Determinístico Opcional e Roteamento de Custo | 0/TBD | Deferred (2026-06-18) | - |
| 8. Distribuição, Atualização e Documentação | 0/TBD | Not started | - |

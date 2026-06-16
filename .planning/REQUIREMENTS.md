# Requirements: Processador de Documentos

**Defined:** 2026-06-15
**Core Value:** Transformar uma pilha de documentos heterogêneos (PDFs e imagens, de tipos variados) em arquivos classificados, nomeados e organizados corretamente de forma automática e confiável — sem o usuário perder arquivos nem confiar cegamente na IA.

## v1 Requirements

Requisitos para o lançamento inicial. Cada um mapeia para fases do roadmap. O motor é **genérico**: qualquer tipo de documento via template + IA. Parsing determinístico de tipos conhecidos (boleto/NF-e) é um **módulo opcional/plugável**, não o eixo do produto.

### Ingestão (ING)

- [x] **ING-02**: Sistema processa automaticamente arquivos colocados em pasta(s) monitorada(s) (hot folder) — único caminho de ingestão no v1 — só após o arquivo estar estável (não processar arquivo parcialmente escrito); o usuário pode configurar múltiplas pastas pela interface
- [x] **ING-04**: Sistema aceita PDF e formatos de imagem comuns (JPG, PNG) como entrada
- [x] **ING-05**: Sistema separa um documento multi-página em blocos pela quantidade de páginas configurada pelo usuário, por pasta monitorada (cada bloco vira um documento independente)
- [x] **ING-06**: Sistema deduplica por hash, evitando reprocessar e cobrar o mesmo arquivo duas vezes

> **Nota de escopo (2026-06-15):** ING-01 (upload manual) e ING-03 (lote por linha de comando) foram removidos do v1 — ingestão é exclusivamente por pasta monitorada. Movidos para v2 (ver ING2). Decisão capturada em `phases/02-ingest-o-e-fila-ass-ncrona/02-CONTEXT.md`.

### Extração (EXT)

- [x] **EXT-01**: Sistema extrai texto nativo de PDFs localmente, sem custo de IA, quando o PDF tem texto
- [x] **EXT-02**: Sistema extrai dados de qualquer tipo de documento via IA (OpenAI), dirigido pelos campos do template (caminho principal, inclui imagens e PDFs escaneados)
- [ ] **EXT-03**: Sistema roteia a extração na ordem: determinístico (quando aplicável) → texto nativo local → IA, mandando à IA só o que não foi resolvido localmente
- [x] **EXT-04**: IA retorna dados em formato estruturado (JSON Schema derivado do template), com validações de campo configuráveis
- [ ] **EXT-05**: (Módulo opcional) Sistema extrai dados de tipos conhecidos sem IA quando presentes — boleto via linha digitável/código de barras e NF-e via chave de 44 dígitos/XML — com validação de dígito verificador

### Templates & Classificação (TPL)

- [x] **TPL-01**: Usuário cria templates de documento no app declarando campos (nome, tipo, validação, dica) — editor schema-first, sem desenhar zonas visuais
- [x] **TPL-03**: Sistema classifica automaticamente cada documento contra os templates disponíveis (usando IA para contexto)
- [x] **TPL-04**: Documento que não casa com nenhum template vai para quarentena (não some)

### Confiança & Revisão (REV)

- [ ] **REV-01**: Sistema calcula um indicador de confiança por documento, baseado em validação determinística pós-extração (não apenas no auto-relato da IA)
- [ ] **REV-02**: Usuário define um limiar de confiança que decide o que vai para revisão manual
- [ ] **REV-03**: Documentos abaixo do limiar ou que falham validação entram numa fila de revisão humana com visualização do documento ao lado dos campos editáveis
- [ ] **REV-04**: Usuário pode aprovar/corrigir os campos antes de qualquer automação ser aplicada
- [ ] **REV-05**: Quarentena é visível, mostra o motivo e permite o usuário resolver/reprocessar

### Automações de Arquivo (AUT)

- [ ] **AUT-01**: Usuário define padrões de renomeação usando os campos extraídos (ex.: `{cliente}_{numero}_{data}.pdf`)
- [ ] **AUT-02**: Usuário define para qual pasta mover, usando os campos extraídos (ex.: `Documentos/{cliente}/{ano-mes}/`)
- [ ] **AUT-03**: Sistema mostra um dry-run/preview (origem → destino, colisões sinalizadas) antes de aplicar qualquer operação de arquivo
- [ ] **AUT-04**: Sistema registra a intenção em log de auditoria ANTES de agir e protege contra colisão (nunca sobrescreve silenciosamente)
- [ ] **AUT-05**: Usuário pode desfazer (undo) operações por documento e por lote/execução
- [ ] **AUT-06**: Operação de mover entre discos diferentes é segura (copia, verifica e só então remove a origem)
- [ ] **TPL-02**: Usuário cria regras condicionais de tratativa por tipo/cliente/emissor/valor (condição sobre os campos extraídos → qual automação aplicar) — permite tratativas diferentes para o mesmo tipo de documento. _(Re-escopado de "sub-templates" da Fase 4 → Fase 6 em 2026-06-16; o que variava não era a extração/campos e sim a automação.)_

### Processamento (PROC)

- [x] **PROC-01**: Cada documento percorre uma máquina de estados explícita persistida (recebido → … → aplicado, com estados de revisão/quarentena/falha)
- [x] **PROC-02**: Processamento roda numa fila assíncrona com worker em background, com retry e backoff (lida com lotes e rate limit da OpenAI)
- [x] **PROC-03**: Fila é idempotente (chave por hash + etapa), impedindo reexecução de etapa concluída e cobrança dupla

### IA & Cobrança (USE)

- [x] **USE-01**: Cada instância usa uma chave OpenAI por cliente (provisionada pelo fornecedor); o cliente é responsável pelo consumo
- [x] **USE-02**: Sistema mede e registra o uso de tokens/chamadas por documento, para apoiar a cobrança por consumo

### Distribuição & Atualização (DIST)

- [x] **DIST-01**: Sistema roda em Windows (plataforma primária) — instalação, watcher e operações de arquivo confiáveis nele
- [x] **DIST-02**: Sistema roda no modo padrão sem broker externo (fila in-process), e opcionalmente em servidor
- [ ] **DIST-03**: Produto tem versão visível e releases versionadas
- [ ] **DIST-04**: Fornecedor consegue publicar novas versões e o cliente consegue atualizar o sistema
- [ ] **DIST-05**: Atualização migra dados com segurança (Alembic), sem perder templates, configurações ou dados do cliente

### Documentação (DOC)

- [ ] **DOC-01**: Guia de instalação (rodar em Windows local ou servidor; configurar a chave OpenAI)
- [ ] **DOC-02**: Guia de atualização (aplicar updates publicados pelo fornecedor sem perder dados)
- [ ] **DOC-03**: Documentação de uso / experiência do usuário (criar templates, revisar, aplicar automações) com exemplos de "como fazer"
- [ ] **DOC-04**: Guia de operação/administração (pasta monitorada, backup dos dados, troubleshooting)

## v2 Requirements

Diferidos para depois. Reconhecidos, mas fora do roadmap atual.

### Ingestão diferida (ING2)

- **ING2-01**: Usuário pode enviar documentos por upload manual (PDF e imagens) pela interface (era ING-01; removido do v1 em 2026-06-15)
- **ING2-02**: Usuário pode processar uma pasta em lote pela linha de comando / backfill (era ING-03; removido do v1 em 2026-06-15)

### Automações avançadas (AUT2)

- **AUT2-01**: Enviar documentos por e-mail
- **AUT2-02**: Enviar documentos por WhatsApp
- **AUT2-03**: Chamar API/webhook ou lançar em outro sistema (ex.: ERP)
- **AUT2-04**: Exportar dados extraídos para CSV/Excel

### Inteligência & Custo (INT2)

- **INT2-01**: Identificar o cliente/sub-template automaticamente pelo CNPJ do documento
- **INT2-02**: Painel de consumo de tokens/custo por período na interface
- **INT2-03**: Controle/transparência detalhada do que é enviado à OpenAI (postura LGPD), por documento
- **INT2-04**: Correções da revisão humana alimentando hints (few-shot) por sub-template
- **INT2-05**: Limiar de confiança por template (em vez de só global)

### Distribuição avançada (DIST2)

- **DIST2-01**: Empacotamento desktop (Tauri + sidecar) para experiência "instala e abre"
- **DIST2-02**: Auto-update embutido (verificar e aplicar updates automaticamente)
- **DIST2-03**: Parsers determinísticos para outros tipos (NFS-e, etc.)
- **DIST2-04**: Provedores de IA alternativos / modelos on-premise

## Out of Scope

Explicitamente excluídos. Documentado para prevenir scope creep.

| Feature | Reason |
|---------|--------|
| Multiusuário / contas / SaaS multi-tenant | Produto single-tenant, cada cliente roda a própria instância |
| Proxy/gateway central de IA | Cada instância usa a própria chave OpenAI; sem componente cloud obrigatório no v1 |
| App desktop (Electron) | Web-first; se houver desktop, preferir Tauri (v2) |
| Billing/faturamento embutido no app | Cobrança feita por fora, com base no uso medido |
| Editor de templates por zonas visuais (canvas/coordenadas) | Anti-feature: template schema-first é mais robusto a variações de layout |
| Acoplar o motor a tipos fiscais específicos | Motor deve ser genérico; parsing fiscal é módulo opcional |

## Traceability

Mapeamento de cada requisito v1 para exatamente uma fase do roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ING-01 | — | Removido do v1 → v2 (ING2-01) |
| ING-02 | Phase 2 | Complete |
| ING-03 | — | Removido do v1 → v2 (ING2-02) |
| ING-04 | Phase 2 | Complete |
| ING-05 | Phase 2 | Complete |
| ING-06 | Phase 2 | Complete |
| EXT-01 | Phase 3 | Complete |
| EXT-02 | Phase 3 | Complete |
| EXT-03 | Phase 7 | Pending |
| EXT-04 | Phase 4 | Pending (re-escopado da Fase 3 → Fase 4 em 2026-06-16) |
| EXT-05 | Phase 7 | Pending |
| TPL-01 | Phase 4 | Complete |
| TPL-02 | Phase 6 | Pending (re-escopado Fase 4 → Fase 6 em 2026-06-16) |
| TPL-03 | Phase 4 | Complete |
| TPL-04 | Phase 4 | Complete |
| REV-01 | Phase 5 | Pending |
| REV-02 | Phase 5 | Pending |
| REV-03 | Phase 5 | Pending |
| REV-04 | Phase 5 | Pending |
| REV-05 | Phase 5 | Pending |
| AUT-01 | Phase 6 | Pending |
| AUT-02 | Phase 6 | Pending |
| AUT-03 | Phase 6 | Pending |
| AUT-04 | Phase 6 | Pending |
| AUT-05 | Phase 6 | Pending |
| AUT-06 | Phase 6 | Pending |
| PROC-01 | Phase 1 | Complete |
| PROC-02 | Phase 2 | Complete |
| PROC-03 | Phase 2 | Complete |
| USE-01 | Phase 1 | Complete (01-01) |
| USE-02 | Phase 3 | Complete |
| DIST-01 | Phase 1 | Complete |
| DIST-02 | Phase 1 | Complete |
| DIST-03 | Phase 8 | Pending |
| DIST-04 | Phase 8 | Pending |
| DIST-05 | Phase 8 | Pending |
| DOC-01 | Phase 8 | Pending |
| DOC-02 | Phase 8 | Pending |
| DOC-03 | Phase 8 | Pending |
| DOC-04 | Phase 8 | Pending |

**Coverage:**

- v1 requirements: 36 total (ING-01 e ING-03 removidos do v1 em 2026-06-15)
- Mapped to phases: 36 ✓
- Unmapped: 0

---
*Requirements defined: 2026-06-15*
*Last updated: 2026-06-15 — Phase 2 discuss: ING-01/ING-03 removidos do v1 (ingestão só por pasta monitorada)*
*Last updated: 2026-06-16 — Phase 3 discuss: EXT-04 (schema derivado de template + validações de campo) re-escopado Fase 3 → Fase 4 (depende de campos de template)*
*Last updated: 2026-06-16 — Phase 4 discuss: TPL-02 re-escopado Fase 4 → Fase 6 (sub-templates viram regras condicionais de automação; o que variava era a automação, não a extração/campos)*

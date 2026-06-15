# Phase 1: Fundação de Estado e Storage - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Esta fase entrega a fundação que garante que nenhum dado se perde: os modelos de domínio, a máquina de estados explícita por documento, o armazenamento imutável endereçado por hash (CAS), as migrações versionadas (Alembic) e a configuração base single-tenant rodando confiavelmente em Windows. Não inclui ingestão real, fila, extração ou automações — apenas a base sobre a qual tudo isso será construído.

**Requirements cobertos:** PROC-01, DIST-01, DIST-02, USE-01.
</domain>

<decisions>
## Implementation Decisions

### Local dos dados (Windows)
- **D-01:** O app usa uma **única pasta de dados configurável** contendo o banco SQLite e o CAS (arquivos originais) juntos. Padrão: `%ProgramData%\ProcessadorDocumentos`. Backup = copiar uma única pasta; sobrevive à troca de usuário Windows.
- **D-02:** O caminho da pasta de dados é ajustável (definido na instalação/config), permitindo apontar para outro disco/volume.

### Configuração da chave OpenAI
- **D-03:** A chave OpenAI (provisionada pelo fornecedor, uma por cliente) é definida **via arquivo de config** (ex.: `.env`/`config`), lido pela aplicação. Sem proxy central. Sem tela de configuração no v1 — trocar a chave significa editar o arquivo de config na máquina do cliente.

### Ciclo de vida do documento (máquina de estados)
- **D-04:** Conjunto **enxuto** de estados visíveis: `RECEBIDO → PROCESSANDO → EM_REVISÃO → CONCLUÍDO`, mais os estados laterais `QUARENTENA` e `FALHA`.
- **D-05:** As subetapas internas do pipeline (dedup, separação, extração, classificação, validação) NÃO são estados de topo — são representadas por um **marcador interno de "última etapa concluída"** ligado ao documento, suficiente para retomada (resume) e idempotência sem expor complexidade na UI.
- **D-06:** Transições são explícitas e validadas: uma transição inválida deve **falhar sem corromper** o dado (critério de sucesso 1 da fase).

### Armazenamento imutável (CAS) e retenção
- **D-07:** O arquivo de entrada é **copiado** para dentro do sistema (CAS endereçado por hash) e tratado internamente. **O arquivo original na pasta de origem permanece intacto** (não é movido na ingestão).
- **D-08:** Originais no CAS são **mantidos para sempre** no v1 (rede de segurança / base de undo). Nenhuma política de expiração automática; limpeza fica a critério do cliente. Recuperável mesmo após qualquer automação posterior (critério de sucesso 2).

### Plataforma e infraestrutura
- **D-09:** Roda em **Windows** no modo padrão **sem broker externo** e sem dependências de infraestrutura adicionais (SQLite local; nada de Redis/serviço externo obrigatório nesta fase).
- **D-10:** O schema do banco evolui **somente via migração Alembic versionada** desde o dia 1 — nunca recriar o banco (base para a atualização segura entre versões da Fase 8).

### Claude's Discretion
- Estrutura concreta das tabelas/modelos (Document, Page, Extraction, AuditLog, Usage ou equivalente enxuto), nomes de colunas, e a implementação da state machine em Python — o planejador/arquiteto decide, respeitando D-04/D-05/D-06.
- Mecanismo concreto do CAS (layout de diretórios por hash, algoritmo de hash — SHA-256 sugerido pela pesquisa) e como o marcador de etapa é persistido.
- Formato exato do arquivo de config e nomes das chaves.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Projeto e escopo
- `.planning/PROJECT.md` — contexto do produto, constraints (Windows primário, single-tenant, genérico), decisões-chave.
- `.planning/REQUIREMENTS.md` — requisitos v1; esta fase cobre PROC-01, DIST-01, DIST-02, USE-01.
- `.planning/ROADMAP.md` §"Phase 1" — objetivo e 5 critérios de sucesso.

### Pesquisa (informa stack e armadilhas desta fundação)
- `.planning/research/STACK.md` — SQLite WAL + SQLAlchemy 2.0 + Alembic desde o dia 1; alerta de licença AGPL do PyMuPDF (relevante a partir da Fase 3, registrar mas não decidir aqui).
- `.planning/research/ARCHITECTURE.md` — máquina de estados por documento, CAS por hash, fronteiras de componentes, ordem de construção.
- `.planning/research/PITFALLS.md` — idempotência por hash + etapa; arquivo parcialmente escrito (relevante na ingestão da Fase 2, mas o hash/CAS é desta fase).

### Estado
- `.planning/STATE.md` §"Blockers/Concerns" — riscos a tratar (fila SQLite in-process validar na Fase 2; modelo de confiança Fase 5; licença PyMuPDF Fase 3; parser de boleto Fase 7).

Sem ADRs/specs externos adicionais — decisões desta fase totalmente capturadas acima.
</canonical_refs>

<code_context>
## Existing Code Insights

Projeto greenfield — nenhum código existente. Esta é a primeira fase e estabelece a estrutura inicial do repositório (backend Python/FastAPI, SQLAlchemy/Alembic, camada de storage).

### Established Patterns (a estabelecer nesta fase, servirão de base para as próximas)
- Camada de banco atrás de uma interface abstraível (SQLite agora; porta aberta para Postgres no modo servidor) — STACK.md.
- Camada de fila atrás de interface (a fila concreta vem na Fase 2; aqui só não bloquear esse desenho).
</code_context>

<specifics>
## Specific Ideas

- Fluxo mental do usuário (confirmado): o cliente monitora uma pasta (ex.: `Downloads`); quando um documento entra, ele é **copiado** para o sistema e tratado internamente, preservando o original. (A monitoração em si é da Fase 2; aqui só fica registrado que a ingestão é por cópia para o CAS.)
- Backup pensado como "copiar uma pasta só" — motivou D-01 (banco + CAS na mesma pasta de dados).
</specifics>

<deferred>
## Deferred Ideas

- **Suporte a outros formatos de entrada (Excel, TXT, CSV, ...)** — além de PDF e imagens. Nova capacidade; o v1 foca em PDF/imagens e a arquitetura deve apenas não impedir a extensão. → fase futura / v2 (relacionado a ING-04).
- **Tela de configuração para a chave OpenAI / settings na UI** — v1 usa só arquivo de config (D-03); uma tela editável é melhoria futura (alinhada a uma eventual área de configurações).
- **Política de retenção/expiração configurável dos originais** — v1 mantém para sempre (D-08); retenção configurável foi considerada e adiada.

### Reviewed Todos (not folded)
None — sem todos pendentes.
</deferred>

---

*Phase: 1-Fundação de Estado e Storage*
*Context gathered: 2026-06-15*

# Phase 2: Ingestão e Fila Assíncrona - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Esta fase entrega a **ingestão por pasta(s) monitorada(s)** e a **fila assíncrona in-process idempotente** que move cada documento ingerido pelo início do pipeline sem nunca reprocessar nem cobrar o mesmo arquivo duas vezes. Inclui: configuração de pastas monitoradas pela UI (com regra de separação por pasta), detecção de arquivo estável (não processar arquivo sendo escrito), separação de páginas, dedup por hash, e o worker em background com retry/backoff e idempotência por hash+etapa.

**Não inclui** (decidido nesta discussão — ver `<deferred>` e nota de escopo):
- **Upload manual pela interface (ING-01)** — removido do v1.
- **Lote por linha de comando (ING-03)** — removido do v1.
- Extração, classificação, revisão ou automações (fases 3+). Na Fase 2 o documento é ingerido/separado e **fica aguardando a etapa de extração da Fase 3**.

**Requirements cobertos (reduzidos):** ING-02, ING-04, ING-05, ING-06, PROC-02, PROC-03.
**Requirements removidos do v1 nesta discussão:** ING-01, ING-03 → mover para Out of Scope/v2 em REQUIREMENTS.md e ajustar os critérios de sucesso da Fase 2 no ROADMAP.md (critérios 1 e 3 referem-se a upload e CLI).

> ⚠️ **Ação de manutenção pendente (fora do CONTEXT):** atualizar `.planning/REQUIREMENTS.md` (ING-01, ING-03 → v2/Out of Scope; traceability) e `.planning/ROADMAP.md` (Phase 2 goal + success criteria 1 e 3). Esta discussão registra a decisão; a edição dos docs de planejamento é separada.
</domain>

<decisions>
## Implementation Decisions

### Caminho de ingestão (escopo)
- **D-01:** Ingestão no v1 é **exclusivamente por pasta monitorada (hot folder)**. Sem upload manual (ING-01 removido) e sem lote CLI (ING-03 removido). Justificativa do usuário: "vamos trabalhar apenas com pastas".

### Pastas monitoradas (configuração)
- **D-02:** Há **múltiplas pastas monitoradas**, configuradas **pela interface (UI)** — não por arquivo de config. Cada pasta tem: caminho + **regra de separação de páginas própria** (qtd. de páginas por bloco). Persistir essa config no banco.
- **D-03:** Após um arquivo da pasta ser ingerido (copiado para o CAS), o **original permanece na pasta** (não é movido nem removido). O dedup por hash garante que ele não seja reprocessado nos rescans seguintes — coerente com D-07 da Fase 1 (não tocar no original). O usuário limpa a pasta manualmente se quiser.

### Estabilização (arquivo parcialmente escrito)
- **D-04:** O evento do watcher é só **gatilho de candidatura**. O arquivo só é enfileirado após **estabilizar** (tamanho/mtime parados por uma janela). A **janela de estabilização é configurável (global)**, com um padrão sensível embutido — atende ao critério de "arquivo parcialmente escrito não é processado" (Pitfall 1) e a redes/arquivos grandes lentos.

### Separação de páginas
- **D-05:** A regra de separação é **por pasta** (D-02): "tudo que cair nesta pasta é separado a cada N páginas". Aplica-se a PDFs multi-página.
- **D-06:** **Cada bloco vira um Document independente** — com seu próprio conteúdo (novo PDF do bloco), próprio hash SHA-256, próprio estado e próprio percurso no pipeline. Ex.: PDF de 10 páginas em pasta "separar a cada 1" → 10 Documents. Caso de uso: scan contínuo de várias notas/boletos num arquivo só.
- **D-07:** O **arquivo original inteiro** continua armazenado no CAS (rede de segurança), além dos blocos. Imagens (JPG/PNG) são página única — não há separação, viram 1 Document.

### Deduplicação
- **D-08:** Dedup é **global e para sempre, por conteúdo** (mesmo hash SHA-256 já visto em qualquer pasta, a qualquer momento = duplicata, não reprocessa nem cobra). Alinhado ao `documents.content_hash` único global já existente (Fase 1) e a PROC-03 (idempotência).
- **D-09:** O dedup deve ser checado no **hash do arquivo ORIGINAL (antes de separar)**, para que rescans da pasta (onde o original permanece — D-03) **não re-separem** o documento. Implicação de schema a resolver no planejamento: hoje `content_hash` único existe em `documents`, mas os Documents são os **blocos** (D-06) — é preciso um registro/gate do hash do original (pré-split) distinto do hash dos blocos. (Ver `<code_context>`.)
- **D-10:** Comportamento ao detectar duplicata: **ignora sem reprocessar/cobrar, mas com visibilidade na UI** — um **contador/indicador de "duplicados ignorados"** (além de registro em log/auditoria). Como o rescan da pasta gera duplicatas rotineiramente (D-03), não deve poluir a lista principal.

### Fila assíncrona
- **D-11:** Fila **in-process, persistida em SQLite, sem broker externo** (constraint Windows/single-tenant da Fase 1). Worker em background com **retry + backoff**, **idempotência por hash + etapa** (não duplica trabalho nem chamadas após retry/crash — PROC-02/PROC-03). Reaproveita a máquina de estados e o `last_completed_step` da Fase 1.

### UI desta fase
- **D-12:** A UI da Fase 2 tem três peças: (1) **gerenciador de pastas monitoradas** (adicionar/editar/remover; caminho + páginas/bloco) — D-02; (2) **lista de documentos com estado** (nome, estado, pasta de origem, data), atualizada por **polling** — suficiente para "ver o documento entrar na fila"; (3) **contador/indicador de duplicados ignorados** — D-10. Sem tela de upload.

### Claude's Discretion
- Estrutura concreta da(s) tabela(s) de fila/jobs e da config de pastas; algoritmo de polling/backoff; nº máximo de tentativas antes de `FALHA`; concorrência do worker.
- Lib do watcher (preferência do projeto: **watchfiles** sobre watchdog) e mecanismo concreto de detecção de estabilidade no Windows (quiescência por size/mtime + teste de lock).
- Lib de split de PDF (pesquisa sugere **pikepdf** MPL; atentar à licença AGPL do PyMuPDF — relevante a partir da Fase 3).
- Como o gate de dedup do **original pré-split** (D-09) é modelado em relação ao schema atual (`documents.content_hash`).
- Onde, na máquina de estados, o documento "para" ao fim do pipeline da Fase 2 (ingestão+split concluídos, aguardando extração da Fase 3) — **não** marcar `CONCLUIDO` prematuramente; ver Integration Points.
- Tratamento de arquivos com extensão não suportada na pasta (PDF/JPG/PNG aceitos — ING-04): no v1, ignorar silenciosamente (quarentena é Fase 5).
- Valor padrão da janela de estabilização (D-04) e padrão de separação por pasta (sugestão: "não separar" como padrão ao criar a pasta).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Projeto e escopo
- `.planning/PROJECT.md` — contexto do produto, constraints (Windows primário, single-tenant, fila in-process sem broker, integridade de arquivos).
- `.planning/REQUIREMENTS.md` — requisitos v1; **esta fase cobre ING-02, ING-04, ING-05, ING-06, PROC-02, PROC-03** (ING-01 e ING-03 removidos nesta discussão — atualizar o doc).
- `.planning/ROADMAP.md` §"Phase 2" — objetivo e critérios de sucesso (critérios 1 e 3 precisam de ajuste após a remoção de upload/CLI).

### Pesquisa (informa stack e armadilhas desta fase)
- `.planning/research/ARCHITECTURE.md` — pipeline orientado a estado; Queue+Worker; Ingest/Dedup (hash→CAS); Page Splitter (`pypdf`/`pikepdf`); idempotência de job por hash+etapa; UI reflete o DB (polling/SSE). Atenção: a pesquisa recomenda `arq`+Redis e `watchdog`, **mas o constraint do projeto manda fila in-process SQLite e o projeto prefere watchfiles** — seguir o constraint.
- `.planning/research/PITFALLS.md` §"Pitfall 1" — processar arquivo parcialmente escrito (estabilização por quiescência + staging) — base de D-04.
- `.planning/research/STACK.md` — watchfiles (hot folder), pikepdf (split, MPL), alerta de licença AGPL do PyMuPDF (Fase 3), fila SQLite in-process como variante sem Redis.
- `.planning/research/SUMMARY.md` / `.planning/STATE.md` §"Blockers/Concerns" — "fila in-process SQLite sem lib consagrada: validar polling de tabela próprio (Fase 2)".

### Fundação da Fase 1 (reuso direto — ver `<code_context>`)
- `.planning/phases/01-funda-o-de-estado-e-storage/01-CONTEXT.md` — D-01 (pasta de dados única), D-04/D-05/D-06 (estados + marcador interno), D-07/D-08 (CAS copia o original, mantém para sempre).

Sem ADRs/specs externos adicionais — decisões desta fase capturadas acima.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/storage/cas.py` — CAS por hash SHA-256: `store(src)` copia o arquivo e retorna o hash (idempotente por conteúdo), `exists(hash)`, `path_for`, `read_bytes`, `open_blob`. **A ingestão da hot folder usa `store` no original; o splitter usa `store` em cada bloco gerado.**
- `backend/app/pipeline/state_machine.py` — `transition(session, doc, to_state, completed_step)` (valida contra allowlist, falha sem corromper) e `mark_step(session, doc, step)` (só o marcador interno D-05). **O worker da fila avança os documentos por aqui.**
- `backend/app/pipeline/states.py` — `TRANSITIONS` (allowlist), `InvalidTransition`, `is_valid_transition`. RECEBIDO→PROCESSANDO já permitido; retry sai de FALHA→PROCESSANDO.
- `backend/app/models/document.py` — `Document` com `content_hash` (String(64), **unique global, index**), `state` (default RECEBIDO), `last_completed_step` (nullable), relação `pages`.
- `backend/app/models/page.py` — `Page` (document_id FK, page_number) — mínimo; conteúdo por página vem em fases futuras.
- `backend/app/config.py` — `Settings` (Pydantic) lido de env/`.env`; `data_dir` (pasta única). **A janela de estabilização global (D-04) pode entrar aqui; a config das pastas monitoradas vai para o banco (D-02), não para o env.**
- `backend/app/storage/db.py` — `Base`, `create_db_engine`, `get_session` (WAL no SQLite). Migrações via Alembic (`backend/alembic/`).

### Established Patterns
- **Camada atrás de interface única** (db, CAS). A fila deve seguir o mesmo: módulo de fila/worker isolável, sem acoplar à API/HTTP.
- **Schema só evolui via Alembic** (D-10 da Fase 1) — novas tabelas (jobs, pastas monitoradas, gate de hash original) entram por migração versionada, nunca `create_all`.
- **API fina**: rotas só validam/leem/configuram; a lógica de pipeline vive em `pipeline/`. A UI reflete o DB por polling (D-12).

### Integration Points
- **Dedup pré-split (D-09):** o schema atual tem `content_hash` único nos **blocos** (Documents). É preciso um gate para o hash do **original** (pré-split) para não re-separar nos rescans (D-03). Resolver o modelo no planejamento (ex.: tabela de "originais ingeridos por hash" ou coluna/registro próprio).
- **Estado terminal da Fase 2:** após ingestão+split, não há extração ainda (Fase 3). O worker **não deve marcar `CONCLUIDO`**; o documento fica em um ponto que sinaliza "ingerido/separado, aguardando extração". Decidir o estado/marcador exato sem violar a allowlist atual.
- **Config de pastas → watcher:** a UI grava pastas no banco; o watcher/worker lê essa config (e reage a mudanças) para saber o que monitorar e qual regra de split aplicar por pasta.
</code_context>

<specifics>
## Specific Ideas

- Modelo mental do usuário: "o usuário define uma pasta de entrada de documentos e a quantidade de páginas que quer; cria uma pasta onde todo documento que entrar é separado a cada 1 página, ou a cada 2, etc." → regra de separação **por pasta** (D-05).
- "Na verdade não iremos fazer upload manual, vamos trabalhar apenas com pastas" → ingestão folder-only (D-01).
- Caso de uso implícito da separação: um único arquivo escaneado contendo vários documentos (notas/boletos) — separar a cada N páginas para que cada documento siga o pipeline sozinho (D-06).
</specifics>

<deferred>
## Deferred Ideas

- **Upload manual pela interface (ING-01)** — removido do v1 por decisão do usuário (D-01). Reconsiderar em v2 se houver demanda. → atualizar REQUIREMENTS.md (mover para v2/Out of Scope).
- **Lote por linha de comando / backfill (ING-03)** — removido do v1 (D-01); útil para processar de uma vez uma pasta cheia de documentos antigos. Candidato natural a v2. → atualizar REQUIREMENTS.md.
- **Mover original para subpasta "processados"** — considerado e descartado no v1 (D-03 mantém o original no lugar); opção futura para manter a pasta de entrada limpa.
- **Janela de estabilização por pasta** (em vez de global) e **threshold/confiança por pasta** — v1 mantém estabilização global (D-04).

### Reviewed Todos (not folded)
None — sem todos pendentes (todo.match-phase retornou 0).
</deferred>

---

*Phase: 2-Ingestão e Fila Assíncrona*
*Context gathered: 2026-06-15*

# Phase 3: Extração Genérica via IA e Medição de Tokens - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Esta fase entrega o **núcleo do motor de extração**: pegar cada documento (bloco) que a Fase 2 deixou parado em `PROCESSANDO` / `last_completed_step="aguardando_extracao"` e extrair seus dados via **IA da OpenAI**, de forma **genérica** — sem ser dirigida por um template específico — aproveitando **texto nativo** de PDF quando existir (input mais barato à IA) e **medindo os tokens** consumidos por documento para apoiar a cobrança por consumo.

**Reframe importante desta discussão (modelo do usuário):** a extração é **genérica primeiro** — a IA lê o documento e devolve os dados que encontrar (pares `dado → valor` + texto integral + palpite de tipo). **Templates não dirigem a extração**; eles são construídos *a partir* do que a extração revelou (Fase 4: identificar o tipo pela presença de certos dados — "beneficiário + linha digitável + CNPJ + valor → boleto"; "dados do colaborador → holerite" — e escolher quais valores buscar). O custo-zero por padrão conhecido (buscar dado localmente sem IA) é a visão das Fases 4 (identifica) + 7 (resolve local).

**Cobre (escopo reduzido nesta discussão):** EXT-01 (texto nativo local), EXT-02 (extração genérica via IA), USE-02 / SC4 (medição de tokens).

**Re-escopado para a Fase 4 nesta discussão:** EXT-04 — "JSON Schema **derivado do template** + **validações de campo configuráveis**". No modelo do usuário não existe template na hora da extração; o modelo de template/campos, o schema derivado de template e as validações de campo dependem de campos definidos, que são da Fase 4. A saída da Fase 3 **continua estruturada** (JSON), mas com um **schema genérico**, não derivado de template.

> ⚠️ **Ação de manutenção pendente (fora do CONTEXT):** atualizar `.planning/REQUIREMENTS.md` e `.planning/ROADMAP.md` para mover EXT-04 (schema derivado de template + validações de campo) da Fase 3 → Fase 4, e ajustar o critério de sucesso 2 da Fase 3 (que hoje fala em "JSON Schema derivado do template" e "validações de campo configuráveis"). Análogo ao re-escopo ING-01/ING-03 da Fase 2. Esta discussão registra a decisão; a edição dos docs é passo separado.

**Não inclui:** templates/sub-templates, classificação/identificação (Fase 4); score de confiança, fila de revisão humana, quarentena visível (Fase 5); automações de arquivo (Fase 6); parsing determinístico de tipos conhecidos e roteamento de custo determinístico→nativo→IA / EXT-03, EXT-05 (Fase 7).
</domain>

<decisions>
## Implementation Decisions

### Modelo de extração (genérica, não dirigida por template)
- **D-01:** A extração da Fase 3 é **genérica**: a IA lê o documento e devolve os dados que encontrar, sem template informando "extraia X, Y, Z". É o caminho de descoberta e o *fallback* universal do motor.
- **D-02:** A saída da IA é **estruturada (JSON) com schema genérico**: um conjunto de pares **`dado → valor`** de tudo que a IA identificar (ex.: `beneficiario: ...`, `linha_digitavel: ...`, `cnpj: ...`, `valor_total: ...`), **mais o texto integral** lido, **mais um palpite de tipo de documento com confiança**. É a base sobre a qual a Fase 4 cria templates/identificação.
- **D-03:** A extração fica **atrás de um roteador/interface** — nunca "sempre chama a IA" cravado. Esse seam permite a Fase 4 (template casado) e a Fase 7 (determinístico → nativo → IA) plugarem o atalho local **sem reescrever o motor**. É o ponto de costura arquitetural mais importante da fase.

### Caminho de custo (texto nativo vs IA) — alavanca do EXT-01 nesta fase
- **D-04:** Como tudo na Fase 3 é documento "novo" (sem layout conhecido ainda), a extração usa IA. A alavanca de custo *aqui* é: **PDF com texto nativo → manda o TEXTO à IA** (input de texto, barato); **escaneado / imagem → render da página → IA por visão** (caro). A IA ainda estrutura os dados em ambos os casos.
- **D-05:** O **custo-zero por layout/padrão conhecido** (identificar localmente e buscar o dado sem IA) **não é desta fase** — é Fase 4 (identifica o padrão) + Fase 7 (resolve local sobre o texto nativo / determinístico). A Fase 3 só não pode bloquear isso (ver D-03).
- **D-06:** Para a Fase 4/7 poderem "criar padrões para buscar os dados", a Fase 3 **persiste o texto nativo extraído e o resultado da extração** ligados ao documento. Sem guardar esse material, não há base para construir layouts/templates depois.

### Destino do documento após a extração (fronteira com Fases 4 e 5)
- **D-07:** Extração com **sucesso** → documento fica em `PROCESSANDO` com `last_completed_step = "extraido"` (mesmo padrão da Fase 2). **Nunca `CONCLUIDO`** — `CONCLUIDO` significa fim do pipeline (após automação, Fase 6). Aguarda a classificação da Fase 4.
- **D-08:** Extração com **falha** (IA erra/recusa, ou esgota retries) → a fila faz **retry/backoff** (mecanismo da Fase 2); ao esgotar as tentativas o documento vai a **`FALHA`** (dead-letter, re-tentável; o CAS preserva o original). Quarentena visível/resolúvel e revisão humana são Fase 5.
- **D-09:** Não há **gate de qualidade** na Fase 3: uma extração "fraca"/incerta ainda assim **persiste o resultado** e segue para `extraido`. Score de confiança e fila de revisão são Fase 5.

### Medição de tokens (SC4 / USE-02)
- **D-10:** Cada chamada à IA registra **prompt_tokens + completion_tokens** lidos de `response.usage`, gravados no modelo `Usage` (já existe) ligado ao `Document`, com `step="extract"`. Base da cobrança por consumo. Painel/relatório de consumo na UI é v2 (INT2-02) — aqui só persistir.

### Licença da lib de PDF
- **D-11:** Usar **PyMuPDF (fitz)** para texto nativo + render de página→imagem. O produto será de **uso interno/pessoal** (não vendido/distribuído — ver `<specifics>`), então a AGPL **não impõe ônus** (sem obrigação de abrir código nem licença comercial). É a lib mais completa para o caso. **Se um dia o uso virar distribuição/venda, revisitar** (fallback permissivo documentado em `<deferred>`).

### Claude's Discretion
- Estrutura concreta do **novo modelo `Extraction`** (não existe ainda) e o **formato exato do schema genérico** da saída da IA (modelo Pydantic → JSON Schema via Structured Outputs). Persistir dados extraídos + texto nativo + palpite de tipo via Alembic.
- **Tipos de campo** ("você decide"): no modelo genérico da Fase 3 a saída é `dado → valor`; tipagem por campo é conceito de template (Fase 4). Manter a saída flexível e extensível.
- **Validações:** o usuário escolheu "aplicar e marcar válido/inválido", mas validações de campo dependem de campos definidos por template → **migram para a Fase 4** (ver re-escopo de EXT-04 no `<domain>`). Na Fase 3, a conformidade ao schema genérico já é garantida pelos Structured Outputs; sem validação de domínio (DV de CNPJ etc.) aqui.
- **Heurística "tem texto nativo suficiente"** (decidir texto vs render por página).
- **Modelo OpenAI** específico (confirmar o vigente na conta — família `gpt-4o`/sucessor com visão + Structured Outputs) e parâmetros; expor em `config.py` como os tunables da fila.
- **Granularidade da extração** de um bloco multi-página (sugestão: 1 chamada por `Document`, enviando todas as páginas do bloco). Decidir no planejamento.
- **Enfileiramento e dispatch da extração** por `step` (ver Integration Points): como o job `step="extract"` é criado após a ingestão e como o worker o despacha; chave de idempotência da extração (por `content_hash` do bloco).
- Tratamento de **chave OpenAI ausente/inválida** (a config já guarda como `SecretStr`, sem tela no v1 — D-03 da Fase 1).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Projeto e escopo
- `.planning/PROJECT.md` — contexto, constraints (Windows, single-tenant, OpenAI, LGPD, integridade de arquivos). ⚠️ Ver premissa "uso interno" em `<specifics>`/`<deferred>` que diverge de "produto vendido".
- `.planning/REQUIREMENTS.md` — esta fase cobre **EXT-01, EXT-02, USE-02**; **EXT-04 re-escopado para a Fase 4** nesta discussão (atualizar o doc).
- `.planning/ROADMAP.md` §"Phase 3" — objetivo e critérios de sucesso (critério 2 precisa de ajuste após mover EXT-04 → Fase 4).

### CLAUDE.md (stack prescritiva — alta confiança)
- `CLAUDE.md` §"Decisões Críticas (4) OpenAI" — **Responses API (`client.responses.parse`) + Structured Outputs** com modelo Pydantic como `text_format`; visão via `input_image` (PyMuPDF → PNG/JPEG); ler `response.usage` para tokens. §"Resumo Prescritivo" — openai 2.41.x, PyMuPDF 1.27.x, pydantic 2.13.x.

### Pesquisa (informa stack e armadilhas desta fase)
- `.planning/research/STACK.md` — OpenAI SDK / Responses API / Structured Outputs; PyMuPDF para texto nativo + render; **alerta de licença AGPL do PyMuPDF** (decidido em D-11 — uso interno, sem ônus).
- `.planning/research/ARCHITECTURE.md` — pipeline orientado a estado; fronteiras de componentes (o roteador/seam de D-03 deve respeitar isso).
- `.planning/research/PITFALLS.md` — idempotência por hash+etapa; chamadas à IA com retry/backoff (não chamar OpenAI síncrono em loop no request).

### Fundação das Fases 1–2 (reuso direto — ver `<code_context>`)
- `.planning/phases/01-funda-o-de-estado-e-storage/01-CONTEXT.md` — D-04/D-05 (estados de topo + marcador interno `last_completed_step`), D-03 (chave OpenAI por config, sem tela), D-10 (schema só via Alembic).
- `.planning/phases/02-ingest-o-e-fila-ass-ncrona/02-CONTEXT.md` — D-11 (fila in-process SQLite, retry/backoff, idempotência por hash+etapa), estado terminal "aguardando_extracao" onde a Fase 3 começa.

Sem ADRs/specs externos adicionais — decisões desta fase capturadas acima.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/models/usage.py` — `Usage(document_id, step, prompt_tokens, completion_tokens, created_at)` **já existe** (D-10). A extração grava aqui o `response.usage` com `step="extract"`.
- `backend/app/config.py` — `Settings` com `openai_api_key: SecretStr` (nunca logado). Modelo/params OpenAI entram aqui, como os tunables `queue_*`.
- `backend/app/pipeline/ingest_stage.py` — define `AWAITING_EXTRACTION_STEP = "aguardando_extracao"`; cada bloco termina em `PROCESSANDO` aguardando extração. **Padrão a espelhar:** um `extract_stage` isolável (sem HTTP), idempotente, commit atômico.
- `backend/app/pipeline/state_machine.py` — `transition(session, doc, to_state, completed_step)`. A extração avança o documento por aqui (set marcador `"extraido"`; FALHA via `transition`, nunca `doc.state` direto).
- `backend/app/pipeline/states.py` — allowlist: `PROCESSANDO → {EM_REVISAO, CONCLUIDO, QUARENTENA, FALHA}`. `PROCESSANDO→FALHA` já permitido (D-08). Não precisa de novo estado de topo (marcador interno cobre "extraido", D-05/Fase 1).
- `backend/app/queue/repo.py` + `worker.py` — fila durável; claim atômico/backoff/resume; idempotência por `(original_hash, step)`. Reusar para o job de extração.
- `backend/app/storage/cas.py` — `read_bytes`/`open_blob`/`path_for` por `content_hash`: a extração lê o bloco do CAS para extrair texto nativo (PyMuPDF) ou renderizar.
- `backend/app/models/document.py` — `content_hash`, `state`, `last_completed_step`, `origin_original_id`. `relationship usages` já mapeado.
- `backend/app/models/page.py` — mínimo (document_id, page_number). Candidato a guardar texto nativo por página (decisão de schema — discretion).

### Established Patterns
- **Camada atrás de interface** (db, CAS, fila). A extração deve seguir: `extract_stage`/cliente OpenAI isoláveis, sem acoplar à API/HTTP. O **roteador de extração (D-03)** é a interface que Fases 4/7 estendem.
- **Schema só evolui via Alembic** (D-10): novo modelo `Extraction` (+ eventual coluna de texto nativo) entra por migração versionada (próxima: `0003`), nunca `create_all`.
- **API fina + UI reflete o DB por polling** (Fase 2). Exposição dos dados extraídos / status na UI segue esse padrão.
- **Idempotência + atomicidade** (PROC-03/CR-02): trabalho por `step`, resume-safe, commit único; chamadas à IA com retry/backoff via fila (não síncrono no request).

### Integration Points
- **Enfileirar a extração:** hoje `ingest_stage` deixa os blocos em `"aguardando_extracao"` mas **não enfileira** job de extração. A Fase 3 precisa criar jobs `step="extract"` (por **bloco/`Document`**, não por original) e o `worker._process_job_blocking` precisa **despachar por `step`** (`ingest` vs `extract`). A constraint `uq_jobs_hash_step` é `(original_hash, step)` — extração é por bloco (`Document.content_hash`); resolver a chave de idempotência da extração no planejamento (usar o hash do bloco como identidade do job de extract, ou ajustar o schema da fila).
- **Persistir resultado:** criar modelo `Extraction` (dados `dado→valor` em JSON + texto nativo + palpite de tipo + FK documento). Não existe ainda — via Alembic.
- **Detecção nativo vs escaneado:** heurística sobre o bloco (quantidade de texto extraível via PyMuPDF por página) decide enviar texto (barato) vs render+visão (D-04).
- **Gravar tokens:** ler `response.usage` por chamada e gravar em `Usage` (`step="extract"`, ligado ao `Document`) — D-10.
</code_context>

<specifics>
## Specific Ideas

- **Modelo mental do usuário (extração → template, não template → extração):** "a ideia é que os dados sejam extraídos e a partir dos dados extraídos, criaremos templates para buscarmos algum dado." Ex.: tem nota fiscal → buscar número da nota e CNPJ; boleto → buscar beneficiário; holerite → buscar nome do colaborador e valor total. "A ideia do sistema é criar templates para identificar documentos" (presença de dados → tipo). [→ Fase 4]
- **Custo é o motor da feature de template:** "criando o template, descobrindo que aquele padrão é nota fiscal/boleto/holerite, a gente consegue criar padrões e buscar dados do documento sem usar IA... assim eu evito gastar." Ex.: beneficiário + CNPJ + linha digitável + valor → boleto → tratativa local, custo 0. [→ Fases 4 + 7]
- "Se já tivermos um layout para um documento e conseguirmos identificar os dados antes de enviar para a IA é melhor, pq aí temos custo 0. No caso de PDF que conseguimos extrair local, podemos criar padrões para buscar os dados, evitando enviar texto para a IA." [→ Fases 4 + 7]
- **Uso interno/pessoal:** "eu não vou vender o produto, irei usar internamente... vamos usar [PyMuPDF] para uso pessoal." Base da decisão D-11. ⚠️ Diverge do PROJECT.md ("produto vendido para empresas") — ver `<deferred>`.
</specifics>

<deferred>
## Deferred Ideas

- **Modelo de template/campos + schema derivado de template + validações de campo configuráveis (EXT-04)** → **Fase 4**. Re-escopado nesta discussão; atualizar REQUIREMENTS.md/ROADMAP.md (passo de manutenção à parte).
- **Identificação/classificação por presença de dados** (boleto = beneficiário+linha digitável+CNPJ+valor; holerite = dados do colaborador) → **Fase 4** (TPL-03).
- **Extração local custo-zero por layout/padrão conhecido** + roteamento determinístico→texto nativo→IA (EXT-03, EXT-05) → **Fase 7**. A Fase 3 deixa o seam pronto (D-03).
- **Validações de domínio** (DV de CNPJ/Módulo 11, datas plausíveis, etc.) e marcar campo válido/inválido → **Fase 4/5** (dependem de campos de template; o usuário queria "aplicar e marcar válido/inválido").
- **Painel de consumo de tokens/custo por período na UI** (INT2-02) → v2. Fase 3 só persiste tokens.
- **Stack permissiva de PDF** (pypdfium2 BSD + pdfplumber MIT) — fallback documentado **caso o uso mude de interno para distribuição/venda** (revisita D-11).
- ⚠️ **Premissa a confirmar (meta, fora da Fase 3): "uso interno" vs "produto vendido".** A fala do usuário ("não vou vender, uso interno") contradiz PROJECT.md/CLAUDE.md (vendido como produto, chave por cliente, cobrança por consumo, distribuição/atualização por cliente na Fase 8, postura LGPD do que sai da máquina). Recomenda-se, num passo à parte, decidir se PROJECT.md/REQUIREMENTS mudam para "uso interno" — relaxa especialmente a Fase 8 e a postura LGPD/multi-instância. Não afeta as decisões de implementação da Fase 3.

### Reviewed Todos (not folded)
None — `todo.match-phase` retornou 0.
</deferred>

---

*Phase: 3-Extração Genérica via IA e Medição de Tokens*
*Context gathered: 2026-06-16*
</content>
</invoke>

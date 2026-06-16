# Phase 4: Templates, Sub-templates e Classificação - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Esta fase entrega o **construtor de templates schema-first** e a **classificação automática** de cada documento contra eles. O usuário cria, no app, templates por **tipo de documento** declarando os **campos a extrair** (nome, tipo opcional, validações, dica) e os **sinais identificadores** do tipo. O sistema pega cada documento que a Fase 3 deixou em `PROCESSANDO` / `last_completed_step="extraido"`, **classifica** contra os templates disponíveis (híbrido regras→IA), **preenche os campos do template** a partir do que já foi extraído (EXT-04), **valida e normaliza** esses campos, e manda para **quarentena** o que não casa com nenhum template.

**Reframe importante desta discussão:** os **sub-templates (TPL-02) saem da Fase 4**. O que o usuário imaginava como "sub-template por cliente/emissor" é, na essência, **roteamento condicional de automação** ("nota fiscal do cliente Y → pasta Documentos"; "holerite > R$ 3.000 → pasta análise"). Como o que muda entre as variações **não é a extração nem os campos** (continua o mesmo tipo, mesmos campos) e sim **qual automação roda**, isso vira uma **lista de regras condicionais sobre os campos extraídos** que pertence à **camada de automação (Fase 6)**, não um segundo tipo de documento. TPL-02 é re-escopado **Fase 4 → Fase 6** (ver `<deferred>` e a ação de manutenção abaixo).

**Cobre:** TPL-01 (construtor schema-first de campos), TPL-03 (classificação automática), TPL-04 (não casa → quarentena), EXT-04 (saída estruturada conforme schema **derivado do template** + validações de campo configuráveis, re-escopado da Fase 3).

> ⚠️ **Ação de manutenção pendente (fora do CONTEXT, passo à parte):** atualizar `.planning/ROADMAP.md` (remover sub-templates do **Goal** e do **Success Criterion 2** da Fase 4; adicionar "regras condicionais de tratativa" ao escopo da Fase 6) e `.planning/REQUIREMENTS.md` (mover **TPL-02** da Fase 4 → Fase 6 na Traceability; ajustar a descrição de TPL-02 para "regras condicionais de automação por cliente/emissor/valor"). Análogo aos re-escopos ING-01/ING-03 (Fase 2) e EXT-04 (Fase 3). Esta discussão **registra a decisão**; a edição dos docs é separada.

**Não inclui:**
- **Sub-templates / tratativas condicionais por cliente/valor (TPL-02)** → **Fase 6** (regras condicionais de automação).
- **Score de confiança determinístico, limiar configurável, fila de revisão humana lado-a-lado, quarentena visível/resolúvel (REV-01..05)** → **Fase 5**. A Fase 4 só **marca** campos válido/inválido e **vincula** o template; quem consome essas marcas (score/limiar/fila) é a Fase 5. A quarentena da Fase 4 é só o **estado** `QUARENTENA` para "não casou" (TPL-04); a tela/resolução é Fase 5.
- **Automações de arquivo (renomear/mover), dry-run, undo, anti-colisão (AUT-01..06)** e as **regras condicionais de tratativa** → **Fase 6**.
- **Roteamento determinístico de tipos conhecidos / extração local custo-zero por layout (EXT-03, EXT-05)** → **Fase 7**.

</domain>

<decisions>
## Implementation Decisions

### Classificação (documento ↔ template) — TPL-03
- **D-01:** A classificação é **híbrida regras→IA**: tenta casar por **regras locais primeiro** (custo 0, sobre os dados que a Fase 3 já extraiu); se nada casa com confiança suficiente, a **IA desempata** pelo contexto. Aproveita o `doc_type_guess` que a Fase 3 já produz como atalho. Materializa parte da visão de custo-zero já aqui, sem perder robustez em documentos variados.
- **D-02:** Cada template declara **sinais identificadores explícitos** do tipo (ex.: "tem linha digitável + CNPJ + valor" = boleto). Os sinais alimentam tanto o casamento por regras quanto servem de dica para a IA no desempate. Materializa o modelo mental da Fase 3 ("o template identifica o tipo pela presença de certos dados").
- **D-03:** **Nenhum template casa → `QUARENTENA`** (TPL-04). **Múltiplos casam → maior confiança vence** e segue; a revisão fina de casos duvidosos é da Fase 5. (No planejamento: definir o limiar/política de desempate, mandando o caso duvidoso para quarentena por padrão — nada classificado às cegas.)
- **D-04:** Documento que **casou com sucesso** fica em `PROCESSANDO` com marcador `last_completed_step="classificado"`, **vinculado ao template** que casou, aguardando revisão (Fase 5) e automação (Fase 6). Espelha o padrão `"extraido"` da Fase 3. **Nunca `CONCLUIDO`** aqui (terminal só após a automação da Fase 6).

### Preenchimento dos campos do template (EXT-04)
- **D-05:** Depois de classificar, os campos do template são preenchidos **mapeando os pares dado→valor que a Fase 3 já extraiu** (`fields_json` + `full_text` da `Extraction` genérica). **Custo 0 por padrão.**
- **D-06:** Se faltarem **campos obrigatórios** do template após o mapeamento, faz **UMA chamada dirigida à IA só para os campos faltantes** (não re-extrai tudo). Aproveita ao máximo o que já foi extraído e minimiza tokens.
- **D-07:** O resultado conforme o template (campos mapeados/validados/normalizados) é guardado num **novo registro ligado a `(documento, template)`**, **preservando intacta** a `Extraction` genérica bruta da Fase 3 (rastreabilidade + base auditável). Schema via Alembic (próxima migração; D-10 da Fase 1).

### Campos, tipos, validações e normalização (EXT-04)
- **D-08:** Cada campo do template tem um **tipo opcional** (padrão **texto/string**). Conjunto: **texto, número, data, moeda, CPF/CNPJ, booleano**. O tipo é só uma etiqueta que destrava validação/comparação/normalização — onde o usuário não se importa, fica texto (comportamento de hoje). "Deixar mais robusto" (decisão do usuário) = oferecer o conjunto comum tipado.
- **D-09:** Validações **configuráveis por campo**: **obrigatório** + **validação por tipo** (data parseável; número/moeda parseável; **DV de CPF/CNPJ via Módulo 11** determinístico próprio — já previsto no CLAUDE.md) + **regex opcional** para casos específicos.
- **D-10:** Quando uma validação falha: **aplica e marca o campo como válido/inválido** e persiste; o documento **segue sem aplicar automação**. Campo obrigatório inválido/faltante **não manda direto para quarentena** nesta fase — fica marcado e o consumo dessas marcas (score, limiar, fila de revisão) é da **Fase 5**. Princípio: nada aplicado às cegas, mas o gate de qualidade/decisão é a Fase 5.
- **D-11:** **Normalizar guardando bruto + normalizado**: mantém o valor como veio do documento (auditável) e guarda também o **valor normalizado** (data→ISO `YYYY-MM-DD`, moeda→decimal, CPF/CNPJ→só dígitos). Necessário para as **condições da Fase 6** (`valor > 3000`) e para renomear/mover com formato consistente. O valor bruto original nunca é perdido.

### Claude's Discretion
- Estrutura concreta dos novos modelos (template, campo de template, registro de campos preenchidos por `(documento, template)`) e o formato de persistência dos sinais identificadores (D-02) e das validações por campo (D-09) — via Alembic.
- **Formato dos sinais identificadores** (D-02): como o usuário declara "presença de X/Y/Z" na UI e como isso vira regra avaliável localmente + dica para a IA.
- **Limiar e política de desempate** da classificação (D-03): valor padrão do limiar de "casou com confiança", como tratar empates de confiança próximos (sugestão: caso duvidoso → quarentena). Limiar **por template** é v2 (INT2-05); aqui, se houver limiar, é global.
- **Como a classificação entra no pipeline:** novo `step="classify"` na fila durável (despacho por `step` no worker, como `ingest`/`extract`), criado após a extração; chave de idempotência por bloco (`Document.content_hash`). Confirmar no planejamento.
- **Prompt/schema da chamada de desempate por IA** (D-01) e da chamada dirigida de campos faltantes (D-06): modelo Pydantic → JSON Schema (Structured Outputs strict, list-of-pairs como na Fase 3); ler `response.usage` e gravar `Usage(step="classify")` (medição de tokens, mesma base da Fase 3).
- **UI do construtor de template** (TemplatesPage hoje é mock): declarar campos + tipos + validações + sinais; criar/editar/remover templates. Detalhe de UX (ex.: seed de campos a partir de um documento já extraído) fica a critério do planejamento/UI-phase, alinhado ao modelo mental "template a partir dos dados".

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Projeto e escopo
- `.planning/PROJECT.md` — contexto do produto, constraints (Windows primário, single-tenant, OpenAI, LGPD, integridade de arquivos, genérico). ⚠️ Premissa em aberto (Fase 3) "uso interno" vs "produto vendido" — carregada adiante, não bloqueia esta fase.
- `.planning/REQUIREMENTS.md` — esta fase cobre **TPL-01, TPL-03, TPL-04, EXT-04**; **TPL-02 re-escopado para a Fase 6** nesta discussão (atualizar a Traceability e a descrição). EXT-04 já havia sido movido Fase 3 → Fase 4.
- `.planning/ROADMAP.md` §"Phase 4" — objetivo e critérios de sucesso (Goal + SC2 precisam de ajuste após mover sub-templates → Fase 6); §"Phase 5" e §"Phase 6" para as fronteiras de revisão/automação.

### CLAUDE.md (stack prescritiva — alta confiança)
- `CLAUDE.md` §"Decisões Críticas (4) OpenAI" — **Responses API (`client.responses.parse`) + Structured Outputs** com modelo Pydantic como `text_format`; ler `response.usage` para tokens (chamada de desempate D-01 e de campos faltantes D-06 seguem o mesmo padrão da Fase 3).
- `CLAUDE.md` §"Decisões Críticas (3) NF-e / CNPJ" — **validar CNPJ/CPF com algoritmo de dígito verificador próprio (Módulo 11)**; não usar dependência externa (base de D-09).
- `CLAUDE.md` §"Resumo Prescritivo" — pydantic 2.13.x, openai 2.41.x, SQLAlchemy 2.0 + Alembic (novos modelos via migração).

### Pesquisa (informa stack e armadilhas)
- `.planning/research/ARCHITECTURE.md` — pipeline orientado a estado; fronteiras de componentes; UI reflete o DB por polling. A classificação respeita o seam de extração (D-03 da Fase 3) e o desenho de fila.
- `.planning/research/PITFALLS.md` — idempotência por hash+etapa; não chamar OpenAI síncrono no request (a chamada de desempate/faltantes vai pela fila com retry/backoff); Structured Outputs strict mode rejeita dict aberto (usar list-of-pairs, como a Fase 3).
- `.planning/research/STACK.md` — Pydantic como contrato da IA + validação; algoritmos Módulo 11 (CNPJ/CPF) domínio público.

### Fundação das Fases 1–3 (reuso direto — ver `<code_context>`)
- `.planning/phases/03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens/03-CONTEXT.md` — modelo mental "extração → template"; `Extraction` genérica (fields_json + full_text + doc_type_guess) como **base da classificação e do preenchimento**; seam `router.choose` (D-03) que a Fase 4 estende; medição de tokens via `Usage`.
- `.planning/phases/02-ingest-o-e-fila-ass-ncrona/02-CONTEXT.md` — fila in-process SQLite, retry/backoff, idempotência por hash+etapa (base do `step="classify"`).
- `.planning/phases/01-funda-o-de-estado-e-storage/01-CONTEXT.md` — D-04/D-05 (estados de topo + marcador interno `last_completed_step`); D-10 (schema só via Alembic).

Sem ADRs/specs externos adicionais — decisões desta fase capturadas acima.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/models/extraction.py` — `Extraction` por bloco com `fields_json` (pares dado→valor + confiança), `full_text`, `doc_type_guess` + `doc_type_confidence`, `route`. **Base da classificação (D-01/D-02) e do preenchimento dos campos (D-05/D-06).** UNIQUE(document_id) = 1 extração por bloco.
- `backend/app/extraction/schema.py` — `ExtractionResult`/`ExtractedField` (list-of-pairs, strict-safe). **Padrão a espelhar** nos schemas das chamadas de desempate (D-01) e de campos faltantes (D-06): nunca dict aberto; `description` guia o modelo.
- `backend/app/extraction/router.py` — seam `choose(blob)` (D-03 da Fase 3), o ponto onde a Fase 4 pluga o atalho local. Manter mínimo; não embutir lógica de classificação que mate o seam.
- `backend/app/extraction/openai_client.py` — Responses API + Structured Outputs + mapeamento de `usage` + tratamento de recusa. Reusar para as chamadas de classificação/faltantes.
- `backend/app/queue/repo.py` + `worker.py` — fila durável; claim atômico/backoff/resume; despacho por `step` (`ingest` vs `extract`). **Adicionar `step="classify"`** seguindo o mesmo padrão; idempotência por bloco.
- `backend/app/pipeline/state_machine.py` + `states.py` — `transition()` + allowlist. `PROCESSANDO → QUARENTENA` **já permitido** (TPL-04 / D-03); `QUARENTENA → PROCESSANDO` para reprocessar (Fase 5). Marcador `"classificado"` via marcador interno (D-04), não novo estado de topo.
- `backend/app/models/usage.py` — `Usage(document_id, step, prompt_tokens, completion_tokens)`. Gravar `step="classify"` nas chamadas pagas da Fase 4.
- `backend/app/config.py` — `Settings`; tunables do limiar de classificação e do modelo OpenAI entram aqui.
- `frontend/src/pages/TemplatesPage.tsx` + `frontend/src/data/mock.ts` — **TemplatesPage é mock** (lista de templates fixa). A Fase 4 substitui pelo construtor real fiado à API (TanStack Query + cliente fetch tipado, padrão da Fase 2).

### Established Patterns
- **Camada atrás de interface** (db, CAS, fila, extração). Classificação/preenchimento devem ser stages isoláveis (sem HTTP), idempotentes, commit atômico — espelhar `extract_stage` (Fase 3).
- **Schema só evolui via Alembic** (D-10): novos modelos (template, campo, campos preenchidos) entram por migração versionada, nunca `create_all`.
- **API fina + UI reflete o DB por polling**; tipos compartilhados via cliente gerado do OpenAPI.
- **Idempotência + atomicidade**: trabalho por `step`, resume-safe; chamadas pagas à IA via fila com retry/backoff, nunca síncronas no request; não re-chamar/re-cobrar (checar registro existente antes da chamada paga, como a Fase 3 faz com `Extraction`).
- **Structured Outputs strict**: list-of-pairs, nunca dict aberto; `description` Pydantic guia o modelo.

### Integration Points
- **Enfileirar a classificação:** hoje o `extract_stage` deixa o bloco em `PROCESSANDO`/`"extraido"` sem enfileirar o próximo passo. A Fase 4 cria jobs `step="classify"` (por bloco) após a extração e o worker despacha por `step`. Resolver a chave de idempotência (hash do bloco).
- **Persistir template + campos preenchidos:** novos modelos (template, campo de template, registro de campos por `(documento, template)`) via Alembic; FK para `documents` e relação com a `Extraction` genérica (D-07).
- **Classificar a partir da extração:** ler `Extraction.fields_json`/`full_text`/`doc_type_guess` do bloco; casar por regras (D-01/D-02) → desempate por IA quando necessário.
- **Validação determinística:** módulo próprio de DV de CPF/CNPJ (Módulo 11) + parsers de data/número/moeda para normalização (D-09/D-11). Candidato a módulo reutilizável (a Fase 7 também usará validação determinística).
- **Quarentena:** `transition(doc, QUARENTENA, ...)` quando nenhum template casa (D-03) — transição já na allowlist.

</code_context>

<specifics>
## Specific Ideas

- **Modelo mental do usuário (sub-template = automação condicional, não segundo tipo):** "tenho uma nota fiscal do cliente X e preciso enviar pra pasta no desktop; nota fiscal do cliente Y → pasta documentos. Holerite com valor > R$ 3.000 → pasta de análise; < R$ 3.000 → manda mensagem/e-mail pro colaborador." Conclusão da discussão: isso é **roteamento condicional de automação (Fase 6)**, não uma entidade sub-template na Fase 4. "Não sei se há real necessidade de criar sub-templates — foi algo que pensei na hora de estruturar."
- **Tipos de campo (esclarecimento do usuário):** "o cliente pode declarar qualquer coisa, mas geralmente vai ser texto, string, número; CPF/CNPJ seria uma string." → tipo **opcional**, padrão texto; tipo só destrava validação (DV de CNPJ), comparação numérica (Fase 6) e normalização. Usuário aceitou o conjunto tipado comum: "pode seguir assim mesmo, deixar mais robusto."
- **Custo como motor (herdado da Fase 3):** preferir resolver localmente (regras, mapeamento do que já foi extraído) e só chamar a IA no que sobra — daí D-01 (híbrido), D-05/D-06 (mapeia, IA só p/ faltantes).

</specifics>

<deferred>
## Deferred Ideas

- **Sub-templates / tratativas condicionais por cliente/emissor/valor (TPL-02)** → **Fase 6**, como **regras condicionais de automação** ("se <condição sobre campos extraídos> → ação"). Re-escopado nesta discussão; atualizar ROADMAP.md (Goal/SC2 da Fase 4; escopo da Fase 6) e REQUIREMENTS.md (Traceability TPL-02 → Fase 6).
- **Auto-identificar o cliente/sub-template pelo CNPJ sem configuração (INT2-01)** → v2. No v1, qualquer roteamento por emissor é via **condição declarada explicitamente** (Fase 6), não inteligência automática.
- **Limiar de confiança por template (em vez de global)** (INT2-05) → v2. A Fase 4 usa, se houver, um limiar global (discretion).
- **Score de confiança, limiar configurável, fila de revisão lado-a-lado, quarentena visível/resolúvel (REV-01..05)** → **Fase 5**. A Fase 4 só marca válido/inválido e vincula o template; o gate que decide o que vai para revisão é a Fase 5.
- **Extração local custo-zero por layout/padrão conhecido + roteamento determinístico (EXT-03, EXT-05)** → **Fase 7**. A Fase 4 já casa por sinais localmente (D-01), mas a resolução determinística de campos sobre o texto nativo (sem IA) é da Fase 7.
- **Correções da revisão humana virando hints/few-shot por template** (INT2-04) → v2.
- **Seed de campos do template a partir de um documento já extraído** (UX que materializa "template a partir dos dados") — considerar no planejamento/UI-phase; não é decisão travada.

### Reviewed Todos (not folded)
None — `todo.match-phase` retornou 0.

</deferred>

---

*Phase: 4-Templates, Sub-templates e Classificação*
*Context gathered: 2026-06-16*

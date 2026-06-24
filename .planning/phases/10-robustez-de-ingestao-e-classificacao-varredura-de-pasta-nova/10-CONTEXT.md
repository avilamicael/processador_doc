# Phase 10: Classificação robusta e reprocessamento - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Tornar a classificação por sinais menos frágil e permitir recuperar documentos da
quarentena sem re-ingerir. Entrega três capacidades (backlog itens 5 e 6):

1. **Matcher tolerante por normalização** — pré-processar o texto antes do casamento
   de sinais (acentos, quebras de linha, espaços, pontuação) para não mandar à
   quarentena por diferenças mecânicas.
2. **Ferramenta "testar sinais"** no construtor de templates — fazer upload de um
   documento de teste e ver quais sinais/grupos casam ou falham contra o texto real.
3. **Reprocessar/reclassificar automático** (sem forçar template) — re-rodar a
   detecção com os templates ATUAIS sobre docs em QUARENTENA e EM_REVISAO, por-doc e
   em lote.

**Fora de escopo (deferido):** varredura de pasta criada depois (item 2), re-ingerir
arquivos de split após remoção (item 7), limiar N-de-M / casamento parcial, e UX de
"negar/remover" na pré-visualização (ver Deferred Ideas).
</domain>

<decisions>
## Implementation Decisions

### Tolerância do matcher (Item 5)
- **D-01:** Tornar o casamento tolerante via **NORMALIZAÇÃO apenas** — NÃO adotar
  limiar N-de-M nesta fase. Manter a semântica atual E-de-todas-as-condições-do-grupo /
  OU-entre-grupos (`matcher.py:152-159`) e a confiança booleana; muda só o
  pré-processamento do texto antes do match.
- **D-02:** Normalização aplicada ao casamento de condições `texto`: (a) lowercase
  (já existe); (b) remover acentos (NFKD + drop combining — reusar o padrão de
  `_strip_accents` introduzido na Phase 9 em `naming.py`); (c) colapsar runs de
  espaço **e quebras de linha** em espaço único; (d) normalizar/neutralizar
  pontuação. O `value` do sinal **e** o `full_text` (haystack) passam pela MESMA
  normalização — senão o casamento fica assimétrico e falha.
- **D-03:** Interação com modo `regex`: normalizar o haystack pode quebrar regex que
  dependem de quebra de linha/acento. Decisão: a normalização vale para o modo
  `texto`; **preservar a semântica do `regex`** (a condição regex roda contra um
  haystack menos normalizado, p.ex. só lowercase como hoje). Detalhe exato a fechar
  no RESEARCH.
- **D-04:** Tradeoff **aceito conscientemente**: normalização sozinha NÃO resolve
  sinal com palavra trocada (ex.: sinal `NATUREZA DA OPERAÇÃO` vs texto real
  `NATUREZA DE OPERAÇÃO`). Esses casos são endereçados pela **ferramenta de testar
  sinais** (o usuário vê o sinal que falha e corrige o template). N-de-M fica
  deferido para fase futura se normalização + teste não bastarem.

### IA quando nenhum template casa (Item 5)
- **D-05:** Adicionar **toggle GLOBAL** (config, padrão **DESLIGADO**): "IA classifica
  quando nenhum template casa". Quando ligado e `matcher.decide` retorna `quarantine`
  por confiança 0.0 (nada casou), chamar a IA para tentar classificar **antes** de
  transicionar para QUARENTENA. Desligado = comportamento atual (quarentena direta).
  Custo explícito: cada doc não-casado vira 1 chamada de IA quando ligado.
- **D-06:** Preservar o **seam D-03** (`matcher.decide` separado e puro). O fallback
  de IA entra no `classify_stage`, não dentro do matcher. Reusar o caminho de
  IA já existente (hoje a IA desempata "ambiguous"; estender para "classificar quando
  nada casa").

### Ferramenta "testar sinais" (Item 5)
- **D-07:** A ferramenta no construtor de templates recebe **UPLOAD de um documento de
  teste**; o backend extrai o texto e roda os sinais do template contra ele,
  devolvendo o detalhamento **por-sinal e por-grupo** (casa/falha) — espelhando o
  diagnóstico manual feito no teste do piloto. Endpoint backend novo (preview de sinais).
- **D-08:** Custo da extração no teste: usar **texto NATIVO** do PDF (PyMuPDF, custo
  zero) por padrão. Se o documento de teste for escaneado (sem texto nativo), avisar
  que precisaria de IA — recomendação MVP: restringir a texto nativo na ferramenta
  (sem custo IA) OU avisar claramente. Fechar no RESEARCH/planning.
- **D-09:** A ferramenta usa a MESMA normalização (D-02) e o MESMO motor
  (`matcher._parse_groups` / `_template_matches` / `_condition_matches`) para que o
  resultado do teste seja **idêntico** ao da classificação real (sem reimplementar).

### Reprocessar/reclassificar (Item 6)
- **D-10:** Nova ação "reprocessar automático" (**sem forçar template**) que re-roda
  matcher→(IA)→filler com os templates ATUAIS. Estados elegíveis: **QUARENTENA e
  EM_REVISAO**. **Por-documento E em lote** (reprocessar todos do balde de uma vez).
- **D-11:** Mecânica: transicionar o doc para PROCESSANDO e re-enfileirar o passo
  `classify` **SEM** `forced_template_id` (≠ do `reclassify` atual que exige template,
  `documents.py:601`). `classify_stage` já recarrega os templates do DB a cada run
  (`stage.py:205`), então pega as edições. Reusar `_requeue` (`documents.py:549`) e o
  payload de classify.
- **D-12:** Em lote: aplicar sobre todos os docs de um balde (QUARENTENA/EM_REVISAO)
  da visão `/documents/attention`. Idempotente/seguro (re-enfileira classify).

### Claude's Discretion
- Conjunto exato de normalização de pontuação e a interação fina com o modo `regex` (D-03) → RESEARCH.
- Forma do endpoint de preview de sinais (multipart upload vs base64) e do(s) endpoint(s) de reprocess (single vs batch) → planning.
- Onde expor o toggle da IA-fallback na UI de configuração.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backlog / requisitos
- `.planning/notes/2026-06-24-melhorias-teste-usuario-final.md` — Itens 5 e 6 (sintomas reais, diagnóstico e referências de código). Item 7 (split) e Item 2 (varredura) deferidos.

### Motor de classificação
- `backend/app/classification/matcher.py` — sinais (grupos E/OU, confiança booleana, `decide`→matched/ambiguous/quarantine). **Onde a normalização (D-02) entra.**
- `backend/app/classification/stage.py` — `classify_stage` (matcher→decide→QUARENTENA; recarrega templates a cada run). **Onde o fallback de IA (D-05) e o reprocess se conectam.**
- `backend/app/models/template.py` — `signals_json` (forma canônica de sinais consumida pelo matcher).

### APIs (reprocessar + testar sinais)
- `backend/app/api/documents.py` — `reclassify`/`retry`/`attention`/`_requeue` (base do reprocessar; `reclassify` exige template, o novo NÃO).
- `backend/app/api/templates.py` — CRUD de templates (onde a ferramenta de testar sinais se conecta).

### Reuso da Phase 9
- `backend/app/automation/naming.py::_strip_accents` — padrão de remoção de acentos (NFKD + drop combining) a reusar na normalização.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `matcher._parse_groups` / `_template_matches` / `_condition_matches`: motor puro reusado tanto na classificação real quanto na ferramenta de teste (D-09).
- `naming._strip_accents` (Phase 9): remoção de acentos pronta para a normalização (D-02).
- `documents._requeue` + payload de classify: base para reprocessar (D-11).
- `classify_stage` já recarrega templates do DB a cada run: reprocessar pega as edições sem trabalho extra.

### Established Patterns
- **Dispatch explícito por etiqueta, nunca `eval`** (matcher `_condition_matches`) — manter na normalização e em qualquer parser novo.
- **Falha-fechada** (grupo vazio/sem sinais não casa; regex inválida não casa).
- **Seam D-03** (`matcher.decide` puro e separado) — preservar; o fallback de IA vive no `classify_stage`.
- **LGPD/V7** — NÃO logar `full_text` nem valores de sinal (vale também para a ferramenta de teste e o reprocess).

### Integration Points
- Novo endpoint de **preview de sinais** na templates API (upload → extrai texto nativo → roda sinais → resultado por-sinal/grupo).
- Novo(s) endpoint(s) de **reprocess** na documents API (QUARENTENA/EM_REVISAO, single + batch, sem forced_template_id).
- Novo **toggle de config** (IA classifica quando nada casa, padrão off) + leitura no `classify_stage`.
- Frontend: TemplatesPage (ferramenta de teste de sinais) + DocumentsPage/AttentionPage (botão reprocessar por-doc e em lote).
</code_context>

<specifics>
## Specific Ideas

- A ferramenta de testar sinais deve reproduzir EXATAMENTE o diagnóstico manual que o
  usuário fez no piloto (DANFE: 5 de 8 sinais casavam, 3 falhavam por "DA"≠"DE" e
  quebra de linha) — mostrar quais casam/falham é o valor central.
- Reprocessar resolve o fluxo "ajustei o template e o doc continua na quarentena" sem
  obrigar a deletar + re-ingerir o arquivo.
</specifics>

<deferred>
## Deferred Ideas

- **Pré-visualização (dry-run) só tem "Aplicar"** — falta "Negar/Pular" uma linha e
  "Remover" o documento. UX de dry-run/triagem, fora do escopo de classificação.
  → registrado como **Item 12** no backlog.
- **Limiar N-de-M / casamento parcial** — não adotado nesta fase (D-01). Revisitar se
  normalização + ferramenta de teste não bastarem.
- **IA classificar sempre (sem toggle)** — não escolhido; o toggle opt-in (D-05) cobre.
- **Itens 2 (varredura de pasta nova) e 7 (re-ingerir split)** — robustez de ingestão,
  movidos para fase futura ao estreitar a Phase 10.

</deferred>

---

*Phase: 10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova*
*Context gathered: 2026-06-24*

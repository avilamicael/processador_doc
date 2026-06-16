# Phase 5: Confiança, Revisão Humana e Quarentena - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

O usuário nunca confia cegamente na IA. Esta fase entrega: (1) um **indicador de confiança por documento** derivado de validação determinística pós-extração; (2) um **limiar configurável** que decide o que precisa de atenção humana; (3) uma **visão de gestão/triagem na web** que lista os documentos que precisam de atenção em 3 baldes (FALHA, QUARENTENA, EM_REVISAO) com o motivo, permitindo **resolver cada um de forma leve** (tentar de novo / atribuir template e reclassificar / corrigir valores de campo e aprovar).

**Reframe de visão (importante):** a web é uma ferramenta de **gestão/configuração e triagem de problemas**, NÃO de manuseio do documento. O usuário lida com os arquivos em si pelo **Windows Explorer**. Os **valores dos campos** extraídos são o dado que a Phase 6 usará para renomear/mover; corrigi-los na web é "corrigir o dado antes da automação", não "mexer no arquivo". Por isso **não há visualizador de documento (imagem/PDF embed) na web** nesta fase.

</domain>

<decisions>
## Implementation Decisions

### Indicador de confiança (REV-01)
- **D-01:** Confiança por documento = **fração de campos obrigatórios que passaram na validação determinística** (Módulo 11 CNPJ/CPF, data, moeda, regex do template). Campos obrigatórios inválidos OU faltantes derrubam o score. NÃO usar o auto-relato de confiança da IA como base (alinhado ao roadmap e ao blocker de pesquisa). A `confidence` do matcher (já persistida em `ClassificationResult`) é um sinal de classificação, separada deste indicador de qualidade de extração.
- **D-02:** Armazenar um **score 0–100%** (alimenta o limiar configurável) e **derivar um rótulo legível** (alta/média/baixa) para a UI. Não só categoria, não só número — ambos, com o número como fonte de verdade.

### Limiar e gatilho de revisão (REV-02 / REV-03)
- **D-03:** Limiar de confiança é **global, na config** (mesmo padrão dos tunables já existentes em `config.py`, ex.: `classify_match_threshold`). Limiar por-template é evolução futura (deferido).
- **D-04:** Um documento vai para **EM_REVISAO** quando: **confiança < limiar OU qualquer campo obrigatório inválido/faltante**. Garante que erros determinísticos sempre são revisados, mesmo com score geral alto.

### Modelo da web — "ativa, leve" (REV-03 / REV-04 / REV-05)
- **D-05:** A web tem **uma visão "Precisam de atenção"** listando os documentos sinalizados nos **3 baldes**, cada um com o **motivo**:
  - **FALHA** → ação **"tentar de novo"** (reprocessa via fila; transição `FALHA→PROCESSANDO` já existe na allowlist).
  - **QUARENTENA** → ação **"atribuir template + reclassificar"** (reclassifica via fila; transição `QUARENTENA→PROCESSANDO` já existe).
  - **EM_REVISAO** → **corrigir os valores dos campos inline** e **aprovar**.
- **D-06:** **Sem visualizador de documento na web** (imagem da página / embed do PDF / texto bruto lado-a-lado). Cortado de escopo por decisão de visão (ver `<deferred>` e a nota de tensão com o roadmap abaixo). A UI mostra motivo + valores de campo, não o documento.

### Aprovação e edição (REV-04)
- **D-07:** Aprovar um documento na revisão faz **EM_REVISAO → CONCLUIDO** (transição já na allowlist). CONCLUIDO = pronto; as automações de arquivo (renomear/mover) são a Phase 6. Aprovação só é permitida quando os campos obrigatórios estão válidos (após correção).
- **D-08:** Correção de campo: **atualiza `raw_value`/`normalized_value` do `FilledField`, revalida pelo tipo do campo (`validation/fields.py`), e marca a origem como "corrigido manualmente"** (auditabilidade + base para a confiança/aprovação). NÃO re-chama a IA (sem custo). Requer um marcador novo no modelo `FilledField` (ex.: coluna `manually_corrected`/origem).

### Resolução de quarentena (REV-05)
- **D-09:** Resolver quarentena = **atribuir um template manualmente e reclassificar via fila** (reusa matcher→filler→validação do `classify_stage` com o template forçado). Reaproveita todo o motor; o reprocesso é viabilizado pelo fix de encadeamento de fila feito ao fim da Phase 4.

### Claude's Discretion
- Forma exata de persistir o indicador de confiança (coluna em `documents` vs em `classification_results`) — decidir no planejamento.
- Layout/UX fino da visão "Precisam de atenção" (uma página única com seções por balde vs filtros) — o mock aprovado é o norte; refinar no `ui-phase`/planejamento.
- Mecânica de "forçar template" no `classify_stage` (parâmetro opcional vs novo caminho) — decisão de planejamento, desde que pule o matcher e use filler+validação.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Escopo e requisitos
- `.planning/ROADMAP.md` § "Phase 5: Confiança, Revisão Humana e Quarentena" — goal + success criteria.
- `.planning/REQUIREMENTS.md` — REV-01, REV-02, REV-03, REV-04, REV-05 (linhas 35-39).
- `.planning/PROJECT.md` — core value (não confiar cegamente na IA; integridade de arquivos).
- `.planning/phases/04-templates-sub-templates-e-classifica-o/04-VERIFICATION.md` — contexto do WARNING de encadeamento de fila (já corrigido) que viabiliza reprocesso/reclassificação.

### Código que esta fase estende (ler antes de planejar)
- `backend/app/classification/stage.py` — `classify_stage`: já marca cada campo `valid`/`invalid` + `invalid_reason`; base do indicador de confiança e do gatilho de revisão; ponto de extensão para "forçar template".
- `backend/app/validation/fields.py` — `validate_field` por tipo; reusar para revalidar valores corrigidos manualmente.
- `backend/app/pipeline/states.py` — `TRANSITIONS` já permite `PROCESSANDO→EM_REVISAO`, `EM_REVISAO→CONCLUIDO`, `QUARENTENA→PROCESSANDO`, `FALHA→PROCESSANDO` (allowlist construída antecipando esta fase).
- `backend/app/queue/worker.py` — fila + sweeps encadeados (extract→classify) já corrigidos; base de "tentar de novo" e "reclassificar".
- `backend/app/models/classification.py` — `ClassificationResult` (tem `confidence`) e `FilledField` (`raw_value`/`normalized_value`/`valid`/`invalid_reason`) — precisará de marcador de correção manual e/ou armazenamento do indicador.
- `backend/app/api/documents.py` e `backend/app/api/templates.py` — padrões de router/endpoint a espelhar para ações de revisão/resolução.
- `frontend/src/pages/DocumentsPage.tsx`, `frontend/src/hooks/useTemplates.ts`, `frontend/src/lib/api.ts` — padrões de página/hook/cliente para a visão "Precisam de atenção".
- `.planning/phases/04-templates-sub-templates-e-classifica-o/04-UI-SPEC.md` — design system TRAVADO a honrar na UI desta fase.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Máquina de estados (`states.py`/`state_machine.py`):** transições da Phase 5 JÁ existem na allowlist (EM_REVISAO, QUARENTENA→PROCESSANDO, FALHA→PROCESSANDO, EM_REVISAO→CONCLUIDO). Não precisa modelar estados novos.
- **`classify_stage` + `validation/fields.py`:** já produzem `valid`/`invalid_reason` por campo — o indicador de confiança (D-01) é um cálculo derivado disso; a revalidação de correções (D-08) reusa `validate_field`.
- **Fila + sweeps encadeados (`worker.py`):** "tentar de novo" e "reclassificar" são reenfileiramentos; o encadeamento runtime já funciona (fix do fim da Phase 4).
- **Padrões de API/UI da Phase 4:** routers finos (templates/documents) e hooks TanStack Query são o molde para os endpoints/visão de revisão.

### Established Patterns
- Commit atômico único por stage; idempotência por chave (UNIQUE) — manter ao adicionar "reclassificar com template forçado".
- Tunables em `config.py` com `AliasChoices`/env — o limiar global (D-03) segue esse padrão.
- Estado de topo persistido + marcador interno (`last_completed_step`) — o cálculo de confiança e o roteamento para EM_REVISAO entram no `classify_stage` mantendo o commit único.

### Integration Points
- `classify_stage`: ao final, calcular confiança (D-01) e decidir CONCLUIDO vs EM_REVISAO vs QUARENTENA (D-04) — substitui o atual "permanece PROCESSANDO+classificado" quando há limiar/validação.
- Novos endpoints de ação: retry (FALHA), reclassify-com-template (QUARENTENA), patch de campos + approve (EM_REVISAO).
- `FilledField`: nova marca de correção manual (D-08); armazenamento do score de confiança por documento (Discretion).

</code_context>

<specifics>
## Specific Ideas

- Mock aprovado da visão "Precisam de atenção" (3 baldes com motivo + ações leves) — é o norte de UX:
  - QUARENTENA: `[ Atribuir template ▾ ] [ Reclassificar ]`
  - EM_REVISAO (conf. %): campo inválido com input de correção inline + `[ Aprovar → concluído ]`
  - FALHA: motivo + `[ Tentar de novo ]`
- Exemplo real validado nesta sessão: `exames_duda.pdf` classificado contra template de exame, CPF validado por Módulo 11, data normalizada pt-BR→ISO — base concreta dos campos que entram na revisão/confiança.

</specifics>

<deferred>
## Deferred Ideas

- **Visualizador de documento na web** (render da página/embed do PDF lado-a-lado) — explicitamente fora de escopo: o usuário manuseia os arquivos pelo Windows Explorer; a web é gestão/triagem. Reconsiderar só se a gestão de documentos na web evoluir.
- **Limiar de confiança por template** — v1 usa limiar global (D-03); por-template é evolução futura (exigiria UI no construtor de templates).
- **Combinar auto-relato de confiança da IA no indicador** — rejeitado para v1 (roadmap quer base determinística).
- **Tensão com a redação do roadmap (REV-03):** o REV-03 diz "fila de revisão com **visualização do documento** ao lado dos campos editáveis". Por D-06, a parte "visualização do documento" cai; mantém-se "campos editáveis + motivo". Recomenda-se ajustar a redação de REV-03 (e revisar REV-04) no ROADMAP/REQUIREMENTS para refletir o modelo "web ativa, leve" antes/durante o planejamento.

</deferred>

---

*Phase: 5-Confiança, Revisão Humana e Quarentena*
*Context gathered: 2026-06-16*

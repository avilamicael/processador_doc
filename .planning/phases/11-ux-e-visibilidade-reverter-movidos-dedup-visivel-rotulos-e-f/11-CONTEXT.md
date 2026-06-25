# Phase 11: UX e visibilidade - Context

**Gathered:** 2026-06-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Expor na UI e corrigir a apresentação de capacidades que **já existem no backend** — sem criar capacidades novas de motor. Cinco itens do backlog do teste de usuário final (`.planning/notes/2026-06-24-melhorias-teste-usuario-final.md`):

- **Item 1** — Reverter documentos já movidos, pela tela, a qualquer momento.
- **Item 3** — Tornar o dedup (duplicata ignorada) explícito/visível na UI.
- **Item 4** — Condição "Valor de campo" da automação usar seletor de campos em vez de texto livre.
- **Item 8** — Rótulo: doc classificado-e-pronto não pode aparecer como "processando".
- **Item 9** — Timestamps com fuso correto (hoje exibidos 3h adiantados).

**Fora de escopo:** novos motores de classificação/automação; histórico de lotes de aplicação; rastreio de dedup por-evento; ações por-linha no dry-run (item 12); correções de ingestão (itens 2, 7). Ver Deferred Ideas.
</domain>

<decisions>
## Implementation Decisions

### Item 1 — Reverter movidos (escopo por-documento)
- **D-01:** Undo persistente exposto **por documento**, no detalhe do documento concluído — mostrar origem→destino (lido do audit) e botão **"Reverter para a origem"** → `POST /automations/undo` com `document_id` (já existe e restaura do CAS, reabre CONCLUIDO→PROCESSANDO).
- **D-02:** Backend ganha **um endpoint GET novo** para listar o que foi aplicado a um documento (origem/destino/status/run_id, lido do `AuditLog`) — alimenta a tela de detalhe. Esse endpoint **ainda não existe**.
- **D-03:** **NÃO** fazer histórico de aplicações por lote (`run_id`) nem persistir o `undoRunId` do dry-run nesta fase — adiado (ver Deferred). O caso central é "desfazer um doc movido a qualquer momento".

### Item 3 — Dedup visível (win barato)
- **D-04:** `POST /rescan` passa a retornar também `skipped_duplicates` (quantos foram vistos e pulados por hash), além de `enqueued`.
- **D-05:** Frontend mostra **toast pós-varredura**: "X novos enfileirados, Y pulados por já existirem". Mata a percepção de "/rescan não faz nada".
- **D-06:** **NÃO** persistir/expor eventos de dedup por-ocorrência (qual arquivo, de qual pasta, contra qual doc) nem lista/filtro "Duplicatas" — adiado (ver Deferred). Hoje só existe o contador agregado `IngestedOriginal.duplicate_hits`.

### Item 4 — Seletor de campo na condição "Valor de campo" (exigir template fixado)
- **D-07:** Trocar o `<input>` de texto livre do nome do campo por um **`<select>`/dropdown estrito dos campos do template** referenciado pela automação.
- **D-08:** A condição "Valor de campo" **exige um template determinável** (fixado) na automação. Quando não houver template determinável, a condição é **bloqueada/desabilitada com aviso claro** — sem fallback de texto livre nem autocomplete global. (Política escolhida pelo usuário: mais simples e seguro, evita o off-by-nome silencioso.)
- **D-09:** (Avaliar no planejamento) sinalizar no dry-run quando uma condição "Valor de campo" referencia um campo que não foi extraído — hoje falha silenciosa (`rules.py` campo ausente → falso).

### Item 8 — Rótulo "pronto" (chip distinto + CTA na lista)
- **D-10:** Quando `state=processando` E `last_completed_step="classificado"`, derivar e exibir um rótulo distinto **"Classificado — pronto para aplicar/aprovar"** (não "processando"). Estado de apresentação derivado do par state+last_completed_step.
- **D-11:** Além do rótulo, expor **CTA na própria lista** (ex.: "Pré-visualizar" / "Aprovar") para agir direto, sem precisar entrar no detalhe.
- **D-12:** Não auto-concluir documentos (decisão Open Q1 das fases anteriores permanece) — conclusão segue via aplicar automação ou aprovar. Esta é só mudança de apresentação + atalho.

### Item 9 — Timestamps com fuso
- **D-13:** Backend serializa timestamps (ex.: `created_at`) como **UTC tz-aware (`...Z`)** em TODA a API, consistente com o que `/watcher/status` já faz. Frontend converte ao fuso local naturalmente via `new Date(iso)`. (Travado como discrição — opção óbvia; paliativo só-no-frontend rejeitado por inconsistência.)

### Claude's Discretion
- Como derivar o rótulo de apresentação (no backend no payload de `/documents` vs no frontend a partir de state+last_completed_step) — planner decide pelo padrão existente.
- Forma exata do endpoint GET de audit por doc (path, shape do response) — seguir o padrão de `api/documents.py`.
- Mecanismo de "template determinável" para o seletor de campo (via condição "Tipo de documento" do próprio pipeline/step) — planner mapeia contra o modelo de pipeline atual.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backlog / origem dos requisitos
- `.planning/notes/2026-06-24-melhorias-teste-usuario-final.md` — itens 1, 3, 4, 8, 9 com diagnóstico, evidência no código (arquivos/linhas) e melhoria proposta. **Fonte autoritativa desta fase.**

### Reversibilidade (item 1)
- `backend/app/automation/undo.py` + `POST /automations/undo` — undo por `document_id` OU `run_id`; restaura do CAS; reabre CONCLUIDO→PROCESSANDO.
- `backend/app/models/audit_log.py` — write-ahead (status intent/done/undone, source_path, dest_path, run_id, content_hash). Fonte do GET novo (D-02).
- `backend/app/storage/cas.py` — CAS imutável por hash (originais recuperáveis).

### Classificação/estado (itens 8)
- `backend/app/classification/stage.py` — doc bem classificado fica em PROCESSANDO + last_completed_step="classificado" (linhas ~357-364).

### Automações/condições (item 4)
- `backend/app/automation/rules.py` — avaliação da condição "Valor de campo" (campo ausente → falso silencioso, ~linhas 72/86-88).
- `backend/app/automation/stage.py` — campos válidos do doc usados na avaliação (~linha 204).
- `frontend/src/pages/AutomationsPage.tsx` — input de texto livre do nome do campo (~657-662) + painel "Campos do template" (~547).

### Dedup/ingestão (item 3)
- `backend/app/api/documents.py` — `POST /rescan` (retorna só `enqueued` hoje); `GET /documents/duplicates-count`.
- `backend/app/ingestion/watcher.py` — dedup por content_hash incrementa `duplicate_hits` e não enfileira (~linha 155).
- `frontend/src/pages/DocumentsPage.tsx` — chip "{N} duplicados ignorados" (~302-308); `formatDate` / `new Date(iso)` (~48, item 9).

### Fuso (item 9)
- `backend/app/api/` (modelos/responses que serializam `created_at` naive) — comparar com `/watcher/status` (já emite `Z` correto) como referência do alvo.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Undo completo no backend** (`undo.py` + `POST /automations/undo` por document_id): item 1 é sobretudo UI + 1 endpoint GET de leitura do audit.
- **`StatusPill` / `ConfidenceBadge`** (frontend): padrão de pílula de status — item 8 estende a derivação do rótulo sem alterar o componente base (faixas/tokens `--st-*` travados).
- **Painel "Campos do template"** já busca os campos na `AutomationsPage` — item 4 reaproveita essa busca para popular o `<select>`.
- **`/watcher/status`** já serializa tz-aware com `Z` — item 9 replica o padrão nos demais timestamps.

### Established Patterns
- API fina espelha `watched_folders.py` (In/Patch/Out, guards de estado como pré-condição → 409/404). GET novo de audit por doc segue esse molde.
- Valores na UI como texto puro (0 `dangerouslySetInnerHTML`) — manter.
- "Code-and-config" nas fases de frontend recentes — evitar npm novo.
- Estados de domínio reais no StatusPill (sem inventar estado persistido novo; rótulo é DERIVADO).

### Integration Points
- Detalhe do documento (`GET /documents/{id}`) — onde plugar origem→destino + botão reverter.
- `POST /rescan` response + toast no fluxo de "Forçar varredura" da aba Documentos.
- Condição "Valor de campo" no construtor de automações (pipeline/step + StepFilter).
- Camada de serialização de timestamps dos responses Pydantic.
</code_context>

<specifics>
## Specific Ideas

- Item 8 confirmado ao vivo no teste: doc 4 (template "Notas Fiscais", score 1.0, EMITENTE e Numero_Nota válidos) ficava "processando" parecendo travado.
- Item 9 confirmado: UI mostrava "24 de jun., 18:03" com horário local 15:03 (UTC-3).
- Item 4: o atrito real é digitar o nome EXATO do campo de memória; o usuário pediu explicitamente para "exigir template fixado" em vez de texto livre/autocomplete global.
</specifics>

<deferred>
## Deferred Ideas

- **Histórico de aplicações por lote (run_id) + undo em lote persistente** (item 1, parte 2/3) — fica para uma fase futura de auditoria/histórico.
- **Rastreio de dedup por-evento** (item 3, parte 2/3): persistir/listar quais arquivos foram pulados, de qual pasta, contra qual doc — backend novo + UI nova; fase futura.
- **Item 2** — Varredura de pasta nova (arquivos pré-existentes não varridos sem /rescan manual): correção de ingestão (`watcher.py`), `/gsd:quick` futuro / fase de robustez de ingestão.
- **Item 7** — "Remover + forçar varredura" não re-ingere arquivos vindos de split (limpeza de dedup não cobre hash de bloco): mesma fase de robustez de ingestão.
- **Item 12** — Ações por-linha no dry-run ("Negar/Pular" e "Remover"): precisa de decisão de semântica de "remover"; fase pequena futura.
- **Item 10/11** — já entregues na Phase 9 (destino configurável + transformação de valores), pendentes só de verificação visual conjunta.

### Reviewed Todos (not folded)
None — discussion stayed within phase scope.

</deferred>

---

*Phase: 11-ux-e-visibilidade-reverter-movidos-dedup-visivel-rotulos-e-f*
*Context gathered: 2026-06-25*

# Phase 12: Robustez de ingestão e modo de aprovação - Context

**Gathered:** 2026-06-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Fechar os três últimos itens do backlog do teste de usuário final. Dois são correções de mecânica de ingestão (backend); o terceiro é uma capacidade nova de produto (modo de aprovação global).

- **Item 2** — Pasta monitorada criada/reativada em runtime não varre os arquivos JÁ presentes.
- **Item 7** — "Remover + forçar varredura" não re-ingere arquivos vindos de split (dedup do bloco não é limpo).
- **Item 12** — Toggle global "automações aguardam minha aprovação": a Pré-visualização vira fila de aprovação durante o período de teste; desligado, o sistema roda sozinho.

**Fora de escopo:** rastreio de dedup por-evento (já deferido na Phase 11); redesenho da tela de atenção; histórico de lotes. Phases 7 (determinístico, ADIADA) e 8 (distribuição/docs) seguem no roadmap, fora desta fase.
</domain>

<decisions>
## Implementation Decisions

### Item 2 — Varredura de pasta nova (backend)
- **D-01:** No supervisor de reconfiguração do watcher (quando o conjunto de pastas ativas muda em runtime), disparar `scan_and_enqueue` sobre as pastas **recém-adicionadas** (diff `current - observed`) ao reatar o `awatch` — fechando a lacuna de que o `awatch` só capta eventos futuros e a varredura de existentes só rodava no startup e no `/rescan` manual. Idempotente por dedup (seguro). Avaliar também varrer ao (re)ativar uma pasta via PATCH.

### Item 7 — Re-ingest de split após remover (backend)
- **D-02:** A limpeza de dedup do `POST /documents/delete` deve cobrir também o(s) **hash(es) de bloco** associados ao documento removido (não só o `original_hash`), liberando a re-ingestão. Materialização de split registra o hash do BLOCO no gate de dedup (anti-loop) como entrada separada do original; a remoção atual limpa só o `IngestedOriginal` do original. Investigar no planejamento como associar bloco↔documento removido para limpar a entrada certa.

### Item 12 — Modo de aprovação global (backend + frontend)
- **D-03:** Setting GLOBAL novo (ex.: `approval_mode` / "automações aguardam aprovação"), **default OFF**, persistido no `.env` + `cache_clear`, com endpoints `GET/PUT` espelhando o par `review-threshold` / `ai-fallback` (Phases 5/10).
- **D-04:** **DESLIGADO (alvo):** comportamento atual mantido — automações de **alta confiança auto-aplicam** sozinhas; baixa confiança/campo inválido → "Precisam de atenção"; não-casou → quarentena. **A trava de confiança é mantida** (rede de segurança), em ambos os modos.
- **D-05:** **LIGADO (período de teste):** automações que hoje auto-aplicariam (alta confiança) **NÃO** auto-aplicam — ficam **pendentes aguardando aprovação**. O `enqueue_pending_applications` / worker respeita o toggle (gate antes do apply automático).
- **D-06:** A **Pré-visualização (DryRunPage) vira a fila de aprovação**: lista as automações pendentes (origem→destino) e oferece **aprovar / negar por linha**. Negar = não aplica naquele doc nesta rodada (o doc fica pronto, arquivo intocado — o move só acontece no aprovar/aplicar). Reusa o dry-run/apply existentes.
- **D-07:** "Precisam de atenção" continua exclusivamente para não-casou / erros / baixa confiança — sem mudança.

### Claude's Discretion
- Nome exato do setting e shape dos endpoints (seguir `review-threshold`/`ai-fallback`).
- Como o gate do toggle se encaixa em `enqueue_pending_applications` / `apply_stage` (planner mapeia contra o auto-apply de alta confiança da decisão [06-04]).
- Como associar hash de bloco ↔ documento na limpeza de dedup do delete (item 7).
- Onde renderizar o toggle no frontend (provável ConfigPage, junto de limiar/IA-fallback).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backlog / origem
- `.planning/notes/2026-06-24-melhorias-teste-usuario-final.md` — itens 2, 7, 12 com diagnóstico e arquivos/linhas. **Fonte autoritativa.**

### Ingestão / watcher / dedup (itens 2, 7)
- `backend/app/ingest/watcher.py` — supervisor de reconfiguração, `scan_and_enqueue`, gate de dedup por `content_hash` (incrementa `duplicate_hits`, não enfileira). Item 2 mexe aqui.
- `backend/app/api/documents.py` — `POST /documents/delete` (quick 260624-far: limpa `IngestedOriginal`/Jobs do original), `POST /rescan`. Item 7 mexe na limpeza de dedup.
- Materialização de split (quick 260623-pzy) — registra hash do BLOCO no dedup (anti-loop); relevante ao item 7.

### Apply / aprovação (item 12)
- `backend/app/automation/stage.py` — `dry_run`, `apply_stage`, `enqueue_pending_applications` (auto-aplica alta confiança — decisão [06-04]); estados PROCESSANDO/EM_REVISAO→CONCLUIDO.
- `backend/app/api/documents.py` — `GET/PUT /config/review-threshold` (Phase 5) e padrão de setting persistido no .env + cache_clear.
- `backend/app/api/config.py` + `GET/PUT /config/ai-fallback` (Phase 10, plano 10-04) — molde EXATO do novo toggle global.
- `frontend/src/pages/DryRunPage.tsx` — vira a fila de aprovação (item 12, D-06).
- `frontend/src/pages/ConfigPage.tsx` — onde fica o toggle (junto de limiar/IA-fallback).

### Padrão de worker/fila
- Decisão [06-04] (STATE.md) — `enqueue_pending_applications` auto-aplica alta confiança (D-01), baixa só após approve. O toggle do item 12 gateia esse auto-apply.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Par de endpoints de config** (`review-threshold`, `ai-fallback`): molde pronto para o toggle global do item 12 (persist .env + cache_clear + GET/PUT).
- **dry_run / apply_stage / undo**: a fila de aprovação reusa o dry-run existente; aprovar = apply; negar = não aplica.
- **scan_and_enqueue** (item 2) + **limpeza de dedup do delete** (item 7): pontos cirúrgicos, já existem — é estender, não criar do zero.
- **enqueue_pending_applications**: ponto único onde o auto-apply de alta confiança acontece — o gate do toggle entra aqui.

### Established Patterns
- Setting global no .env + `cache_clear` + GET/PUT fino (espelha watched_folders/templates).
- Idempotência por dedup torna re-varredura segura (item 2).
- "Nunca perder arquivos": negar/remover NUNCA move nem apaga arquivo (move só no aprovar/aplicar).
- Frontend: TanStack Query, valores texto puro, zero npm novo.

### Integration Points
- Supervisor do watcher (diff de pastas ativas) → scan das recém-adicionadas (item 2).
- `POST /documents/delete` → limpeza de dedup incluindo hash de bloco (item 7).
- `enqueue_pending_applications`/worker → gate do toggle de aprovação (item 12).
- DryRunPage → fila de aprovação; ConfigPage → toggle (item 12).
</code_context>

<specifics>
## Specific Ideas

- Visão do usuário (verbatim, item 12): "a ideia é ter automatizado, o sistema precisa rodar automaticamente e não precisar q eu aprove algo... seria interessante ter um toggle q ele selecione para que as automações fiquem aguardando a aprovação dele, ai ele pode testar durante um período e depois q ele se sentir confiante com o sistema, ele desativa a pré-visualização e o sistema roda tudo sozinho."
- Confirmado com o usuário: modo desligado mantém a trava de confiança (alta confiança auto-aplica; baixa/inválido/não-casou vão pra atenção). Aprovação por linha reusa a Pré-visualização.
</specifics>

<deferred>
## Deferred Ideas

- Rastreio de dedup por-evento + lista/filtro "Duplicatas" (item 3 partes 2/3) — já deferido na Phase 11.
- Histórico de aplicações por lote (run_id) + undo em lote (item 1 partes 2/3) — Phase 11 deferred.
- Redesenho amplo da tela de atenção (aprovar/negar com novo ciclo de vida) — além do toggle desta fase.

### Reviewed Todos (not folded)
None — discussion stayed within phase scope.

</deferred>

---

*Phase: 12-robustez-de-ingestao-e-modo-de-aprovacao*
*Context gathered: 2026-06-25*

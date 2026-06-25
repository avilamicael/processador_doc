### Phase 11: UX e visibilidade

**Goal:** (Item 1) Reverter documentos já movidos pela tela — undo persistente por documento/lote (backend já tem CAS+audit+`POST /automations/undo`; falta UI persistente, hoje só o lote recém-aplicado na DryRunPage). (Item 3) Tornar o dedup (duplicata ignorada) explícito/rastreável na UI. (Item 4) Condição "Valor de campo" usar seletor dos campos do template em vez de texto livre. (Item 8) Rótulo: doc classificado/pronto deve mostrar "Classificado — pronto para aplicar/aprovar" em vez de "processando". (Item 9) Timestamps com fuso correto (serializar UTC tz-aware; hoje vêm naive e o frontend exibe 3h adiantado).
**Requirements**: Backlog itens 1, 3, 4, 8, 9 (`.planning/notes/2026-06-24-melhorias-teste-usuario-final.md`)
**Depends on:** Phase 6.2 (automações/undo) e Phase 5 (estados/revisão)
**Plans:** 4 plans
**UI hint**: yes

Plans:
**Wave 1**

- [ ] 11-01-PLAN.md — Backend: helper de serialização tz-aware (item 9) + `RescanOut.skipped_duplicates`/`scan_and_enqueue` (item 3) + novo `GET /documents/{id}/audit` (item 1)
- [ ] 11-02-PLAN.md — Frontend: `<select>` estrito de campo + guard de template determinável na condição "Valor de campo" (item 4)
- [ ] 11-03-PLAN.md — Frontend: rótulo derivado "Classificado — pronto" + CTA Pré-visualizar/Aprovar na lista (item 8)

**Wave 2** *(blocked on 11-01 + 11-03)*

- [ ] 11-04-PLAN.md — Frontend: UI de reverter (origem→destino + botão, item 1) + toast pós-varredura (item 3)

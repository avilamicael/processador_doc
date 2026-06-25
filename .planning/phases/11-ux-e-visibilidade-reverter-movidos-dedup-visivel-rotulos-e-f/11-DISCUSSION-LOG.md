# Phase 11: UX e visibilidade - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-25
**Phase:** 11-ux-e-visibilidade-reverter-movidos-dedup-visivel-rotulos-e-f
**Areas discussed:** Reverter movidos (item 1), Dedup visível (item 3), Seletor de campo (item 4), Rótulo "pronto" + fuso (itens 8, 9)

---

## Reverter movidos — escopo (item 1)

| Option | Description | Selected |
|--------|-------------|----------|
| Por-doc no detalhe | Botão "Reverter para origem" no detalhe, origem→destino do audit (GET novo) → undo por document_id | ✓ |
| Por-doc + histórico de lotes | Também visão de aplicações por run_id com undo em lote | |
| Por-doc + persistir undo do dry-run | Também tornar persistente o undo do lote recém-aplicado | |

**User's choice:** Por-doc no detalhe.
**Notes:** Caso central = desfazer um doc movido a qualquer momento. Histórico de lotes e persistência do undo do dry-run ficam adiados.

---

## Dedup visível — profundidade (item 3)

| Option | Description | Selected |
|--------|-------------|----------|
| Win barato: toast pós-rescan | /rescan retorna skipped_duplicates + toast "X enfileirados, Y pulados" | ✓ |
| Rastreável por-evento | Persistir cada skip + lista/filtro "Duplicatas" | |
| Toast agora + base de eventos | Os dois | |

**User's choice:** Win barato (toast pós-rescan).
**Notes:** Resolve a confusão de "/rescan não faz nada". Tracking por-evento adiado.

---

## Seletor de campo — fallback (item 4)

| Option | Description | Selected |
|--------|-------------|----------|
| Autocomplete global + texto livre validado | Campos de todos os templates + digitar com aviso quando não casa | |
| Exigir template fixado | Só select dos campos do template referenciado; sem texto livre; bloquear/avisar sem template | ✓ |

**User's choice:** Exigir template fixado.
**Notes:** Usuário inicialmente não entendeu onde a condição "Valor de campo" se aplica (tela Automações → "Quando rodar"); após explicação (input de texto livre do nome do campo, falha silenciosa quando erra o nome), escolheu o caminho mais rígido/seguro: condição exige template determinável, dropdown estrito dos campos dele.

---

## Rótulo "pronto" + fuso (itens 8, 9)

| Option | Description | Selected |
|--------|-------------|----------|
| Chip "pronto" + CTA na lista | Rótulo "Classificado — pronto para aplicar/aprovar" + botão (Pré-visualizar/Aprovar) na lista | ✓ |
| Só trocar o texto da pílula | Apenas o rótulo distinto, sem CTA nova | |

**User's choice:** Chip "pronto" + CTA na lista.
**Notes:** Usuário não entendia onde "processando" enganava; após explicação (doc classificado-e-pronto fica em PROCESSANDO aguardando ação), escolheu chip distinto + atalho de ação. Fuso (item 9) travado como discrição: backend serializa UTC tz-aware (Z) em toda a API; sem objeção do usuário.

---

## Claude's Discretion

- Local da derivação do rótulo (backend no payload vs frontend a partir de state+last_completed_step).
- Forma do endpoint GET de audit por documento (seguir padrão de api/documents.py).
- Mecanismo de "template determinável" para o seletor de campo (via condição "Tipo de documento" do pipeline/step).
- Item 9 (fuso): serialização UTC tz-aware (Z) em toda a API — travado sem necessidade de input do usuário.

## Deferred Ideas

- Histórico de aplicações por lote (run_id) + undo em lote persistente (item 1, partes 2/3).
- Rastreio de dedup por-evento + lista/filtro "Duplicatas" (item 3, partes 2/3).
- Item 2 (varredura de pasta nova), Item 7 (re-ingest de split), Item 12 (ações por-linha no dry-run) — fora do escopo da Phase 11.
- Itens 10/11 já entregues na Phase 9 (pendentes só de verificação visual conjunta).

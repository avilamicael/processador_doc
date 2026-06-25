---
phase: 12-robustez-de-ingest-o-e-modo-de-aprova-o
plan: 04
subsystem: frontend (config toggle + fila de aprovação)
tags: [approval-mode, config-toggle, dry-run, approval-queue, frontend]
requires:
  - "GET/PUT /config/approval-mode ({enabled: bool}) — backend 12-03"
  - "gate do auto-apply em enqueue_pending_applications (worker, 12-03)"
  - "par ai-fallback ponta-a-ponta (Fase 10) como molde"
  - "DryRunPage + useDryRun/useApply/useUndo (06-07 / 06.2)"
provides:
  - "interface ApprovalMode { enabled: boolean } (types.ts)"
  - "get/putApprovalMode contra /config/approval-mode (lib/api.ts)"
  - "useApprovalMode / useSaveApprovalMode (hooks/useAttention.ts)"
  - "ApprovalModeField na ConfigPage (LeituraTab)"
  - "DryRunPage como fila de aprovação: Aprovar (=apply) / Negar (local) por linha quando ligado"
affects:
  - "fluxo de aprovação do usuário final (modo de teste visível)"
tech-stack:
  added: []
  patterns: ["toggle global espelhando o par ai-fallback", "negar = filtro local setRows (sem backend, D-06)"]
key-files:
  created: []
  modified:
    - frontend/src/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/hooks/useAttention.ts
    - frontend/src/pages/ConfigPage.tsx
    - frontend/src/pages/DryRunPage.tsx
decisions:
  - "Negar/Pular é filtro LOCAL via setRows — NÃO chama backend e NÃO move arquivo (D-06/T-12-11)"
  - "Aprovar reusa o doApply existente (aprovar = apply_stage); zero mudança de semântica"
  - "Gate só na renderização (banner + coluna Ações); DESLIGADO = página idêntica ao atual"
  - "Zero npm novo; valores como texto puro (sem dangerouslySetInnerHTML)"
metrics:
  duration: "~8min"
  tasks: 2
  files-changed: 5
  completed: 2026-06-25
requirements: [BL-12]
---

# Phase 12 Plan 04: Modo de Aprovação (frontend) Summary

Toggle global "Automações aguardam minha aprovação" na ConfigPage (espelho 1:1 do par
ai-fallback ponta-a-ponta: types → api → hook → field) e a Pré-visualização (DryRunPage)
repurposada como fila de aprovação. Com o toggle LIGADO, os docs de alta confiança não são
auto-aplicados (gate do worker, 12-03) e aparecem aqui para o usuário aprovar (= aplicar) ou
negar/pular por linha — negar é estritamente local (filtro `setRows`, sem backend, sem mover
arquivo, D-06). Com o toggle DESLIGADO, a página se comporta exatamente como hoje.

## What Was Built

- **ApprovalMode { enabled }** (`types.ts`): interface espelho de `AiFallback`.
- **get/putApprovalMode** (`lib/api.ts`): GET `/config/approval-mode` e PUT com `{ enabled }`,
  cópia 1:1 do par `ai-fallback`; usa o cliente `request` tipado base. Import do tipo
  `ApprovalMode` adicionado.
- **useApprovalMode / useSaveApprovalMode** (`hooks/useAttention.ts`): `APPROVAL_MODE_KEY =
  ['approval-mode']`; `useQuery` para ler e `useMutation` que invalida a key no `onSuccess`.
- **ApprovalModeField** (`ConfigPage.tsx`): card com `<Switch on={enabled} onToggle={toggle}>`,
  título "Automações aguardam minha aprovação" + descrição (LIGADO = aguardam na
  Pré-visualização; DESLIGADO = alta confiança aplica sozinha mantendo a trava de confiança;
  padrão desligado) + estados loading/error/saveError. Renderizado na `LeituraTab` ao lado de
  `ReviewThresholdField`/`AiFallbackField`.
- **DryRunPage como fila de aprovação** (`DryRunPage.tsx`): lê `useApprovalMode()`; quando
  `enabled`:
  - **Banner** no topo explicando Aprovar (aplica) vs Negar (deixa pronto sem mover).
  - **Coluna "Ações"** extra (`BODY_COLS = 5`) com dois botões por linha aplicável:
    **Aprovar** (`doApply([r.document_id])` — o apply existente) e **Negar / Pular**
    (`denyDoc` = `setRows` filtra o `document_id` + tira de `selected`, SEM backend).
  - Quando DESLIGADO: sem banner, sem coluna Ações, `BODY_COLS = 4` — comportamento atual.

## Deviations from Plan

None — plano executado exatamente como escrito.

## Threat Mitigations Applied

- **T-12-11** (Tampering / data loss — "Negar" move ou apaga arquivo): `denyDoc` só filtra
  `rows` via `setRows` (estado local de UI) e remove o id de `selected`; NENHUM apply/undo/
  delete é disparado, nenhuma chamada de backend — arquivo intocado (D-06). O move só acontece
  no Aprovar (`doApply` → `apply_stage`).
- **T-12-12** (Spoofing/XSS — render de caminhos origem→destino): valores como texto puro
  (`cell-mono`), zero `dangerouslySetInnerHTML` — padrão estabelecido da página preservado.
- **T-12-13** (auto-apply quando ligado): a UI não decide auto-apply — o gate autoritativo está
  no worker (12-03); a UI só lista/aprova/nega.
- **T-12-SC** (npm/pip installs): zero npm novo — N/A.

## Visual Checkpoint — DEFERRED (PENDENTE)

A Task 3 (`checkpoint:human-verify`, gate=blocking) NÃO foi executada ao vivo. Por decisão
explícita do usuário, a verificação visual está **DEFERIDA para a rodada de teste final
combinada** (mesmo padrão do checkpoint 09-03 e 11-04). O código está completo e o build
frontend passa; falta apenas a aprovação visual humana.

**A verificar na rodada combinada:**
1. ConfigPage → aba Leitura: card "Automações aguardam minha aprovação", default DESLIGADO;
   ligar deve persistir após reload (GET reflete o PUT).
2. Com o toggle LIGADO, docs de alta confiança NÃO são auto-aplicados pelo worker e aparecem
   na Pré-visualização com o banner do modo de aprovação.
3. Numa linha, "Negar / Pular": a linha some, NENHUM arquivo é movido (verificar na pasta), o
   documento segue pronto.
4. Noutra linha, Aprovar: o arquivo é movido/renomeado e pode ser desfeito.
5. DESLIGAR o toggle: novos docs de alta confiança voltam a ser auto-aplicados; a
   Pré-visualização volta ao comportamento atual (sem banner/Negar).

## Verification

`cd frontend && npm run build` → verde (tsc -b + vite build) após cada task.

## Commits

- `3c598ca` feat(12-04): toggle approval-mode ponta-a-ponta (types+api+hook+ConfigPage)
- `c341064` feat(12-04): DryRunPage vira fila de aprovação (negar/pular local quando ligado)

## Self-Check: PASSED

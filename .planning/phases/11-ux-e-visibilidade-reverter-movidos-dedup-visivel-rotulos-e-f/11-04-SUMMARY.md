---
phase: 11-ux-e-visibilidade
plan: 04
subsystem: frontend
tags: [ux, undo, audit, dedup-toast, documents-detail]
requires:
  - "GET /documents/{id}/audit → DocumentAuditOut (11-01)"
  - "POST /rescan → { enqueued, skipped_duplicates } (11-01)"
  - "POST /automations/undo por document_id (Fase 6, já existente)"
provides:
  - "AuditEntry/DocumentAudit (types) + getDocumentAudit (api client)"
  - "useUndoDocument (hook de mutation por document_id)"
  - "Seção 'Operações aplicadas' (origem→destino) + botão 'Reverter para a origem' no detalhe"
  - "Toast pós-'Forçar varredura' com enfileirados + pulados por duplicata"
affects:
  - frontend/src/types.ts
  - frontend/src/lib/api.ts
  - frontend/src/hooks/useDocuments.ts
  - frontend/src/pages/DocumentsPage.tsx
tech-stack:
  added: []
  patterns:
    - "useQuery ['document-audit', docId] espelha o detailQuery do mesmo modal"
    - "Mutation por document_id reusando postUndo existente (sem novo endpoint)"
    - "Toast efêmero via estado local + setTimeout (sem lib de toast, zero npm novo)"
    - "Confirmação destrutiva inline (molde do confirmDelete da lista)"
key-files:
  created: []
  modified:
    - frontend/src/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/hooks/useDocuments.ts
    - frontend/src/pages/DocumentsPage.tsx
decisions:
  - "Reverter chama undo por document_id (UI envia só o id do doc aberto, sem construir paths) — backend confina/restaura do CAS com guard próprio (T-11-08/T-11-10)"
  - "Só entradas status=='done' rendem origem→destino (operações de fato materializadas), espelhando o critério can_undo do backend"
  - "Toast some sozinho após ~6s; timer limpo no unmount (useEffect cleanup)"
metrics:
  duration: "~12min"
  completed: "2026-06-25"
  tasks: 2
  files: 4
---

# Phase 11 Plan 04: Reverter pela tela + toast de duplicatas (frontend) Summary

O backend já tinha CAS + audit + undo por document_id (item 1) e passou a retornar
`skipped_duplicates` no /rescan (item 3, do 11-01) — faltava a UI. Este plano fia
isso à tela: no detalhe do documento aparece a seção "Operações aplicadas"
(origem→destino, lida do `GET /documents/{id}/audit`) com um botão "Reverter para a
origem" que dispara o undo por `document_id`; e o botão "Forçar varredura" passou a
mostrar um toast "X novos enfileirados, Y pulados por já existirem" em vez de parecer
que nada aconteceu. Zero dependência nova; valores como TEXTO PURO.

## What Was Built

**Task 1 — Tipos + api client + hook [commit edf960e]**
- `types.ts`: `AuditEntry` (`id, action, status, source_path, dest_path, run_id, created_at`)
  e `DocumentAudit` (`items, can_undo`), espelhando o estilo de `DocumentDetail`.
- `api.ts`: `getDocumentAudit(id)` via o wrapper `request<DocumentAudit>` (não
  reimplementa fetch); `postRescan` re-tipado para `{ enqueued, skipped_duplicates }`.
- `useDocuments.ts`: `useUndoDocument` (molde de `useRescan`) — `mutationFn: (id) =>
  postUndo({ document_id: id })`, `onSuccess` invalida `['documents']`,
  `['document-detail', id]` e `['document-audit', id]`. Reusa `postUndo` existente.

**Task 2 — UI de reverter + toast [commit 3c6cae4]**
- `DocumentDetailModal`: novo `useQuery ['document-audit', docId]` (mesmo padrão do
  `detailQuery`). Seção "Operações aplicadas" renderiza, para cada entrada
  `status === 'done'`, o par origem→destino em `cell-mono` (TEXTO PURO), rotulado
  "Movido"/"Cópia" por `action`. Quando `can_undo`, um botão "Reverter para a origem"
  (`btn-primary`) abre uma confirmação inline (molde do `confirmDelete`); confirmar
  chama `useUndoDocument` com o `document_id` do doc aberto e, no sucesso, fecha o
  modal (o doc reabre CONCLUIDO→PROCESSANDO via invalidação do hook).
- `DocumentsPage`: `runRescan()` dispara `rescan.mutate` com `onSuccess` que monta a
  mensagem a partir de `enqueued`/`skipped_duplicates` (singular/plural) e a exibe num
  toast efêmero (estado local + `setTimeout` 6s; timer limpo no unmount). Render inline
  no estilo de mensagem neutra (`var(--text-3)`) do chip de footer; sem lib de toast.

## Verification

- `cd frontend && npm run build` verde nas duas tasks (tsc -b + vite build, 0 erros).
- `grep -c "getDocumentAudit\|skipped_duplicates"` em `api.ts` = 4 (tipo + assinatura
  + path + comentário).
- `grep -c "getDocumentAudit\|useUndoDocument\|skipped_duplicates"` em
  `DocumentsPage.tsx` = 5 (import, queryFn, hook, leitura de `r.skipped_duplicates`).
- Mutation por `document_id` envia só o id do doc aberto — nenhum path construído na UI
  (T-11-08/T-11-10); caminhos vêm do AuditLog persistido e são TEXTO PURO (T-11-09).

## Deviations from Plan

None — plano executado exatamente como escrito (Tasks 1 e 2). A Task 3 é o checkpoint
de verificação visual (ver abaixo), deferido por decisão do usuário.

## CHECKPOINT (Task 3) — DEFERRED / PENDING

Task 3 é `checkpoint:human-verify` (gate="blocking"): verificação visual ao vivo de
que (a) o detalhe de um doc concluído mostra origem→destino + botão "Reverter para a
origem"; (b) clicar "Reverter" devolve o arquivo à origem (CAS), reabre o doc e
atualiza lista/detalhe; (c) após "Forçar varredura" com uma duplicata na pasta, o toast
mostra os enfileirados + pulados por já existirem (ex.: "0 novos enfileirados, 1 pulado
por já existir").

**Por decisão explícita do usuário, a verificação visual ao vivo foi DIFERIDA para uma
rodada final de teste combinada.** Nenhuma aprovação foi fabricada. Status do
checkpoint: **PENDING**. As verificações automáticas (build + greps de aceitação)
passaram.

## Known Stubs

Nenhum. Todos os valores renderizados derivam de dados reais da API
(`/documents/{id}/audit`, `/rescan`); nenhum valor hardcoded flui para a UI.

## Self-Check: PASSED

- FOUND: frontend/src/types.ts (AuditEntry/DocumentAudit adicionados)
- FOUND: frontend/src/lib/api.ts (getDocumentAudit + postRescan novo shape)
- FOUND: frontend/src/hooks/useDocuments.ts (useUndoDocument)
- FOUND: frontend/src/pages/DocumentsPage.tsx (seção reverter + toast)
- FOUND commit edf960e (Task 1)
- FOUND commit 3c6cae4 (Task 2)
- `npm run build` verde

## Commits

- edf960e: feat(11-04): tipos+api+hook para reverter por documento e shape do rescan
- 3c6cae4: feat(11-04): UI reverter (origem→destino + botão) + toast pós-varredura (D-01/D-05)

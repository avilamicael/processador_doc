---
phase: 11-ux-e-visibilidade
plan: 03
subsystem: frontend
tags: [ux, status-pill, cta, documents-list]
requires:
  - "DocumentOut.last_completed_step (backend, já exposto)"
  - "POST /documents/{id}/approve (já existente)"
provides:
  - "Rótulo derivado 'Classificado — pronto' no StatusPill (processando+classificado)"
  - "CTA Pré-visualizar/Aprovar na linha do doc pronto (sem auto-conclusão)"
  - "useApproveDocument (hook de mutation)"
affects:
  - frontend/src/components/StatusPill.tsx
  - frontend/src/pages/DocumentsPage.tsx
  - frontend/src/App.tsx
  - frontend/src/hooks/useDocuments.ts
tech-stack:
  added: []
  patterns:
    - "Rótulo derivado token-driven (resolvePill) — sem estado persistido novo"
    - "TanStack mutation com invalidateQueries no onSuccess (molde useRescan)"
key-files:
  created: []
  modified:
    - frontend/src/components/StatusPill.tsx
    - frontend/src/pages/DocumentsPage.tsx
    - frontend/src/App.tsx
    - frontend/src/hooks/useDocuments.ts
decisions:
  - "Token reusado 'tratado' (verde) para 'Classificado — pronto' — sem inventar token novo (paleta --st-* travada)"
  - "Condição 'pronto' fatorada em helper isClassifiedReady() compartilhado entre pílula e CTA (literal 'classificado' único, casa com CLASSIFIED_STEP)"
  - "CTA renderizada na célula de status (não em coluna nova) — preserva BODY_COLS=6"
metrics:
  duration: "~10min"
  completed: "2026-06-25"
---

# Phase 11 Plan 03: Rótulo "Classificado — pronto" + CTA na lista Summary

Doc bem classificado deixa de parecer travado: a pílula mostra "Classificado — pronto" (verde, rótulo DERIVADO de `processando` + `last_completed_step="classificado"`) e a própria linha da lista ganha uma CTA "Pré-visualizar" (navega ao dry-run) e "Aprovar" (dispara o POST approve existente) — sem inventar estado persistido nem auto-concluir nada (D-10/D-11/D-12).

## What Was Built

**Task 1 — StatusPill (D-10) [commit 91e21c1]**
- Novo ramo em `resolvePill`: `state === 'processando' && lastCompletedStep === 'classificado'` → `{ label: 'Classificado — pronto', token: 'tratado' }`.
- Token verde existente (`tratado`) reusado; ramo `aguardando_extracao` intacto. Literal `'classificado'` casa com `CLASSIFIED_STEP` (backend/app/classification/stage.py:69).

**Task 2 — CTA na linha + onNavigate + hook (D-11/D-12) [commit 6884aed]**
- `useApproveDocument` em useDocuments.ts: `mutationFn: (id) => postApprove(id)`, `onSuccess` invalida `['documents']` e `['document-detail', id]` (molde de `useRescan`).
- `DocumentsPage` recebe prop opcional `onNavigate?: (page: Page) => void`; `App.tsx` passa `onNavigate={setPage}`.
- Helper local `isClassifiedReady(state, step)` fatora a condição "pronto" (literal único, comentário aponta para CLASSIFIED_STEP) — usado tanto para decidir a CTA quanto espelhando o ramo do StatusPill.
- Na célula de status, quando o doc está pronto: botões "Pré-visualizar" (`btn-ghost` → `onNavigate?.('dryrun')`) e "Aprovar" (`btn-primary` → `approve.mutate(d.id)`, com estado de loading por-linha via `approve.variables === d.id`). Valores TEXTO PURO; zero npm novo; sem coluna nova (BODY_COLS preservado).

## Deviations from Plan

None — plano executado exatamente como escrito. (Nota de contexto, não desvio: `stage.py:384` transiciona docs classificados para `EM_REVISAO`; o ramo derivado trata especificamente o caso `processando+classificado` que o plano descreve como o estado "pronto, aguardando ação" observado no teste — implementado conforme a condição literal do plano.)

## CHECKPOINT (Task 3) — DEFERRED / PENDING

Task 3 é `checkpoint:human-verify` (gate="blocking"): verificação visual de que (a) a pílula mostra "Classificado — pronto" verde em vez de "Processando", (b) a linha exibe Pré-visualizar/Aprovar, (c) Pré-visualizar navega ao dry-run, (d) Aprovar conclui e atualiza a lista, (e) outros estados não mostram CTA/rótulo.

**Por decisão explícita do usuário, a verificação visual ao vivo foi DIFERIDA para uma rodada final de teste combinada.** Nenhuma aprovação foi fabricada. Status do checkpoint: **PENDING**. As verificações automáticas (build + greps de aceitação) passaram.

## Self-Check: PASSED

- StatusPill.tsx contém ramo 'classificado' (grep -c "classificado" = 4)
- useDocuments.ts: postApprove/useApproveDocument presentes (grep -c = 3)
- onNavigate presente em DocumentsPage.tsx (3) e App.tsx (2)
- `approve.mutate` só em `onClick` (sem useEffect/auto-conclude)
- `cd frontend && npm run build` verde (tsc -b + vite build, 0 erros)
- Commits 91e21c1 e 6884aed presentes no histórico

## Commits

- 91e21c1: feat(11-03): rótulo derivado 'Classificado — pronto' no StatusPill (D-10)
- 6884aed: feat(11-03): CTA Pré-visualizar/Aprovar na linha do doc pronto (D-11/D-12)

---
phase: 06-automa-es-de-arquivo-renomear-mover
plan: 05
subsystem: frontend
tags: [automations, dry-run, ui, tanstack-query, react]
status: awaiting-checkpoint
requires:
  - "06-04 (API /automations: CRUD regras + dry-run + apply + undo)"
provides:
  - "Aba Automações real (S1/S2/S3) fiada à API, substituindo o mock"
  - "Tela de Pré-visualização/Dry-run (S4) origem→destino + colisão sinalizada"
  - "Ações Aplicar (gated) e Desfazer não-destrutivo (S5/S6)"
affects:
  - "frontend (navegação ganha rota 'dryrun'; mock Automation removido)"
tech-stack:
  added: []
  patterns:
    - "TanStack Query: useQuery para listar regras + useMutation invalidando keys"
    - "mutations de apply/undo invalidam ['automations']/['documents']/['attention']"
    - "valores/paths renderizados como texto puro (React escapa; 0 dangerouslySetInnerHTML)"
    - "cor 100% via token --st-*/--accent; mono para caminhos/padrões"
key-files:
  created:
    - "frontend/src/hooks/useAutomations.ts"
    - "frontend/src/pages/DryRunPage.tsx"
    - ".planning/phases/06-automa-es-de-arquivo-renomear-mover/06-05-SUMMARY.md"
  modified:
    - "frontend/src/types.ts"
    - "frontend/src/lib/api.ts"
    - "frontend/src/pages/AutomationsPage.tsx"
    - "frontend/src/components/Icon.tsx"
    - "frontend/src/components/Sidebar.tsx"
    - "frontend/src/App.tsx"
    - "frontend/src/data/mock.ts"
decisions:
  - "DryRunRow honra o contrato REAL do backend (flags booleanas blocked/collision/skipped_identical), NÃO o enum 'collision' descrito no plano — a API é a autoridade"
  - "Pré-visualização (S4) é uma PÁGINA própria registrada como Page 'dryrun' na navegação (Sidebar + App), não um painel embutido — molde DocumentsPage"
  - "Reordenação de prioridade troca a priority desta regra com a vizinha via duas mutations PATCH (backend ordena por priority)"
  - "Sanitização do preview (S3) é client-side só para ilustração; a autoridade de naming/sanitização é o backend (apply_stage)"
metrics:
  duration: "~18 min"
  completed: "2026-06-17"
  tasks: 2
  files: 9
---

# Phase 6 Plan 5: Frontend de Automações (Dry-run + Aplicar/Desfazer) Summary

Aba Automações real (S1/S2/S3) fiada à API `/automations` substituindo o mock, mais a tela de Pré-visualização/Dry-run (S4) com pares origem→destino sinalizados e ações Aplicar (gated pelo preview) e Desfazer não-destrutivo (S5/S6) — tudo no design system travado, sem dependência npm nova e sem visualizador de documento.

## What Was Built

### Task 1 — Tipos + cliente API + hooks (commit `0d4786e`)
- `types.ts`: o mock `Automation` (`trigger/cond/action/runs`) foi REMOVIDO e substituído por tipos reais: `RuleCondition`, `AutomationRule`, `RuleConditionCreate`, `RuleCreate`, `RulePatch`, `DryRunRow`, `DryRunResult`, `ApplyResult`, `UndoResult`. Adicionado `'dryrun'` ao tipo `Page`.
- `api.ts`: `getAutomationRules`/`createAutomationRule`/`updateAutomationRule`/`deleteAutomationRule` + `postDryRun`/`postApply`/`postUndo`, reusando `request<T>` (paths `/automations*`).
- `useAutomations.ts`: `useAutomations()` (query) + `useCreateRule`/`useUpdateRule`/`useDeleteRule` (invalidam `['automations']`) + `useDryRun`/`useApply`/`useUndo` (apply/undo invalidam também `['documents']` e `['attention']`).
- `mock.ts`: array `AUTOMATIONS` removido (sem consumidor restante).

### Task 2 — AutomationsPage + DryRunPage + ícones + navegação (commit `e5c4362`)
- `AutomationsPage.tsx` reescrita (sem `data/mock`):
  - **S1**: lista de `.rule-card` ordenadas por prioridade, com posição visível, resumo condição→ação, reordenar ↑/↓ (`aria-label`+`title` "Aumentar/Diminuir prioridade"), Switch ativar/pausar, editar/remover (confirmação). Estados loading/erro/vazio com a copy exata do UI-SPEC ("Nenhuma regra de automação ainda").
  - **S2**: editor inline — linhas de condição (campo + operador `= > < contém` + valor), combinador E/OU, padrões de nome/pasta. CTA "Salvar regra"/"Nova regra".
  - **S3**: tokens `{campo}` inseríveis por clique + pré-visualização ao vivo com dados de exemplo e hint exato sobre remoção de caracteres inválidos no Windows.
- `DryRunPage.tsx` (novo, molde `DocumentsPage`):
  - **S4**: `table.docs` origem→destino em `var(--font-mono)`, badge de situação informativa (âmbar sufixo / azul duplicata / vermelho bloqueio) com a copy do UI-SPEC nos `title`; contagem-resumo no topo; seleção por linha e por lote; "Aplicar automações"/"Aplicar selecionados" DESABILITADO até o preview carregar.
  - **S5/S6**: "Desfazer aplicação" (`.row-action` neutra) + diálogo que comunica reversibilidade (texto de undo/undo-via-CAS exato), nunca linguagem de exclusão.
- `Icon.tsx`: `undo`, `arrowUp`, `arrowDown` no mesmo estilo de stroke.
- `Sidebar.tsx`/`App.tsx`: rota e item de navegação "Pré-visualização" registrados.

## Verification Results

- `npx tsc --noEmit`: sem erros.
- `npm run build`: verde (82 módulos, build em ~283ms).
- Mock removido (`grep data/mock` em AutomationsPage = 0).
- `DryRunPage` em App.tsx (import + render).
- `dangerouslySetInnerHTML` = 0 nas duas páginas (texto puro, T-06-17 mitigado).
- `aria-label` em AutomationsPage = 5 (≥2; reordenação ↑/↓ acessível).
- DryRunPage usa `var(--st-*)`/`var(--accent)` (7 ocorrências); os únicos `#fff` são stroke de ícone (convenção existente em DocumentsPage), não cor de superfície.
- Copy exata "Nenhuma regra de automação ainda" = 1.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] DryRunRow honra o contrato real do backend (flags vs enum)**
- **Found during:** Task 1, ao ler `backend/app/api/automations.py` e `app/automation/stage.py`.
- **Issue:** O plano descrevia `DryRunRow.collision: 'none'|'suffix'|'duplicate'|'blocked'` e `blocked_field`. A API REAL retorna três flags booleanas: `blocked`, `collision`, `skipped_identical` (sem `blocked_field`).
- **Fix:** Tipei `DryRunRow` conforme a API real; `CollisionBadge` deriva a sinalização das flags (blocked → vermelho; skipped_identical → azul; collision → âmbar; senão → "Pronto" verde).
- **Files modified:** `frontend/src/types.ts`, `frontend/src/pages/DryRunPage.tsx`.
- **Commit:** `0d4786e` / `e5c4362`.

**2. [Rule 3 - Blocking] Remoção do mock Automation em cadeia**
- **Found during:** Task 1.
- **Issue:** Remover a interface `Automation` de `types.ts` quebraria `data/mock.ts` (importava o tipo e exportava `AUTOMATIONS`) e a antiga `AutomationsPage` (consumia `AUTOMATIONS`/props `autoState`).
- **Fix:** Removido o array `AUTOMATIONS` e seu import; removido o state `autoState`/`setAutoState` órfão em `App.tsx`; props antigas da `AutomationsPage` eliminadas.
- **Files modified:** `frontend/src/data/mock.ts`, `frontend/src/App.tsx`.
- **Commit:** `0d4786e` / `e5c4362`.

**3. [Rule 3 - Blocking] Dry-run como página de navegação própria**
- **Found during:** Task 2.
- **Issue:** O frontend não usa router; a navegação é por `Page` no estado de `App`. A tela de dry-run precisava de um ponto de entrada.
- **Fix:** Adicionado `'dryrun'` ao tipo `Page`, item "Pré-visualização" na Sidebar (ícone `eye`) e render condicional em `App.tsx`.
- **Files modified:** `frontend/src/types.ts`, `frontend/src/components/Sidebar.tsx`, `frontend/src/App.tsx`.
- **Commit:** `0d4786e` / `e5c4362`.

## Threat Surface

- T-06-17 (XSS em paths/valores): mitigado — todos os valores renderizados como texto puro pelo React; `dangerouslySetInnerHTML` = 0 nas duas páginas.
- T-06-18 (otimismo de UI mascarando falha): mitigado — fonte de verdade é a API; mutations invalidam as queries; o preview é recarregado após apply/undo.
- T-06-SC (npm): mantido `accept` — nenhuma dependência npm nova.

## Known Stubs

Nenhum stub. Toda a UI está fiada à API real `/automations`. (Os tokens `{campo}` de exemplo em S3 são auxílio de composição e a pré-visualização usa dados de exemplo POR DESIGN — a autoridade de resolução/sanitização é o backend.)

## Checkpoint

A última task do plano é `checkpoint:human-verify` (verificação visual S1–S6, tema claro/escuro). As tasks de implementação estão completas e commitadas; o plano aguarda a aprovação humana antes de ser marcado como concluído no STATE/ROADMAP/REQUIREMENTS.

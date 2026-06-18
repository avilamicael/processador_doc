---
phase: 6
plan: "06-10"
subsystem: frontend
tags: [automacoes, pipeline, ui, mockup, drag-and-drop, tokens]
requires:
  - "API /automations (CRUD aninhado pipeline/steps/filtros + dry-run/apply/undo)"
  - "API /templates (campos do template para chips de token, D-19)"
  - "design system travado (tokens --st-*/--surface-*/--accent)"
provides:
  - "Construtor de pipeline de automacoes reescrito conforme mockup aprovado"
  - "DryRunPage consistente com o contrato (origem->destino, situacao por cor)"
affects:
  - frontend/src/pages/AutomationsPage.tsx
  - frontend/src/types.ts
tech-stack:
  added: []
  patterns:
    - "drag-and-drop HTML5 nativo (sem dependencia npm nova, D-20)"
    - "edicao inline por etapa (espelha o mockup) + persistencia da colecao inteira"
    - "chips de token derivados dos campos reais do template via TanStack Query"
key-files:
  created: []
  modified:
    - frontend/src/pages/AutomationsPage.tsx
    - frontend/src/types.ts
decisions:
  - "Seguir D-17 (extensao DIGITAVEL via input texto) sobre o select do mockup"
  - "Edicao inline por etapa em vez de modal/form separado (fiel ao mockup)"
  - "Template vigente do pipeline = o do PRIMEIRO gate identify_type (D-19)"
metrics:
  duration: "~25min"
  completed: 2026-06-17
---

# Phase 6 Plan 06-10: Reescrita do Construtor de Automações Summary

Construtor de automações reescrito como pipeline ordenado de etapas componíveis fiel ao mockup aprovado (06-MOCKUP-automacoes.html), com 4 ações (identificar arquivo/identificar tipo/renomear/mover), drag-and-drop nativo, chips de token vindos dos campos reais do template, pré-visualização ao vivo e normalização de aspas em paths.

## O que foi construído

- **`types.ts`** — `StepActionType` ganhou `identify_file` (gate por extensão digitável, D-17); `route` mantido no tipo apenas para tolerar pipelines legados do backend sem expô-lo na UI (D-22).
- **`AutomationsPage.tsx`** (reescrita completa, 84% rewrite):
  - **4 ações do v1** (D-13/D-17): Identificar arquivo (extensão digitável `.pdf, .xlsx` + pasta de origem opcional), Identificar tipo (select de template), Renomear (padrão de nome com tokens), Mover (pasta destino com tokens). **Sem** "Decidir tratativa" (D-22).
  - **Construtor**: lista ordenada de etapas numeradas com conector descendente `↓`, edição inline por etapa (cada card renderiza seus próprios campos conforme a ação), switch ativar/pausar por etapa, switch ativar/pausar do pipeline inteiro no header.
  - **Reordenação (D-20)**: drag-and-drop HTML5 nativo (`draggable` + dragstart/dragover/drop/dragend, feedback visual `inset box-shadow`) **e** botões ↑/↓ com `aria-label` para acessibilidade.
  - **Tokens (D-19)**: os chips são os **campos reais** do template escolhido no primeiro gate "Identificar tipo" do pipeline, buscados via `useTemplates`. Clicar insere `{campo}` no input. Pré-visualização ao vivo usando `hint`/nome como valor de exemplo. Sem gate de template → mensagem orientando a adicionar o gate (sem chips), coerente.
  - **Paths (D-21)**: campos de caminho (Mover destino, pasta de origem) normalizam aspas nas pontas no `onBlur` via `stripQuotes`, espelhando o `strip_quotes` do backend; microcopy "aceita com ou sem aspas".
  - **Persistência**: rascunho local (`StepDraft[]`) é a fonte de verdade do editor; "Salvar pipeline" envia a coleção inteira (PATCH substitui / POST cria). Hidratação a partir do backend que não sobrescreve alterações locais não salvas (`dirty` guard).
  - **Contrato real**: serializa `identify_file → {extensions, source_folder}`, `identify_type → {template_id}`, `rename → {name_pattern}`, `move → {folder_pattern}`. Sem rotas inventadas.
- **DryRunPage**: já consistente com o contrato (4 colunas origem→destino→situação, situação por cor reusando `--st-*`, "Aplicar" só após carregar, aplicar por-doc/lote + desfazer com linguagem de reversibilidade) — nenhuma mudança necessária.
- **App.tsx**: rotas `automacoes` e `dryrun` já registradas — nenhuma mudança necessária.

## Decisões / Desvios do mockup

- **Mockup mostra "Tipo de arquivo" como `<select>`**, mas D-17 manda **extensão DIGITÁVEL** (múltiplas). Segui a decisão D-17 (input texto) — a decisão prevalece sobre o mockup. (Não é um Rule de auto-fix; é o spec mandando D-17 sobre o mockup.)
- **Edição inline por etapa** (cada card edita a si mesmo) em vez do modal/form separado da versão anterior — fiel ao mockup, que renderiza os campos diretamente em cada step.

## Verificação executada

- `cd frontend && npx tsc --noEmit` → EXIT 0
- `cd frontend && npm run build` (`tsc -b && vite build`) → built, EXIT 0

## Self-Check: PASSED

- FOUND: frontend/src/pages/AutomationsPage.tsx (modified)
- FOUND: frontend/src/types.ts (modified)
- FOUND commit 2290291 (types: identify_file)
- FOUND commit 425ea04 (reescrita do construtor)

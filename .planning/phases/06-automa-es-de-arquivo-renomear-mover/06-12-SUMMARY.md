---
phase: 6
plan: 12
subsystem: frontend
tags: [automations, ui, react, conditions-actions, drag-and-drop, tokens]
requires:
  - "backend /automations API (Automation + conditions[] + actions[]) — D-23..D-26"
  - "GET /templates (campos para tokens — D-26)"
provides:
  - "Tela de Automações reescrita: LISTA de N automações + editor Condições→Ações (mockup v3)"
  - "CRUD de N automações fiado ao contrato real (conditions[]/actions[])"
  - "DryRunPage consistente com o novo DryRunRow (sem routed/route_target)"
affects:
  - frontend/src/pages/AutomationsPage.tsx
  - frontend/src/pages/DryRunPage.tsx
  - frontend/src/types.ts
  - frontend/src/lib/api.ts
  - frontend/src/hooks/useAutomations.ts
tech-stack:
  added: []
  patterns:
    - "Rascunho local por automação selecionada + PATCH/POST substitui coleções inteiras"
    - "Drag-and-drop HTML5 nativo + ↑/↓ para reordenar ações (sem dependência npm)"
    - "Chips de token = campos REAIS do template da condição 'Tipo de documento'"
    - "Normalização de aspas em paths no onBlur (D-21)"
key-files:
  created:
    - .planning/phases/06-automa-es-de-arquivo-renomear-mover/06-12-SUMMARY.md
  modified:
    - frontend/src/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/hooks/useAutomations.ts
    - frontend/src/pages/AutomationsPage.tsx
    - frontend/src/pages/DryRunPage.tsx
decisions:
  - "Frontend estava desatualizado (modelo pipeline/steps/filters): reescrito p/ o modelo final Automation+conditions+actions"
  - "Toggle ativo/pausado persiste direto só quando não há alterações pendentes; senão entra no rascunho e salva junto"
metrics:
  duration: ~25min
  completed: 2026-06-18
---

# Phase 6 Plan 12: Reescrita do frontend de Automações (Condições → Ações) Summary

Tela de Automações reescrita para o MODELO FINAL aprovado (mockup v3, D-23..D-26): LISTA de N automações nomeadas + editor "CONDIÇÕES (quando rodar, combinadas por E) → AÇÕES (renomear/mover, ordenadas)", fiada ao contrato real `/automations` (`conditions[]`/`actions[]`).

## O que foi construído

### `types.ts` — novo modelo de dados (substituiu pipeline/steps/filters)
- Removidos: `StepActionType`, `StepFilterType`, `RuleOperator`, `RuleConjunction`, `RouteTarget`, `StepFilter(Create)`, `PipelineStep(Create)`, `AutomationPipeline`, `PipelineCreate`, `PipelinePatch`, e os campos `routed`/`route_target` de `DryRunRow`.
- Adicionados (espelhando os schemas Pydantic do backend): `ConditionField` (`source_folder|extension|template|field|filename|size`), `ConditionOperator` (`eq|contains|gt|lt`), `ActionType` (`rename|move`), `AutomationCondition(Create)`, `AutomationAction(Create)`, `Automation`, `AutomationCreate`, `AutomationPatch`. `DryRunRow` agora tem `automation_id` (qual automação casou, D-25).

### `lib/api.ts` — funções renomeadas para o recurso real
- `getPipelines/createPipeline/updatePipeline/deletePipeline` → `getAutomations/createAutomation/updateAutomation/deleteAutomation` (mesmos paths `/automations`). `dry-run/apply/undo` inalterados.

### `hooks/useAutomations.ts`
- `useCreatePipeline/useUpdatePipeline/useDeletePipeline` → `useCreateAutomation/useUpdateAutomation/useDeleteAutomation`. Invalidação `['automations']` preservada; ações continuam invalidando `documents`/`attention`.

### `pages/AutomationsPage.tsx` — reescrita completa conforme mockup v3
- **LISTA** (coluna 300px): cada automação com dot ativo/pausado, nome, resumo das condições; seleção; "+ Nova automação"; badge "(nova)" para drafts não persistidos. Suporta N automações (corrige o `data[0]` hardcoded antigo, D-23).
- **EDITOR** (cabeçalho com nome editável + switch ativo/pausado):
  - **Quando rodar — Condições**: linhas `SE/E [campo ▾] [operador ▾] [valor]`. 6 tipos de campo. "Tipo de arquivo" e "Pasta de origem" usam input mono; **"Tipo de documento" = select de template real**; "Valor de campo" exibe campo extra `field_name`. "+ Adicionar condição". Pasta de origem normaliza aspas no onBlur (D-21).
  - **O que fazer — Ações**: cards Renomear (violeta `--st-quarentena` #7C3AED) e Mover (verde `--st-tratado` #15803D), ordenados por **drag-and-drop nativo + botões ↑/↓** (D-24), com conector `↓`. Inputs de padrão mono; **chips de token = campos do template** referenciado pela condição "Tipo de documento" (D-26) — sem essa condição, dica em vez de chips; **preview ao vivo** resolvendo `{campo}`; Mover normaliza aspas no onBlur. "+ Renomear / + Mover".
  - **Savebar**: Descartar (quando dirty) / Excluir (com confirmação) / Salvar automação.
- Persistência: validação local → POST (nova, com `position`) ou PATCH (existente, substituindo `conditions`/`actions` inteiros). Rascunho local não é sobrescrito pela hidratação enquanto houver alterações não salvas.

### `pages/DryRunPage.tsx` — consistência com o novo contrato
- Removida toda a lógica de `routed`/`route_target` (`ROUTE_SITUATION`, badge de roteamento). `isApplicable` agora é `!blocked && !no_match`. Card de stat "Roteados / sem etapa" → "Sem automação" (`noMatchCount`). Textos ajustados para "automação" em vez de "pipeline/etapa".

## Verificação técnica

- `npx tsc --noEmit` — sem erros.
- `npm run build` (tsc -b && vite build) — sucesso, 82 módulos, build em ~258ms.
- `grep` por símbolos do modelo antigo (`Pipeline`, `StepFilter`, `routed`, `route_target`, etc.) em `src/` — zero ocorrências órfãs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Frontend completamente dessincronizado da API real**
- **Encontrado durante:** leitura inicial dos contratos.
- **Issue:** `AutomationsPage`/`types`/`api`/`hooks` ainda usavam o modelo antigo (pipeline de steps com filtros por step + gates `identify_file`/`identify_type` + ação `route`), enquanto o backend (`api/automations.py` + `models/automation.py`) já fornece o modelo final `Automation` com `conditions[]`/`actions[]`. As chamadas à API teriam falhado (campos inexistentes).
- **Fix:** reescrita completa dos 5 arquivos para o contrato real. Faz parte do escopo do prompt (que descreve o frontend como desatualizado) — registrado como deviation por ser correção de incompatibilidade, não só estética.

## Known Stubs

Nenhum. Todos os campos da UI estão fiados a dados reais (automações da API, templates da API para tokens). Valores de exemplo na pré-visualização (`sampleValue` usa `hint`/nome do campo do template) são intencionais e locais — o backend é a autoridade da materialização.

## Self-Check: PASSED

- FOUND: frontend/src/pages/AutomationsPage.tsx
- FOUND: frontend/src/pages/DryRunPage.tsx
- FOUND: frontend/src/types.ts
- FOUND: frontend/src/lib/api.ts
- FOUND: frontend/src/hooks/useAutomations.ts
- FOUND: .planning/phases/06-automa-es-de-arquivo-renomear-mover/06-12-SUMMARY.md
- tsc --noEmit: PASS · vite build: PASS

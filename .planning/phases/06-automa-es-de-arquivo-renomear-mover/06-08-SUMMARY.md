---
phase: 06-automa-es-de-arquivo-renomear-mover
plan: 08
subsystem: frontend-automacoes
tags: [frontend, react, pipeline, dry-run, ui-spec, code-and-config]
status: paused-at-checkpoint
requires:
  - "06-07 backend: API /automations CRUD aninhado (pipeline→steps→filtros) + dry-run/apply/undo"
provides:
  - "Construtor de PIPELINE de automações (S1/S2/S3) fiado à API real"
  - "Dry-run origem→destino-final por documento (S4) + aplicar/desfazer (S5/S6)"
  - "tipos/api/hooks de pipeline (substituem o modelo de regra única)"
affects:
  - frontend/src/types.ts
  - frontend/src/lib/api.ts
  - frontend/src/hooks/useAutomations.ts
  - frontend/src/pages/AutomationsPage.tsx
  - frontend/src/pages/DryRunPage.tsx
tech-stack:
  added: []
  patterns:
    - "TanStack Query: query lista pipelines; mutations invalidam ['automations']; ações invalidam ['documents']+['attention']"
    - "Form inline schema-first (molde TemplatesPage) com confirmRemove overlay+card padding:22"
    - "Reordenação por ↑/↓ (code-and-config, sem lib de DnD)"
    - "Cores via tokens --st-*/--accent (sem hex); valores texto puro (0 dangerouslySetInnerHTML)"
key-files:
  created: []
  modified:
    - frontend/src/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/hooks/useAutomations.ts
    - frontend/src/pages/AutomationsPage.tsx
    - frontend/src/pages/DryRunPage.tsx
decisions:
  - "Modelo v1 da UI: UM pipeline (o primeiro de GET /automations); o construtor edita suas ETAPAS. Se não existir, o primeiro 'Salvar etapa' cria o pipeline com a etapa (name='Pipeline de automação')."
  - "PATCH substitui a coleção inteira de steps (contrato do backend): inserir/editar/remover/reordenar/pausar montam a lista completa de StepCreate[] e persistem via useUpdatePipeline (ou useCreatePipeline se não há pipeline)."
  - "Dry-run: aplicável = !blocked && !routed && !no_match (só esses materializam); roteado e sem-etapa têm checkbox disabled."
metrics:
  duration_min: 5
  completed: pending-checkpoint
---

# Phase 06 Plan 08: Frontend do PIPELINE de Automações Summary

Reescrita do frontend de automações do modelo de regra única para o modelo de PIPELINE honrando o 06-UI-SPEC APROVADO: `AutomationsPage` virou o construtor de pipeline (S1 lista ordenada de etapas numeradas com conector descendente + S2 editor de etapa com ação e filtros E/OU + S3 editor de token com pré-visualização ao vivo) e `DryRunPage` mostra UM par origem→destino-final por documento com situação sinalizada por cor (incl. P9 roteado e P10 sem-etapa) + aplicar/desfazer reversível. Zero dependência npm nova; tokens de design travados.

## Tasks Completas (implementação)

| Task | Nome | Commit | Arquivos |
| ---- | ---- | ------ | -------- |
| 1 | Tipos + api + hooks do pipeline | 510e4cc | types.ts, lib/api.ts, hooks/useAutomations.ts |
| 2 | AutomationsPage — construtor (S1/S2/S3) | 42bfb71 | pages/AutomationsPage.tsx |
| 3 | DryRunPage — preview (S4) + aplicar/desfazer (S5/S6) | 1bff65f | pages/DryRunPage.tsx |
| 4 | Checkpoint human-verify | — | (verificação visual pendente) |

## O que foi construído

### Task 1 — tipos/api/hooks de pipeline
- `types.ts`: uniões `StepActionType` (move/rename/identify_type/route), `StepFilterType` (field/source_folder/extension/filename/size/template), `RouteTarget` (em_revisao/nao_tratar/ignorar); interfaces `StepFilter(Create)`, `PipelineStep(Create)`, `AutomationPipeline`/`PipelineCreate`/`PipelinePatch`. `DryRunRow` ganhou `routed`/`route_target`/`no_match` (P9/P10). Removidos os tipos de regra antiga (AutomationRule/RuleCondition/RuleCreate/RulePatch/RuleConditionCreate) — sem referências externas (verificado por grep).
- `lib/api.ts`: `getPipelines`/`getPipeline`/`createPipeline`/`updatePipeline`/`deletePipeline` (CRUD aninhado); `postDryRun`/`postApply`/`postUndo` mantidos.
- `hooks/useAutomations.ts`: `useAutomations` (query), `useCreatePipeline`/`useUpdatePipeline`/`useDeletePipeline`, `useDryRun`/`useApply`/`useUndo`.

### Task 2 — AutomationsPage (S1/S2/S3)
- S1: cards de etapa numerados (1,2,3…) em ordem de `position`, com pílula de AÇÃO em accent (`.flow-pill.action`) + pílulas de FILTRO neutras (`.flow-pill`), resumo dos params (mono), Switch ativar/pausar (etapa pausada = opacidade .6 + badge "Pausada"), ações ↑/↓/editar/remover icon-only com aria-label+title. **Conector descendente** (arrowDown em `--text-3`) entre cards. Empty state "Nenhuma etapa de automação ainda" + "Criar primeira etapa". Loading/erro.
- S2: editor inline — (a) Tipo de ação como 4 cartões com hints do Copywriting; (b) filtros 0..N combináveis E/OU (select tipo + campo se field + operador = > < contém + valor), hint do filtro de tamanho; (c) params por ação (identify_type→template, route→target). Etapa sem filtro → badge "Aplica-se a todos os documentos".
- S3: chips de token clicáveis (aria-label "Inserir {campo} no padrão") que inserem no padrão + pré-visualização ao vivo (reusa SAMPLE_VALUES/resolvePattern) + microcopy "Cada {campo} é trocado pelo valor extraído" + aviso de campo faltante.
- confirmRemove de etapa em linguagem reversível ("As etapas seguintes continuam valendo…").

### Task 3 — DryRunPage (S4/S5/S6)
- S4: `table.docs` origem→destino (mono) + coluna situação via `SituationBadge` com precedência bloqueio→roteado→sem-etapa→duplicata→colisão→pronto. Cores: vermelho só bloqueio (D-07); âmbar colisão (D-09); azul duplicata (D-10); roteado âmbar (revisão) / violeta `--st-quarentena` (não-tratar/ignorar) (P9); neutro `badge-off` sem-etapa (P10); verde pronto. Contagens no topo (prontos/duplicatas/roteados-sem-etapa/bloqueados). Seleção por-linha/lote; linhas não-materializáveis com checkbox disabled. "Aplicar automações"/"Aplicar selecionados" disabled até o preview carregar.
- S5/S6: desfazer por-lote (run_id) com diálogo em linguagem de reversibilidade.

## Deviations from Plan

None — plan executado como escrito. App.tsx já registrava as rotas `automacoes`/`dryrun` (sem mudança necessária). Build em modo `tsc -b` (noUnusedLocals) exigiu remover um import não usado em AutomationsPage — ajuste trivial dentro do mesmo commit da Task 2, não é desvio de escopo.

## Verification

- `cd frontend && npx tsc --noEmit` — limpo
- `cd frontend && npm run build` — sucesso (vite v8.0.16, 82 módulos, 254ms)
- Gates de aceitação: dangerouslySetInnerHTML==0 (ambas as páginas), hex hardcoded==0 (ambas), drag/dnd==0, arrowUp/Down>=1, aria-label>=3, 4 ações presentes, situações P8/P9/P10/D-07/D-09/D-10 presentes, disabled presente, undo/Desfazer presente.
- `package.json`/`package-lock.json` sem mudança — zero dependência npm nova.

## Self-Check: PASSED

- frontend/src/types.ts — FOUND
- frontend/src/lib/api.ts — FOUND
- frontend/src/hooks/useAutomations.ts — FOUND
- frontend/src/pages/AutomationsPage.tsx — FOUND
- frontend/src/pages/DryRunPage.tsx — FOUND
- commit 510e4cc — FOUND
- commit 42bfb71 — FOUND
- commit 1bff65f — FOUND

## Checkpoint pendente (Task 4 — human-verify)

Verificação visual/funcional do frontend reescrito (S1..S6) — ver passos no PLAN.md how-to-verify. autonomous:false: a fase só fecha após aprovação humana.

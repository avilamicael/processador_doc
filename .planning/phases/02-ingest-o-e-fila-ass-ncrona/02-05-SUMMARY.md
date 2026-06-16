---
phase: 02-ingest-o-e-fila-ass-ncrona
plan: 05
subsystem: ui
tags: [react, tanstack-query, typescript, vite, polling, fetch]

# Dependency graph
requires:
  - phase: 02-04
    provides: API fina do backend (CRUD /watched-folders, GET /documents + counts, GET /documents/duplicates-count, POST /rescan)
  - phase: 02-03
    provides: estados de domínio reais (DocState) e estado terminal PROCESSANDO+aguardando_extracao
provides:
  - Camada de dados frontend net-new (TanStack Query 5.101 + cliente fetch tipado src/lib/api.ts)
  - Hooks de domínio com polling sem flicker (useDocuments/useDuplicatesCount/useRescan, useWatchedFolders + mutations CRUD)
  - StatusPill mapeando estados de domínio reais → label pt-BR → token --st-* (inclui "Aguardando extração", nunca "Tratado" nesta fase)
  - Tela Documentos lendo dados reais por polling 4s com empty/loading/error e contador de duplicados neutro
  - Tela Configurações → Pastas monitoradas como CRUD real persistido no backend
affects: [phase-03-extracao, phase-04-templates-classificacao, phase-05-revisao-quarentena, ui, frontend]

# Tech tracking
tech-stack:
  added: ["@tanstack/react-query 5.101"]
  patterns:
    - "Cliente fetch tipado de origem única (base URL relativa, FastAPI serve o front em prod) que lança em !res.ok para o TanStack Query tratar"
    - "Hooks de query com placeholderData=(prev)=>prev + refetchIntervalInBackground:false = polling sem flicker e sem refetch em aba inativa"
    - "Mutations invalidam a queryKey correspondente; a fonte de verdade é sempre a API (sem otimismo que mascare falha — T-02-13)"
    - "StatusPill token-driven (var(--st-${token})/var(--st-${token}-bg)) com mapa estado→label→token derivado do UI-SPEC LOCKED"

key-files:
  created:
    - frontend/src/lib/api.ts
    - frontend/src/hooks/useDocuments.ts
    - frontend/src/hooks/useWatchedFolders.ts
  modified:
    - frontend/package.json
    - frontend/src/main.tsx
    - frontend/src/types.ts
    - frontend/src/components/StatusPill.tsx
    - frontend/src/pages/DocumentsPage.tsx
    - frontend/src/pages/ConfigPage.tsx
    - frontend/src/App.tsx

key-decisions:
  - "Cadastro de pasta permanece por CAMINHO ABSOLUTO via campo de texto (decisão do usuário na verificação visual); seletor de pasta visual, normalização de aspas e validação de existência foram explicitamente adiados — fora de escopo desta fase."
  - "Mapeamento de estados autoritativo do UI-SPEC: RECEBIDO→Na fila, PROCESSANDO→Processando, terminal (processando+aguardando_extracao)→Aguardando extração (azul muted, nunca verde), FALHA→Falha; CONCLUIDO/Tratado reservado mas inalcançável nesta fase."
  - "Polling de documentos a 4s com placeholderData=prev para evitar flicker da tabela; refetch de background silencioso, nunca limpar a tabela."

patterns-established:
  - "Camada api/hooks: fetch tipado lança em erro → TanStack Query gerencia loading/error; UI exibe estados dentro do card (skeleton/empty/erro com Tentar novamente)"
  - "Contador de duplicados neutro no rodapé da tabela (--text-3), informativo e não alerta"

requirements-completed: [ING-02, ING-06]

# Metrics
duration: ~8min
completed: 2026-06-16
---

# Phase 2 Plan 5: Frontend de Ingestão (Documentos por polling + CRUD de Pastas) Summary

**TanStack Query 5.101 + cliente fetch tipado conectando as telas Documentos (polling 4s sem flicker, counts e contador de duplicados neutro) e Configurações → Pastas monitoradas (CRUD real persistido) à API da Fase 2, com StatusPill mapeando estados de domínio reais ("Aguardando extração", nunca "Tratado")**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-15T22:29:38Z (Task 1 commit)
- **Completed:** 2026-06-16
- **Tasks:** 3/3 (Task 3 = verificação humana APROVADA)
- **Files modified:** 10 (3 criados, 7 modificados)

## Accomplishments

- Camada de dados frontend net-new: `@tanstack/react-query` instalado e provido via `QueryClientProvider` em `main.tsx`, cliente fetch tipado em `src/lib/api.ts` e hooks de domínio (`useDocuments`/`useDuplicatesCount`/`useRescan`, `useWatchedFolders` + mutations CRUD).
- Tipos de domínio reais substituindo os mocks: `DocState = recebido | processando | em_revisao | concluido | quarentena | falha`; `Doc`/`Folder` nas formas da API.
- `StatusPill` estendido para mapear estado de domínio real (+ `last_completed_step`) → label pt-BR → token `--st-*`, com o terminal "Aguardando extração" em azul muted e nunca "Tratado/Concluído" nesta fase.
- Tela Documentos lendo dados reais por polling 4s sem flicker (`placeholderData=prev`), com stat-cards/chips por `counts`, empty/loading/error dentro do card, botão "Forçar varredura" (rescan) e contador de duplicados neutro no rodapé.
- Tela Configurações → Pastas monitoradas convertida em CRUD real persistido (adicionar/editar/remover/ativar; confirmação destrutiva; default "Não separar").
- Verificação visual end-to-end dos 8 passos APROVADA pelo usuário ("aprovado").

## Task Commits

Each task was committed atomically:

1. **Task 1: TanStack Query + cliente API tipado + hooks + tipos de domínio** - `a6c5fab` (feat)
2. **Task 2: Fiar StatusPill + DocumentsPage + ConfigPage(PastasTab) aos dados reais** - `7858b40` (feat)
3. **Task 3: Verificação visual end-to-end (Documentos + Pastas)** - checkpoint human-verify, **APROVADO pelo usuário** (sem commit de código — verificação manual)

**Plan metadata:** ver commit final `docs(02-05): ...`

## Files Created/Modified

- `frontend/src/lib/api.ts` - Cliente fetch tipado (getDocuments/getDuplicatesCount/getWatchedFolders/create/update/delete/postRescan); lança em !res.ok.
- `frontend/src/hooks/useDocuments.ts` - Hooks TanStack Query: `useDocuments` (polling 4s, sem flicker), `useDuplicatesCount`, `useRescan` (mutation que invalida ['documents']).
- `frontend/src/hooks/useWatchedFolders.ts` - `useWatchedFolders` (query) + `useCreateFolder`/`useUpdateFolder`/`useDeleteFolder` (mutations que invalidam ['watched-folders']).
- `frontend/package.json` - Adicionada dependência `@tanstack/react-query`.
- `frontend/src/main.tsx` - `QueryClient` + `QueryClientProvider` envolvendo `<App />` dentro do `StrictMode`.
- `frontend/src/types.ts` - `DocState` de domínio real + `Doc`/`Folder` nas formas da API; removida a união mock.
- `frontend/src/components/StatusPill.tsx` - Mapa estado→label→token (inclui "Aguardando extração"), token-driven.
- `frontend/src/pages/DocumentsPage.tsx` - Lê dados reais por polling; counts, empty/loading/error, contador de duplicados neutro, "Forçar varredura"; mock DOCS removido.
- `frontend/src/pages/ConfigPage.tsx` - PastasTab como CRUD real via `useWatchedFolders`; confirmação destrutiva; RegrasTab/LeituraTab/IntegracoesTab fora de escopo.
- `frontend/src/App.tsx` - Estado de filtros/seleção ajustado para os dados reais; sem redesenho de shell.

## Decisions Made

- **Cadastro de pasta por caminho absoluto via texto (mantido por decisão do usuário).** Durante a verificação visual o usuário decidiu manter o campo de texto de caminho absoluto como está; seletor visual, normalização de aspas e validação de existência ficam fora de escopo desta fase (ver Notes / Follow-ups).
- **Mapeamento de estados conforme UI-SPEC LOCKED** (autoritativo), com o terminal exibido como "Aguardando extração" e "Tratado/Concluído" reservado mas inalcançável na Fase 2.
- **Polling a 4s com `placeholderData=prev`** para eliminar flicker; refetch de background silencioso e `refetchIntervalInBackground:false`.

## Deviations from Plan

None - plan executed exactly as written. (As três tarefas seguiram o plano; a Task 3 era checkpoint humano e foi aprovada.)

## Issues Encountered

None.

## Notes / Follow-ups

Ideias levantadas na verificação visual e **explicitamente adiadas por decisão do usuário** — registradas aqui, sem plano nem código nesta fase nem na Fase 2:

- **Seletor de pasta visual (estilo Explorer).** Num app web o navegador não expõe o caminho absoluto do filesystem (nem em `<input type=file>` nem em `showDirectoryPicker`); o seletor nativo só é viável no empacotamento desktop futuro (Tauri) ou via diálogo server-side com GUI no modo local. **Adiado para a fase desktop.**
- **Normalização de aspas no caminho colado.** Não implementado agora — decisão do usuário manter o input cru.
- **Validação de existência da pasta no cadastro.** Não implementado agora — decisão do usuário. (O backend já valida o path com `Path.resolve` em 02-04; a verificação de existência/ acessibilidade fica como melhoria futura.)

Estes itens NÃO são bloqueadores e NÃO geram trabalho nesta fase.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Fase 2 (Ingestão e Fila Assíncrona) concluída: watcher + fila idempotente + dedup + separação + UI de Documentos e Pastas, com verificação visual end-to-end aprovada.
- Pronto para a Fase 3 (Extração Genérica via IA e Medição de Tokens): documentos chegam ao estado terminal PROCESSANDO+aguardando_extracao, prontos para a etapa de extração consumir.
- Lembrete operacional herdado: rodar uvicorn com `--workers 1` no modo padrão (T-02-12 / fila in-process single-writer).

## Self-Check: PASSED

- SUMMARY.md exists ✓
- Task 1 commit `a6c5fab` exists ✓
- Task 2 commit `7858b40` exists ✓
- Task 3 = checkpoint human-verify aprovado pelo usuário (sem commit de código) ✓

---
*Phase: 02-ingest-o-e-fila-ass-ncrona*
*Completed: 2026-06-16*

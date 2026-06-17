---
phase: 05-confian-a-revis-o-humana-e-quarentena
plan: 04
subsystem: frontend
tags: [attention, triage, confidence-badge, review, reclassify, retry, approve, patch-field, review-threshold, tanstack-query, react]

# Dependency graph
requires:
  - phase: 05-confian-a-revis-o-humana-e-quarentena
    plan: 03
    provides: "GET /documents/attention (3 baldes), POST retry/reclassify/approve, PATCH fields/{name}, GET/PUT /config/review-threshold; confidence_score/manually_corrected nos schemas Out"
  - phase: 04-templates-sub-templates-e-classifica-o
    plan: 06
    provides: "DocumentsPage/DocumentDetailModal (molde de página + tabela de campos), StatusPill, GET /templates, useDocuments (polling sem flicker)"
provides:
  - "Página 'Precisam de atenção' (S1-S4): 3 baldes (Falhas/Quarentena/Em revisão) com contagem, motivo e ação leve por item, via polling TanStack Query"
  - "ConfidenceBadge (S5) reutilizável: faixas TRAVADAS Alta/Média/Baixa por token --st-*, número em mono, fallback neutro para score null"
  - "Hooks useAttention: useAttentionDocuments (polling 4s) + mutations retry/reclassify/patch/approve invalidando ['attention']+['documents'] + useReviewThreshold/useSaveReviewThreshold"
  - "lib/api.ts + types.ts estendidos com a superfície de triagem e o limiar"
  - "Campo S6 'Limiar de confiança' na Config (0-100%) lendo/salvando /config/review-threshold"
  - "Navegação: item 'atencao' no grupo OPERAÇÃO + ícone 'alert'"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ConfidenceBadge espelha StatusPill: mapa estático faixa->{label, token} + render token-driven var(--st-${token})/var(--st-${token}-bg); número 0-100% em var(--font-mono); fallback neutro (--surface-3/--text-3) para score null"
    - "useAttention espelha useDocuments/useRescan: query polling 4s (keepPreviousData + refetchIntervalInBackground:false) + helper useInvalidateAttention compartilhado por todas as mutations (invalida ['attention']+['documents'])"
    - "AttentionPage molde DocumentsPage: stat-grid de contagem + chips por balde + estados isInitialLoading/isError/isEmpty; cada balde renderiza um sub-componente de linha (FailureRow/QuarantineRow/ReviewRow) com sua mutation isolada"
    - "S6 converte 0-100 (UI) <-> 0.0-1.0 (API); useEffect sincroniza o input com o valor carregado; validação client-side 0..100 antes do PUT (backend é o guard 422)"
    - "Gate D-07 na UI (defesa em profundidade): botão 'Aprovar' disabled enquanto houver campo inválido + hint; backend permanece o guard autoritativo (409)"

key-files:
  created:
    - frontend/src/components/ConfidenceBadge.tsx
    - frontend/src/hooks/useAttention.ts
    - frontend/src/pages/AttentionPage.tsx
  modified:
    - frontend/src/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/components/Sidebar.tsx
    - frontend/src/components/Icon.tsx
    - frontend/src/pages/ConfigPage.tsx
    - frontend/src/App.tsx

key-decisions:
  - "ConfidenceBadge usa className 'badge' (não 'pill') reusando .badge existente; cor via style inline token-driven; fallback neutro usa --surface-3/--text-3 (não --st-*) para distinguir 'sem score' de 'baixa'"
  - "S6 (Limiar) encaixado na aba 'Leitura de dados' da Config como sub-componente ReviewThresholdField com seu próprio query/mutation; é o ÚNICO campo realmente persistido daquela aba (os demais permanecem mock visual da Fase 2)"
  - "Sem visualizador de documento (D-06): a UI mostra só motivo + valores de campo; nenhum embed/imagem/PDF/texto bruto"
  - "Ícone 'alert' adicionado a Icon.tsx no mesmo estilo de stroke (sw 1.8, viewBox 24) para o item de navegação, evitando lib externa"

patterns-established:
  - "Componente de badge derivado de score (faixa->token) isolado e reutilizável em múltiplas superfícies (S4 + DocumentDetailModal)"
  - "Hook de invalidação compartilhado entre mutations irmãs (useInvalidateAttention) para garantir consistência das queryKeys"

requirements-completed: [REV-02, REV-03, REV-04, REV-05]

# Metrics
duration: 5min
completed: 2026-06-17
---

# Phase 5 Plan 04: Frontend "Precisam de atenção" Summary

**A visão única de triagem (S1-S4) com os 3 baldes (Falhas/Quarentena/Em revisão), polling sem flicker, ConfidenceBadge reutilizável (S5), correção inline de campos com gate D-07 de aprovação, o campo de Limiar global na Config (S6) e a navegação — tudo sobre o design system TRAVADO (04/05-UI-SPEC), sem visualizador de documento (D-06). Fecha o loop REV-03/REV-04/REV-05 visualmente, consumindo os contratos do Plan 03.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-17T03:57:28Z
- **Tasks:** 3 (2 implementadas + 1 checkpoint de verificação humana pendente)
- **Files modified:** 9 (3 criados, 6 editados)

## Accomplishments

- **Task 1 — types/api/hooks/ConfidenceBadge:**
  - `types.ts`: `Page` ganha `'atencao'`; `ClassificationField` ganha `manually_corrected`; `Classification` ganha `confidence_score`; novos `AttentionItem`/`ReviewItem`/`AttentionList`/`ReviewThreshold`.
  - `lib/api.ts`: `getAttention`, `postRetry`, `postReclassify`, `patchField` (com `encodeURIComponent`), `postApprove`, `getReviewThreshold`, `putReviewThreshold` — todos reusando o helper `request<T>`.
  - `ConfidenceBadge.tsx`: badge token-driven espelhando `StatusPill`; faixas TRAVADAS (>=0.8 Alta/tratado; >=0.5 Média/leitura; <0.5 Baixa/erro); número em `var(--font-mono)`; fallback neutro `—` para score null; **zero accent**.
  - `hooks/useAttention.ts`: `useAttentionDocuments` (polling 4s, keepPreviousData, sem refetch em background) + `useRetryDocument`/`useReclassifyDocument`/`usePatchField`/`useApproveDocument` (cada uma invalida `['attention']`+`['documents']`) + `useReviewThreshold`/`useSaveReviewThreshold`.
- **Task 2 — AttentionPage + S6 + navegação:**
  - `AttentionPage.tsx`: `stat-grid` de contagem por balde + `chips` para alternar baldes + estados `isInitialLoading` (skeleton)/`isError` (bloco centralizado + "Tentar novamente")/`isEmpty` ("Tudo em dia"). FALHA (S2): motivo + "Tentar de novo"/"Reenviando…". QUARENTENA (S3): motivo + `select` "Atribuir template" + "Reclassificar" `disabled` até escolher template. EM_REVISAO (S4): `ConfidenceBadge` + tabela Campo/Valor/Normalizado/Marca; campo inválido vira `input` (mono) com `aria-label="Corrigir valor de {campo}"` + "Salvar correção"; badge "corrigido manualmente" quando `manually_corrected`; "Aprovar documento" `disabled` enquanto houver inválido + hint (D-07). Valores como texto puro (sem `dangerouslySetInnerHTML`).
  - `ConfigPage.tsx`: sub-componente `ReviewThresholdField` na aba Leitura — input numérico 0-100 com sufixo "%", hint do UI-SPEC, "Salvar limiar"/"Salvando…", conversão 0-100 <-> 0.0-1.0, estados loading/erro.
  - `Sidebar.tsx` + `Icon.tsx`: item "Precisam de atenção" (ícone `alert` novo) no grupo OPERAÇÃO; `App.tsx`: PAGE_META + render condicional.
- **Build:** `npm run build` (tsc -b + vite build) verde em ambas as tasks.

## Task Commits

1. **Task 1: types, api client, ConfidenceBadge e hooks useAttention** - `f445292` (feat)
2. **Task 2: AttentionPage (3 baldes + ações), S6 na Config e navegação** - `a9b04df` (feat)

_A entrada `PAGE_META['atencao']` foi incluída no commit da Task 1 porque a union `Page` ganhar `'atencao'` torna o `Record<Page, ...>` incompleto — sem ela o `tsc` da Task 1 não passaria. O restante da navegação (import + render + Sidebar) ficou na Task 2._

## Files Created/Modified

- `frontend/src/components/ConfidenceBadge.tsx` (NOVO) - badge de confiança reutilizável (S5)
- `frontend/src/hooks/useAttention.ts` (NOVO) - query de polling + 4 mutations de ação + 2 hooks do limiar
- `frontend/src/pages/AttentionPage.tsx` (NOVO) - visão "Precisam de atenção" (S1-S4)
- `frontend/src/types.ts` - Page+'atencao'; +manually_corrected/+confidence_score; +AttentionItem/ReviewItem/AttentionList/ReviewThreshold
- `frontend/src/lib/api.ts` - +getAttention/postRetry/postReclassify/patchField/postApprove/get+putReviewThreshold
- `frontend/src/components/Sidebar.tsx` - item 'atencao' no grupo OPERAÇÃO
- `frontend/src/components/Icon.tsx` - +ícone 'alert' (mesmo estilo de stroke)
- `frontend/src/pages/ConfigPage.tsx` - +ReviewThresholdField (S6) na aba Leitura
- `frontend/src/App.tsx` - PAGE_META['atencao'] + import + render condicional

## Decisions Made

- **ConfidenceBadge usa `.badge` (não `.pill`):** o UI-SPEC §Component Inventory autoriza "badge de confiança (`.conf-badge` — espelhar `.badge`)"; reusei `.badge` direto com cor inline token-driven, sem criar classe nova.
- **Fallback neutro usa `--surface-3`/`--text-3`, não `--st-*`:** "sem score" (ex.: ainda sem cálculo) é visualmente distinto de "Baixa" (vermelho) — evita confundir ausência de dado com confiança baixa.
- **S6 na aba "Leitura de dados":** é a aba semanticamente ligada a confiança/extração; o campo é o único realmente persistido ali (os outros controles daquela aba seguem mock visual da Fase 2, fora de escopo).
- **Gate D-07 na UI aproximado por "qualquer campo inválido":** o backend re-deriva a validade dos OBRIGATÓRIOS (guard autoritativo, 409); a UI bloqueia de forma conservadora se houver qualquer campo inválido visível, como defesa em profundidade. Se o backend liberar (só não-obrigatórios inválidos), o clique ainda seria barrado na UI — comportamento seguro; o caminho normal de revisão corrige os campos marcados antes de aprovar.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] PAGE_META incompleto após estender a union `Page`**
- **Found during:** Task 1 (build)
- **Issue:** Estender `Page` com `'atencao'` torna `Record<Page, [title, desc]>` em `App.tsx` incompleto (TS2741), quebrando o build exigido como verificação da Task 1.
- **Fix:** Adicionada a entrada `atencao` ao `PAGE_META` no mesmo commit da Task 1 (mudança load-bearing para compilar). O restante da navegação ficou na Task 2.
- **Files modified:** frontend/src/App.tsx
- **Commit:** `f445292`

**2. [Rule 3 - Blocking] Ícone de navegação inexistente**
- **Found during:** Task 2
- **Issue:** O grupo OPERAÇÃO precisava de um ícone para o item "Precisam de atenção"; nenhum ícone de alerta existia em `Icon.tsx`.
- **Fix:** Adicionado o ícone `alert` (triângulo + exclamação) no mesmo estilo de stroke (sw 1.8, viewBox 24) dos existentes — sem lib externa, conforme UI-SPEC.
- **Files modified:** frontend/src/components/Icon.tsx
- **Commit:** `a9b04df`

---

**Total deviations:** 2 auto-fixed (ambas blocking-issue Rule 3, dentro do escopo da navegação prevista pelo plano).
**Impact on plan:** Sem scope creep — ambas são mecânica de compilação/navegação já antecipada pelas tasks.

## Threat Surface

Todas as mitigações do `<threat_model>` materializadas:
- **T-05-16** (XSS): grep confirma **0** ocorrências de `dangerouslySetInnerHTML` em `AttentionPage.tsx`; valores de campo renderizados por interpolação React (texto puro).
- **T-05-17** (Elevation / burlar D-07): botão "Aprovar documento" `disabled` enquanto houver campo inválido + hint; o backend (Plan 03) permanece o guard autoritativo (409).
- **T-05-18** (Information Disclosure): hooks/página NÃO logam valores de campo; só exibem no DOM como texto.
- **T-05-SC** (npm installs): NENHUM pacote novo adicionado — fase code-and-config only; `package.json` inalterado.

Nenhuma nova superfície de ameaça fora do registro do plano.

## Known Stubs

Nenhum stub na superfície desta fase. A aba "Leitura de dados" da Config mantém controles mock pré-existentes (OCR/idioma/deskew/denoise — Fase 2, fora de escopo desta fase); o ÚNICO campo novo (Limiar de confiança) é totalmente fiado à API real.

## Issues Encountered

- Nenhum bloqueio. Os 2 ajustes (PAGE_META e ícone) são mecânica de navegação antecipada pelo plano e foram resolvidos no mesmo ciclo.

## User Setup Required

Para a verificação visual (Task 3): subir backend (`uv run uvicorn app.main:app --reload --port 8000`, migração 0005 aplicada) + frontend (`npm run dev`) e ter documentos em FALHA/QUARENTENA/EM_REVISAO.

## Next Phase Readiness

- A superfície de triagem da Fase 5 está completa no frontend. A Fase 6 (automações de arquivo: renomear/mover, dry-run, undo) construirá sobre o estado CONCLUIDO que o "Aprovar documento" agora produz.

## Self-Check: PASSED (implementação) — Task 3 (verificação humana) PENDENTE

- FOUND: frontend/src/components/ConfidenceBadge.tsx
- FOUND: frontend/src/hooks/useAttention.ts
- FOUND: frontend/src/pages/AttentionPage.tsx
- FOUND commit: f445292
- FOUND commit: a9b04df
- Build: `npm run build` (tsc -b + vite build) verde
- Grep-gates: 0 `dangerouslySetInnerHTML`; ConfidenceBadge sem `var(--accent)`; gates `disabled` em Aprovar/Reclassificar
- PENDENTE: Task 3 é `checkpoint:human-verify` (gate blocking, auto_advance=false) — aguarda confirmação visual do usuário (9 passos de how-to-verify)

---
*Phase: 05-confian-a-revis-o-humana-e-quarentena*
*Completed (implementação): 2026-06-17*

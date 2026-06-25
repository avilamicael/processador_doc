---
phase: 10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova
plan: 05
subsystem: frontend
tags: [preview-sinais, reprocess, ai-fallback, templates, atencao, config]
status: paused-at-checkpoint
requires:
  - "POST /templates/preview-signals (Plano 02 — base64 → relatório por-grupo/condição + scanned)"
  - "POST /documents/{id}/reprocess + POST /documents/reprocess (Plano 03 — single/batch sem template forçado)"
  - "GET/PUT /config/ai-fallback (Plano 04 — toggle global default OFF)"
provides:
  - "previewSignals (File→base64 nativo, JSON), postReprocess/postReprocessBatch, get/putAiFallback (api.ts)"
  - "usePreviewSignals; useReprocessDocument/useReprocessBucket; useAiFallback/useSaveAiFallback (hooks)"
  - "Painel 'Testar sinais' (TemplatesPage); botões Reprocessar/Reprocessar todos (AttentionPage); toggle IA-fallback (ConfigPage)"
affects:
  - "frontend/src/types.ts"
  - "frontend/src/lib/api.ts"
  - "frontend/src/hooks/useTemplates.ts"
  - "frontend/src/hooks/useAttention.ts"
  - "frontend/src/pages/TemplatesPage.tsx"
  - "frontend/src/pages/AttentionPage.tsx"
  - "frontend/src/pages/ConfigPage.tsx"
tech-stack:
  added: []
  patterns:
    - "preview via base64 no body JSON (FileReader/btoa nativos do browser) — zero npm novo, reusa request<T> JSON-only"
    - "leitura de File→base64 em blocos (CHUNK 0x8000) p/ não estourar fromCharCode em arquivos grandes"
    - "hooks de reprocess reusam useInvalidateAttention (invalida ['attention']+['documents']); ai-fallback usa GET/PUT (molde review-threshold)"
    - "valores do backend renderizados como TEXTO PURO (React escapa); sem dangerouslySetInnerHTML (T-10-XSS)"
key-files:
  created: []
  modified:
    - "frontend/src/types.ts"
    - "frontend/src/lib/api.ts"
    - "frontend/src/hooks/useTemplates.ts"
    - "frontend/src/hooks/useAttention.ts"
    - "frontend/src/pages/TemplatesPage.tsx"
    - "frontend/src/pages/AttentionPage.tsx"
    - "frontend/src/pages/ConfigPage.tsx"
decisions:
  - "Painel 'Testar sinais' só aparece para template JÁ SALVO (preview-signals exige template_id persistido); criação mostra hint para salvar primeiro"
  - "Reprocessar (por-doc) exposto em QUARENTENA e EM_REVISAO; 'Reprocessar todos' por balde nesses dois; FALHA mantém 'Tentar de novo' (retry), sem reprocess"
  - "Toggle IA-fallback salva ao alternar (sem botão Salvar) — molde do Switch já presente; default OFF refletido pelo GET"
metrics:
  duration: ~14 min
  completed: 2026-06-25
  tasks: "2 de 3 (Task 3 = checkpoint human-verify, PENDENTE)"
  files: 7
---

# Phase 10 Plan 05: Frontend — testar sinais + reprocessar + toggle IA-fallback Summary

Expõe na UI as três capacidades backend dos Planos 02/03/04: (1) painel "Testar sinais" no
construtor de templates (upload de PDF → relatório por-grupo/condição casa/falha, com aviso de
escaneado); (2) botões "Reprocessar" (por-doc) e "Reprocessar todos" (por balde) na visão
"Precisam de atenção"; (3) toggle de IA-fallback na ConfigPage (default OFF, com aviso de custo).
Zero dependência npm nova (FileReader/btoa nativos; TanStack Query já presente). Build verde.

**STATUS: PAUSADO no Task 3 (checkpoint human-verify, gate="blocking").** O código das duas
tasks de implementação está commitado e o build passa; falta a verificação visual ao vivo pelo
usuário.

## What Was Built

### Task 1 — Camada de dados: types, api.ts, hooks (`2b8ea95`)
- **types.ts:** `PreviewSignalsResult { scanned, matched_any, groups[] }`, `PreviewGroup { matched, conditions[] }`,
  `PreviewCondition { mode, value, matched }`, `ReprocessBatchResult { reprocessed }`, `AiFallback { enabled }`.
- **api.ts:**
  - `previewSignals(templateId, file)` — lê o `File` via `arrayBuffer()` → string binária em blocos
    (`CHUNK 0x8000`) → `btoa` → envia `{ template_id, pdf_base64 }` pelo `request<T>` JSON-only
    (SEM multipart, SEM alterar Content-Type).
  - `postReprocess(id)` — espelha `postReclassify` mas sem template (POST `/documents/{id}/reprocess`).
  - `postReprocessBatch(bucket)` — POST `/documents/reprocess` com `{ bucket }` → `{ reprocessed }`.
  - `getAiFallback()` / `putAiFallback(enabled)` — espelham get/putReviewThreshold (`/config/ai-fallback`).
- **useTemplates.ts:** `usePreviewSignals()` (useMutation, sem invalidação — leitura sob demanda).
- **useAttention.ts:** `useReprocessDocument()` e `useReprocessBucket()` (useMutation + `useInvalidateAttention`
  → invalida `['attention']` + `['documents']`); `useAiFallback()`/`useSaveAiFallback()` (GET/PUT,
  query key `['ai-fallback']`).
- Verificação: `npx tsc --noEmit` passa.

### Task 2 — UI das três capacidades (`b8580a7`)
- **TemplatesPage** — componente `TestSignalsPanel` no Passo 1 "Como reconhecer":
  `<input type="file" accept="application/pdf">` + botão "Testar sinais" → `usePreviewSignals().mutate`.
  Resultado: se `scanned` → aviso "documento escaneado; teste só com texto nativo; a IA cuida na
  ingestão real" (D-08); senão lista cada grupo (casa/não casa) e cada condição com `mode`/`value`
  (texto puro) + indicador ✓/✗ (D-09). Só renderiza para template salvo (precisa de `template_id`);
  na criação mostra hint para salvar primeiro. `disabled` enquanto `isPending`; estado de erro tratado.
- **AttentionPage** — botão "Reprocessar" (por-doc) em `QuarantineRow` e `ReviewRow` (`useReprocessDocument`,
  label condicional, `disabled` em pending); barra `ReprocessBucketBar` com "Reprocessar todos" no topo
  dos baldes QUARENTENA e EM_REVISAO (`useReprocessBucket`, com `window.confirm`). Balde FALHA inalterado
  (mantém "Tentar de novo"/retry).
- **ConfigPage** — componente `AiFallbackField` (molde do `ReviewThresholdField`): `Switch` ligado a
  `enabled`, salva ao alternar; aviso de custo "cada documento que nenhum template reconhecer gera 1
  chamada de IA (custo por token). Padrão: desligado." Default OFF refletido pelo GET.
- Verificação: `npm run build` verde (tsc -b + vite build; bundle 334.50 kB).

### Task 3 — Verificação visual ao vivo (PENDENTE — checkpoint human-verify)
Não executada: requer interação humana (subir backend+frontend, testar sinais com PDF real, quarentenar
→ editar template → reprocessar, ligar toggle e conferir persistência). `gate="blocking"` e plano
`autonomous: false` → execução parada aguardando aprovação.

## Deviations from Plan

None — plano executado exatamente como escrito nas Tasks 1 e 2. Sem dependência npm nova (T-10-SC).
Sem auto-fixes. Sem auth gates.

## Threat model

- **T-10-XSS (mitigate):** todos os valores do backend (mode/value de condição, motivo, nome de campo)
  renderizados por interpolação React (texto puro). Nenhum `dangerouslySetInnerHTML` introduzido. Coberto.
- **T-10-04F (mitigate):** a UI só envia o PDF em base64; validação autoritativa (teto de bytes, magic
  bytes) é no backend (Plano 02). Coberto pelo contrato.
- **T-10-03U (mitigate):** aviso explícito de custo ao lado do toggle IA-fallback; default OFF do backend. Coberto.
- **T-10-05U (accept):** a UI só dispara o reprocess; o guard 409 (estado elegível) é autoritativo no
  backend (Plano 03). Mantido.

## Verification

- `cd frontend && npx tsc --noEmit` — passa (Task 1).
- `cd frontend && npm run build` — verde: `tsc -b && vite build`, 83 módulos, bundle 334.50 kB
  (gzip 94.97 kB), built in 276ms (Task 2).
- Verificação visual ao vivo (Task 3) — **PENDENTE (checkpoint human-verify)**.

## Self-Check: PASSED

- FOUND: frontend/src/types.ts, frontend/src/lib/api.ts, frontend/src/hooks/useTemplates.ts,
  frontend/src/hooks/useAttention.ts, frontend/src/pages/TemplatesPage.tsx,
  frontend/src/pages/AttentionPage.tsx, frontend/src/pages/ConfigPage.tsx — todos FOUND.
- FOUND commit 2b8ea95 (Task 1 — camada de dados).
- FOUND commit b8580a7 (Task 2 — UI).
- Marcadores de conteúdo: `preview-signals`/`previewSignals` em api.ts (2), `Reprocessar`/`reprocess`
  em AttentionPage (20), `ai-fallback`/`AiFallback` em ConfigPage (7), `Testar sinais` em TemplatesPage (5).

---
phase: quick
plan: 260626-gfr
subsystem: frontend
tags: [ux, reprocess, confirmacao, WR-02]
requires: []
provides: ["Guardas window.confirm nos 3 pontos de reprocess da AttentionPage"]
affects: [frontend/src/pages/AttentionPage.tsx]
tech-stack:
  added: []
  patterns: ["window.confirm como guarda de ação destrutiva (padrão já presente no projeto)"]
key-files:
  created: []
  modified: [frontend/src/pages/AttentionPage.tsx]
decisions:
  - "Sem biblioteca de modal nova — reusa window.confirm já usado em ReprocessBucketBar; textos pt-BR condicionais"
requirements: [WR-02]
metrics:
  duration: ~6 min
  completed: 2026-06-26
---

# Phase quick Plan 260626-gfr: Reprocess confirma e avisa perda de correções Summary

Adiciona guardas `window.confirm` nos 3 pontos de "Reprocessar" da `AttentionPage`, avisando explicitamente sobre o descarte de correções manuais em documentos EM_REVISAO (fecha WR-02 do code-review da Phase 10).

## O que foi feito

WR-02: os botões "Reprocessar" disparavam a mutation sem qualquer confirmação, podendo descartar silenciosamente as correções manuais (`manually_corrected`) feitas pelo operador em documentos EM_REVISAO. O re-derivar é intencional (D-10/D-11); o fix é puramente de UI — adiciona confirmação explícita, alinhado à constraint "operações reversíveis, nunca perder; tornar explícito".

Três pontos editados em `frontend/src/pages/AttentionPage.tsx`:

1. **ReviewRow (EM_REVISAO, por-documento)** — Novo `hasCorrections = item.fields.some((f) => f.manually_corrected)`. O `onClick` agora abre `window.confirm` condicional:
   - Com correções: "Reprocessar vai re-rodar a classificação e DESCARTAR as correções manuais feitas neste documento. Continuar?"
   - Sem correções: "Reprocessar vai re-rodar a classificação deste documento. Continuar?"
   - `reprocess.mutate(item.id)` só roda se confirmado.

2. **ReprocessBucketBar (EM_REVISAO, lote)** — Mensagem do confirm passa a ser condicional ao bucket: `em_revisao` avisa "Reprocessar toda a revisão vai re-rodar a classificação e DESCARTAR as correções manuais dos documentos. Continuar?"; `quarentena` mantém o confirm simples original (`Reprocessar todos os documentos d${label}?`). Gate `if (window.confirm(...)) { reprocess.mutate(bucket) }` preservado.

3. **QuarantineRow (QUARENTENA, por-documento)** — `onClick` envolvido em `window.confirm('Reprocessar este documento?')` simples, sem menção a correções (quarentena não tem campos `manually_corrected`).

Botões "Reclassificar" e "Tentar de novo" não foram tocados. Hooks e backend inalterados; nenhuma dependência nova.

## Verificação

Não há teste unitário para diálogos `window.confirm` no projeto — a verificação foi por type-check + build, ambos limpos:

- `npx tsc -b --noEmit` → exit 0, sem erros de tipo.
- `npm run build` (Vite 8.0.16) → build verde, 83 módulos transformados, `dist/` gerado sem erro.

Diff limitado a `AttentionPage.tsx` (1 file changed, 20 insertions(+), 3 deletions(-)); nenhuma alteração fora do arquivo previsto.

Nota: o worktree não tinha `node_modules`; foi necessário `npm ci` (lockfile presente) antes do type-check/build. `node_modules` e `dist` são gitignored — não entraram no commit.

## Deviations from Plan

None - plano executado exatamente como escrito.

## Self-Check: PASSED

- FOUND: frontend/src/pages/AttentionPage.tsx (modificado, 3 guardas window.confirm)
- FOUND: commit 979446f

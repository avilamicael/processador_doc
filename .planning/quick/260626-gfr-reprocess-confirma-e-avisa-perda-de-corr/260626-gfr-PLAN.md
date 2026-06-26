---
phase: quick
plan: 260626-gfr
type: execute
wave: 1
depends_on: []
files_modified: [frontend/src/pages/AttentionPage.tsx]
autonomous: true
requirements: [WR-02]
must_haves:
  truths:
    - "Clicar 'Reprocessar' num doc EM_REVISAO abre window.confirm avisando que as correções manuais serão descartadas"
    - "Clicar 'Reprocessar todos' no bucket em_revisao avisa, no confirm, que correções manuais dos documentos serão descartadas"
    - "Clicar 'Reprocessar' num doc de QUARENTENA pede confirmação simples (sem menção a correções)"
    - "Cancelar qualquer confirm NÃO dispara a mutation de reprocess"
  artifacts:
    - path: "frontend/src/pages/AttentionPage.tsx"
      provides: "Guardas window.confirm nos 3 pontos de reprocess"
      contains: "window.confirm"
  key_links:
    - from: "ReviewRow onClick Reprocessar"
      to: "reprocess.mutate(item.id)"
      via: "window.confirm guard com aviso de descarte de correções"
      pattern: "window\\.confirm"
---

<objective>
Corrigir WR-02 (code-review Phase 10, frontend): os botões "Reprocessar" disparam sem aviso e podem descartar silenciosamente as correções manuais (`manually_corrected`) feitas em documentos EM_REVISAO. O re-derivar é intencional (D-10/D-11) — o fix NÃO toca no backend; apenas adiciona confirmação explícita na UI, alinhando à constraint "operações reversíveis, nunca perder; tornar explícito".

Purpose: Evitar perda silenciosa de trabalho humano ao reprocessar.
Output: `frontend/src/pages/AttentionPage.tsx` com guardas `window.confirm` nos 3 pontos de reprocess.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md

<interfaces>
<!-- Tipos já no contexto; o executor NÃO precisa explorar o codebase. -->

frontend/src/types.ts — campo disponível em cada field de EM_REVISAO:
```typescript
export interface ClassificationField {
  field_name: string
  raw_value: string | null
  normalized_value: string | null
  valid: boolean
  invalid_reason: string | null
  manually_corrected: boolean   // D-08: corrigido pelo operador
}
export interface ReviewItem {
  id: number
  original_filename: string
  motivo: string | null
  confidence_score: number | null
  fields: ClassificationField[]
}
export interface AttentionItem { id: number; original_filename: string; motivo: string | null }
```

frontend/src/hooks/useAttention.ts — assinaturas (NÃO alterar os hooks):
```typescript
useReprocessDocument()  // mutate(id: number)
useReprocessBucket()    // mutate(bucket: 'quarentena' | 'em_revisao')
```

Padrão de confirm já existente no projeto (ReprocessBucketBar ~linha 220):
`if (window.confirm(...)) { reprocess.mutate(...) }`
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Adicionar window.confirm aos 3 pontos de reprocess em AttentionPage.tsx</name>
  <files>frontend/src/pages/AttentionPage.tsx</files>
  <action>
Editar três pontos de `frontend/src/pages/AttentionPage.tsx`, usando o padrão `window.confirm` já presente em `ReprocessBucketBar` (~linha 220). Não introduzir biblioteca de modal. Não alterar hooks nem backend. Textos em pt-BR, claros e específicos.

1. `ReviewRow` (EM_REVISAO, botão "Reprocessar" ~linha 396-403): atualmente `onClick={() => reprocess.mutate(item.id)}`. Computar no corpo do componente se o doc tem alguma correção manual — `const hasCorrections = item.fields.some((f) => f.manually_corrected)` (reaproveita `item.fields`, já disponível). No onClick, envolver a mutation num `window.confirm`. Mensagem condicional à ênfase:
   - Se `hasCorrections`: avisar explicitamente que reprocessar vai re-rodar a classificação e DESCARTAR as correções manuais já feitas neste documento (ex.: "Reprocessar vai re-rodar a classificação e DESCARTAR as correções manuais feitas neste documento. Continuar?").
   - Caso contrário (EM_REVISAO sem correções ainda): aviso de que a classificação será refeita (ex.: "Reprocessar vai re-rodar a classificação deste documento. Continuar?").
   Só chamar `reprocess.mutate(item.id)` se o confirm retornar true.

2. `ReprocessBucketBar` (~linha 199-231), bucket `em_revisao`: hoje o confirm é genérico `Reprocessar todos os documentos d${label}?`. Tornar a mensagem condicional ao bucket: para `em_revisao`, incluir aviso de que as correções manuais dos documentos em revisão serão DESCARTADAS ao reprocessar (ex.: "Reprocessar toda a revisão vai re-rodar a classificação e DESCARTAR as correções manuais dos documentos. Continuar?"). Para `quarentena`, manter a mensagem atual/simples (`Reprocessar todos os documentos d${label}?`). Manter o gate `if (window.confirm(...)) { reprocess.mutate(bucket) }`.

3. `QuarantineRow` (~linha 307-314, botão "Reprocessar"): atualmente `onClick={() => reprocess.mutate(item.id)}`. Envolver num `window.confirm` simples, SEM menção a correções (quarentena não tem campos `manually_corrected`): ex.: "Reprocessar este documento?". Só chamar `reprocess.mutate(item.id)` se confirmado.

Não alterar o botão "Reclassificar" (já é ação explícita com template forçado) nem "Tentar de novo" (FALHA).
  </action>
  <verify>
    <automated>cd frontend && npx tsc -b --noEmit && npm run build</automated>
  </verify>
  <done>tsc -b limpo e build do frontend sem erros; os 3 pontos de reprocess passam por window.confirm; mensagem de EM_REVISAO (row e bucket) menciona descarte de correções manuais; quarentena usa confirm simples.</done>
</task>

</tasks>

<verification>
- `cd frontend && npx tsc -b --noEmit` sem erros de tipo.
- `npm run build` (Vite) conclui sem erro.
- Inspeção do diff: 3 ocorrências novas/ajustadas de `window.confirm`; nenhuma alteração fora de `AttentionPage.tsx`.
</verification>

<success_criteria>
- WR-02 fechado: nenhum caminho de "Reprocessar" dispara sem confirmação.
- EM_REVISAO (por-doc e por-bucket) avisa explicitamente sobre descarte de correções manuais.
- Quarentena tem confirm simples por consistência.
- Backend e hooks inalterados; sem nova dependência de modal.
</success_criteria>

<output>
Create `.planning/quick/260626-gfr-reprocess-confirma-e-avisa-perda-de-corr/260626-gfr-SUMMARY.md` when done. Registrar no SUMMARY que a verificação foi por type-check + build (não há teste unitário para diálogos `window.confirm`).
</output>

---
phase: 11-ux-e-visibilidade-reverter-movidos-dedup-visivel-rotulos-e-f
verified: 2026-06-26T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Verificação inicial — sem VERIFICATION.md anterior"
---

# Phase 11: UX e visibilidade Verification Report

**Phase Goal:** Expor na UI e corrigir a apresentação de capacidades que já existem no backend (backlog itens 1, 3, 4, 8, 9) — sem criar capacidades novas de motor.
**Verified:** 2026-06-26
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (item do backlog) | Status | Evidência no código |
|---|-------------------------|--------|---------------------|
| 1 | **Item 9** — Timestamps serializados como UTC tz-aware (`...Z`/offset), sem deslocar a hora | ✓ VERIFIED | `documents.py:74` `_as_utc(dt)` (`replace(tzinfo=UTC)`, não `astimezone`); aplicado em `created_at` da lista (`:305`), do detalhe (`:394`) e do audit (`:753`). Teste `-k utc` passa. |
| 2 | **Item 3** — `POST /rescan` informa `skipped_duplicates` além de `enqueued`; toast pós-varredura | ✓ VERIFIED | `watcher.py`: `ScanResult(enqueued, skipped_duplicates)` (`:78-88`), `_stabilize_hash_gate_enqueue` retorna `Literal["enqueued"|"duplicate"|"skipped"]` (`:74`), ramo dedup `return "duplicate"` (`:185`), acumula `skipped_duplicates += 1` (`:248`). `documents.py:223` `RescanOut.skipped_duplicates`, `/rescan` desempacota (`:1012-1014`). Ambos call-sites de startup atualizados (`watcher.py:271,334`). Frontend: `postRescan` re-tipado (`api.ts:90`), toast efêmero com singular/plural (`DocumentsPage.tsx:98-103,212-226`). |
| 3 | **Item 1** — Reverter doc movido pela tela: origem→destino do audit + botão restaura do CAS | ✓ VERIFIED | Backend `GET /documents/{id}/audit` (`documents.py:707`) read-only, `select(AuditLog).where(document_id==...)`, 404 se ausente, `can_undo = any(status=="done")`. Frontend: `AuditEntry`/`DocumentAudit` (`types.ts:200,212`), `getDocumentAudit` (`api.ts:84`), `useUndoDocument` por `document_id` reusando `postUndo` (`useDocuments.ts:64-67`), seção "Operações aplicadas" origem→destino (`DocumentsPage.tsx:638-658`) + botão "Reverter para a origem" com confirmação inline (`:660-698`), `doneOps` filtra `status==='done'` (`:478`). UI envia só `document_id` — sem construir paths. |
| 4 | **Item 4** — Condição "Valor de campo" usa dropdown estrito de campos do template; bloqueia sem template | ✓ VERIFIED | `AutomationsPage.tsx`: ramo `isField` renderiza `<select>` populado por `activeTemplate.fields.map` (`:846-859`); sem `activeTemplate` mostra aviso `nochip-box` sem texto livre (`:864-879`); `validate()` bloqueia salvar quando `c.field==='field' && !draftTemplate` (`:578-579`) e exige `field_name` (`:581`). `placeholder="nome do campo"` removido (grep=0). |
| 5 | **Item 8** — Rótulo derivado "Classificado — pronto" no StatusPill + CTA na lista | ✓ VERIFIED | `StatusPill.tsx:39-40` ramo `processando + last_completed_step==='classificado'` → `{label:'Classificado — pronto', token:'tratado'}`; pílula wired com `lastCompletedStep` (`DocumentsPage.tsx:338`). `isClassifiedReady` (`:27`) gate da CTA; "Pré-visualizar" navega ao dry-run (`:349`), "Aprovar" chama `apply.mutate([d.id])` (`:357`, corrigido pós-fase para `/automations/apply` em vez de `/approve` que dava 409). Sem auto-conclusão (D-12). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Esperado | Status | Detalhes |
|----------|----------|--------|----------|
| `backend/app/api/documents.py` | `_as_utc` + `RescanOut.skipped_duplicates` + `GET /{id}/audit` | ✓ VERIFIED | Todos presentes e substantivos; `DocumentAuditOut`/`AuditEntryOut` definidos |
| `backend/app/ingest/watcher.py` | `ScanResult` + literal de 3 estados | ✓ VERIFIED | `scan_and_enqueue → ScanResult`; ambos call-sites usam `result.enqueued` |
| `frontend/src/components/StatusPill.tsx` | rótulo derivado | ✓ VERIFIED | ramo classificado, token `tratado` reusado |
| `frontend/src/pages/DocumentsPage.tsx` | CTA + reverter + toast | ✓ VERIFIED | três peças wired a dados reais |
| `frontend/src/pages/AutomationsPage.tsx` | dropdown estrito + guard | ✓ VERIFIED | select + aviso + validate guard |
| `frontend/src/types.ts` / `lib/api.ts` / `hooks/useDocuments.ts` | tipos + client + hooks | ✓ VERIFIED | `AuditEntry`/`DocumentAudit`, `getDocumentAudit`, `useUndoDocument`/`useApproveDocument` |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `rescan()` | `scan_and_enqueue` | desempacota `result.enqueued/skipped_duplicates` | ✓ WIRED |
| `GET /{id}/audit` | `AuditLog` | `select(AuditLog).where(document_id==...)` | ✓ WIRED |
| `DocumentsPage` toast | `postRescan` response | `r.skipped_duplicates` → mensagem | ✓ WIRED |
| Botão "Reverter" | `POST /automations/undo` | `useUndoDocument` → `postUndo({document_id})` | ✓ WIRED |
| `StatusPill` | `DocumentOut.last_completed_step` | prop `lastCompletedStep` | ✓ WIRED |
| CTA "Aprovar" | `POST /automations/apply` | `useApply().mutate([id])` | ✓ WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Variável | Fonte | Dados reais | Status |
|----------|----------|-------|-------------|--------|
| Seção "Operações aplicadas" | `doneOps` | `getDocumentAudit` → `AuditLog` (DB) | Sim — colunas persistidas | ✓ FLOWING |
| Toast rescan | `rescanToast` | `postRescan` → `scan_and_enqueue` (contadores reais) | Sim | ✓ FLOWING |
| StatusPill rótulo | `last_completed_step` | `DocumentOut` (DB) | Sim | ✓ FLOWING |
| Dropdown campo | `activeTemplate.fields` | template referenciado na condição | Sim | ✓ FLOWING |

### Behavioral Spot-Checks

| Comportamento | Comando | Resultado | Status |
|---------------|---------|-----------|--------|
| Suíte backend (audit/rescan/dedup/utc/scan) | `pytest -k "audit or rescan or duplicat or utc or scan" -q` | 30 passed | ✓ PASS |
| `_as_utc` preserva hora + offset | importação/asserção | termina em `+00:00` (per summary) | ✓ PASS |
| Frontend typecheck | `npx tsc -b` | EXIT=0, 0 erros | ✓ PASS |

### Requirements Coverage

| Requirement | Plano | Descrição | Status | Evidência |
|-------------|-------|-----------|--------|-----------|
| Backlog item 1 (D-01/D-02) | 11-01, 11-04 | Reverter por documento | ✓ SATISFIED | endpoint audit + UI reverter |
| Backlog item 3 (D-04/D-05) | 11-01, 11-04 | Dedup visível + toast | ✓ SATISFIED | skipped_duplicates + toast |
| Backlog item 4 (D-07/D-08) | 11-02 | Dropdown estrito de campo | ✓ SATISFIED | select + guard |
| Backlog item 8 (D-10/D-11) | 11-03 | Rótulo "pronto" + CTA | ✓ SATISFIED | StatusPill + CTA |
| Backlog item 9 (D-13) | 11-01 | Timestamps tz-aware | ✓ SATISFIED | `_as_utc` |

### Anti-Patterns Found

| Arquivo | Linha | Padrão | Severidade | Impacto |
|---------|-------|--------|------------|---------|
| `frontend/src/hooks/useDocuments.ts` | 48 | `useApproveDocument` exportado mas não usado em DocumentsPage (CTA passou a usar `useApply` no fix pós-fase do 409) | ℹ️ Info | Hook órfão inofensivo; o objetivo do item 8 (CTA agir direto) foi atingido e melhorado. Candidato a limpeza, não bloqueia. |

Nenhum TODO/FIXME/XXX/PLACEHOLDER ou stub introduzido nos arquivos da fase. Endpoint audit refina além do plano (exclui registros de split-materialize espúrios).

### Human Verification Required

Nenhuma pendente. Os checkpoints visuais (11-02/03/04) foram deferidos pelos SUMMARYs, mas o usuário confirmou que a verificação visual ao vivo já foi executada via Playwright em 2026-06-26 (todos OK).

### Gaps Summary

Nenhum gap. As cinco capacidades do escopo (itens 1, 3, 4, 8, 9) existem no código real, estão substantivas, wired e fluindo com dados reais. 30 testes backend verdes; typecheck frontend limpo. Únicos itens deferidos (histórico por lote, dedup por-evento, dry-run sinalizando campo não-extraído) estavam explicitamente fora de escopo nas decisões D-03/D-06/D-09.

---

_Verified: 2026-06-26_
_Verifier: Claude (gsd-verifier)_

---
phase: 12-robustez-de-ingest-o-e-modo-de-aprova-o
verified: 2026-06-26T00:00:00Z
status: passed
score: 14/14 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Verificação inicial goal-backward. Checkpoint visual 12-04 já executado ao vivo (Playwright, 2026-06-26)."
---

# Phase 12: Robustez de ingestão e modo de aprovação — Verification Report

**Phase Goal:** (Item 2) varrer pasta nova/reativada em runtime sem `/rescan`; (Item 7) "remover + forçar varredura" re-ingere arquivos de split; (Item 12) modo de aprovação global — desligado roda automático com trava de confiança, ligado segura para aprovação/negação por linha na Pré-visualização.
**Verified:** 2026-06-26
**Status:** passed
**Re-verification:** No — verificação inicial

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Pasta que passa a existir/reativar em runtime tem arquivos já presentes varridos sem `/rescan` | ✓ VERIFIED | `run_watcher` retém `previous_paths` (watcher.py:279,290), chama `_scan_new_active_folders` no topo do loop (l.289); helper computa `current - previous` e chama `scan_and_enqueue` (l.330-334). Teste `test_scan_new_active_folder_enqueues_existing_files` passa. |
| 2 | Re-varrer a mesma pasta nova é idempotente (dedup) | ✓ VERIFIED | Reusa `scan_and_enqueue` → gate `IngestedOriginal` (watcher.py:176-185). Teste `test_scan_new_active_folder_is_idempotent` (2x scan) passa. |
| 3 | Falha no scan de pasta nova nunca derruba o watcher | ✓ VERIFIED | `try/except Exception: # noqa: BLE001` em `_scan_new_active_folders` (l.333-340), `logger.exception` + não propaga, espelhando o scan de startup. |
| 4 | Remover doc de split + re-varrer RE-INGERE o bloco | ✓ VERIFIED | `delete_documents` passo (4): `delete(IngestedOriginal).where(original_hash == content_hash)` (documents.py:566-568). Teste `test_delete_split_block_clears_block_gate_entry` passa. |
| 5 | Limpeza de dedup NUNCA toca arquivo/CAS — só registros | ✓ VERIFIED | documents.py não importa `os`/`shutil`/`Path.unlink` (grep vazio); só `delete(Job)`/`delete(IngestedOriginal)`. Teste `test_delete_endpoint_does_not_import_filesystem_ops` passa. |
| 6 | Remover doc sem split sem regressão (delete extra é no-op) | ✓ VERIFIED | Teste `test_delete_non_split_doc_does_not_remove_unrelated_gate` passa; passo (5) anti-órfão do original preservado (l.570-582). |
| 7 | Existe setting global `approval_mode_enabled` (default OFF) lido do .env via GET/PUT /config/approval-mode | ✓ VERIFIED | config.py:185-190 `Field(default=False, AliasChoices(...))`; api/config.py:119-139 par GET/PUT + `persist_env_setting` + `cache_clear`. Testes em test_api_config.py passam. |
| 8 | OFF → `enqueue_pending_applications` auto-aplica alta confiança como hoje | ✓ VERIFIED | worker.py:391 gate só dispara quando ON; abaixo segue o sweep de threshold (l.394+). Teste `test_off_auto_aplica_alta_confianca` passa. |
| 9 | ON → `enqueue_pending_applications` NÃO auto-aplica nada (docs ficam pendentes) | ✓ VERIFIED | worker.py:391-392 `if get_settings().approval_mode_enabled: return 0` no TOPO, antes da query. Teste `test_on_nao_auto_aplica_nada` passa. |
| 10 | `apply_stage` NÃO é gateado — aprovação manual funciona em ambos os modos | ✓ VERIFIED | Gate vive só em `enqueue_pending_applications` (queue/worker.py); `apply_stage` (automation/stage.py) intocado. Teste `test_trava_de_confianca_intacta_em_ambos_os_modos` passa. |
| 11 | Usuário liga/desliga o toggle na ConfigPage (espelha ai-fallback) | ✓ VERIFIED | ConfigPage.tsx:519-595 `ApprovalModeField` com Switch; `useApprovalMode`/`useSaveApprovalMode` (useAttention.ts:157-170) → get/putApprovalMode (api.ts:191-198). tsc -b limpo. |
| 12 | LIGADO: DryRunPage é fila de aprovação (aprovar/negar por linha) | ✓ VERIFIED | DryRunPage.tsx:93 `approvalEnabled`, banner (l.208), coluna Ações (l.312,391), botões Aprovar (l.399 `doApply([id])`) / Negar (l.410 `denyDoc`). |
| 13 | Negar/pular NÃO chama backend nem move arquivo (doc fica pronto) | ✓ VERIFIED | `denyDoc` (DryRunPage.tsx:162-165) só `setRows` filtra + `setSelected` filtra; zero chamada de API/apply/undo. Confirmado ao vivo (Playwright: arquivo não movido no disco). |
| 14 | Aprovar reusa o apply existente; DESLIGADO a página segue como hoje | ✓ VERIFIED | Aprovar → `doApply([r.document_id])` (apply existente); `BODY_COLS = approvalEnabled ? 5 : 4`, banner/coluna sob `approvalEnabled` (l.189,208,312,391). |

**Score:** 14/14 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `backend/app/ingest/watcher.py` | diff scan no run_watcher | ✓ VERIFIED | `_scan_new_active_folders` + plumbing em run_watcher (l.279-340) |
| `backend/app/api/documents.py` | delete limpa gate de bloco | ✓ VERIFIED | l.566-568 delete IngestedOriginal por content_hash |
| `backend/app/config.py` | setting approval_mode_enabled | ✓ VERIFIED | l.185-190 default False |
| `backend/app/api/config.py` | par GET/PUT /config/approval-mode | ✓ VERIFIED | l.107-139 espelha ai-fallback |
| `backend/app/queue/worker.py` | gate em enqueue_pending_applications | ✓ VERIFIED | l.391-392 curto-circuito no topo |
| `frontend/src/types.ts` | interface ApprovalMode | ✓ VERIFIED | l.415 |
| `frontend/src/lib/api.ts` | get/putApprovalMode | ✓ VERIFIED | l.191-198 |
| `frontend/src/hooks/useAttention.ts` | useApprovalMode/useSaveApprovalMode | ✓ VERIFIED | l.157-170 |
| `frontend/src/pages/ConfigPage.tsx` | card toggle | ✓ VERIFIED | l.519-595 ApprovalModeField |
| `frontend/src/pages/DryRunPage.tsx` | fila de aprovação | ✓ VERIFIED | l.92-414 wired |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| run_watcher | scan_and_enqueue | diff de pastas ativas | ✓ WIRED (watcher.py:289,334) |
| delete_documents | IngestedOriginal (gate bloco) | delete por original_hash==content_hash | ✓ WIRED (documents.py:566) |
| enqueue_pending_applications | get_settings().approval_mode_enabled | return 0 no topo quando ON | ✓ WIRED (worker.py:391) |
| put_approval_mode | .env + cache_clear | persist_env_setting + cache_clear | ✓ WIRED (config.py:137-138) |
| ConfigPage | /config/approval-mode | useApprovalMode/useSaveApprovalMode | ✓ WIRED |
| DryRunPage | estado local (setRows) | denyDoc sem backend | ✓ WIRED (DryRunPage.tsx:162-165) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Testes backend itens 2/7/12 | pytest -k "approval or watcher or split or scan or dedup or delete" | 68 passed, 0 failed | ✓ PASS |
| Typecheck frontend | tsc -b --noEmit | exit 0 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
| ----------- | ----------- | ------ | -------- |
| BL-02 (item 2) | 12-01 | ✓ SATISFIED | Truths 1-3 |
| BL-07 (item 7) | 12-02 | ✓ SATISFIED | Truths 4-6 |
| BL-12 (item 12) | 12-03, 12-04 | ✓ SATISFIED | Truths 7-14 |

### Anti-Patterns Found

Nenhum. Sem TBD/FIXME/XXX nos arquivos da fase; `denyDoc` é filtro local intencional (D-06), não stub; gate `return 0` é curto-circuito deliberado (D-05).

### Human Verification Required

Nenhum pendente. O único item humano (checkpoint visual 12-04 Task 3, originalmente adiado) **já foi executado ao vivo via Playwright em 2026-06-26** — confirmado: modo de aprovação OK e "Negar" não move o arquivo no disco. Sem itens humanos em aberto.

### Gaps Summary

Sem gaps. As três frentes do backlog (itens 2/7/12) estão implementadas, conectadas e cobertas por testes verdes (68 passed). Constraint sagrada "nunca perder arquivos" preservada: delete só toca registros; negar é puramente local; o move só ocorre no aprovar/aplicar. A trava de confiança permanece intacta em ambos os modos (gate só no sweep de auto-apply, nunca em `apply_stage`).

---

_Verified: 2026-06-26_
_Verifier: Claude (gsd-verifier)_

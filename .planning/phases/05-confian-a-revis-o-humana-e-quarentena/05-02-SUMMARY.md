---
phase: 05-confian-a-revis-o-humana-e-quarentena
plan: 02
subsystem: classification
tags: [classify-stage, confidence, state-routing, em-revisao, forced-template, queue, requeue, pytest]

# Dependency graph
requires:
  - phase: 05-confian-a-revis-o-humana-e-quarentena
    plan: 01
    provides: "compute_confidence (pura), confidence_score (coluna), review_confidence_threshold (tunable), migração 0005, scaffolds Wave 0"
  - phase: 04-templates-sub-templates-e-classifica-o
    provides: "classify_stage (matcher→filler→IA→validação, commit atômico), repo (fila SQLite), worker (_dispatch CLASSIFY_STEP)"
provides:
  - "classify_stage roteia EM_REVISAO vs PROCESSANDO+classificado por score, atômico (D-01/D-04, REV-01/REV-02)"
  - "classify_stage aceita forced_template_id: pula matcher/decide/desempate, vai direto a filler+IA-faltantes+validação (D-09, REV-05 base)"
  - "Open Q1 materializada: stage NUNCA transita para CONCLUIDO (grep-gate)"
  - "repo.requeue_step(session, *, content_hash, step, payload) -> int — reseta job existente para pending (resolve UNIQUE na reclassificação, Open Q2)"
  - "worker._dispatch lê forced_template_id do payload do job classify e repassa"
affects: [05-03 endpoints de revisão/reclassify, 05-04 frontend AttentionPage]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Roteamento de estado dentro do commit atômico único: compute_confidence → transition(EM_REVISAO) ou commit terminal PROCESSANDO, sem commit manual antes do transition (Pitfall 2)"
    - "Caminho forçado como ramo if/else ANTES do matcher: forced_template_id pula matcher/decide/desempate preservando passo 7+ (filler/validação) idêntico"
    - "requeue_step espelha requeue_running (UPDATE...WHERE + commit + rowcount) para reutilizar a linha em vez de violar a UNIQUE(hash, step)"

key-files:
  created: []
  modified:
    - backend/app/classification/stage.py
    - backend/app/queue/repo.py
    - backend/app/queue/worker.py
    - backend/tests/classification/test_stage_routing.py
    - backend/tests/classification/test_forced_template.py
    - backend/tests/classification/test_stage.py

key-decisions:
  - "Obrigatório inválido força EM_REVISAO mesmo com score numérico alto (D-04, has_invalid_required) — atualizou a expectativa do test_stage Fase 4 (campo inválido agora vai a EM_REVISAO, não permanece PROCESSANDO; D-10 'não vai a QUARENTENA' preservado)"
  - "No caminho forçado, confidence (score do matcher) = None; confidence_score (qualidade de extração) continua calculado e persistido"
  - "requeue_step reseta attempts=0 para dar ciclo completo de retries ao job reprocessado (T-05-06 aceito: single-tenant, ação humana deliberada)"

patterns-established:
  - "Roteamento de estado por score como passo 9 do classify_stage, atômico com CR+FilledFields+Usages"
  - "forced_template_id como seam de reclassificação manual sem tocar o matcher"

requirements-completed: [REV-01, REV-02, REV-05]

# Metrics
duration: 5min
completed: 2026-06-17
---

# Phase 5 Plan 02: Roteamento de Estado + forced_template_id Summary

**`classify_stage` calcula e persiste o `confidence_score`, roteia EM_REVISAO (score < limiar OU obrigatório inválido, D-04) vs PROCESSANDO+classificado (NUNCA CONCLUIDO, Open Q1) num commit atômico, e aceita `forced_template_id` (D-09) que pula o matcher; mais `repo.requeue_step` (Open Q2) e a leitura de `forced_template_id` no worker.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-17T03:36:39Z
- **Tasks:** 2
- **Files modified:** 6 (0 criados, 6 editados)

## Accomplishments

- **Roteamento por score (REV-01/REV-02, D-01/D-04):** o passo 9 do `classify_stage` agora chama `compute_confidence(cr.filled_fields, template.fields)`, persiste `cr.confidence_score`, e roteia: `transition(EM_REVISAO)` quando `has_invalid_required or score < review_confidence_threshold`, senão mantém PROCESSANDO+marcador "classificado". Tudo num commit atômico único (sem `session.commit()` manual antes do `transition` — Pitfall 2).
- **Open Q1 materializada (T-05-05):** o stage NUNCA transita para CONCLUIDO — grep-gate confirma ausência de `DocState.CONCLUIDO` no `stage.py`. A conclusão fica para a aprovação humana (Plan 03) / captura da Fase 6.
- **forced_template_id (D-09, REV-05 base):** nova assinatura `classify_stage(session, *, content_hash, forced_template_id=None)`. Quando setado, um ramo `if/else` pula matcher/decide/desempate, faz `session.get(Template, forced_template_id)` (None → `raise ValueError("Template forçado inexistente")`, T-05-03) e segue o passo 7+ (filler+IA-faltantes+validação) com o template forçado; `confidence` do matcher = None.
- **repo.requeue_step (Open Q2):** `UPDATE jobs SET status='pending', payload=:payload, next_run_at=:now, attempts=0 WHERE original_hash=:hash AND step=:step`; reseta a linha existente em vez de violar a UNIQUE `uq_jobs_hash_step` na reclassificação.
- **worker:** `_dispatch` CLASSIFY_STEP lê `forced = json.loads(payload).get("forced_template_id")` e repassa; payload normal (`{"content_hash": ...}`) → None → caminho atual inalterado.
- **Testes:** `test_stage_routing.py` (4 casos: abaixo do limiar, acima/pronto, obrigatório inválido força revisão, persistência de confidence_score) + `test_forced_template.py` (3 casos: pula matcher, inexistente → ValueError, confidence None) preenchidos. Suite completa verde (263 passed, 4 skipped — os scaffolds do Plan 03).

## Task Commits

1. **Task 1: roteamento de estado por score + forced_template_id** - `8ffbd07` (feat)
2. **Task 2: repo.requeue_step + worker lê forced_template_id** - `89f1382` (feat)

_Task 1 era `tdd="true"`: implementação no `stage.py` + os 2 testes de classificação foram entregues juntos no mesmo commit (os testes provam o roteamento e o caminho forçado no momento do commit)._

## Files Created/Modified

- `backend/app/classification/stage.py` - +forced_template_id na assinatura e ramo if/else pulando o matcher; passo 9 reescrito com compute_confidence + roteamento EM_REVISAO/PROCESSANDO atômico; import de compute_confidence
- `backend/app/queue/repo.py` - +requeue_step (reset de job existente para pending, Open Q2)
- `backend/app/queue/worker.py` - _dispatch CLASSIFY_STEP lê forced_template_id do payload e repassa
- `backend/tests/classification/test_stage_routing.py` - 4 casos de roteamento (Plan 02)
- `backend/tests/classification/test_forced_template.py` - 3 casos do caminho forçado (Plan 02)
- `backend/tests/classification/test_stage.py` - test_campo_invalido atualizado: obrigatório inválido → EM_REVISAO (não mais PROCESSANDO), D-10 "não vai a QUARENTENA" preservado

## Decisions Made

- **Obrigatório inválido → EM_REVISAO mesmo com score alto** (D-04): consequência direta de `has_invalid_required`. Isso mudou a expectativa do teste de Fase 4 `test_campo_invalido_marca_sem_quarentena` — o documento continua NÃO indo a QUARENTENA (D-10 intacto), mas agora vai a EM_REVISAO em vez de permanecer PROCESSANDO+pronto.
- **No caminho forçado, `confidence` (matcher) = None**; `confidence_score` (qualidade de extração) continua calculado/persistido normalmente.
- **`requeue_step` reseta `attempts=0`** para reprocessar com ciclo completo de retries (T-05-06 aceito: single-tenant, reclassify é ação humana deliberada).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_stage Fase 4 (campo inválido) assumia PROCESSANDO; o roteamento D-04 da Fase 5 o leva a EM_REVISAO**
- **Found during:** Task 1 (após implementar o roteamento por score)
- **Issue:** `test_campo_invalido_marca_sem_quarentena` (Fase 4) assertava `state == PROCESSANDO` após um CNPJ com DV inválido. Com o roteamento da Fase 5, um obrigatório inválido (`has_invalid_required=True`) força EM_REVISAO — a asserção falhava. O ponto do teste (campo inválido NÃO joga em QUARENTENA — D-10) permanece válido.
- **Fix:** Atualizada a asserção para `state == EM_REVISAO` + `state != QUARENTENA`, com docstring explicando a evolução D-04 da Fase 5. A intenção original (D-10: não bloqueia/não quarentena) foi preservada e tornada explícita.
- **Files modified:** backend/tests/classification/test_stage.py
- **Commit:** `8ffbd07` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — atualização de expectativa de teste cross-wave, esperada pelo `<behavior>` do plano)
**Impact on plan:** Sem scope creep. A mudança de roteamento é exatamente o que o Plan 02 entrega; o teste de Fase 4 precisava refletir a nova semântica de estado.

## Issues Encountered

- Nenhum bloqueio. O `test_stage_routing` usou `texto` (não `moeda`) no campo ausente para obter score 0.5 determinístico com a IA de faltantes devolvendo lista vazia, evitando depender de validação de tipo específico.

## User Setup Required

None - nenhuma configuração externa. `REVIEW_CONFIDENCE_THRESHOLD` continua opcional (default 0.8).

## Next Phase Readiness

- Base pronta para o Plan 03 (endpoints de revisão/reclassify): `classify_stage` roteia para EM_REVISAO e expõe `confidence_score`; `repo.requeue_step` + o worker lendo `forced_template_id` viabilizam o reclassify de quarentena. Os scaffolds `test_api_review` (4 skips) aguardam o Plan 03.

## Self-Check: PASSED

- FOUND: backend/app/classification/stage.py (forced_template_id, compute_confidence, transition EM_REVISAO; sem DocState.CONCLUIDO)
- FOUND: backend/app/queue/repo.py (def requeue_step)
- FOUND: backend/app/queue/worker.py (forced_template_id no CLASSIFY_STEP)
- FOUND commit: 8ffbd07
- FOUND commit: 89f1382

---
*Phase: 05-confian-a-revis-o-humana-e-quarentena*
*Completed: 2026-06-17*

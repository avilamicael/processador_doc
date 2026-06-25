---
phase: 12-robustez-de-ingest-o-e-modo-de-aprova-o
plan: 02
subsystem: api
tags: [dedup, split, delete, ingestion, sqlalchemy, fastapi]

# Dependency graph
requires:
  - phase: 10
    provides: "pipeline de split/materialização de blocos + gate de dedup (IngestedOriginal)"
provides:
  - "delete_documents libera a entrada de gate do BLOCO de split (D-02), permitindo re-ingestão após remover + forçar varredura"
affects: [watcher, ingest, dedup, modo-de-aprovacao]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Limpeza de dedup do delete trata gate do ORIGINAL (anti-órfão) E do BLOCO (split anti-loop) — só registros, nunca arquivos"

key-files:
  created: []
  modified:
    - backend/app/api/documents.py
    - backend/tests/test_api_documents.py

key-decisions:
  - "D-02: associação bloco↔documento é trivial — IngestedOriginal.original_hash == doc.content_hash; basta apagar essa entrada no passo (4)"
  - "Delete extra de IngestedOriginal por content_hash é no-op inofensivo em docs sem split (hashes distintos por conteúdo nunca colidem)"

patterns-established:
  - "Constraint sagrada preservada: limpeza de dedup é PURAMENTE de registros (delete(IngestedOriginal)/delete(Job)); módulo não importa os/shutil — arquivo na pasta e blob CAS intactos"

requirements-completed: [BL-07]

# Metrics
duration: 12min
completed: 2026-06-25
---

# Phase 12 Plan 02: Limpeza do gate de split no delete (D-02) Summary

**`delete_documents` agora apaga também a entrada de gate de dedup do BLOCO de split (IngestedOriginal.original_hash == content_hash), liberando "remover + forçar varredura" a re-ingerir arquivos vindos de split — sem jamais tocar o arquivo físico nem o CAS.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-06-25
- **Tasks:** 2 (1 TDD + 1 regressão de verificação)
- **Files modified:** 2

## Accomplishments
- Bug do teste de usuário (Item 7 / D-02) corrigido: re-varrer após remover um doc de split agora re-ingere (`enqueued > 0`) em vez de dedupar.
- Correção cirúrgica de 1 linha efetiva no passo (4) do laço sobre `block_hashes`, reutilizando material já coletado.
- Cobertura de teste para os três cenários: split (gate liberado), não-split (no-op inofensivo) e garantia estática de que o endpoint não importa os/shutil.
- Suítes de documentos + dedup verdes (36 testes), anti-órfão do original (passo 5) e cascade preservados sem regressão.

## Task Commits

1. **Task 1 (RED): teste falhando do gate de split** - `aae6e9a` (test)
2. **Task 1 (GREEN): limpa entrada de gate do bloco no delete** - `13e76ab` (fix)
3. **Task 2: regressão documentos + dedup** - sem commit (verificação, nenhum arquivo alterado)

## Files Created/Modified
- `backend/app/api/documents.py` - `delete_documents` passo (4): além de `delete(Job)`, executa `delete(IngestedOriginal).where(IngestedOriginal.original_hash == content_hash)` para liberar o gate do bloco de split.
- `backend/tests/test_api_documents.py` - 3 testes novos: `test_delete_split_block_clears_block_gate_entry`, `test_delete_non_split_doc_does_not_remove_unrelated_gate`, `test_delete_endpoint_does_not_import_filesystem_ops`.

## Decisions Made
- A correção entrou no passo (4) (laço já existente sobre `block_hashes`), não num passo novo — minimiza superfície e reusa o material já coletado na linha 543.
- O passo (5) (anti-órfão do ORIGINAL via `touched_origin_ids`) ficou intacto: continua preservando o original enquanto outro bloco o referencia.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## Safety / Constraint Verification
- **"Nunca perder arquivos" (constraint sagrada):** a nova linha só executa `delete(IngestedOriginal)` (registro). O módulo `documents.py` NÃO importa `os`/`shutil`/`Path.unlink` — verificado por teste estático (`not hasattr(documents_module, "os"/"shutil")`). O arquivo na pasta monitorada e o blob no CAS permanecem intactos.
- **T-12-04/T-12-05 (threat register) mitigados:** delete extra em doc não-split é no-op (sem entrada de gate própria; hashes distintos por conteúdo não colidem) — comprovado por `test_delete_non_split_doc_does_not_remove_unrelated_gate`.

## Next Phase Readiness
- Cenário do teste de usuário (remover doc de split → forçar varredura → re-ingerir) destravado no backend.
- Pronto para integração com o modo de aprovação (Plano 12-04) e a varredura de pasta nova do watcher (Plano 12-01), que dependem do mesmo caminho de re-ingestão idempotente.

## Self-Check: PASSED

- SUMMARY.md presente; `backend/app/api/documents.py` presente com marcador da implementação.
- Commits `aae6e9a` (test/RED) e `13e76ab` (fix/GREEN) confirmados no histórico.

## TDD Gate Compliance

- RED gate: `aae6e9a` (`test(12-02)`) — teste falhou conforme esperado (gate do bloco não removido).
- GREEN gate: `13e76ab` (`fix(12-02)`) — implementação tornou o teste verde.
- REFACTOR: não necessário (mudança mínima e limpa).

---
*Phase: 12-robustez-de-ingest-o-e-modo-de-aprova-o*
*Completed: 2026-06-25*

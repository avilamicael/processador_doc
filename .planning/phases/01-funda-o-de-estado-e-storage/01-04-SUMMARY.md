---
phase: 01-funda-o-de-estado-e-storage
plan: 04
subsystem: pipeline-state-machine
tags: [state-machine, sqlalchemy-2.0, sqlite, allowlist, tdd, python-3.12]

# Dependency graph
requires:
  - "01-02: DocState (str, Enum) com os 6 estados de topo (app/models/enums.py)"
  - "01-02: Document.state (default RECEBIDO) + Document.last_completed_step (app/models/document.py)"
  - "01-01: get_session/sessão SQLAlchemy 2.0 com commit/rollback (app/storage/db.py)"
provides:
  - "TRANSITIONS: allowlist explícita dict[DocState, set[DocState]] cobrindo os 6 estados; CONCLUIDO terminal (D-04)"
  - "InvalidTransition(from_state, to_state) — exceção dedicada de transição não permitida (D-06)"
  - "is_valid_transition(from, to) — consulta booleana à allowlist (T-01-16)"
  - "transition(session, document, to_state, completed_step=None) — valida, persiste e refresca, ou falha sem corromper (D-06/T-01-15)"
  - "mark_step(session, document, step) — atualiza só o marcador interno para resume/idempotência (D-05)"
affects: [02-ingestao-e-fila, 03-extracao-ia, 05-revisao-confianca, 06-automacoes-undo]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Document as a State Machine: allowlist declarativa (TRANSITIONS) separada do motor (transition)"
    - "Validar ANTES de atribuir; transição inválida nunca toca o estado persistido (rollback defensivo)"
    - "Subetapas internas (dedup/extração/...) vivem em last_completed_step, não em estados de topo"
    - "TDD por tarefa (RED via import faltante → GREEN), uma feature commit por tarefa"

key-files:
  created:
    - backend/app/pipeline/__init__.py
    - backend/app/pipeline/states.py
    - backend/app/pipeline/state_machine.py
    - backend/tests/test_state_machine.py
  modified: []

key-decisions:
  - "Transição inválida valida ANTES de qualquer atribuição + session.rollback() defensivo — o estado persistido (e last_completed_step) permanece o anterior (D-06/T-01-15)"
  - "Auto-laços (X→X) NÃO estão na allowlist e são tratados como inválidos — o motor não inventa idempotência de estado; o chamador (worker) decide se já está no destino antes de pedir a transição"
  - "completed_step opcional na própria transition atualiza o marcador na mesma operação; mark_step cobre o caso de avançar só a subetapa sem mudar o estado de topo (D-05)"
  - "transition/mark_step retornam o Document para encadeamento; usam session.commit()+refresh para garantir relê do banco"

patterns-established:
  - "Pipeline futuro pede transições explícitas via transition(); nunca atribui Document.state diretamente"
  - "Toda nova transição válida entra na allowlist TRANSITIONS (mudança declarativa, testável)"

requirements-completed: [PROC-01]
requirements-partial: []

# Metrics
duration: 4min
completed: 2026-06-15
---

# Phase 1 Plan 4: Máquina de Estados Explícita por Documento Summary

**Máquina de estados explícita por documento: uma allowlist declarativa (`TRANSITIONS`) cobrindo os 6 estados de topo (CONCLUIDO terminal) e uma função `transition` que valida, persiste o novo estado e o marcador interno, ou levanta `InvalidTransition` e faz rollback sem corromper o dado — fechando PROC-01 e o critério de sucesso 1 da fase.**

## Performance

- **Duration:** ~4 min
- **Tasks:** 2 (ambas TDD)
- **Files created:** 4 (0 modificados)
- **Tests:** 10 novos; suíte total 50 verde; ruff limpo

## Accomplishments
- `app/pipeline/states.py`: `TRANSITIONS: dict[DocState, set[DocState]]` como **allowlist explícita** (D-04) com exatamente o modelo do plano — RECEBIDO→{PROCESSANDO,QUARENTENA,FALHA}, PROCESSANDO→{EM_REVISAO,CONCLUIDO,QUARENTENA,FALHA}, EM_REVISAO→{PROCESSANDO,CONCLUIDO,QUARENTENA,FALHA}, QUARENTENA→{PROCESSANDO}, FALHA→{PROCESSANDO}, CONCLUIDO→∅. Todos os 6 membros de `DocState` são chaves; `CONCLUIDO` é terminal.
- `InvalidTransition(from_state, to_state)`: exceção dedicada carregando ambos os estados com mensagem clara, e `is_valid_transition` consultando a allowlist (T-01-16: nenhum par fora do mapa é aceito).
- `app/pipeline/state_machine.py`: `transition(session, document, to_state, completed_step=None)` valida ANTES de atribuir; numa transição válida atualiza `state` (e opcionalmente `last_completed_step`), faz `commit`+`refresh` e relê o novo estado; numa inválida levanta `InvalidTransition` e faz `rollback`, mantendo o estado persistido (e o marcador) intactos (D-06/T-01-15).
- `mark_step(session, document, step)`: avança só o marcador interno de subetapa sem mudar o estado de topo — base de resume/idempotência (D-05).
- 10 testes provando: cobertura/terminalidade do mapa; `is_valid_transition` em pares válidos/inválidos/terminais; persistência round-trip de transição válida; **não-corrupção** após transição inválida (estado e `last_completed_step` permanecem os anteriores); `completed_step` e `mark_step` atualizando o marcador.

## Task Commits

Cada tarefa foi commitada atomicamente (TDD RED→GREEN por tarefa):

1. **Task 1: estados, allowlist TRANSITIONS e exceção** - `3c1ed0e` (feat)
2. **Task 2: transition() + mark_step (valida/persiste/falha sem corromper)** - `4c1e3fb` (feat)

## Files Created/Modified
- `backend/app/pipeline/__init__.py` - pacote do pipeline (vazio).
- `backend/app/pipeline/states.py` - `TRANSITIONS` (allowlist), `InvalidTransition`, `is_valid_transition`.
- `backend/app/pipeline/state_machine.py` - `transition` (valida/persiste/falha sem corromper) e `mark_step` (marcador interno).
- `backend/tests/test_state_machine.py` - 10 testes (mapa + motor de transição + não-corrupção + marcador).

## Decisions Made
- **Validar antes de atribuir + rollback defensivo**: o caminho de transição inválida não toca `document.state`; `session.rollback()` descarta qualquer mudança não-comitada pendente. Assim o estado persistido permanece o anterior sob qualquer estado de sessão (D-06/T-01-15).
- **Auto-laços (X→X) são inválidos**: a allowlist não contém auto-transições; o motor não inventa idempotência de estado. Comportamento previsível — o chamador (worker da Fase 2) verifica se já está no destino antes de pedir a transição.
- **`completed_step` na própria `transition` + `mark_step` separado**: avançar o estado de topo e registrar a subetapa concluída numa só operação (caso comum do worker), e também avançar só a subetapa sem mudar o estado de topo (resume/idempotência interna, D-05).
- **`commit`+`refresh` e retorno do `Document`**: garante que o estado lido reflete o banco e permite encadeamento ergonômico no chamador.

## Deviations from Plan

None — plano executado exatamente como escrito. Mapa de transições, assinatura das funções, comportamento de não-corrupção e marcador interno seguem o `<transition_model>` e os `<acceptance_criteria>` do plano sem ajustes.

## Threat Model Compliance
- **T-01-15 (Tampering — estado persistido):** mitigado. Teste explícito `test_transition_invalida_falha_sem_corromper` + `test_transition_invalida_nao_altera_last_completed_step` provam que após `InvalidTransition` o estado e o marcador relidos do banco permanecem os anteriores.
- **T-01-16 (Tampering — fluxo ilegal):** mitigado. `TRANSITIONS` é allowlist explícita; `CONCLUIDO` terminal; nenhum par fora do mapa é aceito.
- **T-01-17 (DoS — corrida) / T-01-18 (Repudiation — rastro):** `accept` nesta fase, conforme o plano (single-writer na Fase 2; audit write-ahead na Fase 6).

## Known Stubs
Nenhum stub. O motor é puramente de estado por desenho do plano — a lógica real de pipeline (dedup/separação/extração/classificação/validação) é das Fases 2/3/5, registradas via `last_completed_step`.

## Next Phase Readiness
- **Fase 2 (ingestão e fila):** o worker avança documentos chamando `transition()`/`mark_step()`; nunca atribui `Document.state` diretamente. A allowlist garante que saltos ilegais falham cedo.
- **Fases 3/5 (extração/revisão):** subetapas internas usam `mark_step` para resume/idempotência; transições para `EM_REVISAO`/`QUARENTENA`/`FALHA`/`CONCLUIDO` já são válidas onde o fluxo prevê.
- **PROC-01 fechado:** cada documento percorre uma máquina de estados explícita persistida, com revisão/quarentena/falha e transições inválidas falhando sem corromper.

## Self-Check: PASSED

Todos os 4 arquivos declarados existem em disco; ambos os hashes de commit de tarefa (`3c1ed0e`, `4c1e3fb`) presentes no histórico git; `tests/test_state_machine.py` 10 verde, suíte total 50 verde, ruff limpo.

---
*Phase: 01-funda-o-de-estado-e-storage*
*Completed: 2026-06-15*

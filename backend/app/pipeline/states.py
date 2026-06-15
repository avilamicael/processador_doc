"""Mapa de transições válidas entre estados de topo + exceção de transição inválida.

Núcleo declarativo da máquina de estados por documento (Pattern 1: Document as a
State Machine, ARCHITECTURE.md). `TRANSITIONS` é uma **allowlist explícita** (D-04):
um documento só transita por pares presentes no mapa. Qualquer par fora dele é
inválido e deve falhar sem corromper o dado (D-06; T-01-16 — nenhum salto de
etapa/fluxo ilegal).

As subetapas internas do pipeline (dedup, separação, extração, classificação,
validação) NÃO são estados de topo (D-05) — vivem no marcador interno
`Document.last_completed_step`, manipulado em `state_machine.py`.
"""

from app.models.enums import DocState

# Allowlist de transições válidas entre estados de topo (D-04). Derivada do
# `<transition_model>` do plano. Todo membro de DocState é chave (CONCLUIDO mapeia
# para conjunto vazio — estado terminal, sem saídas).
TRANSITIONS: dict[DocState, set[DocState]] = {
    DocState.RECEBIDO: {
        DocState.PROCESSANDO,
        DocState.QUARENTENA,
        DocState.FALHA,
    },
    DocState.PROCESSANDO: {
        DocState.EM_REVISAO,
        DocState.CONCLUIDO,
        DocState.QUARENTENA,
        DocState.FALHA,
    },
    DocState.EM_REVISAO: {
        DocState.PROCESSANDO,
        DocState.CONCLUIDO,
        DocState.QUARENTENA,
        DocState.FALHA,
    },
    # Reprocessar/resolver da quarentena (REV-05 será construído sobre isto na
    # Fase 5).
    DocState.QUARENTENA: {DocState.PROCESSANDO},
    # Retry após falha.
    DocState.FALHA: {DocState.PROCESSANDO},
    # Terminal — sem saídas.
    DocState.CONCLUIDO: set(),
}


class InvalidTransition(Exception):
    """Transição de estado não permitida pela allowlist `TRANSITIONS` (D-06).

    Carrega `from_state` e `to_state` para diagnóstico e para o chamador
    (worker/UI) reagir sem reinspecionar o mapa.
    """

    def __init__(self, from_state: DocState, to_state: DocState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Transição de estado inválida: {from_state.value} -> {to_state.value} "
            f"não está em TRANSITIONS (allowlist explícita, D-06)."
        )


def is_valid_transition(from_state: DocState, to_state: DocState) -> bool:
    """Retorna True somente se `from_state -> to_state` está na allowlist.

    Consulta direta a `TRANSITIONS`; nenhum par fora do mapa é aceito
    (T-01-16). Estados terminais (CONCLUIDO) retornam sempre False.
    """
    return to_state in TRANSITIONS.get(from_state, set())

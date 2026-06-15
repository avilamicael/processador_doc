"""Função de transição de estado por documento — valida, persiste ou falha sem corromper.

Mecanismo de estado puro sobre `Document.state`/`Document.last_completed_step`. NÃO
contém lógica de pipeline real (dedup/separação/extração/classificação são fases
futuras) — apenas o motor de transições, eixo sobre o qual a fila/worker da Fase 2
avança os documentos (Pattern 1: Document as a State Machine, ARCHITECTURE.md).

Garantias:
- Transição VÁLIDA: atualiza o estado de topo, opcionalmente o marcador interno
  de etapa (D-05), faz commit e relê o novo estado.
- Transição INVÁLIDA: levanta `InvalidTransition` SEM persistir nada — o estado no
  banco permanece o anterior (D-06; T-01-15: não corrompe o dado). A validação
  ocorre ANTES de qualquer atribuição; um `rollback` defensivo descarta mudanças
  não-comitadas pendentes na sessão.
"""

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import DocState
from app.pipeline.states import InvalidTransition, is_valid_transition


def transition(
    session: Session,
    document: Document,
    to_state: DocState,
    completed_step: str | None = None,
) -> Document:
    """Transiciona `document` para `to_state`, validando contra a allowlist.

    Numa transição válida: seta `document.state = to_state`, opcionalmente seta
    `document.last_completed_step = completed_step` (marcador interno D-05), faz
    commit e refresca a instância — relendo do banco o estado é `to_state`.

    Numa transição inválida (par fora de `TRANSITIONS`): levanta
    `InvalidTransition(from_state, to_state)` SEM atribuir nada e desfaz qualquer
    mudança pendente na sessão (`rollback`). O estado persistido permanece o
    anterior (D-06) — assim como `last_completed_step`.

    Chamadas idempotentes "estado X já é o destino" (ex.: PROCESSANDO →
    PROCESSANDO) NÃO estão na allowlist e são tratadas como inválidas: o motor
    não inventa auto-laços. O chamador (worker) decide se já está no destino
    antes de pedir a transição — comportamento previsível e explícito (D-06).

    Retorna o próprio `document` para encadeamento.
    """
    from_state = document.state

    # Validar ANTES de qualquer atribuição — caminho de erro não toca o estado.
    if not is_valid_transition(from_state, to_state):
        # Defensivo: descarta mudanças não-comitadas pendentes na sessão, para
        # que o estado persistido permaneça intacto (D-06 / T-01-15).
        session.rollback()
        raise InvalidTransition(from_state, to_state)

    document.state = to_state
    if completed_step is not None:
        document.last_completed_step = completed_step

    session.commit()
    session.refresh(document)
    return document


def mark_step(session: Session, document: Document, step: str) -> Document:
    """Atualiza apenas o marcador interno de última etapa concluída (D-05).

    Suporta resume/idempotência das subetapas internas do pipeline (dedup,
    separação, extração, classificação, validação) SEM mudar o estado de topo.
    Persiste e refresca. Retorna o próprio `document`.
    """
    document.last_completed_step = step
    session.commit()
    session.refresh(document)
    return document

"""Testes da máquina de estados explícita por documento.

Prova:
- O mapa `TRANSITIONS` cobre os 6 estados de topo (D-04), com `CONCLUIDO` terminal.
- `is_valid_transition` aceita apenas pares no mapa (allowlist explícita — D-06,
  T-01-16: nenhum salto de etapa/fluxo ilegal).
- `transition` persiste transições válidas e, numa transição inválida, levanta
  `InvalidTransition` SEM corromper o estado persistido (D-06, T-01-15).
- O marcador interno `last_completed_step` suporta resume/idempotência (D-05).

O schema do banco para os testes vem de `Base.metadata.create_all` num SQLite
temporário — aceitável APENAS em teste (D-10).
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, select

from app.models import DocState, Document
from app.pipeline.states import (
    TRANSITIONS,
    InvalidTransition,
    is_valid_transition,
)
from app.storage.db import Base, get_session


@pytest.fixture
def schema_engine(engine: Engine) -> Iterator[Engine]:
    """Engine com o schema criado via metadata (somente para teste)."""
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)


# --------------------------------------------------------------------------- #
# Task 1: mapa de transições válidas + exceção (transitions_map)
# --------------------------------------------------------------------------- #


def test_transitions_map_cobre_os_seis_estados() -> None:
    assert set(TRANSITIONS.keys()) == set(DocState)
    # CONCLUIDO é terminal — conjunto vazio de saídas.
    assert TRANSITIONS[DocState.CONCLUIDO] == set()


def test_transitions_map_modelo_exato() -> None:
    assert TRANSITIONS[DocState.RECEBIDO] == {
        DocState.PROCESSANDO,
        DocState.QUARENTENA,
        DocState.FALHA,
    }
    assert TRANSITIONS[DocState.PROCESSANDO] == {
        DocState.EM_REVISAO,
        DocState.CONCLUIDO,
        DocState.QUARENTENA,
        DocState.FALHA,
    }
    assert TRANSITIONS[DocState.EM_REVISAO] == {
        DocState.PROCESSANDO,
        DocState.CONCLUIDO,
        DocState.QUARENTENA,
        DocState.FALHA,
    }
    assert TRANSITIONS[DocState.QUARENTENA] == {DocState.PROCESSANDO}
    assert TRANSITIONS[DocState.FALHA] == {DocState.PROCESSANDO}


def test_transitions_map_is_valid_transition() -> None:
    assert is_valid_transition(DocState.RECEBIDO, DocState.PROCESSANDO) is True
    assert is_valid_transition(DocState.RECEBIDO, DocState.CONCLUIDO) is False
    # Terminal: CONCLUIDO não tem saídas válidas.
    assert is_valid_transition(DocState.CONCLUIDO, DocState.PROCESSANDO) is False
    # Retry/reprocesso permitidos.
    assert is_valid_transition(DocState.FALHA, DocState.PROCESSANDO) is True
    assert is_valid_transition(DocState.QUARENTENA, DocState.PROCESSANDO) is True


def test_transitions_map_invalid_transition_carrega_estados() -> None:
    exc = InvalidTransition(DocState.RECEBIDO, DocState.CONCLUIDO)
    assert exc.from_state == DocState.RECEBIDO
    assert exc.to_state == DocState.CONCLUIDO
    # Mensagem clara mencionando ambos os estados.
    assert "recebido" in str(exc)
    assert "concluido" in str(exc)


# --------------------------------------------------------------------------- #
# Task 2: função de transição (valida, persiste, falha sem corromper)
# --------------------------------------------------------------------------- #


def _novo_documento(session, **kwargs) -> Document:
    doc = Document(content_hash="a" * 64, original_filename="nota.pdf", **kwargs)
    session.add(doc)
    session.flush()
    return doc


def test_transition_valida_persiste_e_rele(schema_engine: Engine) -> None:
    from app.pipeline.state_machine import transition

    with get_session(schema_engine) as session:
        doc = _novo_documento(session)
        transition(session, doc, DocState.PROCESSANDO)
        assert doc.state == DocState.PROCESSANDO

    with get_session(schema_engine) as session:
        lido = session.scalar(
            select(Document).where(Document.content_hash == "a" * 64)
        )
        assert lido is not None
        assert lido.state == DocState.PROCESSANDO


def test_transition_invalida_falha_sem_corromper(schema_engine: Engine) -> None:
    from app.pipeline.state_machine import transition

    with get_session(schema_engine) as session:
        doc = _novo_documento(session)
        session.commit()  # estado RECEBIDO já persistido
        with pytest.raises(InvalidTransition):
            transition(session, doc, DocState.CONCLUIDO)

    # D-06 / T-01-15: estado persistido permanece o ANTERIOR (não corrompe).
    with get_session(schema_engine) as session:
        lido = session.scalar(
            select(Document).where(Document.content_hash == "a" * 64)
        )
        assert lido is not None
        assert lido.state == DocState.RECEBIDO


def test_transition_invalida_nao_altera_last_completed_step(
    schema_engine: Engine,
) -> None:
    from app.pipeline.state_machine import transition

    with get_session(schema_engine) as session:
        doc = _novo_documento(session, last_completed_step="dedup")
        session.commit()
        with pytest.raises(InvalidTransition):
            transition(
                session, doc, DocState.CONCLUIDO, completed_step="classificacao"
            )

    with get_session(schema_engine) as session:
        lido = session.scalar(
            select(Document).where(Document.content_hash == "a" * 64)
        )
        assert lido is not None
        # Marcador NÃO foi alterado pela transição inválida.
        assert lido.last_completed_step == "dedup"
        assert lido.state == DocState.RECEBIDO


def test_transition_com_completed_step_atualiza_marcador(
    schema_engine: Engine,
) -> None:
    from app.pipeline.state_machine import transition

    with get_session(schema_engine) as session:
        doc = _novo_documento(session)
        transition(
            session, doc, DocState.PROCESSANDO, completed_step="dedup"
        )

    with get_session(schema_engine) as session:
        lido = session.scalar(
            select(Document).where(Document.content_hash == "a" * 64)
        )
        assert lido is not None
        assert lido.state == DocState.PROCESSANDO
        assert lido.last_completed_step == "dedup"


def test_mark_step_atualiza_so_o_marcador(schema_engine: Engine) -> None:
    from app.pipeline.state_machine import mark_step

    with get_session(schema_engine) as session:
        doc = _novo_documento(session, state=DocState.PROCESSANDO)
        mark_step(session, doc, "extracao")
        assert doc.state == DocState.PROCESSANDO

    with get_session(schema_engine) as session:
        lido = session.scalar(
            select(Document).where(Document.content_hash == "a" * 64)
        )
        assert lido is not None
        # Estado de topo inalterado; só o marcador interno mudou (D-05).
        assert lido.state == DocState.PROCESSANDO
        assert lido.last_completed_step == "extracao"


def test_transition_retorna_o_documento(schema_engine: Engine) -> None:
    from app.pipeline.state_machine import transition

    with get_session(schema_engine) as session:
        doc = _novo_documento(session)
        resultado = transition(session, doc, DocState.PROCESSANDO)
        assert resultado is doc

"""Encadeamento da fila em runtime — `_sweep_pending` roda no startup E ocioso.

Antes, os sweeps (extract/classify) rodavam só no startup do worker, então um
documento ingerido/extraído EM RUNTIME não avançava ingest→extract→classify sem
reiniciar o worker (WARNING da verificação da Fase 4). `_sweep_pending` agora é a
rotina única reusada no startup e a cada ciclo ocioso, fechando os dois gaps.
"""

import json

from sqlalchemy import Engine, select

from app.models import DocState, Document, Extraction, Job
from app.queue import worker
from app.storage.db import get_session

HASH_AWAIT = "c" * 64  # bloco aguardando_extracao (sem Extraction)
HASH_EXTRACTED = "d" * 64  # bloco extraido (sem ClassificationResult)


def _seed_awaiting(session, content_hash: str) -> None:
    """Bloco no estado terminal da Fase 2: PROCESSANDO + 'aguardando_extracao'."""
    session.add(
        Document(
            content_hash=content_hash,
            original_filename="novo.pdf",
            state=DocState.PROCESSANDO,
            last_completed_step="aguardando_extracao",
        )
    )
    session.commit()


def _seed_extracted(session, content_hash: str) -> None:
    """Bloco extraído sem classificação: PROCESSANDO + 'extraido' + Extraction."""
    doc = Document(
        content_hash=content_hash,
        original_filename="extraido.pdf",
        state=DocState.PROCESSANDO,
        last_completed_step="extraido",
    )
    session.add(doc)
    session.commit()
    session.add(
        Extraction(
            document_id=doc.id,
            fields_json=json.dumps([{"key": "x", "value": "1", "confidence": 0.9}]),
            full_text="texto",
            doc_type_guess="outro",
            doc_type_confidence=0.5,
            route="native_text",
        )
    )
    session.commit()


def test_sweep_pending_enfileira_extract_e_classify(schema_engine: Engine) -> None:
    """Um bloco 'aguardando_extracao' e um 'extraido' → 1 extract + 1 classify."""
    with get_session(schema_engine) as s:
        _seed_awaiting(s, HASH_AWAIT)
        _seed_extracted(s, HASH_EXTRACTED)

    total = worker._sweep_pending(schema_engine)

    assert total == 2
    with get_session(schema_engine) as s:
        jobs = {(j.original_hash, j.step) for j in s.scalars(select(Job)).all()}
    assert (HASH_AWAIT, "extract") in jobs
    assert (HASH_EXTRACTED, "classify") in jobs


def test_sweep_pending_idempotente(schema_engine: Engine) -> None:
    """Rodar 2x não cria jobs novos na segunda passada (UNIQUE + sweeps no-op)."""
    with get_session(schema_engine) as s:
        _seed_awaiting(s, HASH_AWAIT)
        _seed_extracted(s, HASH_EXTRACTED)

    first = worker._sweep_pending(schema_engine)
    second = worker._sweep_pending(schema_engine)

    assert first == 2
    assert second == 0
    with get_session(schema_engine) as s:
        assert s.scalar(select(Job.id).where(Job.original_hash == HASH_AWAIT))
        assert s.scalar(select(Job.id).where(Job.original_hash == HASH_EXTRACTED))


def test_sweep_pending_nada_pendente_retorna_zero(schema_engine: Engine) -> None:
    """Sem blocos pendentes, o sweep é no-op e retorna 0 (não dorme à toa)."""
    assert worker._sweep_pending(schema_engine) == 0

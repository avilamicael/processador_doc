"""Sweep idempotente de enqueue de extract no startup (Plan 04, Task 2).

Prova o `<behavior>`:
- Document em PROCESSANDO + last_completed_step='aguardando_extracao' SEM job de
  extract → enqueue (block.content_hash, 'extract').
- idempotente: rodar 2x não cria job duplicado (UNIQUE (original_hash, step) +
  no-op do `enqueue`).
- cobre Documents legados (criados pela Fase 2 antes desta fase).
- Document já com Extraction (já extraído) NÃO é re-enfileirado.

Sem OpenAI: o sweep só enfileira; nenhuma chamada paga ocorre aqui.
"""

import json

from sqlalchemy import Engine, select

from app.models import DocState, Document, Extraction, Job
from app.pipeline.ingest_stage import AWAITING_EXTRACTION_STEP
from app.queue.worker import enqueue_pending_extractions
from app.storage.db import get_session

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _doc(content_hash: str, *, step: str | None = AWAITING_EXTRACTION_STEP) -> Document:
    return Document(
        content_hash=content_hash,
        original_filename="legado.bin",
        state=DocState.PROCESSANDO,
        last_completed_step=step,
    )


def test_sweep_enfileira_pendentes(schema_engine: Engine) -> None:
    """Cada Document aguardando_extracao sem job vira um job (content_hash, 'extract')."""
    with get_session(schema_engine) as s:
        s.add(_doc(HASH_A))
        s.add(_doc(HASH_B))
        s.commit()

    with get_session(schema_engine) as s:
        n = enqueue_pending_extractions(s)
    assert n == 2

    with get_session(schema_engine) as s:
        jobs = s.scalars(select(Job).where(Job.step == "extract")).all()
        hashes = {j.original_hash for j in jobs}
        assert hashes == {HASH_A, HASH_B}
        # payload carrega o content_hash do bloco.
        for j in jobs:
            assert json.loads(j.payload)["content_hash"] == j.original_hash


def test_sweep_idempotente(schema_engine: Engine) -> None:
    """Rodar 2x não duplica jobs (UNIQUE uq_jobs_hash_step + enqueue no-op)."""
    with get_session(schema_engine) as s:
        s.add(_doc(HASH_A))
        s.commit()

    with get_session(schema_engine) as s:
        first = enqueue_pending_extractions(s)
    with get_session(schema_engine) as s:
        second = enqueue_pending_extractions(s)

    assert first == 1
    assert second == 0  # 2ª passada não enfileira nada novo

    with get_session(schema_engine) as s:
        jobs = s.scalars(
            select(Job).where(Job.original_hash == HASH_A, Job.step == "extract")
        ).all()
        assert len(jobs) == 1


def test_sweep_ignora_ja_extraido(schema_engine: Engine) -> None:
    """Document que já tem Extraction NÃO é re-enfileirado (não re-cobra)."""
    with get_session(schema_engine) as s:
        doc = _doc(HASH_A)
        s.add(doc)
        s.commit()
        s.add(
            Extraction(
                document_id=doc.id,
                fields_json="[]",
                full_text="já extraído",
                doc_type_guess="x",
                doc_type_confidence=0.5,
                route="native_text",
            )
        )
        s.commit()

    with get_session(schema_engine) as s:
        n = enqueue_pending_extractions(s)
    assert n == 0

    with get_session(schema_engine) as s:
        jobs = s.scalars(select(Job).where(Job.step == "extract")).all()
        assert jobs == []


def test_sweep_ignora_estado_errado(schema_engine: Engine) -> None:
    """Document que NÃO está em aguardando_extracao não é enfileirado."""
    with get_session(schema_engine) as s:
        # marcador diferente (ainda não chegou ao fim do ingest)
        s.add(_doc(HASH_A, step="outro_passo"))
        # estado FALHA (mesmo com o marcador, não está pronto p/ extrair)
        falha = _doc(HASH_B)
        falha.state = DocState.FALHA
        s.add(falha)
        s.commit()

    with get_session(schema_engine) as s:
        n = enqueue_pending_extractions(s)
    assert n == 0

    with get_session(schema_engine) as s:
        assert s.scalars(select(Job).where(Job.step == "extract")).all() == []

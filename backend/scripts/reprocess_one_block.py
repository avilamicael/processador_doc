"""Reprocessa UM bloco pelo pipeline REAL (extract_stage → classify_stage).

Teste controlado da Fase 4 com chave OpenAI real: pega o primeiro bloco em
estado FALHA (deixado por execuções sem chave), reseta para o estado terminal
da Fase 2 (PROCESSANDO + "aguardando_extracao"), apaga Extraction/Classification
e jobs antigos do bloco, e roda os stages REAIS em sequência:

    extract_stage(content_hash) -> Extraction + Usage (chamada OpenAI de visão)
    classify_stage(content_hash) -> ClassificationResult (match ou QUARENTENA)

Exercita o código de produção (Responses API + Structured Outputs + visão),
fora da fila, para validação rápida sem depender de reinícios do worker.

    uv run python scripts/reprocess_one_block.py [DOC_ID]

Sem DOC_ID, usa o primeiro Document em FALHA. Custa ~1 chamada de visão.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import delete, select

from app.classification.stage import classify_stage
from app.config import get_settings
from app.extraction.stage import extract_stage
from app.models.classification import ClassificationResult
from app.models.document import Document
from app.models.enums import DocState
from app.models.extraction import Extraction
from app.storage.db import create_db_engine, get_session

AWAITING = "aguardando_extracao"


async def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.effective_database_url)

    target_id: int | None = int(sys.argv[1]) if len(sys.argv) > 1 else None

    with get_session(engine) as session:
        if target_id is not None:
            doc = session.scalar(select(Document).where(Document.id == target_id))
        else:
            doc = session.scalar(
                select(Document).where(Document.state == DocState.FALHA).order_by(Document.id)
            )
        if doc is None:
            print("Nenhum bloco encontrado para reprocessar.")
            return

        content_hash = doc.content_hash
        doc_id = doc.id
        print(f"Reprocessando doc {doc_id} ({doc.original_filename}), estado atual: {doc.state.value}")

        # Limpa resultados anteriores do bloco (idempotência dos stages exige ausência).
        session.execute(delete(ClassificationResult).where(ClassificationResult.document_id == doc_id))
        session.execute(delete(Extraction).where(Extraction.document_id == doc_id))
        # Reset ao estado terminal da Fase 2 (assignment direto — utilitário admin).
        doc.state = DocState.PROCESSANDO
        doc.last_completed_step = AWAITING
        session.commit()

    # (1) Extração REAL (visão/texto via OpenAI).
    print("→ extract_stage (chamada OpenAI)...")
    with get_session(engine) as session:
        ext = await extract_stage(session, content_hash=content_hash)
        print(f"   rota={ext.route} called_ai={ext.called_ai}")

    # (2) Classificação REAL (matcher local + IA de desempate/faltantes se preciso).
    print("→ classify_stage...")
    with get_session(engine) as session:
        cls = await classify_stage(session, content_hash=content_hash)
        print(f"   resultado: {cls}")

    # Resumo final do que ficou persistido.
    with get_session(engine) as session:
        doc = session.scalar(select(Document).where(Document.id == doc_id))
        result = session.scalar(
            select(ClassificationResult).where(ClassificationResult.document_id == doc_id)
        )
        print("--- RESULTADO ---")
        print(f"  doc {doc_id}: state={doc.state.value} marcador={doc.last_completed_step}")
        if result is None:
            print("  sem ClassificationResult")
        else:
            print(f"  template_id={result.template_id} confidence={result.confidence}")
            for ff in result.filled_fields:
                mark = "OK" if ff.valid else f"INVALIDO ({ff.invalid_reason})"
                print(f"    - {ff.field_name}: {ff.raw_value!r} -> {ff.normalized_value!r} [{mark}]")


if __name__ == "__main__":
    asyncio.run(main())

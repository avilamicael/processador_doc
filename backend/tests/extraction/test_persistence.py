"""Persistência do modelo `Extraction` (Fase 3).

Cobre:
- round-trip: criar Document + Extraction e ler de volta.
- UNIQUE(document_id): inserir 2 Extractions para o MESMO bloco viola a
  idempotência (1 extração por bloco = não re-cobrar a IA).
- a fixture respx (`mock_openai`) realmente produz `output_parsed` válido e a
  variante de recusa produz `output_parsed is None` — scaffold dos Plans 02-04.
"""

import json

import pytest
from httpx import Response as HxResponse
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from app.extraction.schema import ExtractionResult
from app.models import Document, Extraction
from app.storage.db import get_session


def _make_document(session, content_hash: str) -> Document:
    doc = Document(content_hash=content_hash, original_filename="exemplo.pdf")
    session.add(doc)
    session.flush()  # garante doc.id sem fechar a transação
    return doc


def test_round_trip_extraction(schema_engine: Engine) -> None:
    with get_session(schema_engine) as session:
        doc = _make_document(session, "a" * 64)
        ext = Extraction(
            document_id=doc.id,
            fields_json=json.dumps(
                [{"key": "valor_total", "value": "1.234,56", "confidence": 0.9}]
            ),
            full_text="Texto integral do documento.",
            doc_type_guess="boleto",
            doc_type_confidence=0.75,
            route="native_text",
        )
        session.add(ext)

    with get_session(schema_engine) as session:
        lido = session.scalar(select(Extraction).where(Extraction.document_id == doc.id))
        assert lido is not None
        assert lido.full_text == "Texto integral do documento."
        assert lido.doc_type_guess == "boleto"
        assert lido.doc_type_confidence == 0.75
        assert lido.route == "native_text"
        campos = json.loads(lido.fields_json)
        assert campos[0]["key"] == "valor_total"


def test_unique_por_document_id_rejeita_segunda_extracao(schema_engine: Engine) -> None:
    """1 extração por bloco: a 2ª Extraction para o mesmo document_id deve falhar
    na UNIQUE — é o que garante não re-chamar/re-cobrar a IA (idempotência)."""
    with get_session(schema_engine) as session:
        doc = _make_document(session, "b" * 64)
        session.add(
            Extraction(
                document_id=doc.id,
                fields_json="[]",
                full_text="primeira",
                doc_type_guess="desconhecido",
                doc_type_confidence=0.1,
                route="vision",
            )
        )

    with pytest.raises(IntegrityError):
        with get_session(schema_engine) as session:
            session.add(
                Extraction(
                    document_id=doc.id,
                    fields_json="[]",
                    full_text="segunda",
                    doc_type_guess="desconhecido",
                    doc_type_confidence=0.1,
                    route="vision",
                )
            )


async def test_mock_openai_produz_output_parsed_valido(mock_openai) -> None:
    """A fixture respx de sucesso devolve um ExtractionResult em output_parsed."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key="sk-test")
    resp = await client.responses.parse(
        model="gpt-4o-2024-08-06",
        input=[{"role": "user", "content": [{"type": "input_text", "text": "x"}]}],
        text_format=ExtractionResult,
    )
    assert isinstance(resp.output_parsed, ExtractionResult)
    assert resp.output_parsed.doc_type_guess == "nota_fiscal"
    # usage mapeável para Usage(prompt_tokens, completion_tokens) no Plan 02/03.
    assert resp.usage.input_tokens == 120
    assert resp.usage.output_tokens == 64


async def test_mock_openai_variante_recusa(mock_openai, openai_refusal_payload) -> None:
    """A variante de recusa produz output_parsed is None (Pitfall 2 → FALHA, D-08)."""
    from openai import AsyncOpenAI

    mock_openai.post("/responses").mock(
        return_value=HxResponse(200, json=openai_refusal_payload)
    )
    client = AsyncOpenAI(api_key="sk-test")
    resp = await client.responses.parse(
        model="gpt-4o-2024-08-06",
        input=[{"role": "user", "content": [{"type": "input_text", "text": "x"}]}],
        text_format=ExtractionResult,
    )
    assert resp.output_parsed is None


def test_pdf_fixtures_caminho_texto_vs_visao(
    text_pdf_bytes: bytes, scanned_pdf_bytes: bytes, png_bytes: bytes, jpeg_bytes: bytes
) -> None:
    """Sanidade das fixtures sintéticas: PDF com texto tem caracteres nativos; o
    escaneado não; e as imagens têm os magic bytes esperados (PDF vs imagem)."""
    import fitz

    with fitz.open(stream=text_pdf_bytes, filetype="pdf") as d:
        assert len(d[0].get_text().strip()) > 0

    with fitz.open(stream=scanned_pdf_bytes, filetype="pdf") as d:
        assert len(d[0].get_text().strip()) == 0

    assert text_pdf_bytes[:5] == b"%PDF-"
    assert png_bytes[:4] == b"\x89PNG"
    assert jpeg_bytes[:2] == b"\xff\xd8"

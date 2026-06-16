"""Comportamento do `extract_stage` — orquestração async idempotente + commit atômico.

Cobre o `<behavior>` do Plan 03 (Task 1) com a OpenAI mockada via respx (0 token):
- happy path texto nativo: route="native_text", persiste Extraction, NÃO renderiza visão;
- happy path PDF escaneado: route="vision", envia render à IA, persiste full_text (D-06);
- happy path imagem (PNG/JPEG): magic bytes → caminho visão direto (a imagem é a página);
- recusa: `ExtractionRefused` PROPAGA (não engole), nenhuma Extraction parcial persistida;
- PDF malformado: exceção do fitz PROPAGA controlada (o worker tratará; não derruba).

A sessão usa `schema_engine` (create_all em teste, D-10); o blob é gravado no CAS
(via `data_dir` temporário) antes de chamar o stage.
"""

import json
from pathlib import Path

import pytest
from httpx import Response as HxResponse
from sqlalchemy import Engine, select

from app import config
from app.extraction.openai_client import ExtractionRefused
from app.extraction.stage import extract_stage
from app.models import Document, Extraction, Usage
from app.models.enums import DocState
from app.storage import cas
from app.storage.db import get_session


@pytest.fixture(autouse=True)
def _openai_key(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chave OpenAI fictícia no env (respx mocka o transporte — 0 token).

    Depende de `data_dir` para que ambos `DATA_DIR` e `OPENAI_API_KEY` estejam no
    env antes de o `get_settings` (com cache limpo) recomputar. Não monkeypatcha
    `get_settings` em si: o stage lê dele tanto `data_dir` quanto o tunável de
    extração, então precisamos do Settings real reconstruído com os dois vars.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-stage")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _seed_document_with_blob(session, blob: bytes, data_dir: Path) -> Document:
    """Grava `blob` no CAS e cria o Document (bloco) terminal 'aguardando_extracao'.

    Espelha o estado em que a Fase 2 (ingest_stage) deixa um bloco: PROCESSANDO +
    last_completed_step='aguardando_extracao', referenciado pelo content_hash.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = data_dir / "seed.bin"
    tmp.write_bytes(blob)
    content_hash = cas.store(tmp)
    tmp.unlink(missing_ok=True)
    doc = Document(
        content_hash=content_hash,
        original_filename="exemplo.bin",
        state=DocState.PROCESSANDO,
        last_completed_step="aguardando_extracao",
    )
    session.add(doc)
    # Commit explícito: `get_session` só auto-commita se houver pendências no exit,
    # e o `flush` aqui esvaziaria `session.new` — sem commit o seed seria descartado.
    session.commit()
    return doc


async def test_happy_path_texto_nativo_persiste_extraction(
    schema_engine: Engine, data_dir: Path, mock_openai
) -> None:
    """PDF com texto: route='native_text', Extraction persistida, sem render de visão."""
    with get_session(schema_engine) as session:
        # PDF sintético com texto nativo embutido (não usamos a fixture pois o blob
        # precisa estar no CAS; geramos aqui via fitz).
        import fitz

        d = fitz.open()
        page = d.new_page()
        page.insert_text(
            (72, 72),
            "Nota Fiscal numero 12345 CNPJ 12.345.678/0001-90 Valor 1.234,56",
        )
        blob = d.tobytes()
        d.close()
        doc = _seed_document_with_blob(session, blob, data_dir)
        content_hash = doc.content_hash

    with get_session(schema_engine) as session:
        await extract_stage(session, content_hash=content_hash)

    with get_session(schema_engine) as session:
        ext = session.scalar(
            select(Extraction).where(Extraction.document_id == doc.id)
        )
        assert ext is not None
        assert ext.route == "native_text"
        assert ext.doc_type_guess == "nota_fiscal"
        assert ext.full_text  # texto persistido (D-06)
        campos = json.loads(ext.fields_json)
        assert campos[0]["key"] == "cnpj_emitente"


async def test_happy_path_pdf_escaneado_caminho_visao(
    schema_engine: Engine, data_dir: Path, mock_openai
) -> None:
    """PDF sem texto: route='vision'; envia render à IA; persiste full_text (D-06)."""
    with get_session(schema_engine) as session:
        import fitz

        d = fitz.open()
        page = d.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 64, 64))
        pix.clear_with(255)
        page.insert_image(fitz.Rect(0, 0, 64, 64), pixmap=pix)
        blob = d.tobytes()
        d.close()
        doc = _seed_document_with_blob(session, blob, data_dir)
        content_hash = doc.content_hash

    with get_session(schema_engine) as session:
        await extract_stage(session, content_hash=content_hash)

    with get_session(schema_engine) as session:
        ext = session.scalar(
            select(Extraction).where(Extraction.document_id == doc.id)
        )
        assert ext is not None
        assert ext.route == "vision"
        # full_text persistido (o que houver de texto nativo — D-06)
        assert ext.full_text is not None


async def test_happy_path_imagem_png_caminho_visao(
    schema_engine: Engine, data_dir: Path, mock_openai, png_bytes: bytes
) -> None:
    """Blob de imagem (magic bytes PNG) → caminho visão direto (a imagem é a página)."""
    with get_session(schema_engine) as session:
        doc = _seed_document_with_blob(session, png_bytes, data_dir)
        content_hash = doc.content_hash

    with get_session(schema_engine) as session:
        await extract_stage(session, content_hash=content_hash)

    with get_session(schema_engine) as session:
        ext = session.scalar(
            select(Extraction).where(Extraction.document_id == doc.id)
        )
        assert ext is not None
        assert ext.route == "vision"


async def test_refusal_propaga_sem_corromper_estado(
    schema_engine: Engine, data_dir: Path, mock_openai, openai_refusal_payload
) -> None:
    """ExtractionRefused PROPAGA; nenhuma Extraction/Usage parcial persistida."""
    mock_openai.post("/responses").mock(
        return_value=HxResponse(200, json=openai_refusal_payload)
    )
    with get_session(schema_engine) as session:
        import fitz

        d = fitz.open()
        page = d.new_page()
        page.insert_text((72, 72), "Documento com texto nativo suficiente para a rota texto.")
        blob = d.tobytes()
        d.close()
        doc = _seed_document_with_blob(session, blob, data_dir)
        content_hash = doc.content_hash

    with get_session(schema_engine) as session:
        with pytest.raises(ExtractionRefused):
            await extract_stage(session, content_hash=content_hash)

    # Estado não corrompido: nada parcial comitado.
    with get_session(schema_engine) as session:
        assert session.scalar(
            select(Extraction).where(Extraction.document_id == doc.id)
        ) is None
        assert session.scalar(
            select(Usage).where(Usage.document_id == doc.id)
        ) is None
        reloaded = session.get(Document, doc.id)
        assert reloaded.state == DocState.PROCESSANDO
        assert reloaded.last_completed_step == "aguardando_extracao"


async def test_pdf_malformado_propaga_excecao_controlada(
    schema_engine: Engine, data_dir: Path
) -> None:
    """PDF malformado: fitz levanta → extract_stage propaga (worker tratará); sem Extraction.

    Sem `mock_openai`: a exceção do PyMuPDF ocorre ANTES de qualquer chamada à IA
    (prova que o erro é local e a IA nunca é tocada num PDF corrompido).
    """
    import fitz

    blob = b"%PDF-1.7\nconteudo-corrompido-nao-e-um-pdf-valido\n%%EOF"
    with get_session(schema_engine) as session:
        doc = _seed_document_with_blob(session, blob, data_dir)
        content_hash = doc.content_hash

    with get_session(schema_engine) as session:
        # fitz.FileDataError é a exceção concreta que o PyMuPDF levanta num PDF
        # corrompido; o stage a propaga sem capturar (o worker do Plan 04 trata).
        with pytest.raises(fitz.FileDataError):
            await extract_stage(session, content_hash=content_hash)

    with get_session(schema_engine) as session:
        assert session.scalar(
            select(Extraction).where(Extraction.document_id == doc.id)
        ) is None

"""Idempotência / não cobrar duas vezes (T-03-07 / Failure Mode 3).

Maior alavanca de confiança da fase: re-executar `extract_stage` para o MESMO
bloco NÃO pode re-chamar a IA (custo) nem duplicar Extraction/Usage. Prova via
respx que a Responses API foi chamada EXATAMENTE uma vez em 2 execuções.
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from app import config
from app.extraction.stage import extract_stage
from app.models import Document, Extraction, Usage
from app.models.enums import DocState
from app.storage import cas
from app.storage.db import get_session


@pytest.fixture(autouse=True)
def _openai_key(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chave fictícia no env (respx mocka o transporte — 0 token)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-stage")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _seed_text_pdf(session, data_dir: Path) -> Document:
    import fitz

    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 72), "Documento de teste com texto nativo suficiente.")
    blob = d.tobytes()
    d.close()

    data_dir.mkdir(parents=True, exist_ok=True)
    tmp = data_dir / "seed.bin"
    tmp.write_bytes(blob)
    content_hash = cas.store(tmp)
    tmp.unlink(missing_ok=True)

    doc = Document(
        content_hash=content_hash,
        original_filename="exemplo.pdf",
        state=DocState.PROCESSANDO,
        last_completed_step="aguardando_extracao",
    )
    session.add(doc)
    session.commit()
    return doc


async def test_reexecucao_nao_re_chama_ia_nem_duplica(
    schema_engine: Engine, data_dir: Path, mock_openai
) -> None:
    """2x extract_stage no mesmo bloco → IA chamada 1x, sem Extraction/Usage duplicados."""
    with get_session(schema_engine) as session:
        doc = _seed_text_pdf(session, data_dir)
        content_hash = doc.content_hash

    # 1ª execução: chama a IA e persiste.
    with get_session(schema_engine) as session:
        r1 = await extract_stage(session, content_hash=content_hash)
    assert r1.called_ai is True

    # 2ª execução: deve ser no-op idempotente (Extraction já existe).
    with get_session(schema_engine) as session:
        r2 = await extract_stage(session, content_hash=content_hash)
    assert r2.called_ai is False

    # A Responses API foi chamada EXATAMENTE uma vez (não re-cobrar — T-03-07).
    # `mock_openai.calls` registra todas as requisições passadas pelo router; só a
    # 1ª execução deve ter tocado o endpoint /responses (a 2ª é no-op idempotente).
    assert mock_openai.calls.call_count == 1

    # Sem duplicação de Extraction nem de Usage.
    with get_session(schema_engine) as session:
        n_ext = session.scalar(
            select(func.count())
            .select_from(Extraction)
            .where(Extraction.document_id == doc.id)
        )
        n_usage = session.scalar(
            select(func.count())
            .select_from(Usage)
            .where(Usage.document_id == doc.id, Usage.step == "extract")
        )
        assert n_ext == 1
        assert n_usage == 1

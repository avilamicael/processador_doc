"""Medição de tokens (USE-02 / SC4) — base da cobrança por consumo.

Prova que cada extração grava EXATAMENTE 1 `Usage(step="extract")` com o mapeamento
correto input_tokens→prompt_tokens e output_tokens→completion_tokens. A fixture
respx (`mock_openai`) devolve usage sintético conhecido (input=120, output=64), de
modo que os números asseridos são determinísticos e não gastam token.
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from app import config
from app.extraction.stage import extract_stage
from app.models import Document, Usage
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
    """Grava um PDF com texto nativo no CAS e cria o Document do bloco."""
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


async def test_uma_usage_extract_com_tokens_mapeados(
    schema_engine: Engine, data_dir: Path, mock_openai
) -> None:
    """Após extração: exatamente 1 Usage(step='extract') com prompt/completion mapeados.

    A fixture de sucesso expõe input_tokens=120 / output_tokens=64; o stage mapeia
    input→prompt e output→completion (USE-02 / SC4 — base da cobrança).
    """
    with get_session(schema_engine) as session:
        doc = _seed_text_pdf(session, data_dir)
        content_hash = doc.content_hash

    with get_session(schema_engine) as session:
        await extract_stage(session, content_hash=content_hash)

    with get_session(schema_engine) as session:
        usages = list(
            session.scalars(
                select(Usage).where(
                    Usage.document_id == doc.id, Usage.step == "extract"
                )
            )
        )
        assert len(usages) == 1
        usage = usages[0]
        assert usage.prompt_tokens == 120  # input_tokens → prompt_tokens
        assert usage.completion_tokens == 64  # output_tokens → completion_tokens


async def test_nenhuma_usage_duplicada_por_extracao(
    schema_engine: Engine, data_dir: Path, mock_openai
) -> None:
    """Uma extração não pode gerar mais de 1 Usage(step='extract') (sem dupla cobrança)."""
    with get_session(schema_engine) as session:
        doc = _seed_text_pdf(session, data_dir)
        content_hash = doc.content_hash

    with get_session(schema_engine) as session:
        await extract_stage(session, content_hash=content_hash)

    with get_session(schema_engine) as session:
        count = session.scalar(
            select(func.count())
            .select_from(Usage)
            .where(Usage.document_id == doc.id, Usage.step == "extract")
        )
        assert count == 1

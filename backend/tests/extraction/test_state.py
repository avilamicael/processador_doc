"""Transição de estado da extração (D-07) — marcador 'extraido', NUNCA CONCLUIDO.

Prova a correção crítica de estado da fase:
- sucesso → `state` permanece PROCESSANDO e `last_completed_step == "extraido"`;
- o documento NUNCA atinge CONCLUIDO na extração;
- a função `transition` NÃO é chamada com PROCESSANDO→PROCESSANDO (auto-laço fora
  da allowlist, `states.py`) — o stage avança SÓ o marcador interno em memória.
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app import config
from app.extraction import stage as stage_mod
from app.extraction.stage import EXTRACTED_STEP, extract_stage
from app.models import Document
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


async def test_sucesso_avanca_marcador_mantendo_processando(
    schema_engine: Engine, data_dir: Path, mock_openai
) -> None:
    """Sucesso: state==PROCESSANDO e last_completed_step=='extraido' (D-07)."""
    with get_session(schema_engine) as session:
        doc = _seed_text_pdf(session, data_dir)
        content_hash = doc.content_hash

    with get_session(schema_engine) as session:
        await extract_stage(session, content_hash=content_hash)

    with get_session(schema_engine) as session:
        reloaded = session.get(Document, doc.id)
        assert reloaded.state == DocState.PROCESSANDO
        assert reloaded.last_completed_step == EXTRACTED_STEP == "extraido"
        # Nunca CONCLUIDO na extração (D-07 — classificação/automação são fases adiante).
        assert reloaded.state != DocState.CONCLUIDO


async def test_nao_chama_transition_com_auto_laco(
    schema_engine: Engine,
    data_dir: Path,
    mock_openai,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O stage NÃO usa `transition` (PROCESSANDO→PROCESSANDO quebraria a allowlist).

    Espiona o módulo de stage: se ele importasse/chamasse `transition`, o sentinela
    abaixo registraria a chamada. Como o avanço é via marcador em memória + commit
    único, `transition` jamais é invocado no caminho de sucesso.
    """
    chamadas: list[tuple] = []

    def _spy_transition(session: Session, document, to_state, completed_step=None):
        chamadas.append((document.state, to_state))
        raise AssertionError(
            "extract_stage não deve chamar transition no sucesso "
            "(PROCESSANDO→PROCESSANDO é auto-laço inválido)."
        )

    # Patcha o símbolo no namespace do módulo de stage (caso fosse referenciado lá).
    monkeypatch.setattr(stage_mod, "transition", _spy_transition, raising=False)

    with get_session(schema_engine) as session:
        doc = _seed_text_pdf(session, data_dir)
        content_hash = doc.content_hash

    with get_session(schema_engine) as session:
        await extract_stage(session, content_hash=content_hash)

    assert chamadas == []  # transition nunca foi chamado

"""Dispatch bifurcado do worker por `step` + FALHA por content_hash (Plan 04, Task 1).

Prova o `<behavior>`:
- `step="ingest"` → caminho `to_thread` (`_process_job_blocking`) como na Fase 2,
  inalterado (a suíte `test_queue.py` continua verde — regressão coberta lá).
- `step="extract"` → `await extract_stage(session, content_hash=row.original_hash)`
  no loop (NÃO `to_thread`, NÃO `asyncio.run`): persiste a `Extraction` do bloco e
  marca o job `done`.
- falha de extract esgotando retries → o `Document` do bloco (achado por
  `content_hash`) vai a `DocState.FALHA` via `transition`; re-tentável; o original
  preservado (não tocamos `IngestedOriginal`).

A OpenAI é mockada via respx (`mock_openai`, conftest local) — 0 token. O blob é
gravado no CAS via `data_dir` temporário, espelhando o bloco que a Fase 2 deixa em
PROCESSANDO + last_completed_step='aguardando_extracao'.
"""

import asyncio
import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest
from sqlalchemy import Engine, select

from app import config
from app.models import DocState, Document, Extraction, Job, JobStatus, Usage
from app.queue import repo, worker
from app.storage import cas
from app.storage.db import get_session


@pytest.fixture(autouse=True)
def _openai_key(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chave OpenAI fictícia no env (respx mocka o transporte — 0 token).

    Depende de `data_dir` para que `DATA_DIR` e `OPENAI_API_KEY` coexistam antes de
    `get_settings` (cache limpo) recomputar — o stage lê ambos do Settings.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dispatch")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _seed_block(session, blob: bytes, data_dir: Path) -> Document:
    """Grava `blob` no CAS e cria o Document (bloco) terminal 'aguardando_extracao'."""
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
    session.commit()  # get_session só auto-commita com pendências no exit
    return doc


def _text_pdf() -> bytes:
    d = fitz.open()
    page = d.new_page()
    page.insert_text(
        (72, 72),
        "Nota Fiscal numero 12345 CNPJ 12.345.678/0001-90 Valor 1.234,56",
    )
    blob = d.tobytes()
    d.close()
    return blob


def test_dispatch_extract_chama_stage_e_marca_done(
    schema_engine: Engine, data_dir: Path, mock_openai
) -> None:
    """step='extract' → await extract_stage no loop; Extraction persistida; job done."""
    with get_session(schema_engine) as s:
        doc = _seed_block(s, _text_pdf(), data_dir)
        content_hash = doc.content_hash
        doc_id = doc.id

    # Job de extract: a "identidade do trabalho" é o content_hash do bloco (Pitfall 2).
    with get_session(schema_engine) as s:
        repo.enqueue(
            s,
            original_hash=content_hash,
            step="extract",
            payload=json.dumps({"content_hash": content_hash}),
        )

    processed = asyncio.run(worker._run_once(schema_engine))
    assert processed is True

    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == content_hash))
        assert job.status == JobStatus.DONE
        ext = s.scalar(select(Extraction).where(Extraction.document_id == doc_id))
        assert ext is not None
        assert ext.route == "native_text"
        usage = s.scalar(select(Usage).where(Usage.document_id == doc_id))
        assert usage is not None and usage.step == "extract"
        # estado terminal correto: PROCESSANDO + marcador 'extraido'
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.PROCESSANDO
        assert reloaded.last_completed_step == "extraido"

    # A OpenAI foi tocada exatamente uma vez (caminho async, não to_thread).
    assert mock_openai.calls.call_count == 1


def test_dispatch_extract_esgota_retries_leva_documento_a_falha(
    schema_engine: Engine, data_dir: Path, mock_openai, monkeypatch
) -> None:
    """extract falhando com retries esgotados → Document (por content_hash) a FALHA."""
    with get_session(schema_engine) as s:
        doc = _seed_block(s, _text_pdf(), data_dir)
        content_hash = doc.content_hash
        doc_id = doc.id

    # Força o stage a falhar (erro transitório) para exercitar o caminho de FALHA.
    async def _boom(session, *, content_hash):  # noqa: ANN001
        raise RuntimeError("falha simulada de extração")

    monkeypatch.setattr(worker, "extract_stage", _boom)

    with get_session(schema_engine) as s:
        repo.enqueue(
            s,
            original_hash=content_hash,
            step="extract",
            payload=json.dumps({"content_hash": content_hash}),
            max_attempts=1,  # esgota na 1ª tentativa
        )

    asyncio.run(worker._run_once(schema_engine))

    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == content_hash))
        assert job.status == JobStatus.FAILED
        # O Document do bloco (achado por content_hash) foi levado a FALHA.
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.FALHA


def test_dispatch_ingest_inalterado(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    """step='ingest' continua via to_thread (process_ingest); sem regressão."""
    from app.ingest.hashing import sha256_file

    import pikepdf

    src = tmp_path / "doc.pdf"
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.save(src)
    pdf.close()
    original_hash = sha256_file(src)

    with get_session(schema_engine) as s:
        repo.enqueue(
            s,
            original_hash=original_hash,
            step="ingest",
            payload=json.dumps(
                {
                    "source_path": str(src),
                    "folder_id": None,
                    "pages_per_block": None,
                }
            ),
        )

    processed = asyncio.run(worker._run_once(schema_engine))
    assert processed is True

    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == original_hash))
        assert job.status == JobStatus.DONE
        docs = s.scalars(select(Document)).all()
        assert len(docs) >= 1
        assert all(d.state == DocState.PROCESSANDO for d in docs)

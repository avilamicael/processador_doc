"""Watcher — caminho determinístico estabiliza→hash→gate→enqueue (Plano 02-04).

Prova o comportamento sem depender do timing do `awatch`: usa `scan_and_enqueue`
(o mesmo caminho usado no startup e no `/rescan`) sobre uma pasta temporária com
uma `WatchedFolder` ativa.

- 1ª varredura de um PDF novo cria UM Job `pending`.
- 2ª varredura do MESMO arquivo NÃO cria um segundo Job (gate de dedup: o original
  já está em `ingested_originals` via o enqueue? não — o enqueue não cria o
  original; o gate de dedup no watcher é a UNIQUE da fila). Aqui a 2ª passada bate
  na UNIQUE `(original_hash, ingest)` da fila → idempotência PROC-03, 0 enfileirados.

A janela de estabilização é encurtada via env para o teste rodar em <1s.
"""

import asyncio
from pathlib import Path

import pikepdf
import pytest
from sqlalchemy import Engine, func, select

from app import config
from app.ingest.watcher import scan_and_enqueue
from app.models.ingested_original import IngestedOriginal
from app.models.job import Job
from app.models.watched_folder import WatchedFolder
from app.storage.db import get_session


def _make_pdf(path: Path, pages: int = 2) -> Path:
    pdf = pikepdf.Pdf.new()
    for i in range(pages):
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pikepdf.Stream(
            pdf, f"BT /F1 12 Tf 20 100 Td (pagina {i}) Tj ET".encode()
        )
    pdf.save(path)
    pdf.close()
    return path


@pytest.fixture
def fast_stabilization(monkeypatch: pytest.MonkeyPatch) -> None:
    """Encurta a janela de estabilização para o scan rodar rápido no teste."""
    monkeypatch.setenv("STABILIZATION_WINDOW_SECONDS", "0.0")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _count_jobs(engine: Engine) -> int:
    with get_session(engine) as session:
        return session.scalar(select(func.count(Job.id))) or 0


def test_scan_enqueues_new_pdf(
    schema_engine: Engine, data_dir: Path, fast_stabilization: None, tmp_path: Path
) -> None:
    watched = tmp_path / "hot"
    watched.mkdir()
    _make_pdf(watched / "doc.pdf")

    with get_session(schema_engine) as session:
        session.add(WatchedFolder(path=str(watched.resolve()), pages_per_block=None, active=True))
        session.commit()

    enqueued = asyncio.run(scan_and_enqueue(schema_engine, [watched.resolve()]))

    assert enqueued == 1
    assert _count_jobs(schema_engine) == 1


def test_scan_is_idempotent(
    schema_engine: Engine, data_dir: Path, fast_stabilization: None, tmp_path: Path
) -> None:
    watched = tmp_path / "hot"
    watched.mkdir()
    _make_pdf(watched / "doc.pdf")

    with get_session(schema_engine) as session:
        session.add(WatchedFolder(path=str(watched.resolve()), pages_per_block=None, active=True))
        session.commit()

    first = asyncio.run(scan_and_enqueue(schema_engine, [watched.resolve()]))
    second = asyncio.run(scan_and_enqueue(schema_engine, [watched.resolve()]))

    assert first == 1
    assert second == 0  # mesmo arquivo não enfileira de novo (idempotência da fila)
    assert _count_jobs(schema_engine) == 1


def test_scan_increments_duplicate_hits_when_already_ingested(
    schema_engine: Engine, data_dir: Path, fast_stabilization: None, tmp_path: Path
) -> None:
    """Se o original já está em ingested_originals, re-varrer incrementa o contador."""
    from app.ingest.hashing import sha256_file

    watched = tmp_path / "hot"
    watched.mkdir()
    pdf = _make_pdf(watched / "doc.pdf")
    original_hash = sha256_file(pdf)

    with get_session(schema_engine) as session:
        session.add(WatchedFolder(path=str(watched.resolve()), pages_per_block=None, active=True))
        # Simula um original já ingerido (worker já processou).
        session.add(
            IngestedOriginal(
                original_hash=original_hash,
                original_filename="doc.pdf",
                source_folder_id=None,
                block_count=1,
            )
        )
        session.commit()

    enqueued = asyncio.run(scan_and_enqueue(schema_engine, [watched.resolve()]))

    assert enqueued == 0  # gate de dedup: não enfileira
    assert _count_jobs(schema_engine) == 0
    with get_session(schema_engine) as session:
        original = session.scalar(
            select(IngestedOriginal).where(IngestedOriginal.original_hash == original_hash)
        )
        assert original.duplicate_hits == 1


def test_run_watcher_and_app_import() -> None:
    """run_watcher/scan_and_enqueue e o app importam sem efeitos de rede."""
    from app.ingest.watcher import run_watcher, scan_and_enqueue  # noqa: F401
    from app.main import app  # noqa: F401

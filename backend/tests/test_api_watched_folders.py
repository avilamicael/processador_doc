"""API de pastas monitoradas — CRUD + validação de path (Plano 02-04 Task 2).

Usa `TestClient` sobre o app com `app.state.engine` sobrescrito por um engine de
teste com schema (D-10: create_all só em teste). Prova:
- POST cria (path normalizado/resolvido) + GET lista + PATCH edita + DELETE remove
- POST com path duplicado → 409 (UNIQUE do modelo)
- POST com path vazio/inválido → 422 (V5/V12 — T-02-10)
- DELETE de pasta NÃO apaga Documents (D-03 / SET NULL)
"""

import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

# TestClient (Starlette) emite um DeprecationWarning sobre httpx no ambiente atual;
# silenciado só para o import não poluir a saída do teste.
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.main import app
from app.models.document import Document
from app.models.ingested_original import IngestedOriginal
from app.models.watched_folder import WatchedFolder
from app.storage.db import get_session


@pytest.fixture
def client(schema_engine: Engine) -> Iterator[TestClient]:
    """TestClient com o engine de teste injetado em app.state.engine."""
    previous = getattr(app.state, "engine", None)
    app.state.engine = schema_engine
    # NÃO entra no `with TestClient` (que dispara o lifespan e subiria
    # watcher/worker reais); instancia direto para exercitar só as rotas.
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.state.engine = previous


def test_crud_lifecycle(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "hot"
    folder.mkdir()

    # POST cria
    resp = client.post("/watched-folders", json={"path": str(folder), "pages_per_block": 2})
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["path"] == str(folder.resolve())  # normalizado
    assert created["pages_per_block"] == 2
    assert created["active"] is True
    folder_id = created["id"]

    # GET lista
    resp = client.get("/watched-folders")
    assert resp.status_code == 200
    assert any(f["id"] == folder_id for f in resp.json())

    # PATCH edita
    resp = client.patch(f"/watched-folders/{folder_id}", json={"pages_per_block": 5, "active": False})
    assert resp.status_code == 200
    patched = resp.json()
    assert patched["pages_per_block"] == 5
    assert patched["active"] is False

    # DELETE remove
    resp = client.delete(f"/watched-folders/{folder_id}")
    assert resp.status_code == 204
    resp = client.get("/watched-folders")
    assert all(f["id"] != folder_id for f in resp.json())


def test_duplicate_path_returns_409(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "dup"
    folder.mkdir()
    first = client.post("/watched-folders", json={"path": str(folder)})
    assert first.status_code == 201
    second = client.post("/watched-folders", json={"path": str(folder)})
    assert second.status_code == 409, second.text


def test_empty_path_returns_422(client: TestClient) -> None:
    resp = client.post("/watched-folders", json={"path": "   "})
    assert resp.status_code == 422, resp.text


def test_relative_path_is_normalized(client: TestClient) -> None:
    """Path com '..' é resolvido (V5/V12) — barra path traversal acidental."""
    resp = client.post("/watched-folders", json={"path": "/tmp/foo/../bar"})
    assert resp.status_code == 201
    assert resp.json()["path"] == str(Path("/tmp/foo/../bar").resolve())
    assert ".." not in resp.json()["path"]


def test_delete_folder_preserves_documents(
    client: TestClient, schema_engine: Engine, tmp_path: Path
) -> None:
    folder = tmp_path / "keep"
    folder.mkdir()
    resp = client.post("/watched-folders", json={"path": str(folder)})
    folder_id = resp.json()["id"]

    # Semeia um original ligado à pasta + um Document ligado ao original.
    with get_session(schema_engine) as session:
        original = IngestedOriginal(
            original_hash="a" * 64,
            original_filename="x.pdf",
            source_folder_id=folder_id,
            block_count=1,
        )
        session.add(original)
        session.flush()
        doc = Document(
            content_hash="b" * 64,
            original_filename="x.pdf",
            origin_original_id=original.id,
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id

    # DELETE da pasta
    resp = client.delete(f"/watched-folders/{folder_id}")
    assert resp.status_code == 204

    # Document permanece (D-03); o vínculo da pasta foi SET NULL.
    with get_session(schema_engine) as session:
        survived = session.get(Document, doc_id)
        assert survived is not None
        original = session.scalar(
            select(IngestedOriginal).where(IngestedOriginal.original_hash == "a" * 64)
        )
        assert original is not None
        assert original.source_folder_id is None


def test_patch_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.patch("/watched-folders/999999", json={"active": False})
    assert resp.status_code == 404

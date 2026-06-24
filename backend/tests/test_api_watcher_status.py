"""API de status do watcher — GET /watcher/status (quick 260624-far).

Espelha o padrão de `test_api_documents.py`: `TestClient` sobre o app com
`app.state.engine` sobrescrito por um engine de teste com schema.

Prova:
- /watcher/status retorna {active, active_folder_count, last_scan_at}
- active_folder_count = nº de WatchedFolder com active=True (pasta inativa não conta)
- last_scan_at é null quando nunca houve varredura
- last_scan_at reflete o timestamp gravado em scan_and_enqueue (módulo watcher)
"""

import warnings
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from sqlalchemy import Engine

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.ingest import watcher
from app.main import app
from app.models.watched_folder import WatchedFolder
from app.storage.db import get_session


@pytest.fixture
def client(schema_engine: Engine) -> Iterator[TestClient]:
    previous = getattr(app.state, "engine", None)
    app.state.engine = schema_engine
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.state.engine = previous


@pytest.fixture(autouse=True)
def _reset_last_scan() -> Iterator[None]:
    """Garante isolamento do estado de módulo LAST_SCAN_AT entre testes."""
    watcher.LAST_SCAN_AT = None
    yield
    watcher.LAST_SCAN_AT = None


def test_status_shape_and_defaults(client: TestClient) -> None:
    resp = client.get("/watcher/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"active", "active_folder_count", "last_scan_at"}
    assert isinstance(body["active"], bool)
    assert body["active_folder_count"] == 0
    # Nunca varreu → null.
    assert body["last_scan_at"] is None


def test_active_folder_count_counts_only_active(
    client: TestClient, schema_engine: Engine
) -> None:
    with get_session(schema_engine) as session:
        session.add(WatchedFolder(path="/tmp/a", pages_per_block=None, active=True))
        session.add(WatchedFolder(path="/tmp/b", pages_per_block=None, active=True))
        session.add(WatchedFolder(path="/tmp/c", pages_per_block=None, active=False))
        session.commit()

    body = client.get("/watcher/status").json()
    assert body["active_folder_count"] == 2


def test_last_scan_at_reflects_module_timestamp(client: TestClient) -> None:
    ts = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)
    watcher.LAST_SCAN_AT = ts
    body = client.get("/watcher/status").json()
    assert body["last_scan_at"] is not None
    # ISO 8601 com a data esperada.
    assert body["last_scan_at"].startswith("2026-06-24T12:00:00")


def test_get_last_scan_at_helper() -> None:
    assert watcher.get_last_scan_at() is None
    ts = datetime(2026, 6, 24, 9, 30, 0, tzinfo=timezone.utc)
    watcher.LAST_SCAN_AT = ts
    assert watcher.get_last_scan_at() == ts

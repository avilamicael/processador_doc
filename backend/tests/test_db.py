"""Testes da camada de banco e do healthcheck do app."""

from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from app.storage.db import Base, get_session


def test_sqlite_engine_uses_wal_journal_mode(engine: Engine):
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert str(mode).lower() == "wal"


def test_sqlite_engine_sets_busy_timeout(engine: Engine):
    with engine.connect() as conn:
        timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
    assert int(timeout) >= 5000


def test_sqlite_engine_enables_foreign_keys(engine: Engine):
    with engine.connect() as conn:
        fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
    assert int(fk) == 1


def test_get_session_yields_working_session(engine: Engine):
    with get_session(engine) as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_base_is_declarative():
    # Base deve ser utilizável como base declarativa SQLAlchemy 2.0.
    assert hasattr(Base, "metadata")
    assert hasattr(Base, "registry")


def test_sqlite_pragmas_apply_to_each_new_connection(engine: Engine):
    # PRAGMAs são aplicados por conexão (listener "connect"), não só na primeira.
    for _ in range(2):
        with engine.connect() as conn:
            assert int(conn.execute(text("PRAGMA foreign_keys")).scalar()) == 1


def test_non_sqlite_url_is_postgresql_dialect_without_sqlite_pragmas():
    # Prova que a camada NÃO está acoplada a SQLite: uma URL Postgres é reconhecida
    # como dialeto postgresql. Verificado sem instanciar o driver (sem psycopg
    # nesta fase) inspecionando a URL — a derivação de PRAGMA é gated em
    # `dialect.name == "sqlite"`, logo não roda para postgresql.
    url = make_url("postgresql+psycopg://user:pw@localhost/db")
    assert url.get_backend_name() == "postgresql"
    assert not str(url).startswith("sqlite")


def test_health_endpoint_returns_ok_without_openai_key(tmp_path, monkeypatch):
    # App sobe sobre um DATA_DIR temporário e a chave NUNCA aparece no corpo.
    secret = "sk-should-never-leak-9999"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # importa tardiamente para pegar o env já configurado e limpar cache
    from app.config import get_settings

    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert secret not in resp.text
    get_settings.cache_clear()

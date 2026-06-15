"""Aplicação FastAPI — fundação que confirma o sistema subindo.

Responsabilidade nesta fase: subir o app, garantir a pasta de dados, abrir o
engine (aplicando WAL no SQLite) e expor `GET /health` que prova a fundação.
A chave OpenAI NUNCA é incluída em respostas (T-01-02).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app import __version__
from app.config import ensure_data_dir, get_settings
from app.storage.db import create_db_engine, get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa a fundação: pasta de dados + engine (WAL no SQLite)."""
    settings = get_settings()
    ensure_data_dir(settings)

    engine = create_db_engine(settings.effective_database_url)
    # Abre uma conexão de verificação; no SQLite confirma o modo WAL.
    with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert str(mode).lower() == "wal", f"WAL não habilitado (got {mode!r})"

    app.state.engine = engine
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title="Processador de Documentos",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Healthcheck: confirma que app e banco estão de pé.

    Nunca inclui a chave OpenAI nem qualquer segredo no corpo.
    """
    engine = app.state.engine
    with get_session(engine) as session:
        session.execute(text("SELECT 1")).scalar()
    return {"status": "ok", "db": "ok", "version": __version__}

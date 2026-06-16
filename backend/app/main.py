"""Aplicação FastAPI — fundação + ingestão de ponta a ponta.

Responsabilidade: subir o app, garantir a pasta de dados, abrir o engine
(aplicando WAL no SQLite), subir o **watcher** e o **worker** como `asyncio.Task`
no `lifespan` e encerrá-los limpo no shutdown, e expor `GET /health` + a API fina
(pastas monitoradas, documentos, rescan) que a UI consome.

A chave OpenAI NUNCA é incluída em respostas (T-01-02).

IMPORTANTE — 1 worker uvicorn (Pitfall 5 / T-02-12): o watcher e o worker sobem
como `asyncio.Task` UMA vez por PROCESSO neste `lifespan`. Rodar uvicorn com
múltiplos workers (`--workers N`, N>1) duplicaria watcher+worker, causando
processamento concorrente da mesma pasta e contenção de escrita no SQLite
single-writer. O modo padrão (Windows, single-tenant) DEVE rodar com
`uvicorn app.main:app --workers 1`.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app import __version__
from app.api import documents as documents_api
from app.api import templates as templates_api
from app.api import watched_folders as watched_folders_api
from app.config import ensure_data_dir, get_settings
from app.ingest.watcher import run_watcher
from app.queue.worker import run_worker
from app.storage.db import create_db_engine, get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa a fundação + sobe watcher/worker; encerra tudo limpo no shutdown.

    Ordem: pasta de dados → engine (WAL no SQLite) → `app.state.engine` → cria o
    `stop` Event e as tasks watcher/worker. No shutdown: seta `stop`, cancela as
    tasks, faz `gather(return_exceptions=True)` e só então descarta o engine.
    """
    settings = get_settings()
    ensure_data_dir(settings)

    engine = create_db_engine(settings.effective_database_url)
    # Abre uma conexão de verificação; no SQLite confirma o modo WAL.
    with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert str(mode).lower() == "wal", f"WAL não habilitado (got {mode!r})"

    app.state.engine = engine

    # Sobe watcher + worker como tasks do processo (1 worker uvicorn — Pitfall 5).
    # O mesmo `stop` Event encerra ambos limpo no shutdown.
    stop = asyncio.Event()
    app.state.stop_event = stop
    watcher_task = asyncio.create_task(run_watcher(engine, stop), name="watcher")
    worker_task = asyncio.create_task(run_worker(engine, stop), name="worker")
    app.state.background_tasks = (watcher_task, worker_task)

    try:
        yield
    finally:
        stop.set()
        for task in (watcher_task, worker_task):
            task.cancel()
        await asyncio.gather(watcher_task, worker_task, return_exceptions=True)
        engine.dispose()


app = FastAPI(
    title="Processador de Documentos",
    version=__version__,
    lifespan=lifespan,
)

# API fina consumida pela UI (Plano 05): CRUD de pastas + documentos/rescan.
app.include_router(watched_folders_api.router)
app.include_router(documents_api.router)
app.include_router(templates_api.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Healthcheck: confirma que app e banco estão de pé.

    Nunca inclui a chave OpenAI nem qualquer segredo no corpo.
    """
    engine = app.state.engine
    with get_session(engine) as session:
        session.execute(text("SELECT 1")).scalar()
    return {"status": "ok", "db": "ok", "version": __version__}

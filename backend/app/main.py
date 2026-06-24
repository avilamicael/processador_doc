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
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text

from app import __version__
from app.api import automations as automations_api
from app.api import config as config_api
from app.api import documents as documents_api
from app.api import templates as templates_api
from app.api import watched_folders as watched_folders_api
from app.api import watcher_status as watcher_status_api
from app.config import ensure_data_dir, get_settings
from app.ingest.watcher import run_watcher
from app.queue.worker import run_worker
from app.storage.db import create_db_engine, get_session

logger = logging.getLogger(__name__)

# Raiz do frontend buildado (Vite -> frontend/dist). Resolvido a partir do
# arquivo (NÃO do CWD): __file__ = backend/app/main.py, logo a raiz do repo é
# parents[2] e o dist é repo_root/frontend/dist. É git-ignored e pode não existir
# num checkout limpo — o serviço degrada (ver `_serve_frontend`).
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


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
app.include_router(config_api.router)
app.include_router(automations_api.router)
app.include_router(watcher_status_api.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Healthcheck: confirma que app e banco estão de pé.

    Nunca inclui a chave OpenAI nem qualquer segredo no corpo.
    """
    engine = app.state.engine
    with get_session(engine) as session:
        session.execute(text("SELECT 1")).scalar()
    return {"status": "ok", "db": "ok", "version": __version__}


if not FRONTEND_DIST.is_dir():
    # Caso comum em dev/CI e em checkout limpo (dist é git-ignored). NÃO crashar:
    # a API e o /health funcionam sem UI. Aviso acionável em PT-BR.
    logger.warning(
        "frontend/dist ausente em %s — UI não será servida; "
        "rode 'npm run build' no frontend para gerar o bundle.",
        FRONTEND_DIST,
    )


@app.get("/{full_path:path}")
def _serve_frontend(full_path: str) -> FileResponse:
    """Serve o frontend buildado (Vite) com fallback de SPA — registrado POR
    ÚLTIMO, depois de todos os routers e do /health.

    Por que catch-all em vez de `StaticFiles(html=True)` montado em "/":
    `html=True` só serve index.html na raiz e dá 404 em subcaminhos inexistentes,
    quebrando deep-links de SPA (ex.: GET /documentos). Aqui, como o handler é o
    último a registrar, o FastAPI casa as rotas de API (/documents, /templates,
    /health, ...) ANTES; este só pega o que sobra.

    Comportamento:
    - dist ausente            -> 404 (degradação aceitável; API segue de pé).
    - arquivo real dentro do dist (favicon, vite.svg, assets/*.js) -> serve o arquivo.
    - qualquer outro caminho  -> index.html (fallback SPA).

    Segurança: o caminho pedido é resolvido e confinado a dentro do dist
    (`is_relative_to`), rejeitando path traversal; fora do dist cai no index.html.
    `FRONTEND_DIST` é lido do módulo a cada requisição (não capturado em closure),
    para que testes possam apontar um dist temporário via monkeypatch.
    """
    dist = FRONTEND_DIST
    if not dist.is_dir():
        raise HTTPException(status_code=404, detail="frontend não disponível")

    index = dist / "index.html"
    candidate = (dist / full_path).resolve()
    dist_root = dist.resolve()
    # Arquivo real e CONFINADO ao dist -> serve o arquivo; senão -> fallback SPA.
    if (
        full_path
        and candidate.is_file()
        and candidate.is_relative_to(dist_root)
    ):
        return FileResponse(candidate)
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="index.html ausente no dist")

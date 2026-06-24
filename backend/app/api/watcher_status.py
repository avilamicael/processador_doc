"""API de status do watcher — GET /watcher/status (quick 260624-far).

Router fino que a Sidebar consome por polling para mostrar o estado REAL do
watcher (antes hardcoded "4 pastas · varredura há 2 min"):

- `active`: o watcher está vivo? Lido de `app.state.stop_event` (criado no
  `lifespan` de `main.py`): ativo = o Event NÃO está setado. Em testes (que não
  sobem o lifespan) o atributo pode não existir → fallback `True`.
- `active_folder_count`: nº de `WatchedFolder` com `active=True`.
- `last_scan_at`: timestamp (UTC) da última varredura concluída, lido do estado
  de módulo do watcher via `watcher.get_last_scan_at()` (atualizado ao final de
  `scan_and_enqueue`). `null` enquanto nenhuma varredura ocorreu.
"""

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from app.ingest import watcher
from app.models.watched_folder import WatchedFolder
from app.storage.db import get_session

router = APIRouter(tags=["watcher"])


class WatcherStatusOut(BaseModel):
    """Status real do watcher para a Sidebar."""

    active: bool
    active_folder_count: int
    last_scan_at: datetime | None


@router.get("/watcher/status", response_model=WatcherStatusOut)
def watcher_status(request: Request) -> WatcherStatusOut:
    """Estado real do watcher: ativo, nº de pastas ativas e última varredura."""
    # `active`: watcher vivo = stop_event existe e NÃO está setado. Sem o lifespan
    # (testes) o atributo não existe → fallback True.
    stop_event = getattr(request.app.state, "stop_event", None)
    active = True if stop_event is None else not stop_event.is_set()

    engine = request.app.state.engine
    with get_session(engine) as session:
        active_folder_count = session.scalar(
            select(func.count())
            .select_from(WatchedFolder)
            .where(WatchedFolder.active.is_(True))
        )

    return WatcherStatusOut(
        active=active,
        active_folder_count=int(active_folder_count or 0),
        last_scan_at=watcher.get_last_scan_at(),
    )

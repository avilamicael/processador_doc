"""API de pastas monitoradas — CRUD com validação de path (D-02 / T-02-10).

Router fino (`/watched-folders`) que a UI (Plano 05) usa para configurar as hot
folders: criar/listar/editar/remover pastas com `path`, `pages_per_block` (D-05,
`None` = "não separar") e `active`. As pastas vivem no banco (D-02); o watcher
(`ingest.watcher`) relê esta tabela.

VALIDAÇÃO DE PATH (T-02-10): no create/edit o `path` é **normalizado** com
`Path(path).resolve()` e rejeitado (HTTP 422) se vazio/em branco. `resolve()`
apenas canoniza o FORMATO (absolutiza, colapsa `..`/`.`) — NÃO confina a nenhuma
raiz permitida e, portanto, NÃO impede path traversal: um operador pode cadastrar
qualquer diretório do host. No v1 single-tenant local isso é por design — a pasta
monitorada é escolha do operador e não há allowlist de raízes; o confinamento de
raiz fica para um eventual modo servidor (multiusuário). Não confunda normalização
de formato com controle de acesso.

Endurecimento básico viável agora (T-02-10): se o path JÁ existe, ele precisa ser
um DIRETÓRIO (arquivo → 422) e NÃO pode ser um symlink (→ 422), para não seguir
um link como pasta monitorada (reduz a superfície de leitura fora da pasta —
relacionado a WR-03). Se o path ainda NÃO existe, o cadastro é permitido (a pasta
pode ser criada depois), sem alegação de segurança. A UNIQUE de `path` no modelo
impede duplicatas → `IntegrityError` vira HTTP 409.

DELETE remove só o monitoramento — NÃO apaga Documents (D-03): a FK
`ingested_originals.source_folder_id` é `ON DELETE SET NULL`, então o histórico
de originais/documentos sobrevive ao descadastro da pasta.
"""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.watched_folder import WatchedFolder
from app.storage.db import get_session

router = APIRouter(prefix="/watched-folders", tags=["watched-folders"])


def _normalize_path(raw: str) -> str:
    """Normaliza/valida um path de pasta (T-02-10).

    Rejeita (HTTP 422): vazio/branco; path que já existe e NÃO é diretório (ex.:
    arquivo); e symlinks (não seguimos um link como pasta monitorada). `resolve()`
    apenas canoniza o formato (absolutiza, colapsa `..`) — NÃO confina raiz nem
    barra path traversal; no v1 single-tenant a pasta é escolha do operador.
    Retorna a forma resolvida. Um path AINDA inexistente é aceito (a pasta pode
    ser criada depois) — sem alegação de segurança.
    """
    if raw is None or not str(raw).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="path da pasta não pode ser vazio",
        )

    source = Path(str(raw).strip())

    # Checagens no path NÃO-resolvido (antes do resolve, que seguiria o symlink):
    # rejeitar symlink reduz a superfície de leitura fora da pasta (WR-03). Se o
    # alvo existe e não é diretório (ex.: arquivo), também rejeitar.
    try:
        if source.is_symlink():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="path da pasta não pode ser um symlink",
            )
        if source.exists() and not source.is_dir():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="path da pasta precisa ser um diretório",
            )
        # strict=False: não exige que a pasta exista já; só normaliza o formato.
        return str(source.resolve())
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"path da pasta inválido: {raw!r}",
        ) from exc


class WatchedFolderIn(BaseModel):
    """Body de criação de pasta monitorada."""

    path: str
    pages_per_block: int | None = None
    active: bool = True

    @field_validator("pages_per_block")
    @classmethod
    def _non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("pages_per_block não pode ser negativo")
        return v


class WatchedFolderPatch(BaseModel):
    """Body de edição parcial de pasta monitorada (todos opcionais)."""

    path: str | None = None
    pages_per_block: int | None = None
    active: bool | None = None

    @field_validator("pages_per_block")
    @classmethod
    def _non_negative(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("pages_per_block não pode ser negativo")
        return v


class WatchedFolderOut(BaseModel):
    """Representação de resposta de uma pasta monitorada."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str
    pages_per_block: int | None
    active: bool
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[WatchedFolderOut])
def list_folders(request: Request) -> list[WatchedFolder]:
    """Lista todas as pastas monitoradas cadastradas."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        return list(session.scalars(select(WatchedFolder).order_by(WatchedFolder.id)).all())


@router.post("", response_model=WatchedFolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(request: Request, body: WatchedFolderIn) -> WatchedFolder:
    """Cria uma pasta monitorada com path normalizado/validado e único."""
    resolved = _normalize_path(body.path)
    engine = request.app.state.engine
    with get_session(engine) as session:
        folder = WatchedFolder(
            path=resolved,
            pages_per_block=body.pages_per_block,
            active=body.active,
        )
        session.add(folder)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"pasta já cadastrada: {resolved}",
            ) from exc
        session.refresh(folder)
        return folder


@router.patch("/{folder_id}", response_model=WatchedFolderOut)
def update_folder(request: Request, folder_id: int, body: WatchedFolderPatch) -> WatchedFolder:
    """Edita path/pages_per_block/active de uma pasta. Revalida path se mudado."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        folder = session.get(WatchedFolder, folder_id)
        if folder is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"pasta {folder_id} não encontrada",
            )
        if body.path is not None:
            folder.path = _normalize_path(body.path)
        if body.pages_per_block is not None:
            folder.pages_per_block = body.pages_per_block
        if body.active is not None:
            folder.active = body.active
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="pasta já cadastrada com este path",
            ) from exc
        session.refresh(folder)
        return folder


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(request: Request, folder_id: int) -> None:
    """Remove o monitoramento da pasta. NÃO apaga Documents (D-03, SET NULL)."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        folder = session.get(WatchedFolder, folder_id)
        if folder is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"pasta {folder_id} não encontrada",
            )
        session.delete(folder)
        session.commit()

"""API de pastas monitoradas — CRUD com validação de path (D-02 / T-02-10).

Router fino (`/watched-folders`) que a UI (Plano 05) usa para configurar as hot
folders: criar/listar/editar/remover pastas com `path`, `pages_per_block` (D-05,
`None` = "não separar") e `active`. As pastas vivem no banco (D-02); o watcher
(`ingest.watcher`) relê esta tabela.

VALIDAÇÃO DE PATH (Security V5/V12 — T-02-10): no create/edit o `path` é
**normalizado** com `Path(path).resolve()` e rejeitado (HTTP 422) se vazio/em
branco. Armazena-se a forma RESOLVIDA — barra path traversal acidental
(`..\\..\\Windows`) e quebras de parsing por caminhos relativos. No v1
single-tenant local a pasta é escolha do operador (não há allowlist de raízes),
mas o formato é sempre validado/normalizado. A UNIQUE de `path` no modelo impede
duplicatas → `IntegrityError` vira HTTP 409.

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
    """Normaliza/valida um path de pasta (V5/V12 — T-02-10).

    Rejeita vazio/branco (HTTP 422) e retorna a forma resolvida (absoluta,
    sem `..`). Não toca o filesystem além de resolver — a pasta pode ainda não
    existir no momento do cadastro.
    """
    if raw is None or not str(raw).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="path da pasta não pode ser vazio",
        )
    try:
        # strict=False: não exige que a pasta exista já; só normaliza o formato.
        return str(Path(str(raw).strip()).resolve())
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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

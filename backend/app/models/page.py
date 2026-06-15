"""Modelo `Page` — uma página de um `Document`.

Campos mínimos nesta fase (o conteúdo extraído por página vem em fases futuras —
separação na Fase 2, extração na Fase 3). Aqui só a estrutura e o vínculo ao
documento.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base

if TYPE_CHECKING:
    from app.models.document import Document


class Page(Base):
    """Página pertencente a um documento."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="pages")

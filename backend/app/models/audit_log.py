"""Modelo `AuditLog` — base write-ahead para auditoria/undo das automações.

Apenas a estrutura nesta fase. O uso write-ahead (registrar a intenção antes de
agir, para suportar desfazer) é da Fase 6 (T-01-08). `document_id` é nullable
para acomodar eventos não atrelados a um documento específico.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base

if TYPE_CHECKING:
    from app.models.document import Document


class AuditLog(Base):
    """Registro de auditoria de ações aplicadas (ou a aplicar) a documentos."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document | None"] = relationship(back_populates="audit_logs")

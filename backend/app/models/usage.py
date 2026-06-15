"""Modelo `Usage` — base da medição de consumo de IA por documento/etapa.

Apenas a estrutura nesta fase. A gravação real de tokens (lendo `response.usage`
da OpenAI) é da Fase 3, sustentando a cobrança por consumo (uma chave por
cliente). `step` indica a etapa que gerou o consumo.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base

if TYPE_CHECKING:
    from app.models.document import Document


class Usage(Base):
    """Consumo de tokens de IA atribuído a um documento e etapa."""

    __tablename__ = "usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    step: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="usages")

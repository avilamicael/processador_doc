"""Modelo `Extraction` — resultado bruto da extração genérica por bloco (Fase 3).

Persiste, por `Document` (bloco), o que a IA da OpenAI devolveu: os pares
`dado→valor` (serializados em JSON), o **texto integral** lido (`full_text`, base
das Fases 4/7 — D-06), o **palpite de tipo** com confiança, e o **caminho** usado
(`route`: texto nativo vs visão — métrica de custo D-04).

UNIQUE em `document_id` = **uma extração por bloco** = idempotência: um retry/crash
da fila não dispara nova chamada paga à IA para o mesmo bloco (evita cobrança
dupla — Pitfall 3 / Critical Failure Mode 3). Os tokens de cada chamada vão no
modelo `Usage` (step="extract"), não aqui.

Schema nasce e evolui SOMENTE via Alembic (migração 0003, D-10); nenhum
`create_all` em produção.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base

if TYPE_CHECKING:
    from app.models.document import Document


class Extraction(Base):
    """Resultado da extração de um bloco — pares + texto integral + palpite de tipo."""

    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # UNIQUE: 1 extração por bloco = idempotência (não re-extrair / não re-cobrar).
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        unique=True,
        nullable=False,
    )
    # list[ExtractedField] serializado em JSON (D-02/D-06). Schema genérico — sem
    # tipagem por campo (isso é Fase 4).
    fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Texto nativo/integral persistido (D-06) — base para as Fases 4/7 construírem
    # templates e atalhos locais.
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type_guess: Mapped[str] = mapped_column(String, nullable=False)
    doc_type_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # Caminho de extração: "native_text" | "vision" — métrica de custo (D-04).
    route: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="extraction")

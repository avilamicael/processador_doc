"""Modelo `IngestedOriginal` — gate de deduplicação PRÉ-split (D-08/D-09/D-10).

Antes de separar páginas, o pipeline registra o **arquivo original** pelo seu
`original_hash` (SHA-256). A coluna é `unique` — é exatamente o gate D-09: tentar
ingerir o mesmo original de novo viola a constraint e é detectado como duplicata,
sem reprocessar nem cobrar IA duas vezes (D-08). Cada acerto de duplicata
incrementa `duplicate_hits`, que alimenta o contador exposto na UI (D-10).

`block_count` registra quantos blocos/documentos o original gerou (vínculo
inverso de `documents.origin_original_id`). Schema evolui SOMENTE via Alembic
(D-10).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.db import Base


class IngestedOriginal(Base):
    """Original ingerido — gate de dedup por `original_hash` único (D-09)."""

    __tablename__ = "ingested_originals"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Hash SHA-256 (hex) do arquivo ORIGINAL (pré-split) — o gate de dedup (D-09).
    # Único global: o mesmo original não é reprocessado/cobrado duas vezes (D-08).
    original_hash: Mapped[str] = mapped_column(
        String(64), index=True, unique=True, nullable=False
    )

    original_filename: Mapped[str] = mapped_column(String, nullable=False)

    # Pasta de origem (D-02). Nullable + SET NULL: apagar a pasta não apaga o
    # histórico de originais já ingeridos dela.
    source_folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("watched_folders.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Quantos blocos/documentos este original gerou (inverso de
    # documents.origin_original_id).
    block_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # Contador de tentativas de re-ingestão do mesmo original — alimenta o
    # contador de duplicatas exibido na UI (D-10).
    duplicate_hits: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

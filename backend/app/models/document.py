"""Modelo `Document` — entidade central do domínio.

Persiste o **estado de topo** (`state`, D-04) e o **marcador interno de última
etapa concluída** (`last_completed_step`, D-05) que dá suporte a resume +
idempotência. Referencia o conteúdo no CAS por `content_hash` (D-07) — base de
deduplicação; a implementação do CAS é o Plan 04, aqui só a coluna.

`origin_original_id` (FK nullable → `ingested_originals`) vincula cada bloco ao
**original** do qual foi separado (D-09 / RESEARCH Open Question 1): permite
saber de qual arquivo de entrada um documento veio, mesmo após o split.

Schema nasce e evolui SOMENTE via Alembic (D-10); nenhum `create_all` em produção.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.enums import DocState
from app.storage.db import Base

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.extraction import Extraction
    from app.models.page import Page
    from app.models.usage import Usage


class Document(Base):
    """Documento ingerido — estado persistido + marcador interno de etapa."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Hash SHA-256 (hex) do conteúdo no CAS — base de dedup (D-07). Único: o mesmo
    # conteúdo não é reprocessado/cobrado duas vezes.
    content_hash: Mapped[str] = mapped_column(
        String(64), index=True, unique=True, nullable=False
    )

    original_filename: Mapped[str] = mapped_column(String, nullable=False)

    # Estado de topo (D-04). Persistido como string (valor do enum); default
    # RECEBIDO já na instância recém-criada.
    state: Mapped[DocState] = mapped_column(
        SAEnum(
            DocState,
            name="ck_documents_doc_state",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [member.value for member in enum],
            length=20,
        ),
        default=DocState.RECEBIDO,
        server_default=DocState.RECEBIDO.value,
        nullable=False,
    )

    # Marcador interno de "última etapa concluída" (D-05) — nullable; nenhuma
    # etapa concluída ainda quando o documento entra.
    last_completed_step: Mapped[str | None] = mapped_column(String, nullable=True)

    # Vínculo bloco→original (D-09 / RESEARCH Open Question 1). Nullable + SET
    # NULL: documentos podem existir sem original registrado, e apagar o original
    # não apaga os blocos.
    origin_original_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingested_originals.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    def __init__(self, **kwargs: object) -> None:
        # Garante o default D-04 já na instância recém-criada (antes do flush),
        # não só no INSERT — a UI/state machine lê `state` antes de persistir.
        kwargs.setdefault("state", DocState.RECEBIDO)
        super().__init__(**kwargs)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    pages: Mapped[list["Page"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    usages: Mapped[list["Usage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    # 1:1 (UNIQUE em extractions.document_id): no máximo uma extração por bloco.
    extraction: Mapped["Extraction | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )

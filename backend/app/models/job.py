"""Modelo `Job` — fila durável in-process sobre SQLite (PROC-02/PROC-03).

No modo padrão (Windows, single-tenant) NÃO há broker externo: a fila é uma
tabela SQLite consumida por um worker asyncio no próprio processo. Cada `Job`
descreve uma unidade de trabalho (`step`, ex.: "ingest") sobre um original
identificado por `original_hash`, com o `payload` (JSON) que o worker precisa.

**Idempotência (PROC-03):** o par `(original_hash, step)` é único
(`uq_jobs_hash_step`) — um mesmo original não enfileira trabalho duplicado para a
mesma etapa, mesmo sob re-emissão (rescan, retry).

**Retry com backoff (PROC-02):** `attempts`/`max_attempts` + `next_run_at`
(quando o job fica elegível para claim) suportam backoff exponencial; ao esgotar
as tentativas o `status` vai a `FAILED` (dead-letter). Schema evolui SOMENTE via
Alembic (D-10).
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import JobStatus
from app.storage.db import Base


class Job(Base):
    """Unidade de trabalho da fila durável (PROC-02/PROC-03)."""

    __tablename__ = "jobs"

    # PROC-03: (original_hash, step) é a chave de idempotência da fila.
    __table_args__ = (
        UniqueConstraint("original_hash", "step", name="uq_jobs_hash_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Hash SHA-256 (hex) do original ao qual este trabalho se refere.
    original_hash: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )

    # Etapa do pipeline que este job representa (ex.: "ingest").
    step: Mapped[str] = mapped_column(
        String, default="ingest", server_default="ingest", nullable=False
    )

    # JSON com o que o worker precisa (source_path, folder_id, pages_per_block...).
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Estado do job. Persistido como string (valor do enum) com CHECK constraint
    # — mesma forma de DocState (D-06): garantia de estado legal na fronteira do
    # storage, não só em Python.
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(
            JobStatus,
            name="ck_jobs_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum: [member.value for member in enum],
            length=10,
        ),
        default=JobStatus.PENDING,
        server_default=JobStatus.PENDING.value,
        nullable=False,
    )

    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=5, server_default="5", nullable=False
    )

    # Quando o job fica elegível para claim (backoff exponencial escreve aqui).
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __init__(self, **kwargs: object) -> None:
        # Garante o default de status (PROC-02) já na instância recém-criada,
        # antes do flush — o worker/fila leem `status` antes de persistir.
        kwargs.setdefault("status", JobStatus.PENDING)
        super().__init__(**kwargs)

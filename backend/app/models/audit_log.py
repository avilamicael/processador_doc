"""Modelo `AuditLog` — base write-ahead para auditoria/undo das automações.

A estrutura mínima nasceu na Fase 1; a Fase 6 a ESTENDE com as colunas do padrão
write-ahead (registrar a intenção ANTES de agir, para suportar desfazer):
`status` (intent/done/undone), `source_path`/`dest_path` (origem→destino do arquivo,
AUT-04), `run_id` (undo por-lote, AUT-05) e `content_hash` (undo via CAS, AUT-05).
`document_id` é nullable para acomodar eventos não atrelados a um documento específico.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base

if TYPE_CHECKING:
    from app.models.document import Document


# Prefixo do campo `details` dos AuditLog gravados pela materialização de split
# (split_to_files, quick 260623-pzy). Esses registros usam action="apply" mas NÃO
# são automações — são a gravação física do bloco na pasta. A idempotência do apply
# (`_has_done`) e o sweep de auto-apply (`enqueue_pending_applications`) DEVEM
# ignorá-los; senão um documento vindo de pasta com split nunca aplica sua automação
# (o audit "done" do split curto-circuita o apply real). Ver bug do deploy 2026-06-25.
SPLIT_MATERIALIZE_DETAILS_PREFIX = "split_to_files:"


class AuditLog(Base):
    """Registro de auditoria de ações aplicadas (ou a aplicar) a documentos."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Estado do registro write-ahead (AUT-04): "intent" (intenção persistida ANTES
    # de tocar o disco), "done" (operação física concluída) ou "undone"/"undone_from_cas"
    # (revertida pelo undo, AUT-05). server_default "done" preserva o significado
    # dos registros legados (criados antes desta coluna existir).
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="done"
    )
    # Caminho de ORIGEM do arquivo antes da automação (AUT-04) — necessário ao undo
    # para devolver o arquivo ao lugar original. nullable: eventos sem move físico.
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Caminho de DESTINO do arquivo após renomear/mover (AUT-04). nullable idem.
    dest_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Identificador do LOTE/execução (AUT-05): permite undo por-run (reverter tudo
    # que uma execução de automação aplicou de uma vez). nullable.
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Hash SHA-256 (hex) do conteúdo no CAS — base do undo via CAS (AUT-05): se o
    # destino sumiu/mudou, o arquivo é restaurado de `cas.read_bytes(content_hash)`.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document | None"] = relationship(back_populates="audit_logs")

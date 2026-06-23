"""Modelo `WatchedFolder` — pasta monitorada (hot folder) configurável (D-02).

No v1 a ingestão é **folder-only**: o cliente cadastra, pela interface, as pastas
a observar e a regra de separação por pasta. Cada `WatchedFolder` carrega o
caminho, a quantidade de páginas por bloco (`pages_per_block`, D-05) e se está
ativa. A configuração de pastas vive no banco (D-02), não em arquivo de config —
o watcher (plano posterior) lê desta tabela.

`pages_per_block = None` significa "não separar" (cada original vira um único
bloco) — é o default da UI. Schema evolui SOMENTE via Alembic (D-10).

`split_to_files` (opt-in, default DESLIGADO): quando LIGADO, ao ingerir um PDF
multipágina o sistema SEPARA o PDF em arquivos físicos NA PRÓPRIA PASTA,
substituindo o original pelos blocos (`<stem>_p1-2.pdf`, …) ANTES do pipeline de
IA. Materialização segura e reversível: o original já vai ao CAS antes do split
(rede de não-perda — CLAUDE.md) e só é removido do disco DEPOIS dos blocos
gravados e verificados por hash; cada gravação/remoção é registrada em AuditLog
write-ahead. Default OFF preserva o comportamento atual (nada gravado/removido).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.db import Base


class WatchedFolder(Base):
    """Pasta monitorada com sua regra de separação (D-02/D-05)."""

    __tablename__ = "watched_folders"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Caminho da pasta observada. Único: não cadastrar a mesma pasta duas vezes.
    path: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )

    # Páginas por bloco (D-05). None = "não separar" — default da UI; cada
    # original ingerido vira um único bloco/documento.
    pages_per_block: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Se a pasta está ativa para o watcher. Default True (servidor + ORM).
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1"), nullable=False
    )

    # Opt-in de separação física em arquivos na própria pasta (default OFF).
    # LIGADO: ao ingerir um PDF multipágina, o original é substituído pelos
    # blocos gravados na pasta (ANTES da IA), de forma reversível e sem perda
    # (original no CAS; remoção só após blocos verificados; AuditLog write-ahead).
    split_to_files: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )

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
        # Garante os defaults D-02/D-05 já na instância recém-criada (antes do
        # flush) — a UI/watcher leem `active`/`pages_per_block` antes de persistir.
        kwargs.setdefault("active", True)
        kwargs.setdefault("pages_per_block", None)
        kwargs.setdefault("split_to_files", False)
        super().__init__(**kwargs)

"""Modelos `ClassificationResult` + `FilledField` — o resultado de classificar um
bloco (Document) contra os templates do cliente (Fase 4).

`ClassificationResult` registra, por bloco, qual template casou e com que
confiança:
- `document_id` FK→documents **UNIQUE** (Pitfall 2): uma classificação por bloco
  = rede de banco contra double-charge (o stage no Plan 05 consome isto para não
  re-chamar/re-cobrar a IA de desempate);
- `template_id` FK→templates **nullable** com SET NULL: `null` = quarentena /
  não-casou (D-03), e apagar um template não apaga o histórico de classificação;
- `confidence` nullable — score do matcher local ou do desempate por IA.

Cada `FilledField` é um campo do template preenchido para aquele documento:
- `raw_value` (D-11 bruto) e `normalized_value` (D-11 normalizado — data/moeda/etc.);
- `valid` (D-10) marca se passou na validação (required/regex do TemplateField);
- `invalid_reason` opcional — motivo legível da falha de validação.

Schema nasce e evolui SOMENTE via Alembic (migração 0004, D-10); nenhum
`create_all` em produção.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base

if TYPE_CHECKING:
    from app.models.document import Document


class ClassificationResult(Base):
    """Resultado de classificar um bloco contra os templates — 1 por documento."""

    __tablename__ = "classification_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    # UNIQUE: 1 classificação por bloco = idempotência / rede contra double-charge
    # (Pitfall 2). Consumido pelo stage no Plan 05.
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        unique=True,
        nullable=False,
    )
    # Nullable + SET NULL: null = quarentena / não-casou (D-03); apagar um template
    # não apaga o histórico de classificação do documento.
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    # Score do matcher local ou do desempate por IA — nullable (quarentena = sem score).
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Score 0.0–1.0 de QUALIDADE DE EXTRAÇÃO (D-01: fração de obrigatórios válidos).
    # NÃO confundir com `confidence` (acima) = score do MATCHER/desempate (D-01 separa
    # qualidade de extração vs score do matcher). nullable: quarentena não tem score
    # (sem template = sem campos obrigatórios). Preenchido pelo roteamento do Plan 02.
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # 1:1 (UNIQUE em document_id): reverso em Document.classification.
    document: Mapped["Document"] = relationship(back_populates="classification")
    # 1:N — apagar a classificação apaga seus campos preenchidos.
    filled_fields: Mapped[list["FilledField"]] = relationship(
        back_populates="classification_result", cascade="all, delete-orphan"
    )


class FilledField(Base):
    """Campo do template preenchido para um documento — bruto/normalizado + validação."""

    __tablename__ = "filled_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    classification_result_id: Mapped[int] = mapped_column(
        ForeignKey("classification_results.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    # Valor bruto lido (D-11) — opcional (campo pode não ter sido encontrado).
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Valor normalizado (D-11) — data/moeda/cnpj normalizados; opcional.
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Marca de validade (D-10): passou na validação required/regex do TemplateField.
    valid: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    # Motivo legível da falha de validação — opcional.
    invalid_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # D-08: origem do valor marcada como corrigida manualmente (auditabilidade +
    # base do approve). default False (valor veio da IA/documento, não do humano).
    manually_corrected: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )

    classification_result: Mapped["ClassificationResult"] = relationship(
        back_populates="filled_fields"
    )

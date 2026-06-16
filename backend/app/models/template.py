"""Modelos `Template` + `TemplateField` — a configuração de classificação por tipo
de documento que o cliente monta no app (Fase 4, TPL-01).

Um `Template` representa um TIPO de documento (ex.: "Nota Fiscal", "Boleto") com:
- `name` único — rótulo do template no app;
- `doc_type` opcional — categoria livre (agrupar/automação futura);
- `signals_json` — lista de termos/chaves serializada em JSON: os **sinais
  identificadores** (D-02) que o matcher local usa para casar o documento contra
  este template sem custo de IA (palavras-âncora, regex de chave, etc.).

Cada `TemplateField` declara um **campo a extrair** do documento (TPL-01):
- `field_type` (D-08) — conjunto texto/numero/data/moeda/cpf_cnpj/booleano;
- `required` — campo obrigatório (alimenta a marca `valid` do FilledField, D-10);
- `regex` opcional (D-09) — validação determinística pós-extração;
- `hint` opcional — dica de extração passada à IA.

Schema nasce e evolui SOMENTE via Alembic (migração 0004, D-10); nenhum
`create_all` em produção. Um `Template` NÃO pertence a um `Document` — é
configuração reusável; não há relação reversa Template→Document.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base


class Template(Base):
    """Template de um tipo de documento — sinais identificadores + campos a extrair."""

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Rótulo do template; único no app (não há dois templates com o mesmo nome).
    name: Mapped[str] = mapped_column(String, index=True, unique=True, nullable=False)
    # Categoria livre opcional (agrupar/automação futura); não confundir com `name`.
    doc_type: Mapped[str | None] = mapped_column(String, nullable=True)
    # Lista de termos/chaves dos sinais identificadores (D-02) serializada em JSON.
    # O matcher local (Plan seguinte) consome isto para casar custo-zero.
    signals_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 1:N — apagar o template apaga seus campos (cascade delete-orphan).
    fields: Mapped[list["TemplateField"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class TemplateField(Base):
    """Campo a extrair de um documento — tipo (D-08), obrigatoriedade e validação (D-09)."""

    __tablename__ = "template_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Conjunto D-08: texto/numero/data/moeda/cpf_cnpj/booleano. Default "texto".
    field_type: Mapped[str] = mapped_column(
        String, default="texto", server_default="texto", nullable=False
    )
    # Campo obrigatório — alimenta a marca `valid` do FilledField (D-10).
    required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    # Validação determinística pós-extração (D-09) — opcional.
    regex: Mapped[str | None] = mapped_column(String, nullable=True)
    # Dica de extração passada à IA — opcional.
    hint: Mapped[str | None] = mapped_column(String, nullable=True)

    template: Mapped["Template"] = relationship(back_populates="fields")

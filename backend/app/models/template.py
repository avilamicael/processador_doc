"""Modelos `Template` + `TemplateField` — a configuração de classificação por tipo
de documento que o cliente monta no app (Fase 4, TPL-01).

Um `Template` representa um TIPO de documento (ex.: "Nota Fiscal", "Boleto") com:
- `name` único — rótulo do template no app;
- `doc_type` — coluna DORMENTE (D-T5): legado da Fase 4, removido do form do Plano 03;
  mantida no schema só por compat, sem migração de remoção (nenhuma feature a alimenta);
- `signals_json` — sinais identificadores como GRUPOS E/OU serializados em JSON (D-T2):
  lista de grupos; cada grupo é uma lista de condições `{mode, value}` com
  `mode ∈ {texto, regex}`. O matcher local (Plano 01) avalia OU entre grupos e E dentro
  do grupo para casar o documento contra este template sem custo de IA. A forma plana
  legada `list[str]` continua legível (forward-compatible em `_parse_groups`).

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
    # DORMENTE (D-T5): legado da Fase 4, fora do form do Plano 03. Mantida só por
    # compat — sem migração de remoção, nenhuma feature a alimenta.
    doc_type: Mapped[str | None] = mapped_column(String, nullable=True)
    # Sinais identificadores como GRUPOS E/OU (D-T2) serializados em JSON: lista de
    # grupos, cada grupo uma lista de condições {mode, value}. O matcher local
    # (Plano 01) avalia OU entre grupos e E dentro do grupo (custo zero).
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

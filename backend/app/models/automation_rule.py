"""Modelos `AutomationRule` + `RuleCondition` — regras condicionais de automação
que o cliente monta no app (Fase 6, TPL-02).

Uma `AutomationRule` expressa uma regra do tipo "SE estas condições casarem ENTÃO
renomeie/mova assim". Espelha a forma do par `Template` 1:N `TemplateField`:

- `priority` (Integer, indexado) — ordem de avaliação; a **primeira regra que casa
  vence** (D-05). Ordenável para reordenação na UI.
- `conjunction` — combinador entre as condições da MESMA regra: `"and"` (todas) ou
  `"or"` (qualquer uma) — D-04 (E/OU).
- `name_pattern` — padrão de renomeação com tokens `{campo}` (AUT-01); opcional.
- `folder_pattern` — padrão de pasta-destino com tokens `{campo}` (AUT-02); opcional.
- `active` — regra ligada/desligada sem apagá-la.

Cada `RuleCondition` é um teste `{field_name} {operator} {value}` (D-04):
- `operator` — um de `eq`/`gt`/`lt`/`contains` (mapeando `= > < contém`);
- `value` — o valor de comparação (string; coerção numérica via Decimal no avaliador);
- `position` — ordem da condição dentro da regra.

Schema nasce e evolui SOMENTE via Alembic (migração 0006, D-10); nenhum
`create_all` em produção. A LÓGICA de avaliação (dispatch por operador, coerção
numérica, precedência) é do Plan 02 — aqui só o schema.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base


class AutomationRule(Base):
    """Regra condicional de automação — condições → renomear/mover (TPL-02)."""

    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Ordem de avaliação (D-05): primeira regra que casa vence. Indexada para
    # ordenar/reordenar; não-única (várias regras podem compartilhar prioridade).
    priority: Mapped[int] = mapped_column(
        Integer, index=True, default=0, server_default="0", nullable=False
    )
    # Combinador E/OU entre as condições da regra (D-04). Default "and" (todas).
    conjunction: Mapped[str] = mapped_column(
        String, default="and", server_default="and", nullable=False
    )
    # Padrão de renomeação com tokens {campo} (AUT-01) — opcional.
    name_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Padrão de pasta-destino com tokens {campo} (AUT-02) — opcional.
    folder_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Regra ligada/desligada sem apagar (default ligada).
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
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

    # 1:N — apagar a regra apaga suas condições (cascade delete-orphan), igual a
    # Template.fields.
    conditions: Mapped[list["RuleCondition"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )


class RuleCondition(Base):
    """Condição `{campo} {operador} {valor}` de uma regra (D-04)."""

    __tablename__ = "rule_conditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Nome do campo extraído a comparar (ex.: "valor", "cliente").
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    # Operador D-04: eq (=) / gt (>) / lt (<) / contains (contém). O avaliador
    # (Plan 02) despacha por este rótulo; nunca `eval`.
    operator: Mapped[str] = mapped_column(String, nullable=False)
    # Valor de comparação (string; coerção numérica via Decimal no avaliador).
    value: Mapped[str] = mapped_column(String, nullable=False)
    # Ordem da condição dentro da regra.
    position: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    rule: Mapped["AutomationRule"] = relationship(back_populates="conditions")

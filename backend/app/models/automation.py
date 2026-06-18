"""Modelos `Automation` + `AutomationCondition` + `AutomationAction` — o MODELO
FINAL aprovado da Fase 6 (D-23..D-26).

SUBSTITUI o modelo de "pipeline de etapas com filtros por etapa + gates"
(`automation_pipelines`/`pipeline_steps`/`step_filters`, 0007). O modelo final é
muito mais simples e direto, espelhando o mockup v3 aprovado:

    VÁRIAS automações nomeadas. Cada automação =
        CONDIÇÕES (quando rodar, combinadas por E)  →
        AÇÕES (o que fazer, ordenadas: rename/move).

- **D-23/D-24:** existem N `Automation` nomeadas; cada uma tem `name`, `active`,
  `position` (prioridade/ordem entre automações), 0..N condições e 0..N ações.
- **D-24 (condições):** `AutomationCondition` no NÍVEL da automação, combinadas por
  E (AND). `field` ∈ {source_folder, extension, template, field, filename, size};
  `operator` ∈ {eq, contains, gt, lt}; `value`; `field_name` só quando
  `field="field"` (qual campo extraído comparar). A pasta de origem é só mais uma
  condição — a automação NÃO é atrelada a uma pasta.
- **D-24 (ações):** `AutomationAction` ordenada por `position` (drag-and-drop +
  ↑/↓). `action_type` ∈ {rename, move}; `params_json` carrega `name_pattern`
  (rename) ou `dest_folder` (move). "Rotear/decidir tratativa" continua FORA do v1
  (D-22) — não há `action_type` route aqui.
- **D-25 (resolução entre automações):** o executor (stage) avalia as automações
  ATIVAS por ordem de `position`; a PRIMEIRA cujas TODAS as condições casam executa
  suas ações; as demais NÃO rodam para esse documento.

A forma espelha o par já provado `Template` 1:N `TemplateField` (cascade
delete-orphan + FK ondelete CASCADE). A LÓGICA (avaliar condições, despachar ações,
resolver plano-alvo, materializar do CAS) é do executor/stage — AQUI só o schema. O
schema nasce e evolui SOMENTE via Alembic (migração 0008); nenhum `create_all` em
produção.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base


class Automation(Base):
    """Automação nomeada — CONDIÇÕES (E) → AÇÕES ordenadas (D-23/D-24)."""

    __tablename__ = "automations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Ligada/pausada sem apagar (Switch da UI; default ligada).
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    # Prioridade/ORDEM entre automações (D-25): menor `position` é avaliada antes.
    # A primeira cujas condições TODAS casam vence. Indexada para ordenar na UI.
    position: Mapped[int] = mapped_column(
        Integer, index=True, default=0, server_default="0", nullable=False
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

    # 1:N — apagar a automação apaga suas condições e ações (cascade delete-orphan),
    # igual a Template.fields.
    conditions: Mapped[list["AutomationCondition"]] = relationship(
        back_populates="automation", cascade="all, delete-orphan"
    )
    actions: Mapped[list["AutomationAction"]] = relationship(
        back_populates="automation", cascade="all, delete-orphan"
    )


class AutomationCondition(Base):
    """Condição no NÍVEL da automação — `{field} {operator} {value}` (D-24).

    Todas as condições de uma automação combinam por E (AND): a automação só roda
    quando TODAS casam. `field_name` só é usado quando `field == "field"` (qual
    campo extraído do documento comparar).
    """

    __tablename__ = "automation_conditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(
        ForeignKey("automations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Dimensão a comparar (D-24): "source_folder" | "extension" | "template" |
    # "field" | "filename" | "size".
    field: Mapped[str] = mapped_column(String, nullable=False)
    # Operador (D-24): "eq" ('é') | "contains" ('contém') | "gt" ('>') | "lt" ('<').
    operator: Mapped[str] = mapped_column(String, nullable=False)
    # Valor de comparação (string; coerção numérica no avaliador, sem eval).
    value: Mapped[str] = mapped_column(String, nullable=False)
    # Só para field="field": qual campo extraído comparar.
    field_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Ordem da condição na automação (cosmético — todas combinam por E).
    position: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    automation: Mapped["Automation"] = relationship(back_populates="conditions")


class AutomationAction(Base):
    """Ação ordenada de uma automação — rename/move (D-24).

    `params_json` carrega os parâmetros da ação:
      rename → {"name_pattern": "{cliente}_{numero}"}
      move   → {"dest_folder": "Documentos/{cliente}/{data:aaaa-mm}"}
    A ORDEM (`position`) vem do drag-and-drop/↑↓ da UI. Rename compõe o NOME-alvo,
    Move compõe a PASTA-alvo; a materialização do CAS é ÚNICA no fim (D-26).
    """

    __tablename__ = "automation_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(
        ForeignKey("automations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Ordem de execução da ação na automação (D-24). Indexada para ordenar na UI.
    position: Mapped[int] = mapped_column(
        Integer, index=True, default=0, server_default="0", nullable=False
    )
    # Tipo da ação (D-24): "rename" | "move". O executor despacha por este rótulo;
    # nunca `eval`. (Não há "route" no v1 — D-22.)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    # Parâmetros serializados em JSON (rename→name_pattern; move→dest_folder).
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    automation: Mapped["Automation"] = relationship(back_populates="actions")

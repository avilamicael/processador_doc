"""Modelos `AutomationPipeline` + `PipelineStep` + `StepFilter` — o PIPELINE
ordenado de etapas componíveis que o cliente monta no app (Fase 6, REDESIGN
D-12..D-16, TPL-02/AUT-01/AUT-02).

Substitui o modelo anterior de "regra única" (`automation_rules`/`rule_conditions`,
0006). Em vez de UMA regra "SE condições ENTÃO renomeie+mova", o cliente compõe
uma LISTA ORDENADA de etapas, cada etapa com 0..N filtros de entrada e UMA ação
atômica. A forma espelha exatamente o par já provado `Template` 1:N `TemplateField`
(cascade delete-orphan + FK ondelete CASCADE).

- D-12 (ordem): `PipelineStep.position` (Integer, indexado) define a ORDEM de
  execução das etapas dentro do pipeline. O executor (06-07) itera os steps
  ordenados por `position`.
- D-13 (1 filtro + 1 ação por etapa): cada `PipelineStep` carrega 0..N
  `StepFilter` (a condição de entrada) e UMA `action_type` atômica
  (`move`/`rename`/`identify_type`/`route`) com seus `params_json`.
- D-14 (filtros componíveis): cada `StepFilter` é um teste
  `{filter_type}/{operator}/{value}` (+ `field_name` quando `filter_type="field"`);
  `PipelineStep.conjunction` (`and`/`or`) combina os filtros da MESMA etapa.

`PipelineStep.active` permite ligar/pausar a etapa (Switch da UI) sem apagá-la.

A LÓGICA do pipeline (avaliação de filtros, dispatch de ações, resolução de
plano-alvo, write-ahead) é do executor (06-07) — AQUI só o schema. O schema nasce
e evolui SOMENTE via Alembic (migração 0007, D-10); nenhum `create_all` em
produção.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.db import Base


class AutomationPipeline(Base):
    """Pipeline de automação — lista ORDENADA de etapas componíveis (D-12)."""

    __tablename__ = "automation_pipelines"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Pipeline ligado/desligado sem apagar (default ligado).
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

    # 1:N — apagar o pipeline apaga suas etapas (e, em cascata, os filtros das
    # etapas), igual a Template.fields.
    steps: Mapped[list["PipelineStep"]] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan"
    )


class PipelineStep(Base):
    """Etapa do pipeline — 0..N filtros de entrada + UMA ação atômica (D-13)."""

    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(
        ForeignKey("automation_pipelines.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Ordem de execução da etapa dentro do pipeline (D-12). Indexada para
    # ordenar/reordenar na UI.
    position: Mapped[int] = mapped_column(
        Integer, index=True, default=0, server_default="0", nullable=False
    )
    # Ação atômica da etapa (D-13): "move" | "rename" | "identify_type" | "route".
    # O executor (06-07) despacha por este rótulo; nunca `eval`.
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    # Combinador E/OU entre os filtros da MESMA etapa (D-14). Default "and".
    conjunction: Mapped[str] = mapped_column(
        String, default="and", server_default="and", nullable=False
    )
    # Parâmetros da ação serializados em JSON (D-13):
    #   {"folder_pattern": ...} | {"name_pattern": ...}
    #   | {"template_id": N} | {"target": "em_revisao"|"nao_tratar"|"ignorar"}
    params_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Etapa ligada/pausada (Switch da UI) sem apagar.
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )

    pipeline: Mapped["AutomationPipeline"] = relationship(back_populates="steps")
    # 1:N — apagar a etapa apaga seus filtros (cascade delete-orphan).
    filters: Mapped[list["StepFilter"]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )


class StepFilter(Base):
    """Filtro de entrada de uma etapa — `{filter_type} {operator} {value}` (D-14)."""

    __tablename__ = "step_filters"

    id: Mapped[int] = mapped_column(primary_key=True)
    step_id: Mapped[int] = mapped_column(
        ForeignKey("pipeline_steps.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Tipo do filtro (D-14): "field" | "source_folder" | "extension" |
    # "filename" | "size" | "template".
    filter_type: Mapped[str] = mapped_column(String, nullable=False)
    # Operador (reusa o vocabulário de rules.py): eq | gt | lt | contains.
    operator: Mapped[str] = mapped_column(String, nullable=False)
    # Valor de comparação (string; coerção numérica no avaliador, 06-07).
    value: Mapped[str] = mapped_column(String, nullable=False)
    # Só para filter_type="field": qual campo extraído comparar.
    field_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Ordem do filtro dentro da etapa.
    position: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    step: Mapped["PipelineStep"] = relationship(back_populates="filters")

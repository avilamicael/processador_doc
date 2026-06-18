"""Testes do modelo de pipeline — `AutomationPipeline` 1:N `PipelineStep` 1:N
`StepFilter` (Fase 6 REDESIGN, D-12..D-14).

Provam o contrato de schema que o executor (06-07) e a API (06-08) assumem:
- ordem das etapas preservada por `position` (D-12);
- cascade delete-orphan em ambos os níveis (apagar o pipeline apaga steps e
  filters), igual a `Template`→`TemplateField`;
- FK ondelete CASCADE no banco (apagar o pipeline via SQL apaga as filhas).

Usa a fixture `schema_engine` do conftest raiz (create_all em SQLite temporário).
"""

from sqlalchemy import Engine, func, select

from app.models.automation_pipeline import (
    AutomationPipeline,
    PipelineStep,
    StepFilter,
)
from app.storage.db import get_session


def test_pipeline_preserva_ordem_dos_steps(schema_engine: Engine) -> None:
    """D-12: as etapas são uma LISTA ORDENADA — `position` é persistido e usado
    para reler as etapas na ordem de execução."""
    with get_session(schema_engine) as session:
        pipeline = AutomationPipeline(name="P1")
        pipeline.steps = [
            PipelineStep(position=0, action_type="identify_type"),
            PipelineStep(position=1, action_type="rename"),
            PipelineStep(position=2, action_type="move"),
        ]
        session.add(pipeline)
        session.commit()
        pid = pipeline.id

    with get_session(schema_engine) as session:
        steps = session.scalars(
            select(PipelineStep)
            .where(PipelineStep.pipeline_id == pid)
            .order_by(PipelineStep.position)
        ).all()
        assert [s.position for s in steps] == [0, 1, 2]
        assert [s.action_type for s in steps] == ["identify_type", "rename", "move"]


def test_step_carrega_filtros(schema_engine: Engine) -> None:
    """D-14: cada etapa carrega 0..N filtros componíveis; `conjunction` combina
    os filtros da MESMA etapa."""
    with get_session(schema_engine) as session:
        pipeline = AutomationPipeline(name="P2")
        step = PipelineStep(position=0, action_type="rename", conjunction="or")
        step.filters = [
            StepFilter(
                filter_type="field",
                field_name="cliente",
                operator="eq",
                value="ACME Ltda",
            ),
            StepFilter(filter_type="extension", operator="eq", value=".pdf"),
        ]
        pipeline.steps = [step]
        session.add(pipeline)
        session.commit()
        sid = step.id

    with get_session(schema_engine) as session:
        step = session.get(PipelineStep, sid)
        assert step is not None
        assert step.conjunction == "or"
        assert {f.filter_type for f in step.filters} == {"field", "extension"}


def test_cascade_orm_apaga_steps_e_filtros(schema_engine: Engine) -> None:
    """Cascade delete-orphan (ORM): apagar o pipeline via sessão remove suas
    etapas E os filtros das etapas — igual a `Template`→`TemplateField`."""
    with get_session(schema_engine) as session:
        pipeline = AutomationPipeline(name="P3")
        step = PipelineStep(position=0, action_type="rename")
        step.filters = [
            StepFilter(filter_type="extension", operator="eq", value=".pdf"),
            StepFilter(filter_type="size", operator="gt", value="1000"),
        ]
        pipeline.steps = [step]
        session.add(pipeline)
        session.commit()
        pid = pipeline.id

    with get_session(schema_engine) as session:
        pipeline = session.get(AutomationPipeline, pid)
        assert pipeline is not None
        session.delete(pipeline)
        session.commit()

    with get_session(schema_engine) as session:
        n_pipelines = session.scalar(select(func.count()).select_from(AutomationPipeline))
        n_steps = session.scalar(select(func.count()).select_from(PipelineStep))
        n_filters = session.scalar(select(func.count()).select_from(StepFilter))
        assert n_pipelines == 0
        assert n_steps == 0, "steps órfãos após apagar o pipeline (cascade falhou)"
        assert n_filters == 0, "filtros órfãos após apagar a etapa (cascade falhou)"


def test_fk_ondelete_cascade_no_banco(schema_engine: Engine) -> None:
    """FK ondelete=CASCADE: apagar o pipeline via DELETE (sem o ORM carregar as
    filhas) remove steps e filters no nível do banco. Exige PRAGMA
    foreign_keys=ON (aplicado por `create_db_engine`)."""
    with get_session(schema_engine) as session:
        pipeline = AutomationPipeline(name="P4")
        step = PipelineStep(position=0, action_type="move")
        step.filters = [StepFilter(filter_type="template", operator="eq", value="1")]
        pipeline.steps = [step]
        session.add(pipeline)
        session.commit()
        pid = pipeline.id

    # DELETE direto na pai — sem o ORM iterar as filhas; depende do CASCADE do banco.
    with get_session(schema_engine) as session:
        pipeline = session.get(AutomationPipeline, pid)
        assert pipeline is not None
        session.execute(
            AutomationPipeline.__table__.delete().where(
                AutomationPipeline.id == pid
            )
        )
        session.commit()

    with get_session(schema_engine) as session:
        n_steps = session.scalar(
            select(func.count())
            .select_from(PipelineStep)
            .where(PipelineStep.pipeline_id == pid)
        )
        n_filters = session.scalar(select(func.count()).select_from(StepFilter))
        assert n_steps == 0, "steps não removidos pelo FK CASCADE do banco"
        assert n_filters == 0, "filters não removidos pelo FK CASCADE (cadeia)"

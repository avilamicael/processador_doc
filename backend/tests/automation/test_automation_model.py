"""Testes do modelo de automação — `Automation` 1:N `AutomationCondition` +
`Automation` 1:N `AutomationAction` (Fase 6 MODELO FINAL, D-23..D-24).

Provam o contrato de schema que o executor (stage) e a API assumem:
- ordem das ações preservada por `position` (D-24);
- ordem entre automações por `position` (D-25);
- cascade delete-orphan em ambas as filhas (apagar a automação apaga condições e
  ações), igual a `Template`→`TemplateField`;
- FK ondelete CASCADE no banco (apagar a automação via SQL apaga as filhas).

Usa a fixture `schema_engine` do conftest raiz (create_all em SQLite temporário).
"""

from sqlalchemy import Engine, func, select

from app.models.automation import (
    Automation,
    AutomationAction,
    AutomationCondition,
)
from app.storage.db import get_session


def test_automation_preserva_ordem_das_acoes(schema_engine: Engine) -> None:
    """D-24: as ações são uma LISTA ORDENADA — `position` é persistido e usado para
    reler as ações na ordem de execução."""
    with get_session(schema_engine) as session:
        automation = Automation(name="A1")
        automation.actions = [
            AutomationAction(position=0, action_type="rename"),
            AutomationAction(position=1, action_type="move"),
        ]
        session.add(automation)
        session.commit()
        aid = automation.id

    with get_session(schema_engine) as session:
        actions = session.scalars(
            select(AutomationAction)
            .where(AutomationAction.automation_id == aid)
            .order_by(AutomationAction.position)
        ).all()
        assert [a.position for a in actions] == [0, 1]
        assert [a.action_type for a in actions] == ["rename", "move"]


def test_automation_carrega_condicoes(schema_engine: Engine) -> None:
    """D-24: cada automação carrega 0..N condições combinadas por E (AND)."""
    with get_session(schema_engine) as session:
        automation = Automation(name="A2")
        automation.conditions = [
            AutomationCondition(
                field="field", field_name="cliente", operator="eq", value="ACME Ltda"
            ),
            AutomationCondition(field="extension", operator="eq", value=".pdf"),
        ]
        session.add(automation)
        session.commit()
        aid = automation.id

    with get_session(schema_engine) as session:
        automation = session.get(Automation, aid)
        assert automation is not None
        assert {c.field for c in automation.conditions} == {"field", "extension"}


def test_automations_ordenadas_por_position(schema_engine: Engine) -> None:
    """D-25: as automações têm `position` (prioridade/ordem) — a primeira que casa
    vence; a UI/executor ordena por ela."""
    with get_session(schema_engine) as session:
        session.add(Automation(name="Específica", position=0))
        session.add(Automation(name="Genérica", position=1))
        session.commit()

    with get_session(schema_engine) as session:
        names = [
            a.name
            for a in session.scalars(
                select(Automation).order_by(Automation.position)
            ).all()
        ]
        assert names == ["Específica", "Genérica"]


def test_cascade_orm_apaga_condicoes_e_acoes(schema_engine: Engine) -> None:
    """Cascade delete-orphan (ORM): apagar a automação via sessão remove suas
    condições E ações — igual a `Template`→`TemplateField`."""
    with get_session(schema_engine) as session:
        automation = Automation(name="A3")
        automation.conditions = [
            AutomationCondition(field="extension", operator="eq", value=".pdf"),
            AutomationCondition(field="size", operator="gt", value="1000"),
        ]
        automation.actions = [
            AutomationAction(position=0, action_type="move"),
        ]
        session.add(automation)
        session.commit()
        aid = automation.id

    with get_session(schema_engine) as session:
        automation = session.get(Automation, aid)
        assert automation is not None
        session.delete(automation)
        session.commit()

    with get_session(schema_engine) as session:
        n_auto = session.scalar(select(func.count()).select_from(Automation))
        n_cond = session.scalar(select(func.count()).select_from(AutomationCondition))
        n_act = session.scalar(select(func.count()).select_from(AutomationAction))
        assert n_auto == 0
        assert n_cond == 0, "condições órfãs após apagar a automação (cascade falhou)"
        assert n_act == 0, "ações órfãs após apagar a automação (cascade falhou)"


def test_fk_ondelete_cascade_no_banco(schema_engine: Engine) -> None:
    """FK ondelete=CASCADE: apagar a automação via DELETE (sem o ORM carregar as
    filhas) remove condições e ações no nível do banco. Exige PRAGMA
    foreign_keys=ON (aplicado por `create_db_engine`)."""
    with get_session(schema_engine) as session:
        automation = Automation(name="A4")
        automation.conditions = [
            AutomationCondition(field="template", operator="eq", value="1")
        ]
        automation.actions = [AutomationAction(position=0, action_type="move")]
        session.add(automation)
        session.commit()
        aid = automation.id

    # DELETE direto na pai — sem o ORM iterar as filhas; depende do CASCADE do banco.
    with get_session(schema_engine) as session:
        session.execute(
            Automation.__table__.delete().where(Automation.id == aid)
        )
        session.commit()

    with get_session(schema_engine) as session:
        n_cond = session.scalar(
            select(func.count())
            .select_from(AutomationCondition)
            .where(AutomationCondition.automation_id == aid)
        )
        n_act = session.scalar(
            select(func.count())
            .select_from(AutomationAction)
            .where(AutomationAction.automation_id == aid)
        )
        assert n_cond == 0, "condições não removidas pelo FK CASCADE do banco"
        assert n_act == 0, "ações não removidas pelo FK CASCADE do banco"

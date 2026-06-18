"""Executor PURO das automações (`app.automation.executor`) + condições (D-24).

Fonte de verdade da API pública do executor do MODELO FINAL (D-23..D-26). Cobre:
- condições (D-24): cada `field` casa/não-casa; combinadas por E (AND);
- ordem entre automações (D-25): a PRIMEIRA cujas condições casam vence;
- ações (D-24): rename muta só o nome; move muta só a pasta; ordem por position;
- order-independent: [move,rename] == [rename,move] (folder/name independentes);
- blocked (D-07): token p/ campo faltante → blocked;
- no-match (D-25): nenhuma automação casa → matched=False, plano = default.

Executor é PURO (sem disco, sem ORM): recebe specs puros + fields + file_attrs.
"""

from pathlib import Path

from app.automation import rules
from app.automation.executor import (
    ActionSpec,
    AutomationSpec,
    evaluate_automations,
)

# ---- helpers de montagem dos specs puros ---------------------------------- #


def _cond(field, operator, value, field_name=None):
    return rules.ConditionSpec(
        field=field, operator=operator, value=value, field_name=field_name
    )


def _action(action_type, *, position=0, params=None):
    return ActionSpec(position=position, action_type=action_type, params=params or {})


def _auto(*, position=0, conditions=None, actions=None, active=True, automation_id=None):
    return AutomationSpec(
        position=position,
        conditions=conditions or [],
        actions=actions or [],
        active=active,
        automation_id=automation_id,
    )


FIELDS = {
    "cliente": "ACME Ltda",
    "numero": "1234",
    "valor": "1500.00",
    "data": "2026-06-17",
}

ATTRS = {
    "ext": ".pdf",
    "size": 120_000,
    "source_folder_id": 7,
    "source_folder": "Downloads",
    "original_filename": "entrada.pdf",
    "template_id": None,
}

BASE = Path("/tmp/organizados")


# ---- condições (D-24) ------------------------------------------------------ #


def test_condition_field_match():
    c = _cond("field", "eq", "ACME Ltda", field_name="cliente")
    assert rules.automation_conditions_match([c], FIELDS, ATTRS, None) is True


def test_condition_field_no_match():
    c = _cond("field", "eq", "Outra", field_name="cliente")
    assert rules.automation_conditions_match([c], FIELDS, ATTRS, None) is False


def test_condition_extension_case_and_dot_insensitive():
    # D-24: extensão digitada (.PDF / PDF / .pdf) casa case/dot-insensitive.
    for value in (".PDF", "PDF", ".pdf"):
        c = _cond("extension", "eq", value)
        assert rules.automation_conditions_match([c], FIELDS, ATTRS, None) is True


def test_condition_source_folder_match():
    c = _cond("source_folder", "eq", "Downloads")
    assert rules.automation_conditions_match([c], FIELDS, ATTRS, None) is True


def test_condition_template_match():
    c = _cond("template", "eq", "42")
    assert rules.automation_conditions_match([c], FIELDS, ATTRS, 42) is True
    assert rules.automation_conditions_match([c], FIELDS, ATTRS, 99) is False


def test_condition_size_numeric_gt():
    # Pitfall 2: comparação numérica, não lexicográfica.
    c = _cond("size", "gt", "100000")
    assert rules.automation_conditions_match([c], FIELDS, ATTRS, None) is True
    c2 = _cond("size", "lt", "100000")
    assert rules.automation_conditions_match([c2], FIELDS, ATTRS, None) is False


def test_conditions_combined_by_and():
    ok = _cond("source_folder", "eq", "Downloads")
    bad = _cond("extension", "eq", ".xlsx")
    # Uma falha → o E (AND) reprova.
    assert rules.automation_conditions_match([ok, bad], FIELDS, ATTRS, None) is False
    ok2 = _cond("extension", "eq", ".pdf")
    assert rules.automation_conditions_match([ok, ok2], FIELDS, ATTRS, None) is True


def test_empty_conditions_never_match():
    # Automação sem condições NÃO casa (falha fechada).
    assert rules.automation_conditions_match([], FIELDS, ATTRS, None) is False


def test_condition_unknown_field_fails_closed():
    c = _cond("xpto", "eq", "x")
    assert rules.automation_conditions_match([c], FIELDS, ATTRS, None) is False


# ---- ações (D-24) ---------------------------------------------------------- #


def test_actions_rename_mutates_only_name():
    autos = [
        _auto(
            conditions=[_cond("extension", "eq", ".pdf")],
            actions=[_action("rename", params={"name_pattern": "{cliente}_{numero}"})],
        )
    ]
    plan = evaluate_automations(autos, FIELDS, ATTRS, base_root=BASE)
    assert plan.target_name == "ACME Ltda_1234"
    assert plan.target_folder == BASE.resolve()  # pasta inalterada
    assert plan.matched is True
    assert plan.blocked is False


def test_actions_move_mutates_only_folder():
    autos = [
        _auto(
            conditions=[_cond("extension", "eq", ".pdf")],
            actions=[_action("move", params={"dest_folder": "NF/{cliente}"})],
        )
    ]
    plan = evaluate_automations(autos, FIELDS, ATTRS, base_root=BASE)
    assert plan.target_folder == (BASE.resolve() / "NF" / "ACME Ltda")
    assert plan.target_name == "entrada.pdf"  # nome inalterado


def test_actions_rename_then_move_compose():
    autos = [
        _auto(
            conditions=[_cond("extension", "eq", ".pdf")],
            actions=[
                _action("rename", position=0, params={"name_pattern": "{numero}"}),
                _action("move", position=1, params={"dest_folder": "NF/{cliente}"}),
            ],
        )
    ]
    plan = evaluate_automations(autos, FIELDS, ATTRS, base_root=BASE)
    assert plan.target_name == "1234"
    assert plan.target_folder == (BASE.resolve() / "NF" / "ACME Ltda")


def test_actions_order_independent():
    # folder e name são dimensões independentes → ordem não altera o plano-alvo.
    a = evaluate_automations(
        [
            _auto(
                conditions=[_cond("extension", "eq", ".pdf")],
                actions=[
                    _action("move", position=0, params={"dest_folder": "NF/{cliente}"}),
                    _action("rename", position=1, params={"name_pattern": "{numero}"}),
                ],
            )
        ],
        FIELDS, ATTRS, base_root=BASE,
    )
    b = evaluate_automations(
        [
            _auto(
                conditions=[_cond("extension", "eq", ".pdf")],
                actions=[
                    _action("rename", position=0, params={"name_pattern": "{numero}"}),
                    _action("move", position=1, params={"dest_folder": "NF/{cliente}"}),
                ],
            )
        ],
        FIELDS, ATTRS, base_root=BASE,
    )
    assert a.target_folder == b.target_folder
    assert a.target_name == b.target_name


def test_actions_blocked_missing_field():
    # D-07: token p/ campo faltante → blocked.
    autos = [
        _auto(
            conditions=[_cond("extension", "eq", ".pdf")],
            actions=[_action("rename", params={"name_pattern": "{inexistente}"})],
        )
    ]
    plan = evaluate_automations(autos, FIELDS, ATTRS, base_root=BASE)
    assert plan.blocked is True
    assert plan.matched is True


# ---- ordem entre automações (D-25) ----------------------------------------- #


def test_first_matching_automation_wins():
    # Específica (position 0) casa → suas ações vencem; a genérica (position 1) NÃO roda.
    autos = [
        _auto(
            position=0,
            automation_id=1,
            conditions=[
                _cond("extension", "eq", ".pdf"),
                _cond("source_folder", "eq", "Downloads"),
            ],
            actions=[_action("move", params={"dest_folder": "ESPECIFICA"})],
        ),
        _auto(
            position=1,
            automation_id=2,
            conditions=[_cond("extension", "eq", ".pdf")],
            actions=[_action("move", params={"dest_folder": "GENERICA"})],
        ),
    ]
    plan = evaluate_automations(autos, FIELDS, ATTRS, base_root=BASE)
    assert plan.matched is True
    assert plan.automation_id == 1
    assert plan.target_folder == (BASE.resolve() / "ESPECIFICA")


def test_order_matters_position_decides():
    # Mesmas condições, ordem invertida: a de menor position vence.
    autos = [
        _auto(
            position=5,
            automation_id=99,
            conditions=[_cond("extension", "eq", ".pdf")],
            actions=[_action("move", params={"dest_folder": "TARDE"})],
        ),
        _auto(
            position=1,
            automation_id=11,
            conditions=[_cond("extension", "eq", ".pdf")],
            actions=[_action("move", params={"dest_folder": "CEDO"})],
        ),
    ]
    plan = evaluate_automations(autos, FIELDS, ATTRS, base_root=BASE)
    assert plan.automation_id == 11
    assert plan.target_folder == (BASE.resolve() / "CEDO")


def test_inactive_automation_skipped():
    autos = [
        _auto(
            position=0,
            active=False,
            automation_id=1,
            conditions=[_cond("extension", "eq", ".pdf")],
            actions=[_action("move", params={"dest_folder": "PAUSADA"})],
        ),
        _auto(
            position=1,
            active=True,
            automation_id=2,
            conditions=[_cond("extension", "eq", ".pdf")],
            actions=[_action("move", params={"dest_folder": "ATIVA"})],
        ),
    ]
    plan = evaluate_automations(autos, FIELDS, ATTRS, base_root=BASE)
    assert plan.automation_id == 2
    assert plan.target_folder == (BASE.resolve() / "ATIVA")


# ---- no-match (D-25) ------------------------------------------------------- #


def test_no_match_is_explicit_noop():
    autos = [
        _auto(
            conditions=[_cond("field", "eq", "Outra", field_name="cliente")],
            actions=[_action("move", params={"dest_folder": "NF"})],
        )
    ]
    plan = evaluate_automations(autos, FIELDS, ATTRS, base_root=BASE)
    assert plan.matched is False
    assert plan.blocked is False
    assert plan.automation_id is None
    # Plano default: raiz-base + nome original (o caller decide no-op, não materializa).
    assert plan.target_folder == BASE.resolve()
    assert plan.target_name == "entrada.pdf"


def test_no_automations_is_no_match():
    plan = evaluate_automations([], FIELDS, ATTRS, base_root=BASE)
    assert plan.matched is False
    assert plan.target_folder == BASE.resolve()

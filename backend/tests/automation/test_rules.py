"""RED (Wave 0) — avaliador de regras condicionais (TPL-02, D-04/D-05).

Alvo: `app.automation.rules` (a criar). Cobre:
- operadores `=` / `>` / `<` / `contém` (eq/gt/lt/contains);
- combinação E/OU (conjunction) entre condições da mesma regra;
- comparação numérica via Decimal (NUNCA string: "500" vs "3000" não pode inverter);
- precedência: a PRIMEIRA regra que casa vence (ordem de prioridade, D-05).

`importorskip` evita ImportError fatal na coleta enquanto `rules` não existe.
"""

import pytest

rules = pytest.importorskip("app.automation.rules")


def _fields() -> dict[str, str]:
    return {
        "cliente": "ACME Ltda",
        "numero": "1234",
        "valor": "1500.00",
        "data": "2026-06-17",
    }


def test_operator_eq() -> None:
    """D-04: operador `=` (eq) casa por igualdade."""
    cond = rules.Condition(field_name="cliente", operator="eq", value="ACME Ltda")
    assert rules.evaluate_condition(cond, _fields()) is True


def test_operator_contains() -> None:
    """D-04: operador `contém` (contains)."""
    cond = rules.Condition(field_name="cliente", operator="contains", value="ACME")
    assert rules.evaluate_condition(cond, _fields()) is True


def test_operator_gt_lt_numeric_via_decimal() -> None:
    """D-04 + Pitfall 2: `>`/`<` de moeda/numero comparam via Decimal, não string.
    Como string, "1500.00" < "500.00" (erro). Como Decimal, 1500 > 500 (correto)."""
    gt = rules.Condition(field_name="valor", operator="gt", value="500.00")
    lt = rules.Condition(field_name="valor", operator="lt", value="2000.00")
    assert rules.evaluate_condition(gt, _fields()) is True
    assert rules.evaluate_condition(lt, _fields()) is True
    # E o caso que a comparação por string inverteria:
    not_gt = rules.Condition(field_name="valor", operator="gt", value="3000.00")
    assert rules.evaluate_condition(not_gt, _fields()) is False


def test_conjunction_and_or() -> None:
    """D-04: E (todas) vs OU (qualquer) entre condições da regra."""
    c_true = rules.Condition(field_name="cliente", operator="contains", value="ACME")
    c_false = rules.Condition(field_name="cliente", operator="eq", value="OUTRO")
    rule_and = rules.Rule(
        priority=0, conjunction="and", conditions=[c_true, c_false], name_pattern="x"
    )
    rule_or = rules.Rule(
        priority=0, conjunction="or", conditions=[c_true, c_false], name_pattern="x"
    )
    assert rules.rule_matches(rule_and, _fields()) is False
    assert rules.rule_matches(rule_or, _fields()) is True


def test_precedence_first_match_wins() -> None:
    """D-05: avaliadas por prioridade, a PRIMEIRA regra que casa vence."""
    low = rules.Rule(
        priority=10,
        conjunction="and",
        conditions=[rules.Condition(field_name="cliente", operator="contains", value="ACME")],
        name_pattern="baixa",
    )
    high = rules.Rule(
        priority=1,
        conjunction="and",
        conditions=[rules.Condition(field_name="cliente", operator="contains", value="ACME")],
        name_pattern="alta",
    )
    chosen = rules.first_matching_rule([low, high], _fields())
    assert chosen is not None
    assert chosen.name_pattern == "alta"

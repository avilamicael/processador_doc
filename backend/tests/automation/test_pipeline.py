"""RED→GREEN — executor PURO do pipeline (`app.automation.pipeline`) + filtros D-14.

Fonte de verdade da API pública do executor (06-07, Wave 2). Cobre os marcadores
do Test Map (06-RESEARCH §"Phase Requirements → Test Map"):
- `-k filter` (D-14): cada filter_type casa/não-casa; sem filtro → casa sempre (P10);
- `-k ordering` (D-12): itera por position; step active=False é ignorado;
- `-k actions` (D-13): rename muta só o nome; move muta só a pasta;
- `-k order_independent` (Pitfall 8): [move,rename] == [rename,move];
- `-k route_stops` (Pitfall 9): route interrompe e NÃO produz plano-alvo materializável;
- `-k no_match` (Pitfall 10): nenhum step casa → matched_any=False, plano = default;
- `-k gate` (D-15): identify_type usa classify_fn; NÃO re-cobra IA (closure idempotente).

Executor é PURO (sem disco, sem ORM): recebe specs puros + fields + file_attrs.
"""

from pathlib import Path

import pytest

from app.automation import rules
from app.automation.pipeline import (
    PipelineStepSpec,
    run_pipeline,
)

# ---- helpers de montagem dos specs puros ---------------------------------- #


def _filter(filter_type, operator, value, field_name=None):
    """Filtro puro duck-typed (espelha StepFilter ORM mapeado p/ forma pura)."""
    return rules.FilterSpec(
        filter_type=filter_type,
        operator=operator,
        value=value,
        field_name=field_name,
    )


def _step(action_type, *, position=0, params=None, filters=None, conjunction="and", active=True):
    return PipelineStepSpec(
        position=position,
        action_type=action_type,
        conjunction=conjunction,
        params=params or {},
        filters=filters or [],
        active=active,
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
    "original_filename": "entrada.pdf",
    "template_id": None,
}

BASE = Path("/tmp/organizados")


def _no_classify(_template_id):  # pragma: no cover - não deve ser chamado
    raise AssertionError("classify_fn não deveria ser chamado")


# ---- filtros (D-14) -------------------------------------------------------- #


def test_filter_field_match():
    f = _filter("field", "eq", "ACME Ltda", field_name="cliente")
    assert rules.filter_matches([f], "and", FIELDS, ATTRS, None) is True


def test_filter_field_no_match():
    f = _filter("field", "eq", "Outra", field_name="cliente")
    assert rules.filter_matches([f], "and", FIELDS, ATTRS, None) is False


def test_filter_extension_case_insensitive():
    f = _filter("extension", "eq", ".PDF")
    assert rules.filter_matches([f], "and", FIELDS, ATTRS, None) is True


def test_filter_filename_contains():
    f = _filter("filename", "contains", "entrada")
    assert rules.filter_matches([f], "and", FIELDS, ATTRS, None) is True


def test_filter_size_numeric_gt():
    # Pitfall 2: comparação numérica, não lexicográfica.
    f = _filter("size", "gt", "100000")
    assert rules.filter_matches([f], "and", FIELDS, ATTRS, None) is True
    f2 = _filter("size", "lt", "100000")
    assert rules.filter_matches([f2], "and", FIELDS, ATTRS, None) is False


def test_filter_source_folder_eq():
    f = _filter("source_folder", "eq", "7")
    assert rules.filter_matches([f], "and", FIELDS, ATTRS, None) is True


def test_filter_template_eq():
    f = _filter("template", "eq", "42")
    assert rules.filter_matches([f], "and", FIELDS, ATTRS, 42) is True
    assert rules.filter_matches([f], "and", FIELDS, ATTRS, 99) is False


def test_filter_unknown_type_fails_closed():
    # V5: filter_type desconhecido nunca casa (falha fechada).
    f = _filter("xpto", "eq", "x")
    assert rules.filter_matches([f], "and", FIELDS, ATTRS, None) is False


def test_filter_empty_matches_all():
    # P10: step sem filtros aplica-se a todo documento.
    assert rules.filter_matches([], "and", FIELDS, ATTRS, None) is True


def test_filter_conjunction_or():
    f1 = _filter("field", "eq", "Outra", field_name="cliente")  # falso
    f2 = _filter("extension", "eq", ".pdf")  # verdadeiro
    assert rules.filter_matches([f1, f2], "or", FIELDS, ATTRS, None) is True
    assert rules.filter_matches([f1, f2], "and", FIELDS, ATTRS, None) is False


# ---- ações (D-13) ---------------------------------------------------------- #


def test_actions_rename_mutates_only_name():
    steps = [_step("rename", params={"name_pattern": "{cliente}_{numero}"})]
    plan = run_pipeline(steps, FIELDS, dict(ATTRS), base_root=BASE, classify_fn=_no_classify)
    assert plan.target_name == "ACME Ltda_1234"
    assert plan.target_folder == BASE.resolve()  # pasta inalterada
    assert plan.matched_any is True
    assert plan.blocked is False


def test_actions_move_mutates_only_folder():
    steps = [_step("move", params={"folder_pattern": "NF/{cliente}"})]
    plan = run_pipeline(steps, FIELDS, dict(ATTRS), base_root=BASE, classify_fn=_no_classify)
    assert plan.target_folder == (BASE.resolve() / "NF" / "ACME Ltda")
    assert plan.target_name == "entrada.pdf"  # nome inalterado


def test_actions_blocked_missing_field():
    # D-07: token p/ campo faltante → blocked.
    steps = [_step("rename", params={"name_pattern": "{inexistente}"})]
    plan = run_pipeline(steps, FIELDS, dict(ATTRS), base_root=BASE, classify_fn=_no_classify)
    assert plan.blocked is True


# ---- ordem (D-12) + Pitfall 8 ---------------------------------------------- #


def test_ordering_respects_position():
    steps = [
        _step("move", position=1, params={"folder_pattern": "B"}),
        _step("move", position=0, params={"folder_pattern": "A"}),
    ]
    plan = run_pipeline(steps, FIELDS, dict(ATTRS), base_root=BASE, classify_fn=_no_classify)
    # position 1 (B) é o último a rodar → vence a pasta.
    assert plan.target_folder == (BASE.resolve() / "B")


def test_ordering_inactive_step_skipped():
    steps = [
        _step("rename", params={"name_pattern": "{cliente}"}),
        _step("move", position=1, params={"folder_pattern": "NF"}, active=False),
    ]
    plan = run_pipeline(steps, FIELDS, dict(ATTRS), base_root=BASE, classify_fn=_no_classify)
    # O move pausado NÃO participa: pasta fica no default.
    assert plan.target_folder == BASE.resolve()
    assert plan.target_name == "ACME Ltda"


def test_order_independent_move_rename_vs_rename_move():
    # Pitfall 8: [move,rename] e [rename,move] → MESMO plano-alvo.
    a = run_pipeline(
        [
            _step("move", position=0, params={"folder_pattern": "NF/{cliente}"}),
            _step("rename", position=1, params={"name_pattern": "{numero}"}),
        ],
        FIELDS, dict(ATTRS), base_root=BASE, classify_fn=_no_classify,
    )
    b = run_pipeline(
        [
            _step("rename", position=0, params={"name_pattern": "{numero}"}),
            _step("move", position=1, params={"folder_pattern": "NF/{cliente}"}),
        ],
        FIELDS, dict(ATTRS), base_root=BASE, classify_fn=_no_classify,
    )
    assert a.target_folder == b.target_folder
    assert a.target_name == b.target_name


# ---- route (Pitfall 9) ----------------------------------------------------- #


def test_route_stops_pipeline_no_materialize():
    steps = [
        _step("route", position=0, params={"target": "em_revisao"}),
        _step("move", position=1, params={"folder_pattern": "NUNCA"}),
    ]
    plan = run_pipeline(steps, FIELDS, dict(ATTRS), base_root=BASE, classify_fn=_no_classify)
    assert plan.route_to == "em_revisao"
    assert plan.matched_any is True
    # O move após o route NÃO rodou.
    assert plan.target_folder is None or plan.target_folder == BASE.resolve()


# ---- no_match (Pitfall 10) ------------------------------------------------- #


def test_no_match_is_explicit_noop():
    steps = [
        _step(
            "move",
            params={"folder_pattern": "NF"},
            filters=[_filter("field", "eq", "Outra", field_name="cliente")],
        )
    ]
    plan = run_pipeline(steps, FIELDS, dict(ATTRS), base_root=BASE, classify_fn=_no_classify)
    assert plan.matched_any is False
    assert plan.blocked is False
    assert plan.route_to is None
    # Plano default: raiz-base + nome original (o caller decide no-op, não materializa).
    assert plan.target_folder == BASE.resolve()
    assert plan.target_name == "entrada.pdf"


# ---- gate identify_type (D-15) --------------------------------------------- #


def test_gate_identify_sets_template_and_filters_downstream():
    calls = {"n": 0}

    def classify_fn(template_id):
        calls["n"] += 1
        return template_id

    steps = [
        _step("identify_type", position=0, params={"template_id": 42}),
        _step(
            "move",
            position=1,
            params={"folder_pattern": "NF"},
            filters=[_filter("template", "eq", "42")],
        ),
    ]
    plan = run_pipeline(steps, FIELDS, dict(ATTRS), base_root=BASE, classify_fn=classify_fn)
    assert plan.identified_template_id == 42
    assert plan.target_folder == (BASE.resolve() / "NF")  # filtro template casou
    assert calls["n"] == 1  # gate chamado exatamente uma vez (não re-cobra)


def test_gate_does_not_recall_when_already_classified():
    # classify_fn que conta chamadas; com 0 steps identify_type, nunca chama.
    calls = {"n": 0}

    def classify_fn(template_id):  # pragma: no cover
        calls["n"] += 1
        return template_id

    steps = [_step("rename", params={"name_pattern": "{cliente}"})]
    run_pipeline(steps, FIELDS, dict(ATTRS), base_root=BASE, classify_fn=classify_fn)
    assert calls["n"] == 0

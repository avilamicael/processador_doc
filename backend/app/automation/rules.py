"""Avaliador puro de regras condicionais de automação (Fase 6 — TPL-02/D-04/D-05).

Função PURA — sem IA, sem disco, sem banco. Espelha o estilo de dispatch por
etiqueta de `validation/fields.py` (lá por `field_type`; aqui por `operator`).

D-04 (operadores + E/OU): cada condição é `{campo} {operador} {valor}`, com
`operador ∈ {eq, gt, lt, contains}` (mapeando `= > < contém`). As condições de uma
regra combinam por `conjunction` ("and" = todas / "or" = qualquer uma).

D-05 (precedência): as regras são avaliadas em ordem de `priority` e a PRIMEIRA que
casa vence (a ordem que o operador definiu na UI manda).

Pitfall 2 (coerção numérica OBRIGATÓRIA): `gt`/`lt` sobre moeda/número comparam via
`Decimal`, NUNCA como string — lexicograficamente "500" > "3000" (errado), mas
Decimal(500) < Decimal(3000) (certo). Data ISO `YYYY-MM-DD` já é lexicograficamente
ordenável, então comparar a string ISO é correto.

Segurança (V5): o casamento de operador é um DISPATCH EXPLÍCITO — NUNCA `eval`. Um
operador desconhecido nunca casa (falha fechada).

Estes objetos `Condition`/`Rule` são a forma PURA consumida pelo avaliador; a
persistência (modelos `AutomationRule`/`RuleCondition`, Plan 01) é mapeada para eles
pelo caller. NÃO loga valores de campo (LGPD).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# Operadores suportados (D-04). Um operador fora deste conjunto nunca casa (V5).
_OPERATORS = frozenset({"eq", "gt", "lt", "contains"})


@dataclass
class Condition:
    """Uma condição `{field_name} {operator} {value}` (D-04). Objeto puro."""

    field_name: str
    operator: str
    value: str


@dataclass
class Rule:
    """Regra: condições combinadas por `conjunction`, com `priority` (D-05)."""

    priority: int
    conjunction: str
    conditions: list[Condition] = field(default_factory=list)
    name_pattern: str | None = None
    folder_pattern: str | None = None
    active: bool = True


def _as_decimal(text: str) -> Decimal | None:
    """Tenta interpretar `text` como número/moeda Decimal-comparável; senão None.

    Reusa a disciplina de `validation` (já normaliza moeda BRL para string
    Decimal-parseável); aqui o valor do campo já chega normalizado, então um
    `Decimal(text)` direto basta. Texto não-numérico → None (cai no ramo string).
    """
    if text is None:
        return None
    try:
        return Decimal(text.strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def evaluate_condition(cond: Condition, fields: dict[str, str]) -> bool:
    """Avalia UMA condição contra os campos normalizados. Retorna True/False.

    Dispatch explícito por `operator` (NUNCA `eval` — V5):
    - `eq`: igualdade case-insensitive sobre o valor do campo;
    - `contains`: substring case-insensitive;
    - `gt`/`lt`: coerção numérica obrigatória (Pitfall 2) — se AMBOS os lados são
      Decimal-parseáveis, compara como `Decimal`; senão compara as strings (data ISO
      já ordenável; texto solto cai aqui sem inverter números, pois números teriam
      ido pelo ramo Decimal).

    Campo ausente/vazio → condição falsa (não levanta). Operador desconhecido → False
    (falha fechada). NÃO loga valores.
    """
    raw = fields.get(cond.field_name)
    if raw is None or not str(raw).strip():
        return False
    field_value = str(raw)
    target = cond.value if cond.value is not None else ""

    op = cond.operator
    if op == "eq":
        return field_value.strip().casefold() == target.strip().casefold()

    if op == "contains":
        return target.strip().casefold() in field_value.casefold()

    if op in ("gt", "lt"):
        left_dec = _as_decimal(field_value)
        right_dec = _as_decimal(target)
        if left_dec is not None and right_dec is not None:
            # Coerção numérica (Pitfall 2): compara grandeza, não lexicograficamente.
            return left_dec > right_dec if op == "gt" else left_dec < right_dec
        # Fallback não-numérico: data ISO YYYY-MM-DD já é lexicograficamente ordenável;
        # texto solto compara estável (números nunca chegam aqui).
        left_s = field_value.strip()
        right_s = target.strip()
        return left_s > right_s if op == "gt" else left_s < right_s

    # Operador desconhecido: falha fechada (V5) — nunca casa.
    return False


def rule_matches(rule: Rule, fields: dict[str, str]) -> bool:
    """Verdadeiro se a regra casa: combina suas condições por `conjunction` (D-04).

    "and" → todas as condições casam; "or" → qualquer uma. Regra SEM condições não
    casa (evita aplicar uma regra vazia a tudo). NÃO loga valores.
    """
    if not rule.conditions:
        return False
    results = (evaluate_condition(c, fields) for c in rule.conditions)
    if (rule.conjunction or "and").strip().casefold() == "or":
        return any(results)
    return all(results)


def first_matching_rule(rules: list[Rule], fields: dict[str, str]) -> Rule | None:
    """Devolve a PRIMEIRA regra que casa, em ordem de `priority` (D-05).

    As regras são ordenadas por `priority` (menor = avaliada antes); regras com
    `active=False` são ignoradas. Nenhuma casa → `None` (caller mantém o documento
    sem automação / quarentena). NÃO loga valores.
    """
    ordered = sorted((r for r in rules if r.active), key=lambda r: r.priority)
    for rule in ordered:
        if rule_matches(rule, fields):
            return rule
    return None

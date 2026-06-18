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

import re
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


# --------------------------------------------------------------------------- #
# Filtros de entrada do PIPELINE (D-14) — generaliza o avaliador de condições.  #
# --------------------------------------------------------------------------- #

# Tipos de filtro suportados (D-14). Um tipo fora deste conjunto nunca casa (V5).
_FILTER_TYPES = frozenset(
    {"field", "source_folder", "extension", "filename", "size", "template"}
)


def normalize_extensions(raw) -> list[str]:
    """Normaliza extensões DIGITADAS pelo usuário (D-17) → lista canônica `.ext`.

    Aceita uma lista (`[".pdf", "XLSX"]`) OU uma string única separada por vírgula/
    espaço/ponto-e-vírgula (`"pdf, .xlsx; PNG"`). Cada item é: stripado, lowercased,
    prefixado com "." se ausente. Itens vazios são descartados. Resultado sem
    duplicatas, preservando a ordem. NÃO loga valores.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        items = re.split(r"[,;\s]+", raw)
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = [raw]

    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        token = str(item).strip().casefold()
        if not token:
            continue
        if not token.startswith("."):
            token = "." + token
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def ext_matches(raw_extensions, file_ext: str | None) -> bool:
    """Casa a EXTENSÃO do arquivo (`file_ext`) contra as extensões digitadas (D-17).

    `raw_extensions` vem dos params do step (`{"extensions": [...]/"..."}`); é
    normalizado por `normalize_extensions` (case/dot-insensitive). True quando a
    extensão do arquivo está na lista normalizada. Lista vazia → False (um gate sem
    extensão configurada nunca casa: falha fechada, V5). NÃO loga valores.
    """
    wanted = normalize_extensions(raw_extensions)
    if not wanted:
        return False
    actual = str(file_ext or "").strip().casefold()
    if actual and not actual.startswith("."):
        actual = "." + actual
    return actual in wanted


@dataclass
class FilterSpec:
    """Filtro de entrada PURO de uma etapa do pipeline — `{filter_type} {op} {value}`.

    Forma pura consumida pelo avaliador; o caller (pipeline.py / stage.py) mapeia o
    `StepFilter` ORM para esta forma (igual `Condition` faz para `RuleCondition`).
    `field_name` só é usado quando `filter_type == "field"`.
    """

    filter_type: str
    operator: str
    value: str
    field_name: str | None = None


def evaluate_filter(
    filter: FilterSpec,
    fields: dict[str, str],
    file_attrs: dict,
    identified_template_id: int | None,
) -> bool:
    """Avalia UM filtro de entrada (D-14). Dispatch EXPLÍCITO por `filter_type` (V5).

    - `field`: reusa `evaluate_condition` (campo extraído `{campo} op valor`);
    - `source_folder`: `eq` sobre `str(file_attrs["source_folder_id"])`;
    - `extension`: `eq`/`contains` case-insensitive sobre `file_attrs["ext"]`;
    - `filename`: `eq`/`contains` sobre `file_attrs["original_filename"]`;
    - `size`: coerção numérica (`_as_decimal`) `gt`/`lt` sobre `file_attrs["size"]`
      (Pitfall 2 — nunca lexicográfico);
    - `template`: `eq` sobre `str(identified_template_id)` (porteiro do gate, D-15).

    `filter_type` desconhecido → False (falha fechada, V5). NÃO loga valores.
    """
    ft = filter.filter_type
    if ft not in _FILTER_TYPES:
        return False  # V5: falha fechada

    if ft == "field":
        cond = Condition(
            field_name=filter.field_name or "",
            operator=filter.operator,
            value=filter.value,
        )
        return evaluate_condition(cond, fields)

    if ft == "source_folder":
        sfid = file_attrs.get("source_folder_id")
        if sfid is None:
            return False
        return str(sfid).strip() == str(filter.value).strip()

    if ft == "extension":
        ext = str(file_attrs.get("ext") or "").strip().casefold()
        target = str(filter.value or "").strip().casefold()
        if filter.operator == "contains":
            return target in ext
        return ext == target

    if ft == "filename":
        name = str(file_attrs.get("original_filename") or "")
        target = str(filter.value or "")
        if filter.operator == "contains":
            return target.strip().casefold() in name.casefold()
        return name.strip().casefold() == target.strip().casefold()

    if ft == "size":
        left = _as_decimal(str(file_attrs.get("size", "")))
        right = _as_decimal(str(filter.value))
        if left is None or right is None:
            return False
        if filter.operator == "gt":
            return left > right
        if filter.operator == "lt":
            return left < right
        # eq sobre tamanho (uso raro mas coerente).
        if filter.operator == "eq":
            return left == right
        return False

    if ft == "template":
        if identified_template_id is None:
            return False
        return str(identified_template_id).strip() == str(filter.value).strip()

    return False  # inalcançável (V5)


def filter_matches(
    filters: list[FilterSpec],
    conjunction: str,
    fields: dict[str, str],
    file_attrs: dict,
    identified_template_id: int | None,
) -> bool:
    """Casa a etapa: combina seus filtros de entrada por `conjunction` (D-14).

    SEM filtros → True (a etapa aplica-se a TODO documento, P10). Senão `or` → any /
    `and` (default) → all. NÃO loga valores.
    """
    if not filters:
        return True
    results = [
        evaluate_filter(f, fields, file_attrs, identified_template_id) for f in filters
    ]
    if (conjunction or "and").strip().casefold() == "or":
        return any(results)
    return all(results)


# --------------------------------------------------------------------------- #
# Condições do MODELO FINAL (D-24) — nível da automação, combinadas por E.      #
#                                                                               #
# `field` do modelo final mapeia 1:1 para o `filter_type` do avaliador acima    #
# (source_folder/extension/template/field/filename/size). Esta camada fina      #
# reusa `evaluate_filter` (sem eval, V5) e combina por E (AND) — não há OU no    #
# nível da automação (D-24).                                                     #
# --------------------------------------------------------------------------- #

# Campos de condição suportados (D-24). Fora do conjunto → nunca casa (V5).
_CONDITION_FIELDS = _FILTER_TYPES


@dataclass
class ConditionSpec:
    """Condição PURA de uma automação — `{field} {operator} {value}` (D-24).

    Forma pura consumida pelo executor; o caller (stage.py) mapeia o
    `AutomationCondition` ORM para esta forma. `field_name` só é usado quando
    `field == "field"` (qual campo extraído comparar). `field` casa o vocabulário
    de `evaluate_filter` (1:1 com `filter_type`).
    """

    field: str
    operator: str
    value: str
    field_name: str | None = None


def condition_matches(
    cond: ConditionSpec,
    fields: dict[str, str],
    file_attrs: dict,
    template_id: int | None,
) -> bool:
    """Avalia UMA condição da automação (D-24). Reusa `evaluate_filter` (V5).

    `field` mapeia 1:1 para `filter_type`; a `extension` aceita a extensão digitada
    pelo usuário (`.pdf`/`pdf`/`.PDF` — case/dot-insensitive via `ext_matches`),
    diferenciando-se do `evaluate_filter` "extension" cru (que compara literal).
    NÃO loga valores.
    """
    if cond.field == "extension":
        # D-24: a condição de tipo de arquivo casa a extensão DIGITADA pelo usuário,
        # case/dot-insensitive (ex.: ".pdf" casa "PDF"). `contains` mantém o
        # comportamento de substring literal de `evaluate_filter`.
        if cond.operator == "contains":
            return evaluate_filter(
                FilterSpec("extension", "contains", cond.value),
                fields,
                file_attrs,
                template_id,
            )
        return ext_matches(cond.value, file_attrs.get("ext"))

    if cond.field == "source_folder":
        # D-24: a condição "pasta de origem" compara o CAMINHO/NOME da pasta
        # monitorada digitado pelo usuário (ex.: "Downloads", "C:\\Downloads"),
        # NÃO o id interno. `eq` = igualdade case-insensitive; `contains` = substring.
        actual = str(file_attrs.get("source_folder") or "")
        if not actual:
            return False
        target = str(cond.value or "")
        if cond.operator == "contains":
            return target.strip().casefold() in actual.casefold()
        return actual.strip().casefold() == target.strip().casefold()

    spec = FilterSpec(
        filter_type=cond.field,
        operator=cond.operator,
        value=cond.value,
        field_name=cond.field_name,
    )
    return evaluate_filter(spec, fields, file_attrs, template_id)


def automation_conditions_match(
    conditions: list[ConditionSpec],
    fields: dict[str, str],
    file_attrs: dict,
    template_id: int | None,
) -> bool:
    """True quando TODAS as condições da automação casam (E/AND, D-24).

    Uma automação SEM condições NÃO casa (evita aplicar uma automação vazia a todo
    documento — falha fechada, espelha `rule_matches`). NÃO loga valores.
    """
    if not conditions:
        return False
    return all(
        condition_matches(c, fields, file_attrs, template_id) for c in conditions
    )

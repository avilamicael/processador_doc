"""Orquestrador de validação por tipo de campo (Fase 4) — D-09/D-10/D-11.

Estilo seam de despacho por etiqueta (espelha `extraction/router.choose`): uma só
função pura `validate_field` decide, por `field_type`, qual validador/normalizador
determinístico aplicar (`doc_ids`/`dates`/`money` da Task 1), consolidando o
resultado num `FieldValidation`.

Princípios da fase (o gate de decisão é a Fase 5, não aqui):
- **D-10 — marca, não bloqueia:** validação falha → `valid=False` + `invalid_reason`;
  NUNCA levanta exceção (campo obrigatório ausente também só marca).
- **D-11 — bruto + normalizado:** o `raw_value` é SEMPRE preservado (auditável),
  mesmo quando inválido; o `normalized_value` guarda a forma canônica (ISO, Decimal,
  só dígitos) ou `None` quando o parse falha (nunca chuta um valor errado — T-04-05).
- **D-09 — regex opcional + V5/ReDoS:** o pattern do operador roda via
  `re.fullmatch` SOBRE um valor com teto de tamanho (`_MAX_REGEX_LEN`); valores
  acima do teto são recusados antes de tocar a engine de regex (T-04-03). O operador
  é single-tenant (não atacante externo), mas o limite é por desenho.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.validation.dates import normalize_date
from app.validation.doc_ids import is_valid_cnpj, is_valid_cpf, normalize_doc_id
from app.validation.money import normalize_money_brl

# Teto de tamanho do valor antes de aplicar o regex do operador (mitiga ReDoS — V5).
_MAX_REGEX_LEN = 4096

# Conjunto de valores booleanos reconhecidos (D-08), normalizados para "true"/"false".
_BOOL_TRUE = {"sim", "true", "1", "verdadeiro", "s", "v"}
_BOOL_FALSE = {"não", "nao", "false", "0", "falso", "n", "f"}


@dataclass
class FieldValidation:
    """Resultado estruturado de validar um campo (D-10 marca, D-11 bruto+normalizado)."""

    valid: bool
    raw_value: str | None
    normalized_value: str | None
    invalid_reason: str | None


def _normalize_numero(raw: str) -> str | None:
    """Normaliza um número inteiro/decimal via `Decimal` (NUNCA float — T-04-05)."""
    try:
        return str(Decimal(raw.strip()))
    except (InvalidOperation, ValueError):
        return None


def _normalize_booleano(raw: str) -> str | None:
    """Reconhece sim/não/true/false (D-08) → "true"/"false"; desconhecido → None."""
    key = raw.strip().lower()
    if key in _BOOL_TRUE:
        return "true"
    if key in _BOOL_FALSE:
        return "false"
    return None


def validate_field(
    *,
    field_type: str,
    raw: str | None,
    required: bool = False,
    regex: str | None = None,
) -> FieldValidation:
    """Valida e normaliza um campo por tipo, marcando válido/inválido sem bloquear.

    Despacha por `field_type` (D-08): "data"→ISO, "moeda"/"numero"→Decimal,
    "cpf_cnpj"→Módulo 11 + só dígitos, "booleano"→true/false, "texto"/desconhecido→
    passthrough. Aplica `required` (ausente/vazio + required → inválido, NÃO levanta —
    D-10) e o `regex` opcional via `re.fullmatch` sobre valor limitado (V5).

    O `raw` é SEMPRE preservado em `raw_value` (D-11). Parse falho → `valid=False` +
    `invalid_reason`, `normalized_value=None` (nunca chuta um valor — T-04-05).
    """
    # D-10/D-11: obrigatório ausente/vazio só MARCA (não levanta); bruto preservado.
    is_empty = raw is None or not raw.strip()
    if is_empty:
        if required:
            return FieldValidation(
                valid=False,
                raw_value=raw,
                normalized_value=None,
                invalid_reason="campo obrigatório ausente",
            )
        return FieldValidation(
            valid=True, raw_value=raw, normalized_value=None, invalid_reason=None
        )

    # Despacho por tipo → (normalized, reason_se_falhou). raw é garantidamente não-vazio.
    normalized: str | None
    reason: str | None = None

    if field_type == "data":
        normalized = normalize_date(raw)
        if normalized is None:
            reason = "data inválida (não parseável)"
    elif field_type == "moeda":
        normalized = normalize_money_brl(raw)
        if normalized is None:
            reason = "moeda inválida (não parseável)"
    elif field_type == "numero":
        normalized = _normalize_numero(raw)
        if normalized is None:
            reason = "número inválido (não parseável)"
    elif field_type == "cpf_cnpj":
        if is_valid_cnpj(raw) or is_valid_cpf(raw):
            normalized = normalize_doc_id(raw)
        else:
            normalized = None
            reason = "CPF/CNPJ inválido (dígito verificador)"
    elif field_type == "booleano":
        normalized = _normalize_booleano(raw)
        if normalized is None:
            reason = "booleano não reconhecido"
    else:
        # "texto" e tipos desconhecidos: passthrough (comportamento de hoje — D-08).
        normalized = raw

    if reason is not None:
        # Parse falhou: marca inválido, preserva bruto, não chuta (D-10/D-11).
        return FieldValidation(
            valid=False, raw_value=raw, normalized_value=None, invalid_reason=reason
        )

    # D-09/V5: regex opcional via fullmatch sobre valor com teto de tamanho.
    if regex is not None:
        if len(raw) > _MAX_REGEX_LEN:
            return FieldValidation(
                valid=False,
                raw_value=raw,
                normalized_value=normalized,
                invalid_reason=f"valor excede o limite de {_MAX_REGEX_LEN} caracteres",
            )
        pattern = re.compile(regex)
        if pattern.fullmatch(raw) is None:
            return FieldValidation(
                valid=False,
                raw_value=raw,
                normalized_value=normalized,
                invalid_reason="valor não casa o padrão (regex)",
            )

    return FieldValidation(
        valid=True, raw_value=raw, normalized_value=normalized, invalid_reason=None
    )

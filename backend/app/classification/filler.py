"""Filler de campos (Fase 4, D-05) — mapeia pares já extraídos → campos do template.

Função PURA de módulo (sem DB, sem IA): pega os pares `dado→valor` que a Fase 3 já
extraiu (`fields_json`) e casa cada `TemplateField` por NOME (case-insensitive,
acentos/espaços normalizados de forma simples). É o passo CUSTO ZERO que preenche
a maioria dos campos antes de qualquer chamada paga — só o que sobra (campos
obrigatórios sem correspondência) alimenta a chamada D-06 (campos faltantes) no
stage.

NÃO chama IA e NÃO valida (validação determinística é o Plan 02 / o stage). O
filler só mapeia e lista o que faltou.
"""

import json
import unicodedata
from dataclasses import dataclass

from app.models.template import TemplateField


@dataclass(frozen=True)
class FillResult:
    """Resultado do mapeamento local pares→campos (D-05).

    - `filled`: lista de `(field_name, raw_value)` — campos casados com um par
      extraído (valor cru, sem normalizar/validar);
    - `missing_required`: nomes dos campos OBRIGATÓRIOS sem par correspondente —
      input da chamada D-06 (campos faltantes) no stage.
    """

    filled: list[tuple[str, str]]
    missing_required: list[str]


def _norm(name: str) -> str:
    """Normaliza um nome p/ comparação: minúsculo, sem acento, espaços colapsados.

    Mantém deliberadamente simples (D-05): casefold + remoção de diacríticos
    (NFKD) + colapso de espaços/underscores. Suficiente para casar 'Número Nota'
    com 'numero nota' / 'numero_nota'.
    """
    decomposed = unicodedata.normalize("NFKD", name or "")
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    collapsed = no_accents.replace("_", " ").casefold()
    return " ".join(collapsed.split())


def _pairs(fields_json: str) -> dict[str, str]:
    """Lê `fields_json` (list-of-pairs) → dict normalizado {nome_norm: raw_value}."""
    out: dict[str, str] = {}
    try:
        parsed = json.loads(fields_json or "[]")
    except (ValueError, TypeError):
        return out
    if not isinstance(parsed, list):
        return out
    for pair in parsed:
        if isinstance(pair, dict) and "key" in pair:
            out[_norm(str(pair["key"]))] = str(pair.get("value", ""))
    return out


def map_fields(
    *, template_fields: list[TemplateField], fields_json: str
) -> FillResult:
    """Casa cada `TemplateField` com o par extraído por nome normalizado (D-05).

    Obrigatório sem correspondência → `missing_required`. Opcional sem
    correspondência é simplesmente omitido (não é faltante). PURA: sem IA, sem
    validação.
    """
    by_name = _pairs(fields_json)
    filled: list[tuple[str, str]] = []
    missing_required: list[str] = []

    for field in template_fields:
        raw = by_name.get(_norm(field.name))
        if raw is not None:
            filled.append((field.name, raw))
        elif field.required:
            missing_required.append(field.name)

    return FillResult(filled=filled, missing_required=missing_required)

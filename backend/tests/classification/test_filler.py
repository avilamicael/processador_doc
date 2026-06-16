"""Testes do `filler` (Fase 4, D-05) — mapeia pares extraídos → campos, custo 0.

Cobre o `<behavior>` do Task 2:
- cada `TemplateField` casa o par extraído por nome (case-insensitive, acento/
  espaço normalizados) → preenche;
- campo obrigatório sem par correspondente → `missing_required` (alimenta D-06);
- sem IA, sem validação (validação é o Plan 02 / o stage).

`TemplateField` é montado em memória; `fields_json` é a string list-of-pairs que a
Extraction grava (key/value/confidence).
"""

import json

from app.classification import filler
from app.models.template import TemplateField


def _field(name: str, *, required: bool = False) -> TemplateField:
    return TemplateField(name=name, required=required)


def _fields_json(pairs: dict[str, str]) -> str:
    return json.dumps(
        [{"key": k, "value": v, "confidence": 1.0} for k, v in pairs.items()]
    )


def test_pares_mapeados_sem_ia() -> None:
    fields = [_field("numero_nota"), _field("valor_total")]
    fj = _fields_json({"numero_nota": "12345", "valor_total": "1.234,56"})
    result = filler.map_fields(template_fields=fields, fields_json=fj)
    filled = dict(result.filled)
    assert filled["numero_nota"] == "12345"
    assert filled["valor_total"] == "1.234,56"
    assert result.missing_required == []


def test_match_case_insensitive_e_acento() -> None:
    fields = [_field("Número Nota")]
    fj = _fields_json({"numero nota": "999"})
    result = filler.map_fields(template_fields=fields, fields_json=fj)
    assert dict(result.filled)["Número Nota"] == "999"


def test_obrigatorio_ausente_vira_missing_required() -> None:
    fields = [_field("numero_nota", required=True), _field("observacao")]
    fj = _fields_json({"observacao": "qualquer"})
    result = filler.map_fields(template_fields=fields, fields_json=fj)
    assert result.missing_required == ["numero_nota"]
    # opcional ausente NÃO entra em missing_required
    assert "observacao" in dict(result.filled)


def test_opcional_ausente_nao_e_faltante() -> None:
    fields = [_field("opcional", required=False)]
    result = filler.map_fields(template_fields=fields, fields_json=_fields_json({}))
    assert result.missing_required == []
    assert result.filled == []

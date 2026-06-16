"""Testes do schema genérico de extração (Fase 3, ponto técnico nº 1).

Garante que `ExtractionResult` é o contrato `text_format` que a Responses API
da OpenAI exige em strict mode:
- `fields` é uma `list[ExtractedField]` (list-of-pairs), NÃO um `dict` aberto —
  strict mode rejeita objetos com chaves arbitrárias (additionalProperties:true).
- o JSON Schema gerado não traz `additionalProperties: true` em objeto algum.

Sem validações de domínio (DV de CNPJ, datas) — isso é Fase 4 (EXT-04 re-escopado).
"""

import pytest
from pydantic import ValidationError

from app.extraction.schema import ExtractedField, ExtractionResult


def _objects(node: object) -> list[dict]:
    """Coleta recursivamente todos os subnós que são objetos JSON Schema (dict)."""
    found: list[dict] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(_objects(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_objects(item))
    return found


def test_extraction_result_valida_com_list_of_pairs() -> None:
    result = ExtractionResult(
        fields=[
            {"key": "cnpj_emitente", "value": "12.345.678/0001-90", "confidence": 0.9},
            {"key": "valor_total", "value": "1.234,56", "confidence": 0.8},
        ],
        full_text="Texto integral lido do documento.",
        doc_type_guess="nota_fiscal",
        doc_type_confidence=0.7,
    )

    assert isinstance(result.fields, list)
    assert all(isinstance(f, ExtractedField) for f in result.fields)
    assert result.fields[0].key == "cnpj_emitente"
    assert result.fields[0].value == "12.345.678/0001-90"
    assert result.fields[1].confidence == 0.8
    assert result.full_text.startswith("Texto integral")
    assert result.doc_type_guess == "nota_fiscal"
    assert result.doc_type_confidence == 0.7


def test_fields_rejeita_dict_bruto() -> None:
    """`fields` como dict aberto (`{nome: valor}`) é o instinto óbvio para
    dado→valor — e exatamente o que strict mode rejeita. O modelo deve recusar."""
    with pytest.raises(ValidationError):
        ExtractionResult(
            fields={"cnpj_emitente": "12.345.678/0001-90"},  # type: ignore[arg-type]
            full_text="...",
            doc_type_guess="desconhecido",
            doc_type_confidence=0.1,
        )


def test_json_schema_sem_additional_properties_true() -> None:
    """Compatibilidade com strict mode: nenhum objeto do JSON Schema gerado pode
    permitir chaves extras (`additionalProperties: true`)."""
    schema = ExtractionResult.model_json_schema()
    for obj in _objects(schema):
        if "additionalProperties" in obj:
            assert obj["additionalProperties"] is not True, obj

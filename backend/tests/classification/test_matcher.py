"""Testes do `matcher` local por sinais (Fase 4, D-02) — função pura, custo 0.

Cobre o `<behavior>` do Task 2:
- sinais presentes na extração → confiança alta (fração presente ~1.0);
- sinais ausentes → confiança baixa;
- `doc_type_guess` casando com `Template.doc_type` soma pontos;
- maior confiança vence (D-03); zona cinzenta entre top-2 → "ambíguo" (precisa IA);
- nenhum sinal/abaixo do piso → não casa (quarentena).

`Template`/`TemplateField` são montados em memória (sem DB) — o matcher recebe os
templates já carregados (função pura de módulo, estilo router.choose).
"""

import json

from app.classification import matcher
from app.models.template import Template


def _tpl(tpl_id: int, *, doc_type: str | None, signals: list[str]) -> Template:
    """Monta um Template em memória (sem persistir) com id e sinais."""
    t = Template(name=f"tpl-{tpl_id}", doc_type=doc_type, signals_json=json.dumps(signals))
    t.id = tpl_id
    return t


def _fields_json(*keys: str) -> str:
    """Serializa pares list-of-pairs com as chaves dadas (como a Extraction grava)."""
    return json.dumps([{"key": k, "value": "x", "confidence": 1.0} for k in keys])


# --- pontuação por sinais ---


def test_sinais_presentes_dao_confianca_alta() -> None:
    tpl = _tpl(1, doc_type="boleto", signals=["linha digitável", "cnpj", "valor"])
    matches = matcher.match_templates(
        fields_json=_fields_json("cnpj", "valor"),
        full_text="Pague este boleto: linha digitável 12345",
        doc_type_guess="desconhecido",
        templates=[tpl],
    )
    assert len(matches) == 1
    # todos os 3 sinais presentes (key OU full_text) → fração ~1.0
    assert matches[0].confidence >= 0.99


def test_sinais_ausentes_dao_confianca_baixa() -> None:
    tpl = _tpl(1, doc_type="boleto", signals=["linha digitável", "cnpj", "valor"])
    matches = matcher.match_templates(
        fields_json=_fields_json("nome", "endereco"),
        full_text="Documento sem nenhum sinal relevante.",
        doc_type_guess="desconhecido",
        templates=[tpl],
    )
    assert matches[0].confidence < 0.5


def test_doc_type_guess_casando_soma_pontos() -> None:
    signals = ["linha digitável", "cnpj", "valor", "vencimento"]
    full_text = "linha digitável e cnpj presentes"
    fields = _fields_json()
    tpl_match = _tpl(1, doc_type="boleto", signals=signals)
    tpl_no_match = _tpl(2, doc_type="nota_fiscal", signals=signals)
    m_with = matcher.match_templates(
        fields_json=fields, full_text=full_text, doc_type_guess="boleto",
        templates=[tpl_match],
    )
    m_without = matcher.match_templates(
        fields_json=fields, full_text=full_text, doc_type_guess="boleto",
        templates=[tpl_no_match],
    )
    # mesma fração de sinais; só muda o doc_type → o que casa pontua mais
    assert m_with[0].confidence > m_without[0].confidence


# --- ordenação e política de desempate ---


def test_maior_confianca_vence() -> None:
    forte = _tpl(1, doc_type="boleto", signals=["linha digitável", "cnpj", "valor"])
    fraco = _tpl(2, doc_type="nota_fiscal", signals=["chave de acesso", "danfe"])
    matches = matcher.match_templates(
        fields_json=_fields_json("cnpj", "valor"),
        full_text="boleto com linha digitável",
        doc_type_guess="boleto",
        templates=[forte, fraco],
    )
    # resultado ordenado: maior confiança primeiro
    assert matches[0].template_id == 1
    assert matches[0].confidence > matches[1].confidence
    decision = matcher.decide(matches, threshold=0.5)
    assert decision.status == "matched"
    assert decision.template_id == 1


def test_zona_cinzenta_marca_ambiguo() -> None:
    # dois templates com sinais quase idênticos e ambos acima do piso → ambíguo
    a = _tpl(1, doc_type=None, signals=["cnpj", "valor"])
    b = _tpl(2, doc_type=None, signals=["cnpj", "valor"])
    matches = matcher.match_templates(
        fields_json=_fields_json("cnpj", "valor"),
        full_text="cnpj e valor presentes",
        doc_type_guess="desconhecido",
        templates=[a, b],
    )
    decision = matcher.decide(matches, threshold=0.5)
    assert decision.status == "ambiguous"
    assert decision.template_id is None


def test_nenhum_sinal_vai_para_quarentena() -> None:
    tpl = _tpl(1, doc_type="boleto", signals=["linha digitável", "cnpj"])
    matches = matcher.match_templates(
        fields_json=_fields_json("nada"),
        full_text="texto irrelevante",
        doc_type_guess="desconhecido",
        templates=[tpl],
    )
    decision = matcher.decide(matches, threshold=0.5)
    assert decision.status == "quarantine"
    assert decision.template_id is None


def test_sem_templates_vai_para_quarentena() -> None:
    decision = matcher.decide(
        matcher.match_templates(
            fields_json=_fields_json("cnpj"),
            full_text="x",
            doc_type_guess="boleto",
            templates=[],
        ),
        threshold=0.5,
    )
    assert decision.status == "quarantine"
    assert decision.template_id is None

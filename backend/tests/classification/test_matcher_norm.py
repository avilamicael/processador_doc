"""Testes de NORMALIZAÇÃO do matcher (Fase 10, D-01/D-02/D-03/D-04/D-09).

Cobre a tolerância MECÂNICA do ramo `texto` via NORMALIZAÇÃO simétrica
(`_normalize_text` aplicada a value E haystack): acento, caixa, quebra de linha
e pontuação deixam de causar quarentena falsa. Sem N-de-M (D-01) e sem mexer no
ramo `regex` (D-03, que continua rodando contra o haystack lowercase-só, NÃO
normalizado). Palavra trocada NÃO é resolvida por normalização (D-04, tradeoff
aceito — fica para a ferramenta de testar sinais).

Também cobre o helper PÚBLICO `evaluate_groups` (D-09): relatório por-grupo e
por-condição que reusa a MESMA preparação de haystack do `match_templates`, base
do preview de sinais do Plano 02.

Os testes que dependem de `_normalize_text`/`evaluate_groups` ficam RED até a
Task 2 (símbolos ainda inexistentes). V7: nada de logar `full_text`/valores.
"""

import json
import time

from app.classification import matcher
from app.models.template import Template

# Valores de borda LOCAIS (não importados do módulo): só para construir casos.
_EXPECTED_MAX_SIGNAL_REGEX_LEN = 512

# Deadline FOLGADO de observação do ReDoS (NÃO é a constante interna do módulo):
# mede o comportamento observável — o matcher TERMINA rápido. Não-flaky.
_REDOS_DEADLINE_S = 2.0


def _tpl(tpl_id: int, *, signals: object) -> Template:
    """Monta um Template em memória (sem persistir) com signals_json arbitrário."""
    t = Template(name=f"tpl-{tpl_id}", doc_type=None, signals_json=json.dumps(signals))
    t.id = tpl_id
    return t


def _confidence(tpl: Template, full_text: str) -> float:
    """Roda o matcher contra um único template e devolve a confiança dele."""
    matches = matcher.match_templates(
        fields_json="[]",
        full_text=full_text,
        doc_type_guess="desconhecido",
        templates=[tpl],
    )
    assert len(matches) == 1
    return matches[0].confidence


# --- D-02: normalização simétrica do ramo texto ---


def test_norm_acento() -> None:
    # sinal sem acento casa haystack ACENTUADO (ambos perdem acento na normalização)
    tpl = _tpl(1, signals=[[{"mode": "texto", "value": "nota fiscal"}]])
    assert _confidence(tpl, "Documento Notá Fiscál emitido") == 1.0


def test_norm_quebra_de_linha() -> None:
    # quebra de linha no meio do termo colapsa para espaço único → casa
    tpl = _tpl(1, signals=[[{"mode": "texto", "value": "nota fiscal"}]])
    assert _confidence(tpl, "cabecalho\nNota\nFiscal\nrodape") == 1.0


def test_norm_caixa() -> None:
    # caixa alta no haystack vira lower → casa
    tpl = _tpl(1, signals=[[{"mode": "texto", "value": "nota fiscal"}]])
    assert _confidence(tpl, "ISTO E UMA NOTA FISCAL ELETRONICA") == 1.0


def test_norm_pontuacao_simetrica_cnpj() -> None:
    # CNPJ com pontuação no sinal E no haystack: ambos viram "12 345 678 0001 99"
    tpl = _tpl(1, signals=[[{"mode": "texto", "value": "12.345.678/0001-99"}]])
    assert _confidence(tpl, "Cliente CNPJ 12.345.678/0001-99 referente a maio") == 1.0


def test_norm_simetria_value_tambem_normalizado() -> None:
    # Prova que o VALUE também é normalizado (não só o haystack):
    # sinal ACENTUADO casa haystack SEM acento — só possível se value perdeu acento.
    tpl_acentuado = _tpl(1, signals=[[{"mode": "texto", "value": "Notá Fiscál"}]])
    assert _confidence(tpl_acentuado, "documento nota fiscal comum") == 1.0
    # e o inverso: sinal SEM acento casa haystack ACENTUADO.
    tpl_sem = _tpl(2, signals=[[{"mode": "texto", "value": "nota fiscal"}]])
    assert _confidence(tpl_sem, "documento Notá Fiscál comum") == 1.0


# --- D-04: palavra trocada NÃO é resolvida por normalização (tradeoff aceito) ---


def test_d04_palavra_trocada_nao_casa() -> None:
    # "da" vs "de" é troca de PALAVRA, não diferença mecânica — normalização NÃO
    # resolve isso (fica para a ferramenta de testar sinais).
    tpl = _tpl(1, signals=[[{"mode": "texto", "value": "natureza da operacao"}]])
    assert _confidence(tpl, "campo natureza de operacao preenchido") == 0.0


# --- D-03: regex intacto (haystack lowercase-só, NÃO normalizado) ---


def test_d03_regex_44_digitos_casa() -> None:
    chave = "7" * 44
    tpl = _tpl(1, signals=[[{"mode": "regex", "value": r"\d{44}"}]])
    assert _confidence(tpl, f"chave {chave} fim") == 1.0
    assert _confidence(tpl, "sem chave 123") == 0.0


def test_d03_regex_roda_contra_haystack_nao_normalizado() -> None:
    # A normalização colapsa pontuação→espaço; o regex NÃO pode ver isso (roda no
    # lowercase-só). Um pattern que casa o PONTO literal deve casar — prova que o
    # ramo regex NÃO recebeu o haystack normalizado (onde o ponto teria sumido).
    tpl = _tpl(1, signals=[[{"mode": "regex", "value": r"12\.345"}]])
    assert _confidence(tpl, "cnpj 12.345.678 aqui") == 1.0
    # se o regex rodasse contra o normalizado ("12 345 678"), o `\.` não casaria.
    tpl_sem_ponto = _tpl(2, signals=[[{"mode": "regex", "value": r"12\.345"}]])
    assert _confidence(tpl_sem_ponto, "valor 12 345 678 sem ponto") == 0.0


# --- D-03: ReDoS/tetos intactos (não-regressão de segurança) ---


def test_d03_redos_termina_no_deadline() -> None:
    pattern = r"(a+)+$"
    tpl = _tpl(1, signals=[[{"mode": "regex", "value": pattern}]])
    full_text = "a" * 40 + "X"
    start = time.monotonic()
    result = _confidence(tpl, full_text)
    elapsed = time.monotonic() - start
    assert elapsed < _REDOS_DEADLINE_S, (
        f"matcher demorou {elapsed:.3f}s — o timeout real de regex não abortou"
    )
    assert result == 0.0


def test_d03_pattern_acima_do_teto() -> None:
    big_pattern = "a" * (_EXPECTED_MAX_SIGNAL_REGEX_LEN + 1)
    tpl = _tpl(1, signals=[[{"mode": "regex", "value": big_pattern}]])
    assert _confidence(tpl, "a" * 50) == 0.0


# --- D-09: helper público evaluate_groups (base do preview do Plano 02) ---


def test_evaluate_groups_relatorio_por_grupo_e_condicao() -> None:
    chave = "5" * 44
    grupo_ok = [
        {"mode": "texto", "value": "nota fiscal"},
        {"mode": "regex", "value": r"\d{44}"},
    ]
    grupo_falha = [{"mode": "texto", "value": "boleto bancario"}]
    groups = [grupo_ok, grupo_falha]
    full_text = f"Documento NOTÁ FISCÁL chave {chave} fim"

    reports = matcher.evaluate_groups(groups, full_text)

    assert len(reports) == 2
    # grupo 1: ambas as condições casam (texto normalizado + regex no lower)
    assert reports[0].matched is True
    assert len(reports[0].conditions) == 2
    assert reports[0].conditions[0].mode == "texto"
    assert reports[0].conditions[0].value == "nota fiscal"
    assert reports[0].conditions[0].matched is True
    assert reports[0].conditions[1].mode == "regex"
    assert reports[0].conditions[1].matched is True
    # grupo 2: a única condição falha → grupo falha
    assert reports[1].matched is False
    assert reports[1].conditions[0].mode == "texto"
    assert reports[1].conditions[0].value == "boleto bancario"
    assert reports[1].conditions[0].matched is False


def test_evaluate_groups_agregado_bate_com_match_templates() -> None:
    # D-09: o agregado de evaluate_groups (algum grupo casou?) tem que bater com a
    # confiança 1.0/0.0 do match_templates — mesma preparação de haystack.
    chave = "3" * 44
    grupo_ok = [{"mode": "regex", "value": r"\d{44}"}]
    grupo_falha = [{"mode": "texto", "value": "inexistente"}]

    # caso casa: full_text com 44 dígitos
    signals = [grupo_ok, grupo_falha]
    full_text_ok = f"texto {chave} fim"
    reports_ok = matcher.evaluate_groups(signals, full_text_ok)
    agregado_ok = any(r.matched for r in reports_ok)
    conf_ok = _confidence(_tpl(1, signals=signals), full_text_ok)
    assert agregado_ok is True
    assert conf_ok == 1.0

    # caso não casa: sem 44 dígitos e sem o texto
    full_text_no = "texto sem chave 123"
    reports_no = matcher.evaluate_groups(signals, full_text_no)
    agregado_no = any(r.matched for r in reports_no)
    conf_no = _confidence(_tpl(2, signals=signals), full_text_no)
    assert agregado_no is False
    assert conf_no == 0.0


# --- _normalize_text: função pura (unit) ---


def test_normalize_text_pura() -> None:
    # acento + caixa + pontuação + espaços/quebras colapsados + strip
    assert matcher._normalize_text("  Notá   Fiscál \n Nº123!  ") == "nota fiscal n123"
    # pontuação vira espaço e colapsa (CNPJ)
    assert matcher._normalize_text("12.345.678/0001-99") == "12 345 678 0001 99"
    # vazio/None-safe
    assert matcher._normalize_text("") == ""

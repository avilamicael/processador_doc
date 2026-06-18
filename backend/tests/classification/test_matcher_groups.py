"""Testes do matcher booleano de grupos E/OU texto|regex (Fase 06.1, D-T1/D-T2).

Cobre o redesign do `matcher` de "fração de termos literais" para **avaliação
booleana de grupos**: OU entre grupos, E dentro do grupo; cada condição é
`texto` (substring case-insensitive) ou `regex` (`re.search` IGNORECASE com tetos
de pattern e de input — falha fechada).

Forma canônica de `signals_json` (definida nesta fase, consumida por 02/03):

    [
      [ {"mode": "texto", "value": "DANFE"}, {"mode": "regex", "value": "\\\\d{44}"} ],
      [ {"mode": "texto", "value": "12.345.678/0001-99"} ]
    ]

Os testes exercitam SOMENTE a API pública `match_templates` (confidence 1.0/0.0).
Não importam helpers internos (`_condition_matches`/`_group_matches`/
`_template_matches`) nem as constantes de teto — os valores de borda são definidos
localmente apenas para construir os casos.
"""

import json

from app.classification import matcher
from app.models.template import Template

# Valores de borda LOCAIS (não importados do módulo): só para construir casos.
# Devem bater com as constantes do matcher na implementação GREEN.
_EXPECTED_MAX_SIGNAL_REGEX_LEN = 512
_EXPECTED_MAX_HAYSTACK_LEN = 200_000


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


# --- E dentro do grupo ---


def test_grupo_todas_condicoes_E() -> None:
    chave = "1" * 44
    grupo = [{"mode": "texto", "value": "DANFE"}, {"mode": "regex", "value": r"\d{44}"}]
    tpl = _tpl(1, signals=[grupo])
    # ambos presentes → casa (E)
    assert _confidence(tpl, f"Documento DANFE chave {chave} fim") == 1.0
    # falta a chave de 44 dígitos → não casa
    assert _confidence(tpl, "Documento DANFE sem chave") == 0.0
    # falta a âncora DANFE → não casa
    assert _confidence(tpl, f"Documento chave {chave} fim") == 0.0


# --- OU entre grupos ---


def test_qualquer_grupo_OU() -> None:
    grupo_nf = [{"mode": "texto", "value": "DANFE"}, {"mode": "regex", "value": r"\d{44}"}]
    grupo_cnpj = [{"mode": "texto", "value": "12.345.678/0001-99"}]
    tpl = _tpl(1, signals=[grupo_nf, grupo_cnpj])
    # bate só no grupo 2 (CNPJ literal) → casa (OU)
    assert _confidence(tpl, "Cliente CNPJ 12.345.678/0001-99 sem danfe") == 1.0
    # bate só no grupo 1 → casa
    assert _confidence(tpl, "DANFE " + "9" * 44) == 1.0
    # não bate em nenhum → não casa
    assert _confidence(tpl, "documento irrelevante") == 0.0


# --- condição texto: substring case-insensitive ---


def test_texto_case_insensitive() -> None:
    tpl = _tpl(1, signals=[[{"mode": "texto", "value": "trylab"}]])
    assert _confidence(tpl, "Relatório do cliente TryLab referente a maio") == 1.0
    assert _confidence(tpl, "Relatório de outro cliente") == 0.0


# --- condição regex: re.search no full_text (NÃO fullmatch — A4) ---


def test_regex_search_no_full_text() -> None:
    chave = "4" * 44
    tpl = _tpl(1, signals=[[{"mode": "regex", "value": r"\d{44}"}]])
    # chave embutida no MEIO do texto deve casar (search, não fullmatch)
    assert _confidence(tpl, f"texto antes {chave} texto depois") == 1.0
    # nenhuma sequência de 44 dígitos → não casa
    assert _confidence(tpl, "texto sem chave 123") == 0.0


# --- regex inválida: falha fechada, sem exceção ---


def test_regex_invalida_falha_fechada() -> None:
    tpl = _tpl(1, signals=[[{"mode": "regex", "value": "("}]])
    # regex inválida não deve propagar exceção e não deve casar
    assert _confidence(tpl, "qualquer ( texto") == 0.0


# --- pattern acima do teto: não compila, não casa ---


def test_regex_pattern_acima_do_teto() -> None:
    # pattern absurdamente longo (> teto do PATTERN) → não casa, sem compilar
    big_pattern = "a" * (_EXPECTED_MAX_SIGNAL_REGEX_LEN + 1)
    tpl = _tpl(1, signals=[[{"mode": "regex", "value": big_pattern}]])
    assert _confidence(tpl, "a" * 50) == 0.0


# --- ReDoS: input cortado pelo teto antes de aplicar a regex ---


def test_redos_nao_trava() -> None:
    # pattern catastrófico contra input longo — o teto de input deve cortar o
    # haystack antes do .search, então termina rápido e não trava o matcher.
    pattern = r"(a+)+$"
    tpl = _tpl(1, signals=[[{"mode": "regex", "value": pattern}]])
    full_text = "a" * (_EXPECTED_MAX_HAYSTACK_LEN + 10_000) + "!"
    # apenas exigimos que termine sem travar/erro; resultado booleano qualquer.
    result = _confidence(tpl, full_text)
    assert result in (0.0, 1.0)


# --- legado: lista plana de strings continua parseável ---


def test_legado_lista_plana_parseavel() -> None:
    # forma antiga: list[str]; cada termo vira 1 grupo OU de 1 condição texto.
    tpl = _tpl(1, signals=["DANFE", "NOTA FISCAL"])
    # "qualquer termo basta" (OU) — bate só com DANFE
    assert _confidence(tpl, "documento DANFE qualquer") == 1.0
    # bate só com NOTA FISCAL
    assert _confidence(tpl, "isto é uma NOTA FISCAL eletrônica") == 1.0
    # nenhum termo presente → não casa
    assert _confidence(tpl, "recibo simples") == 0.0


# --- falha fechada: vazio e grupo vazio não casam ---


def test_grupo_vazio_e_sem_grupos_nao_casam() -> None:
    # signals_json '[]' (sem grupos) → não casa
    sem_grupos = _tpl(1, signals=[])
    assert _confidence(sem_grupos, "qualquer texto") == 0.0
    # grupo vazio '[[]]' → E sobre conjunto vazio NÃO deve casar (falha fechada)
    grupo_vazio = _tpl(2, signals=[[]])
    assert _confidence(grupo_vazio, "qualquer texto") == 0.0

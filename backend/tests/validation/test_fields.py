"""Orquestrador validate_field por tipo (Task 2, Plan 04-02) — D-09/D-10/D-11.

- despacho por field_type (texto/numero/data/moeda/cpf_cnpj/booleano);
- marca válido/inválido SEM bloquear nem levantar (D-10 — gate é Fase 5);
- preserva o valor BRUTO sempre + guarda o normalizado (D-11);
- regex opcional via re.fullmatch sobre valor com teto de tamanho (ReDoS V5/T-04-03).
"""

from app.validation.fields import FieldValidation, validate_field

# --- despacho por tipo + normalização (D-11 guarda bruto + normalizado) ---


def test_data_valida_normaliza_dayfirst():
    r = validate_field(field_type="data", raw="03/04/2026", required=True)
    assert r.valid is True
    assert r.normalized_value == "2026-04-03"
    assert r.raw_value == "03/04/2026"


def test_moeda_normaliza_decimal():
    r = validate_field(field_type="moeda", raw="1.234,56")
    assert r.valid is True
    assert r.normalized_value == "1234.56"


def test_numero_sem_float():
    r = validate_field(field_type="numero", raw="42")
    assert r.valid is True
    assert r.normalized_value == "42"


def test_cpf_cnpj_valido():
    r = validate_field(field_type="cpf_cnpj", raw="11.222.333/0001-81")
    assert r.valid is True
    assert r.normalized_value == "11222333000181"


def test_booleano_reconhece_sim_nao():
    assert validate_field(field_type="booleano", raw="sim").normalized_value == "true"
    assert validate_field(field_type="booleano", raw="não").normalized_value == "false"
    assert validate_field(field_type="booleano", raw="true").normalized_value == "true"


def test_texto_passthrough():
    r = validate_field(field_type="texto", raw="qualquer coisa")
    assert r.valid is True
    assert r.normalized_value == "qualquer coisa"


def test_tipo_desconhecido_passthrough():
    r = validate_field(field_type="tipo_inexistente", raw="x")
    assert r.valid is True
    assert r.normalized_value == "x"


# --- inválido marca SEM levantar + preserva bruto (D-10 + D-11) ---


def test_cpf_cnpj_invalido_bruto_preservado():
    r = validate_field(field_type="cpf_cnpj", raw="11.222.333/0001-80")
    assert r.valid is False
    assert r.invalid_reason  # não-vazio
    assert r.raw_value == "11.222.333/0001-80"  # bruto preservado (D-11)
    assert r.normalized_value is None  # DV falhou, não chuta


def test_data_invalida_normalized_none():
    r = validate_field(field_type="data", raw="não é data")
    assert r.valid is False
    assert r.invalid_reason
    assert r.normalized_value is None
    assert r.raw_value == "não é data"  # bruto preservado mesmo inválido


def test_moeda_invalida_normalized_none():
    r = validate_field(field_type="moeda", raw="xyz")
    assert r.valid is False
    assert r.normalized_value is None


def test_bruto_preservado_quando_invalido():
    # Marcador explícito do AC "-k bruto": o bruto sobrevive a qualquer falha (D-11).
    r = validate_field(field_type="numero", raw="abc")
    assert r.valid is False
    assert r.raw_value == "abc"


# --- obrigatório ausente: marca, NÃO levanta (D-10) ---


def test_obrigatorio_ausente_nao_levanta():
    r = validate_field(field_type="texto", raw=None, required=True)
    assert r.valid is False
    assert r.invalid_reason


def test_obrigatorio_vazio_marca_invalido():
    r = validate_field(field_type="texto", raw="   ", required=True)
    assert r.valid is False


def test_opcional_ausente_valido():
    r = validate_field(field_type="texto", raw=None, required=False)
    assert r.valid is True


# --- regex via fullmatch sobre input limitado (D-09 + ReDoS V5) ---


def test_regex_reprova():
    r = validate_field(field_type="texto", raw="x", regex="^[0-9]+$")
    assert r.valid is False


def test_regex_aprova():
    r = validate_field(field_type="texto", raw="123", regex="^[0-9]+$")
    assert r.valid is True


def test_regex_fullmatch_nao_search():
    # fullmatch: "123abc" NÃO casa ^[0-9]+$ (search casaria o prefixo "123").
    r = validate_field(field_type="texto", raw="123abc", regex="^[0-9]+$")
    assert r.valid is False


def test_regex_valor_acima_do_teto_recusado():
    # Valor acima do teto (4096) é recusado ANTES de aplicar o regex (mitiga ReDoS).
    grande = "1" * 5000
    r = validate_field(field_type="texto", raw=grande, regex="^[0-9]+$")
    assert r.valid is False
    assert r.invalid_reason


# --- forma do resultado ---


def test_resultado_e_field_validation():
    r = validate_field(field_type="texto", raw="x")
    assert isinstance(r, FieldValidation)

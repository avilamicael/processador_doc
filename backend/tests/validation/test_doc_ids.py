"""Casos pt-BR de Módulo 11 CNPJ/CPF + parsers de data e moeda (Task 1, Plan 04-02).

Testa o coração determinístico de EXT-04 (D-09/D-10/D-11) isolado, sem DB nem IA:
- CNPJ/CPF via dígito verificador Módulo 11 PRÓPRIO (dep externa de DV PROIBIDA,
  CLAUDE.md Decisão Crítica 3);
- data pt-BR dd/mm/aaaa SEMPRE dayfirst→ISO (Pitfall 3 — defaults en-US trocam dia↔mês);
- moeda pt-BR '1.234,56'→Decimal '1234.56' (NUNCA float; T-04-05);
- parse falho → None (marca inválido depois, nunca chuta — D-10).
"""

from decimal import Decimal

from app.validation.dates import normalize_date
from app.validation.doc_ids import is_valid_cnpj, is_valid_cpf, normalize_doc_id
from app.validation.money import normalize_money_brl


# --- CNPJ (Módulo 11 próprio) ---


def test_cnpj_valido_com_mascara():
    assert is_valid_cnpj("11.222.333/0001-81") is True


def test_cnpj_valido_so_digitos():
    assert is_valid_cnpj("11222333000181") is True


def test_cnpj_dv_errado():
    assert is_valid_cnpj("11.222.333/0001-80") is False


def test_cnpj_todos_iguais_rejeitado():
    assert is_valid_cnpj("11111111111111") is False


def test_cnpj_tamanho_errado():
    assert is_valid_cnpj("123") is False
    assert is_valid_cnpj("") is False


# --- CPF (Módulo 11 próprio) ---


def test_cpf_valido():
    # 529.982.247-25 é um CPF de exemplo com DV válido conhecido.
    assert is_valid_cpf("529.982.247-25") is True


def test_cpf_dv_errado():
    assert is_valid_cpf("529.982.247-24") is False


def test_cpf_todos_iguais_rejeitado():
    assert is_valid_cpf("11111111111") is False


def test_cpf_tamanho_errado():
    assert is_valid_cpf("123") is False


# --- normalize_doc_id (só dígitos) ---


def test_normalize_doc_id_remove_mascara():
    assert normalize_doc_id("11.222.333/0001-81") == "11222333000181"
    assert normalize_doc_id("529.982.247-25") == "52998224725"


# --- normalize_date (dayfirst→ISO) ---


def test_date_pt_br_dayfirst():
    # 03/04/2026 é 3 de abril (dayfirst), NÃO 4 de março.
    assert normalize_date("03/04/2026") == "2026-04-03"


def test_date_iso_preservado():
    assert normalize_date("2026-04-03") == "2026-04-03"


def test_date_com_espacos():
    assert normalize_date("  03/04/2026  ") == "2026-04-03"


def test_date_lixo_retorna_none():
    assert normalize_date("lixo") is None
    assert normalize_date("") is None


# --- normalize_money_brl (→ Decimal, nunca float) ---


def test_money_milhar_e_decimal():
    assert normalize_money_brl("1.234,56") == "1234.56"


def test_money_com_simbolo():
    assert normalize_money_brl("R$ 2.000,00") == "2000.00"


def test_money_resultado_decimal_parseavel():
    out = normalize_money_brl("1.234,56")
    assert out is not None
    # Tem de ser parseável por Decimal sem erro (sem corrupção de float).
    assert Decimal(out) == Decimal("1234.56")


def test_money_lixo_retorna_none():
    assert normalize_money_brl("abc") is None
    assert normalize_money_brl("") is None

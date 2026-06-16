"""Dígito verificador Módulo 11 PRÓPRIO de CNPJ/CPF + normalização (Fase 4).

Funções PURAS (sem classe, sem DB) — espelham o estilo de `extraction/pdf_io.py`.

CLAUDE.md Decisão Crítica 3: o DV de CNPJ/CPF é algoritmo próprio; dependência
externa (`python-stdnum`, `validate-docbr`, etc.) é PROIBIDA — a especificação é de
domínio público (Módulo 11, Receita Federal) e trivial de implementar.

Disciplina (T-04-05): parse falho → marca inválido depois (D-10), nunca chuta um
valor; aqui isso vira `False` (inválido) — o bruto nunca é perdido pelo chamador.
"""

# Pesos do Módulo 11 do CNPJ (04-RESEARCH.md linhas 313-329).
_CNPJ_W1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
_CNPJ_W2 = [6] + _CNPJ_W1


def normalize_doc_id(raw: str) -> str:
    """Remove máscara de um CNPJ/CPF, devolvendo só os dígitos.

    Ex.: "11.222.333/0001-81" → "11222333000181"; "529.982.247-25" → "52998224725".
    """
    return "".join(ch for ch in raw if ch.isdigit())


def _mod11_dv(digits: str, weights: list[int]) -> int:
    """Calcula um dígito verificador Módulo 11 sobre `digits` com `weights`.

    `s % 11` → DV = 0 se o resto < 2, senão 11 - resto (regra padrão da Receita).
    """
    s = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
    r = s % 11
    return 0 if r < 2 else 11 - r


def is_valid_cnpj(raw: str) -> bool:
    """Valida um CNPJ pelo dígito verificador Módulo 11 próprio.

    Rejeita: tamanho != 14 dígitos e sequências todas-iguais (ex. "11111111111111").
    "11.222.333/0001-81" → True; "11.222.333/0001-80" → False (DV errado).
    """
    digits = normalize_doc_id(raw)
    if len(digits) != 14:
        return False
    if digits == digits[0] * 14:
        return False
    dv1 = _mod11_dv(digits[:12], _CNPJ_W1)
    dv2 = _mod11_dv(digits[:13], _CNPJ_W2)
    return digits[12] == str(dv1) and digits[13] == str(dv2)


def is_valid_cpf(raw: str) -> bool:
    """Valida um CPF pelo dígito verificador Módulo 11 próprio.

    Pesos 10..2 (1º DV) e 11..2 (2º DV). Rejeita tamanho != 11 e todos-iguais.
    "529.982.247-25" → True; "529.982.247-24" → False (DV errado).
    """
    digits = normalize_doc_id(raw)
    if len(digits) != 11:
        return False
    if digits == digits[0] * 11:
        return False
    w1 = list(range(10, 1, -1))  # 10..2 (9 pesos)
    w2 = list(range(11, 1, -1))  # 11..2 (10 pesos)
    dv1 = _mod11_dv(digits[:9], w1)
    dv2 = _mod11_dv(digits[:10], w2)
    return digits[9] == str(dv1) and digits[10] == str(dv2)

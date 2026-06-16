"""Parser de moeda pt-BR → Decimal (Fase 4). Função PURA, sem DB.

T-04-05: moeda usa `Decimal`, NUNCA float — float corrompe valores monetários
silenciosamente (0.1 + 0.2 != 0.3). O formato pt-BR usa `.` como separador de
milhar e `,` como decimal: "1.234,56" → "1234.56".

Disciplina D-10: parse falho → None (marca inválido depois, nunca chuta um valor).
"""

from decimal import Decimal, InvalidOperation


def normalize_money_brl(raw: str) -> str | None:
    """Normaliza moeda pt-BR ("1.234,56", "R$ 2.000,00") para string Decimal-parseável.

    Mantém só dígitos e os separadores `,.-`, remove o milhar `.` e troca `,`→`.`,
    então valida via `Decimal` e devolve `str(Decimal(...))`:
    - "1.234,56" → "1234.56"; "R$ 2.000,00" → "2000.00";
    - "abc"/"" → None (D-10, nunca chuta).
    O retorno é sempre parseável por `Decimal` sem erro de float (T-04-05).
    """
    if raw is None:
        return None
    kept = "".join(ch for ch in raw if ch.isdigit() or ch in ",.-")
    if not kept:
        return None
    normalized = kept.replace(".", "").replace(",", ".")
    try:
        return str(Decimal(normalized))
    except (InvalidOperation, ValueError):
        return None

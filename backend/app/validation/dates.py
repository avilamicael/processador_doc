"""Parser de data pt-BR → ISO (Fase 4). Função PURA, sem DB.

Pitfall 3 (04-RESEARCH.md): os defaults en-US do dateutil trocam dia↔mês em datas
ambíguas (03/04 viraria 4 de março). Por isso `dayfirst=True` é OBRIGATÓRIO —
03/04/2026 é 3 de abril.

Disciplina D-10: parse falho → None (marca inválido depois, nunca chuta uma data
errada — T-04-05).
"""

from datetime import date

from dateutil import parser as dtparser


def normalize_date(raw: str) -> str | None:
    """Normaliza uma data pt-BR (dd/mm/aaaa, ISO, etc.) para ISO YYYY-MM-DD.

    Estratégia em duas etapas para resolver a ambiguidade dia↔mês (Pitfall 3):
    1. ISO YYYY-MM-DD é NÃO-ambíguo → `date.fromisoformat` o preserva fielmente
       ("2026-04-03" → "2026-04-03"); aplicar `dayfirst=True` aqui leria o `04`
       como dia e corromperia a data.
    2. Demais formatos pt-BR (dd/mm/aaaa) → dateutil com `dayfirst=True`
       OBRIGATÓRIO: "03/04/2026" → "2026-04-03" (3 de abril, não 4 de março).

    Entrada inválida/vazia → None (D-10, nunca chuta uma data errada — T-04-05).
    """
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        pass
    try:
        return dtparser.parse(s, dayfirst=True).date().isoformat()
    except (ValueError, OverflowError):
        return None

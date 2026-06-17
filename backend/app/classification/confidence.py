"""Indicador determinístico de QUALIDADE DE EXTRAÇÃO (Fase 5, REV-01 / D-01 / D-04).

Função PURA — sem DB, sem IA, sem import de SQLAlchemy — derivada do laço de
validação do `stage.py` (que produz `FilledField.valid` por campo). Isolável e
testável diretamente (`tests/classification/test_confidence.py`).

O score é a **fração de campos OBRIGATÓRIOS válidos** (D-01): a OpenAI não expõe
confiança por campo, então a confiança do produto é derivada das validações
determinísticas (required/regex) que já rodam pós-extração. `has_invalid_required`
força revisão humana mesmo quando o score numérico é alto (D-04): qualquer
obrigatório inválido é motivo de revisão.

Convenção sem obrigatórios → `(1.0, False)`: se o template não tem campos
obrigatórios, não há o que revisar por validação determinística.
"""

from collections.abc import Iterable
from typing import Protocol


class _FilledFieldLike(Protocol):
    """Forma mínima consumida de um campo preenchido (pato-tipado)."""

    field_name: str
    valid: bool


class _TemplateFieldLike(Protocol):
    """Forma mínima consumida de um campo de template (pato-tipado)."""

    name: str
    required: bool


def compute_confidence(
    filled_fields: Iterable[_FilledFieldLike],
    template_fields: Iterable[_TemplateFieldLike],
) -> tuple[float, bool]:
    """Retorna `(score 0.0-1.0, has_invalid_required)`. D-01 / D-04.

    - `score`: fração de campos obrigatórios cujo `valid` é True.
    - `has_invalid_required`: True se algum obrigatório é inválido ou ausente.
    - Sem campos obrigatórios → `(1.0, False)` (nada a revisar por validação).
    - Campo obrigatório AUSENTE em `filled_fields` conta como inválido
      (`valid_by_name.get(name, False)` == False).
    - Campos NÃO obrigatórios não afetam o score nem o flag.
    """
    required = [f for f in template_fields if f.required]
    if not required:
        return 1.0, False
    valid_by_name = {ff.field_name: ff.valid for ff in filled_fields}
    valid_count = sum(1 for f in required if valid_by_name.get(f.name, False))
    has_invalid_required = valid_count < len(required)
    return valid_count / len(required), has_invalid_required

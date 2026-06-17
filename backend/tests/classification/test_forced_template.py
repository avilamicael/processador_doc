"""Scaffold Wave 0 — caminho forced_template_id do classify_stage (Fase 5, Plan 02).

Cobre (preenchido no Plan 02):
- `classify_stage(..., forced_template_id=N)` pula matcher/decide/disambiguate e
  casa o template forçado direto (caminho do reclassify humano, D-09);
- template forçado inexistente → ValueError;
- `confidence` (do matcher) fica None quando o template é forçado manualmente.

ARQUIVO + fixtures devem EXISTIR e a coleta passar agora (Wave 0). Corpos
`pytest.mark.skip` até o Plan 02 adicionar o parâmetro `forced_template_id` à
assinatura do `classify_stage`.
"""

import pytest
from sqlalchemy import Engine

from app.classification.stage import classify_stage  # noqa: F401  (prova o seam)
from app.storage.db import get_session  # noqa: F401


@pytest.mark.skip(reason="forced_template_id implementado no Plan 02")
def test_forced_template_skips_matcher(schema_engine: Engine) -> None:
    """forced_template_id casa o template direto, sem chamar matcher/IA."""


@pytest.mark.skip(reason="forced_template_id implementado no Plan 02")
def test_forced_template_inexistente_raises(schema_engine: Engine) -> None:
    """Template forçado inexistente → ValueError."""


@pytest.mark.skip(reason="forced_template_id implementado no Plan 02")
def test_forced_template_confidence_none(schema_engine: Engine) -> None:
    """Sem score de matcher quando o template é forçado manualmente (confidence None)."""

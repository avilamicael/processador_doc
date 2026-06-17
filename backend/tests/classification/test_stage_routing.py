"""Scaffold Wave 0 — roteamento de estado do classify_stage (Fase 5, Plan 02).

Cobre (preenchido no Plan 02):
- roteamento EM_REVISAO vs estado-pronto (PROCESSANDO + last_completed_step
  "classificado") segundo `review_confidence_threshold` e `has_invalid_required`;
- persistência de `confidence_score` em `classification_results`.

Este ARQUIVO + fixtures devem EXISTIR e a coleta passar agora (Wave 0). Os corpos
ainda não cobertos ficam `pytest.mark.skip` até o Plan 02 implementar o ramo de
roteamento no `stage.py`. Importa `classify_stage` (prova que o seam existe) e usa
a fixture `schema_engine` (DB com schema via create_all).
"""

import pytest
from sqlalchemy import Engine

from app.classification.stage import classify_stage  # noqa: F401  (prova o seam)
from app.storage.db import get_session  # noqa: F401


@pytest.mark.skip(reason="roteamento EM_REVISAO implementado no Plan 02")
def test_routes_to_em_revisao_below_threshold(schema_engine: Engine) -> None:
    """Score < review_confidence_threshold → transita para EM_REVISAO."""


@pytest.mark.skip(reason="roteamento estado-pronto implementado no Plan 02")
def test_routes_to_ready_above_threshold(schema_engine: Engine) -> None:
    """Score >= threshold e sem obrigatório inválido → PROCESSANDO+classificado
    (NUNCA CONCLUIDO — Open Q1 resolvida; CONCLUIDO só via approve humano)."""


@pytest.mark.skip(reason="has_invalid_required força revisão — Plan 02")
def test_invalid_required_forces_em_revisao(schema_engine: Engine) -> None:
    """Obrigatório inválido força EM_REVISAO mesmo com score alto (D-04)."""


@pytest.mark.skip(reason="persistência de confidence_score — Plan 02")
def test_persists_confidence_score(schema_engine: Engine) -> None:
    """confidence_score é gravado em classification_results no commit atômico."""

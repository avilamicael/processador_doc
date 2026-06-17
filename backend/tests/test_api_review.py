"""Scaffold Wave 0 — endpoints de revisão da Fase 5 (Plan 03).

Cobre (preenchido no Plan 03) os 4 endpoints de ação sobre documentos em revisão:
- POST /documents/{id}/retry      (FALHA→PROCESSANDO, reenfileira o step)
- POST /documents/{id}/reclassify (QUARENTENA→PROCESSANDO, forced_template_id;
  apaga CR de quarentena ANTES — Pitfall 3)
- PATCH /documents/{id}/fields/{field_name} (revalida SEM IA, manually_corrected=True,
  recalcula confidence_score — Pitfall 4)
- POST /documents/{id}/approve    (EM_REVISAO→CONCLUIDO; guard obrigatórios válidos)

Este ARQUIVO + a fixture `client` (sobre `schema_engine`) devem EXISTIR e coletar
agora (Wave 0). Os corpos ficam `pytest.mark.skip` até o Plan 03 criar os
endpoints. Reusa o molde da fixture de `test_api_documents.py` e o respx de
`tests/classification/conftest.py` (prova sem-IA no patch).
"""

import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.main import app
from app.storage.db import get_session  # noqa: F401


@pytest.fixture
def client(schema_engine: Engine) -> Iterator[TestClient]:
    """TestClient sobre o app com `app.state.engine` apontando para o schema de teste."""
    previous = getattr(app.state, "engine", None)
    app.state.engine = schema_engine
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.state.engine = previous


@pytest.mark.skip(reason="endpoint /retry implementado no Plan 03")
def test_retry_non_failed_returns_409(client: TestClient) -> None:
    """retry de documento que não está em FALHA → 409 (transição fora da allowlist)."""


@pytest.mark.skip(reason="endpoint /reclassify implementado no Plan 03")
def test_reclassify_deletes_cr_and_requeues(client: TestClient) -> None:
    """reclassify apaga o CR de quarentena e reenfileira (não no-op da idempotência)."""


@pytest.mark.skip(reason="endpoint PATCH /fields implementado no Plan 03")
def test_patch_field_revalidates_without_ai(client: TestClient) -> None:
    """patch revalida o campo, marca manually_corrected e NÃO chama a IA (respx==0)."""


@pytest.mark.skip(reason="endpoint /approve implementado no Plan 03")
def test_approve_blocks_invalid_required_then_succeeds(client: TestClient) -> None:
    """approve → 409 com obrigatório inválido; → 200 (CONCLUIDO) após a correção."""

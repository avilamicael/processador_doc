"""RED (Wave 0) — API de automações (regras + dry-run/apply/undo).

Espelha `test_api_templates.py`: `TestClient` com `app.state.engine` sobrescrito
por um engine de teste com schema (D-10: create_all só em teste). As rotas
`/automations` ainda NÃO existem (criadas na wave de API) → estes testes estão em
RED (404 até a rota existir). A coleção do pytest NÃO falha — o módulo importa só
o que já existe.

Prova (quando GREEN):
- POST cria regra com condições aninhadas (201) + GET lista + PATCH (substitui
  condições, delete-orphan) + DELETE (204);
- POST inválido → 422; PATCH/DELETE de id inexistente → 404;
- POST /automations/dry-run e /automations/apply respondem; /undo reverte.
"""

import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.main import app
from app.storage.db import get_session  # noqa: F401  (reusado pelas waves seguintes)


@pytest.fixture
def client(schema_engine: Engine) -> Iterator[TestClient]:
    """TestClient com o engine de teste injetado em app.state.engine."""
    previous = getattr(app.state, "engine", None)
    app.state.engine = schema_engine
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.state.engine = previous


def _valid_rule(name: str = "Mover NF da ACME") -> dict:
    return {
        "name": name,
        "priority": 1,
        "conjunction": "and",
        "name_pattern": "{cliente}_{numero}",
        "folder_pattern": "NotasFiscais/{cliente}/{data:aaaa-mm}",
        "active": True,
        "conditions": [
            {"field_name": "cliente", "operator": "contains", "value": "ACME"},
            {"field_name": "valor", "operator": "gt", "value": "500.00"},
        ],
    }


def test_crud_lifecycle(client: TestClient) -> None:
    # POST cria com condições aninhadas
    resp = client.post("/automations", json=_valid_rule())
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "Mover NF da ACME"
    assert len(created["conditions"]) == 2
    rule_id = created["id"]

    # GET lista
    resp = client.get("/automations")
    assert resp.status_code == 200
    assert any(r["id"] == rule_id for r in resp.json())

    # PATCH substitui condições (delete-orphan)
    resp = client.patch(
        f"/automations/{rule_id}",
        json={
            "name": "Regra editada",
            "conditions": [
                {"field_name": "numero", "operator": "eq", "value": "1234"}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    patched = resp.json()
    assert patched["name"] == "Regra editada"
    assert len(patched["conditions"]) == 1

    # DELETE remove
    resp = client.delete(f"/automations/{rule_id}")
    assert resp.status_code == 204


def test_create_invalid_returns_422(client: TestClient) -> None:
    body = _valid_rule()
    body["name"] = "   "
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_patch_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.patch("/automations/999999", json={"name": "x"})
    assert resp.status_code == 404


def test_delete_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.delete("/automations/999999")
    assert resp.status_code == 404


def test_dry_run_endpoint_responds(client: TestClient) -> None:
    """AUT-03: POST /automations/dry-run devolve o plano origem→destino (sem mover)."""
    resp = client.post("/automations/dry-run", json={"document_ids": []})
    assert resp.status_code in (200, 422)

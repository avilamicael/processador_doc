"""GREEN — API de automações (CRUD aninhado de pipeline/steps/filtros + dry-run/apply/undo).

Espelha `test_api_templates.py`: `TestClient` com `app.state.engine` sobrescrito por
um engine de teste com schema. Prova:
- POST cria pipeline com steps + filtros aninhados (201) + GET lista + GET por id +
  PATCH (substitui steps, delete-orphan) + DELETE (204, cascade);
- 422: action_type/filter_type/operator inválido; param obrigatório faltante por tipo;
- 404: pipeline ausente (GET/PATCH/DELETE);
- dry-run / apply / undo respondem.
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


def _valid_pipeline(name: str = "Organizar NFs") -> dict:
    return {
        "name": name,
        "active": True,
        "steps": [
            {
                "action_type": "identify_type",
                "params": {"template_id": 1},
                "filters": [],
            },
            {
                "action_type": "rename",
                "params": {"name_pattern": "{cliente}_{numero}"},
                "conjunction": "and",
                "filters": [
                    {
                        "filter_type": "field",
                        "field_name": "cliente",
                        "operator": "contains",
                        "value": "ACME",
                    },
                    {"filter_type": "extension", "operator": "eq", "value": ".pdf"},
                ],
            },
            {
                "action_type": "move",
                "params": {"folder_pattern": "NotasFiscais/{cliente}"},
                "filters": [],
            },
        ],
    }


def test_crud_lifecycle(client: TestClient) -> None:
    # POST cria pipeline com steps + filtros aninhados
    resp = client.post("/automations", json=_valid_pipeline())
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "Organizar NFs"
    assert len(created["steps"]) == 3
    # Steps em ordem de position; o segundo tem 2 filtros.
    assert created["steps"][0]["action_type"] == "identify_type"
    assert len(created["steps"][1]["filters"]) == 2
    pid = created["id"]

    # GET lista + GET por id
    resp = client.get("/automations")
    assert resp.status_code == 200
    assert any(p["id"] == pid for p in resp.json())

    resp = client.get(f"/automations/{pid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == pid

    # PATCH substitui steps (delete-orphan)
    resp = client.patch(
        f"/automations/{pid}",
        json={
            "name": "Pipeline editado",
            "steps": [
                {
                    "action_type": "route",
                    "params": {"target": "em_revisao"},
                    "filters": [],
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    patched = resp.json()
    assert patched["name"] == "Pipeline editado"
    assert len(patched["steps"]) == 1
    assert patched["steps"][0]["action_type"] == "route"

    # DELETE remove (cascade)
    resp = client.delete(f"/automations/{pid}")
    assert resp.status_code == 204
    resp = client.get(f"/automations/{pid}")
    assert resp.status_code == 404


def test_create_blank_name_returns_422(client: TestClient) -> None:
    body = _valid_pipeline()
    body["name"] = "   "
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_invalid_action_type_returns_422(client: TestClient) -> None:
    body = _valid_pipeline()
    body["steps"] = [{"action_type": "explode", "params": {}, "filters": []}]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_invalid_filter_type_returns_422(client: TestClient) -> None:
    body = _valid_pipeline()
    body["steps"] = [
        {
            "action_type": "rename",
            "params": {"name_pattern": "{cliente}"},
            "filters": [{"filter_type": "xpto", "operator": "eq", "value": "x"}],
        }
    ]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_invalid_operator_returns_422(client: TestClient) -> None:
    body = _valid_pipeline()
    body["steps"] = [
        {
            "action_type": "rename",
            "params": {"name_pattern": "{cliente}"},
            "filters": [
                {
                    "filter_type": "field",
                    "field_name": "cliente",
                    "operator": "regex",
                    "value": "x",
                }
            ],
        }
    ]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_missing_required_param_returns_422(client: TestClient) -> None:
    # move sem folder_pattern → 422 (param obrigatório por tipo, D-13).
    body = _valid_pipeline()
    body["steps"] = [{"action_type": "move", "params": {}, "filters": []}]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_invalid_route_target_returns_422(client: TestClient) -> None:
    body = _valid_pipeline()
    body["steps"] = [
        {"action_type": "route", "params": {"target": "lixeira"}, "filters": []}
    ]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_identify_file_gate_accepts_extensions(client: TestClient) -> None:
    """D-17: action_type 'identify_file' com params.extensions é aceito (201) e
    persiste as extensões digitadas."""
    body = _valid_pipeline("Gate por extensão")
    body["steps"] = [
        {
            "action_type": "identify_file",
            "params": {"extensions": [".pdf", "xlsx"]},
            "filters": [],
        },
        {
            "action_type": "move",
            "params": {"folder_pattern": "NF"},
            "filters": [],
        },
    ]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 201, resp.text
    steps = resp.json()["steps"]
    assert steps[0]["action_type"] == "identify_file"
    assert steps[0]["params"]["extensions"] == [".pdf", "xlsx"]


def test_create_identify_file_without_extensions_returns_422(client: TestClient) -> None:
    """D-17: 'identify_file' sem extensões → 422 (param obrigatório)."""
    body = _valid_pipeline()
    body["steps"] = [
        {"action_type": "identify_file", "params": {}, "filters": []}
    ]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_identify_file_empty_extensions_returns_422(client: TestClient) -> None:
    """D-17: 'identify_file' com extensões em branco → 422."""
    body = _valid_pipeline()
    body["steps"] = [
        {
            "action_type": "identify_file",
            "params": {"extensions": ["  ", ""]},
            "filters": [],
        }
    ]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_pipeline_without_route_is_ok(client: TestClient) -> None:
    """D-22: pipelines sem nenhuma etapa 'route' funcionam (route não é obrigatório)."""
    body = _valid_pipeline("Sem route")
    # _valid_pipeline já não usa route; confirma criação 201 e ausência de route.
    resp = client.post("/automations", json=body)
    assert resp.status_code == 201, resp.text
    actions = [s["action_type"] for s in resp.json()["steps"]]
    assert "route" not in actions


def test_patch_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.patch("/automations/999999", json={"name": "x"})
    assert resp.status_code == 404


def test_delete_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.delete("/automations/999999")
    assert resp.status_code == 404


def test_dry_run_endpoint_responds(client: TestClient) -> None:
    """AUT-03: POST /automations/dry-run devolve o preview (sem mover)."""
    resp = client.post("/automations/dry-run", json={"document_ids": []})
    assert resp.status_code == 200, resp.text
    assert "rows" in resp.json()


def test_apply_without_ids_returns_422(client: TestClient) -> None:
    resp = client.post("/automations/apply", json={})
    assert resp.status_code == 422


def test_undo_without_target_returns_422(client: TestClient) -> None:
    resp = client.post("/automations/undo", json={})
    assert resp.status_code == 422

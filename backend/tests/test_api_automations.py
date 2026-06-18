"""API de automações — CRUD com condições/ações + dry-run/apply/undo (MODELO FINAL).

Espelha `test_api_templates.py`: `TestClient` com `app.state.engine` sobrescrito por
um engine de teste com schema. Prova:
- POST cria automação com conditions[] + actions[] aninhados (201) + GET lista + GET
  por id + PATCH (substitui coleções, delete-orphan) + DELETE (204, cascade);
- 422: action_type/field/operator inválido; param obrigatório faltante por ação;
- 404: automação ausente (GET/PATCH/DELETE);
- ordem entre automações (position) preservada na listagem;
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


def _valid_automation(name: str = "Organizar NFs", position: int = 0) -> dict:
    return {
        "name": name,
        "active": True,
        "position": position,
        "conditions": [
            {"field": "source_folder", "operator": "eq", "value": "Downloads"},
            {"field": "extension", "operator": "eq", "value": ".pdf"},
            {
                "field": "field",
                "field_name": "cliente",
                "operator": "contains",
                "value": "ACME",
            },
        ],
        "actions": [
            {"action_type": "rename", "params": {"name_pattern": "{cliente}_{numero}"}},
            {"action_type": "move", "params": {"dest_folder": "NotasFiscais/{cliente}"}},
        ],
    }


def test_crud_lifecycle(client: TestClient) -> None:
    # POST cria automação com conditions + actions aninhadas
    resp = client.post("/automations", json=_valid_automation())
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "Organizar NFs"
    assert len(created["conditions"]) == 3
    assert len(created["actions"]) == 2
    # Ações em ordem de position.
    assert created["actions"][0]["action_type"] == "rename"
    assert created["actions"][1]["action_type"] == "move"
    aid = created["id"]

    # GET lista + GET por id
    resp = client.get("/automations")
    assert resp.status_code == 200
    assert any(a["id"] == aid for a in resp.json())

    resp = client.get(f"/automations/{aid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == aid

    # PATCH substitui conditions/actions (delete-orphan)
    resp = client.patch(
        f"/automations/{aid}",
        json={
            "name": "Automação editada",
            "conditions": [
                {"field": "extension", "operator": "eq", "value": ".xlsx"}
            ],
            "actions": [
                {"action_type": "move", "params": {"dest_folder": "Planilhas"}}
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    patched = resp.json()
    assert patched["name"] == "Automação editada"
    assert len(patched["conditions"]) == 1
    assert len(patched["actions"]) == 1
    assert patched["actions"][0]["action_type"] == "move"

    # DELETE remove (cascade)
    resp = client.delete(f"/automations/{aid}")
    assert resp.status_code == 204
    resp = client.get(f"/automations/{aid}")
    assert resp.status_code == 404


def test_list_ordered_by_position(client: TestClient) -> None:
    """D-25: a listagem reflete a ordem de `position` (a primeira que casa vence)."""
    client.post("/automations", json=_valid_automation("Genérica", position=5))
    client.post("/automations", json=_valid_automation("Específica", position=1))
    resp = client.get("/automations")
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert names.index("Específica") < names.index("Genérica")


def test_create_blank_name_returns_422(client: TestClient) -> None:
    body = _valid_automation()
    body["name"] = "   "
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_invalid_action_type_returns_422(client: TestClient) -> None:
    body = _valid_automation()
    body["actions"] = [{"action_type": "explode", "params": {}}]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_route_action_rejected(client: TestClient) -> None:
    """D-22: 'route' não existe no v1 → 422."""
    body = _valid_automation()
    body["actions"] = [{"action_type": "route", "params": {"target": "em_revisao"}}]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_invalid_condition_field_returns_422(client: TestClient) -> None:
    body = _valid_automation()
    body["conditions"] = [{"field": "xpto", "operator": "eq", "value": "x"}]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_invalid_operator_returns_422(client: TestClient) -> None:
    body = _valid_automation()
    body["conditions"] = [
        {"field": "field", "field_name": "cliente", "operator": "regex", "value": "x"}
    ]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_rename_without_pattern_returns_422(client: TestClient) -> None:
    body = _valid_automation()
    body["actions"] = [{"action_type": "rename", "params": {}}]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_move_without_dest_returns_422(client: TestClient) -> None:
    body = _valid_automation()
    body["actions"] = [{"action_type": "move", "params": {}}]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_without_conditions_or_actions_is_ok(client: TestClient) -> None:
    """Automação em branco (sem condições/ações) é criável — a UI cria e o usuário
    preenche depois. (O executor trata sem-condições como no-match.)"""
    resp = client.post(
        "/automations",
        json={"name": "Em branco", "conditions": [], "actions": []},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["conditions"] == []
    assert body["actions"] == []


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


# --------------------------------------------------------------------------- #
# Fase 06.2 — ação COPIAR: validação (espelha move) + dry-run discrimina saída #
# --------------------------------------------------------------------------- #


def test_create_copy_without_dest_returns_422(client: TestClient) -> None:
    """V5: ação 'copy' exige params.dest_folder (espelha 'move')."""
    body = _valid_automation()
    body["actions"] = [{"action_type": "copy", "params": {}}]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 422, resp.text


def test_create_copy_with_dest_returns_201(client: TestClient) -> None:
    """Ação 'copy' com dest_folder é aceita (action_type válido + param presente)."""
    body = _valid_automation()
    body["actions"] = [
        {"action_type": "copy", "params": {"dest_folder": "Arquivo/{cliente}"}}
    ]
    resp = client.post("/automations", json=body)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["actions"][0]["action_type"] == "copy"
    assert created["actions"][0]["params"]["dest_folder"] == "Arquivo/{cliente}"


def _seed_ready_doc(engine: Engine) -> int:
    """Semeia um Document PROCESSANDO+classificado pronto para o dry-run do endpoint."""
    from app.models.classification import ClassificationResult, FilledField
    from app.models.document import Document
    from app.models.enums import DocState
    from app.models.template import Template, TemplateField
    from app.storage.db import get_session

    with get_session(engine) as session:
        template = Template(name="NF", doc_type="Fiscal")
        template.fields = [TemplateField(name="cliente", field_type="texto")]
        session.add(template)
        session.flush()
        doc = Document(
            content_hash="b" * 64,
            original_filename="entrada.pdf",
            state=DocState.PROCESSANDO,
            last_completed_step="classificado",
        )
        session.add(doc)
        session.flush()
        cr = ClassificationResult(
            document_id=doc.id, template_id=template.id, confidence=0.95
        )
        cr.filled_fields = [
            FilledField(
                field_name="cliente",
                raw_value="ACME",
                normalized_value="ACME",
                valid=True,
            )
        ]
        session.add(cr)
        session.commit()
        return doc.id


def test_dry_run_copy_move_emits_row_per_output(
    client: TestClient, schema_engine: Engine
) -> None:
    """Dry-run de copy+move emite UMA linha de cópia (não remove original) E uma de
    move para o mesmo document_id, com discriminador action_kind/removes_original."""
    doc_id = _seed_ready_doc(schema_engine)
    client.post(
        "/automations",
        json={
            "name": "Copiar e mover",
            "conditions": [{"field": "extension", "operator": "eq", "value": ".pdf"}],
            "actions": [
                {"action_type": "copy", "params": {"dest_folder": "Arquivo"}},
                {"action_type": "move", "params": {"dest_folder": "Processados"}},
            ],
        },
    )
    resp = client.post("/automations/dry-run", json={"document_ids": [doc_id]})
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    same_doc = [r for r in rows if r["document_id"] == doc_id]
    kinds = {r["action_kind"] for r in same_doc}
    assert "copy" in kinds
    assert "move" in kinds
    copy_row = next(r for r in same_doc if r["action_kind"] == "copy")
    move_row = next(r for r in same_doc if r["action_kind"] == "move")
    assert copy_row["removes_original"] is False
    assert move_row["removes_original"] is True

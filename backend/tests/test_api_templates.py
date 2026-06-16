"""API de templates — CRUD schema-first (Plano 04-04 Task 1).

Usa `TestClient` sobre o app com `app.state.engine` sobrescrito por um engine de
teste com schema (D-10: create_all só em teste). Espelha
`test_api_watched_folders.py`. Prova:
- POST cria template com campos aninhados (201) + GET lista + GET detalhe + PATCH
  edita (incl. substituição de campos) + DELETE remove (204)
- POST com name duplicado → 409 (UNIQUE de templates.name)
- POST sem campos → 422; campo sem nome → 422; name em branco → 422
- DELETE de template NÃO apaga classificações já feitas (D-03 / SET NULL)
- O endpoint NÃO compila/executa a regex do operador (T-04-10) — guardada como string
"""

import warnings
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, select

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.main import app
from app.models.classification import ClassificationResult
from app.models.document import Document
from app.models.template import Template
from app.storage.db import get_session


@pytest.fixture
def client(schema_engine: Engine) -> Iterator[TestClient]:
    """TestClient com o engine de teste injetado em app.state.engine."""
    previous = getattr(app.state, "engine", None)
    app.state.engine = schema_engine
    # NÃO entra no `with TestClient` (que dispararia o lifespan e subiria
    # watcher/worker reais); instancia direto para exercitar só as rotas.
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.state.engine = previous


def _valid_body(name: str = "Nota Fiscal") -> dict:
    return {
        "name": name,
        "doc_type": "Fiscal",
        "signals": ["linha digitável", "CNPJ"],
        "fields": [
            {
                "name": "CNPJ emitente",
                "field_type": "cpf_cnpj",
                "required": True,
                "regex": r"\d{14}",
                "hint": "número após o rótulo CNPJ",
            },
            {"name": "Número da nota", "field_type": "numero"},
        ],
    }


def test_crud_lifecycle(client: TestClient) -> None:
    # POST cria com campos aninhados
    resp = client.post("/templates", json=_valid_body())
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "Nota Fiscal"
    assert created["doc_type"] == "Fiscal"
    assert created["signals"] == ["linha digitável", "CNPJ"]
    assert len(created["fields"]) == 2
    cnpj = next(f for f in created["fields"] if f["name"] == "CNPJ emitente")
    assert cnpj["field_type"] == "cpf_cnpj"
    assert cnpj["required"] is True
    assert cnpj["regex"] == r"\d{14}"
    assert cnpj["hint"] == "número após o rótulo CNPJ"
    template_id = created["id"]

    # GET lista
    resp = client.get("/templates")
    assert resp.status_code == 200
    assert any(t["id"] == template_id for t in resp.json())

    # GET detalhe
    resp = client.get(f"/templates/{template_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == template_id
    assert len(resp.json()["fields"]) == 2

    # PATCH edita nome/sinais e SUBSTITUI a lista de campos
    resp = client.patch(
        f"/templates/{template_id}",
        json={
            "name": "NF-e",
            "signals": ["chave de acesso"],
            "fields": [{"name": "Chave de acesso", "field_type": "texto"}],
        },
    )
    assert resp.status_code == 200, resp.text
    patched = resp.json()
    assert patched["name"] == "NF-e"
    assert patched["signals"] == ["chave de acesso"]
    assert len(patched["fields"]) == 1
    assert patched["fields"][0]["name"] == "Chave de acesso"

    # DELETE remove
    resp = client.delete(f"/templates/{template_id}")
    assert resp.status_code == 204
    resp = client.get(f"/templates/{template_id}")
    assert resp.status_code == 404


def test_get_detail_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.get("/templates/999999")
    assert resp.status_code == 404


def test_duplicate_name_returns_409(client: TestClient) -> None:
    first = client.post("/templates", json=_valid_body("Boleto"))
    assert first.status_code == 201
    second = client.post("/templates", json=_valid_body("Boleto"))
    assert second.status_code == 409, second.text


def test_no_fields_returns_422(client: TestClient) -> None:
    body = _valid_body()
    body["fields"] = []
    resp = client.post("/templates", json=body)
    assert resp.status_code == 422, resp.text


def test_field_without_name_returns_422(client: TestClient) -> None:
    body = _valid_body()
    body["fields"] = [{"name": "   ", "field_type": "texto"}]
    resp = client.post("/templates", json=body)
    assert resp.status_code == 422, resp.text


def test_blank_template_name_returns_422(client: TestClient) -> None:
    body = _valid_body()
    body["name"] = "   "
    resp = client.post("/templates", json=body)
    assert resp.status_code == 422, resp.text


def test_patch_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.patch("/templates/999999", json={"name": "x"})
    assert resp.status_code == 404


def test_field_defaults_applied(client: TestClient) -> None:
    """Campo só com nome herda os defaults (field_type='texto', required=False)."""
    body = {"name": "Recibo", "fields": [{"name": "Valor"}]}
    resp = client.post("/templates", json=body)
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["doc_type"] is None
    assert out["signals"] == []
    field = out["fields"][0]
    assert field["field_type"] == "texto"
    assert field["required"] is False
    assert field["regex"] is None
    assert field["hint"] is None


def test_delete_template_preserves_classifications(
    client: TestClient, schema_engine: Engine
) -> None:
    """DELETE do template NÃO apaga classificações já feitas (D-03 / SET NULL)."""
    resp = client.post("/templates", json=_valid_body("Comprovante"))
    template_id = resp.json()["id"]

    # Semeia um documento classificado por esse template.
    with get_session(schema_engine) as session:
        doc = Document(content_hash="c" * 64, original_filename="x.pdf")
        session.add(doc)
        session.flush()
        result = ClassificationResult(
            document_id=doc.id, template_id=template_id, confidence=0.9
        )
        session.add(result)
        session.commit()
        result_id = result.id

    # DELETE do template
    resp = client.delete(f"/templates/{template_id}")
    assert resp.status_code == 204

    # A classificação permanece; o vínculo do template foi SET NULL (D-03).
    with get_session(schema_engine) as session:
        survived = session.get(ClassificationResult, result_id)
        assert survived is not None
        assert survived.template_id is None
        assert session.scalar(select(Template).where(Template.id == template_id)) is None

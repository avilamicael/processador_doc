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

Fase 06.1-02 — sinais como GRUPOS E/OU (D-T2):
- POST/GET com grupos de condições {mode, value}; mode inválido → 422 (Literal, T-06.1-07)
- value vazio → 422; regex catastrófica guardada como STRING sem compilar (T-04-10/T-06.1-06)
- forma plana legada `["DANFE"]` lida como `[[{texto, DANFE}]]` (forward-compatible, T-06.1-08)
- PATCH só com signals preserva fields; PATCH sem signals preserva os signals atuais
- field.name preservado byte-a-byte (ponte campo→token de automação, D-T9)
"""

import base64
import warnings
from collections.abc import Iterator

import fitz  # PyMuPDF — constrói PDFs de teste de texto nativo em memória
import pytest
from sqlalchemy import Engine, select

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.classification import matcher
from app.main import app
from app.models.classification import ClassificationResult
from app.models.document import Document
from app.models.template import Template, TemplateField
from app.storage.db import get_session


def _native_pdf_b64(text: str) -> str:
    """Cria um PDF de TEXTO NATIVO com o `text` dado e devolve em base64.

    Usa PyMuPDF para inserir o texto numa página — garante route='native_text' no
    `pdf_io.extract_text_and_decide`, exercitando o caminho custo-zero do preview.
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return base64.b64encode(data).decode("ascii")


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
        "signals": [
            [{"mode": "texto", "value": "linha digitável"}],
            [{"mode": "texto", "value": "CNPJ"}],
        ],
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
    assert created["signals"] == [
        [{"mode": "texto", "value": "linha digitável"}],
        [{"mode": "texto", "value": "CNPJ"}],
    ]
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
            "signals": [[{"mode": "texto", "value": "chave de acesso"}]],
            "fields": [{"name": "Chave de acesso", "field_type": "texto"}],
        },
    )
    assert resp.status_code == 200, resp.text
    patched = resp.json()
    assert patched["name"] == "NF-e"
    assert patched["signals"] == [[{"mode": "texto", "value": "chave de acesso"}]]
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


# ---------------------------------------------------------------------------
# Fase 06.1-02 — sinais como GRUPOS E/OU (D-T2)
# ---------------------------------------------------------------------------


def test_cria_template_com_grupos(client: TestClient) -> None:
    """POST com 2 grupos (E dentro, OU entre) → 201; GET devolve os mesmos grupos."""
    body = {
        "name": "NF-e grupos",
        "signals": [
            [
                {"mode": "texto", "value": "TryLab"},
                {"mode": "regex", "value": r"\d{44}"},
            ],
            [{"mode": "texto", "value": "12.345.678/0001-99"}],
        ],
        "fields": [{"name": "Chave"}],
    }
    resp = client.post("/templates", json=body)
    assert resp.status_code == 201, resp.text
    template_id = resp.json()["id"]
    assert resp.json()["signals"] == body["signals"]

    resp = client.get(f"/templates/{template_id}")
    assert resp.status_code == 200
    assert resp.json()["signals"] == body["signals"]


def test_mode_invalido_422(client: TestClient) -> None:
    """Uma condição com `mode` fora de texto|regex → 422 (Literal), nunca 500."""
    body = {
        "name": "Modo inválido",
        "signals": [[{"mode": "qualquer", "value": "x"}]],
        "fields": [{"name": "f"}],
    }
    resp = client.post("/templates", json=body)
    assert resp.status_code == 422, resp.text


def test_value_vazio_422(client: TestClient) -> None:
    """Condição com `value` em branco → 422 (field_validator), nunca 500."""
    body = {
        "name": "Valor vazio",
        "signals": [[{"mode": "texto", "value": "   "}]],
        "fields": [{"name": "f"}],
    }
    resp = client.post("/templates", json=body)
    assert resp.status_code == 422, resp.text


def test_legado_lido_como_grupos(client: TestClient, schema_engine: Engine) -> None:
    """Template gravado na forma plana legada `["DANFE"]` é lido como 1 grupo OU."""
    with get_session(schema_engine) as session:
        tpl = Template(name="Legado plano", signals_json='["DANFE"]')
        tpl.fields = [TemplateField(name="Campo")]
        session.add(tpl)
        session.commit()
        template_id = tpl.id

    resp = client.get(f"/templates/{template_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["signals"] == [[{"mode": "texto", "value": "DANFE"}]]


def test_patch_signals_substitui(client: TestClient) -> None:
    """PATCH só com signals preserva fields; PATCH sem signals preserva signals."""
    created = client.post("/templates", json=_valid_body("Patch sinais")).json()
    template_id = created["id"]
    fields_antes = created["fields"]

    # PATCH só com signals → substitui signals, preserva fields.
    resp = client.patch(
        f"/templates/{template_id}",
        json={"signals": [[{"mode": "regex", "value": r"\d{2}"}]]},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["signals"] == [[{"mode": "regex", "value": r"\d{2}"}]]
    assert [f["name"] for f in out["fields"]] == [f["name"] for f in fields_antes]

    # PATCH sem signals → preserva os signals atuais.
    resp = client.patch(f"/templates/{template_id}", json={"name": "Patch sinais 2"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["signals"] == [[{"mode": "regex", "value": r"\d{2}"}]]


def test_regex_guardada_como_string(client: TestClient) -> None:
    """Regex catastrófica como value → 201; endpoint NÃO compila/executa (T-04-10)."""
    body = {
        "name": "Regex catastrófica",
        "signals": [[{"mode": "regex", "value": "(a+)+$"}]],
        "fields": [{"name": "f"}],
    }
    resp = client.post("/templates", json=body)
    assert resp.status_code == 201, resp.text
    assert resp.json()["signals"] == [[{"mode": "regex", "value": "(a+)+$"}]]


def test_field_name_preservado_D_T9(client: TestClient) -> None:
    """field.name persiste byte-a-byte (ponte campo→token de automação, D-T9)."""
    body = {
        "name": "Ponte D-T9",
        "signals": [],
        "fields": [{"name": "CNPJ do emitente"}],
    }
    resp = client.post("/templates", json=body)
    assert resp.status_code == 201, resp.text
    assert resp.json()["fields"][0]["name"] == "CNPJ do emitente"


# ---------------------------------------------------------------------------
# Fase 10-02 — POST /templates/preview-signals (D-07/D-08/D-09)
# ---------------------------------------------------------------------------


def _make_template_with_signals(client: TestClient, signals: list) -> int:
    body = {
        "name": f"Preview {id(signals)}",
        "signals": signals,
        "fields": [{"name": "Campo"}],
    }
    resp = client.post("/templates", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_preview_texto_nativo_casa(client: TestClient) -> None:
    """Sinais que casam o texto do PDF → scanned=false, matched_any=true (D-07)."""
    signals = [
        [{"mode": "texto", "value": "NOTA FISCAL"}],
        [{"mode": "texto", "value": "inexistente"}],
    ]
    template_id = _make_template_with_signals(client, signals)
    pdf_b64 = _native_pdf_b64("NOTA FISCAL ELETRONICA CNPJ 12.345.678/0001-99")

    resp = client.post(
        "/templates/preview-signals",
        json={"template_id": template_id, "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["scanned"] is False
    assert out["matched_any"] is True
    # Grupo 1 (NOTA FISCAL) casa; grupo 2 (inexistente) falha — relatório por-grupo.
    assert out["groups"][0]["matched"] is True
    assert out["groups"][0]["conditions"][0]["matched"] is True
    assert out["groups"][1]["matched"] is False
    assert out["groups"][1]["conditions"][0]["matched"] is False


def test_preview_texto_nativo_nao_casa(client: TestClient) -> None:
    """Texto do PDF não contém os sinais → matched_any=false, condições matched=false."""
    signals = [[{"mode": "texto", "value": "BOLETO BANCARIO"}]]
    template_id = _make_template_with_signals(client, signals)
    pdf_b64 = _native_pdf_b64("NOTA FISCAL ELETRONICA")

    resp = client.post(
        "/templates/preview-signals",
        json={"template_id": template_id, "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["matched_any"] is False
    assert out["groups"][0]["matched"] is False
    assert out["groups"][0]["conditions"][0]["matched"] is False


def test_preview_nao_pdf_422(client: TestClient) -> None:
    """Blob que não é PDF (magic bytes) → 422, sem 500 (V5/T-10-04T)."""
    template_id = _make_template_with_signals(client, [[{"mode": "texto", "value": "x"}]])
    not_pdf_b64 = base64.b64encode(b"not a pdf at all").decode("ascii")

    resp = client.post(
        "/templates/preview-signals",
        json={"template_id": template_id, "pdf_base64": not_pdf_b64},
    )
    assert resp.status_code == 422, resp.text


def test_preview_base64_invalido_422(client: TestClient) -> None:
    """base64 malformado → 422 amigável, sem 500."""
    template_id = _make_template_with_signals(client, [[{"mode": "texto", "value": "x"}]])
    resp = client.post(
        "/templates/preview-signals",
        json={"template_id": template_id, "pdf_base64": "!!!nao-e-base64!!!"},
    )
    assert resp.status_code == 422, resp.text


def test_preview_template_inexistente_404(client: TestClient) -> None:
    """template_id ausente → 404."""
    pdf_b64 = _native_pdf_b64("qualquer texto")
    resp = client.post(
        "/templates/preview-signals",
        json={"template_id": 999999, "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 404, resp.text


def test_preview_escaneado_scanned_true_sem_ia(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """route='vision' → scanned=true, groups=[], IA NUNCA chamada (D-08/Pitfall 7)."""
    template_id = _make_template_with_signals(
        client, [[{"mode": "texto", "value": "NOTA"}]]
    )
    pdf_b64 = _native_pdf_b64("NOTA FISCAL")

    # Mock route='vision' (PDF escaneado) — assegura que não há texto extraível.
    monkeypatch.setattr(
        "app.api.templates.pdf_io.extract_text_and_decide",
        lambda blob, min_chars: ("", "vision"),
    )
    # Sentinela: se evaluate_groups for chamado num escaneado, falha (custo IA evitado
    # é simbolizado aqui pela ausência de avaliação de sinais sobre texto inexistente).
    def _boom(*args, **kwargs):  # pragma: no cover - só dispara se o contrato quebrar
        raise AssertionError("evaluate_groups não deve rodar em PDF escaneado")

    monkeypatch.setattr("app.api.templates.matcher.evaluate_groups", _boom)

    resp = client.post(
        "/templates/preview-signals",
        json={"template_id": template_id, "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["scanned"] is True
    assert out["matched_any"] is False
    assert out["groups"] == []


def test_preview_identico_ao_motor_real(client: TestClient) -> None:
    """O relatório do endpoint é IGUAL ao de matcher.evaluate_groups (D-09)."""
    signals = [
        [
            {"mode": "texto", "value": "NOTA FISCAL"},
            {"mode": "texto", "value": "CNPJ"},
        ],
        [{"mode": "regex", "value": r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"}],
    ]
    template_id = _make_template_with_signals(client, signals)
    texto = "NOTA FISCAL ELETRONICA CNPJ 12.345.678/0001-99"
    pdf_b64 = _native_pdf_b64(texto)

    resp = client.post(
        "/templates/preview-signals",
        json={"template_id": template_id, "pdf_base64": pdf_b64},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()

    # Roda o motor real diretamente sobre o MESMO texto e compara o agregado (D-09).
    expected = matcher.evaluate_groups(signals, texto)
    assert out["matched_any"] == any(g.matched for g in expected)
    assert len(out["groups"]) == len(expected)
    for got, exp in zip(out["groups"], expected, strict=True):
        assert got["matched"] == exp.matched
        assert [c["matched"] for c in got["conditions"]] == [
            c.matched for c in exp.conditions
        ]
        assert [c["mode"] for c in got["conditions"]] == [
            c.mode for c in exp.conditions
        ]
        assert [c["value"] for c in got["conditions"]] == [
            c.value for c in exp.conditions
        ]

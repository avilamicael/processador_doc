"""API de documentos — lista + counts + duplicados + rescan (Plano 02-04 Task 3).

Usa `TestClient` sobre o app com `app.state.engine` sobrescrito por um engine de
teste com schema. Prova:
- GET /documents retorna as linhas (Documents = blocos), counts por estado e total
- GET /documents inclui last_completed_step (UI distingue "Aguardando extração")
- duplicatas NUNCA aparecem como linhas (D-10)
- GET /documents/duplicates-count = SUM(duplicate_hits)
- POST /rescan retorna 200 e um inteiro de enfileirados (pasta vazia → 0)
"""

import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.main import app
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.models.ingested_original import IngestedOriginal
from app.models.template import Template
from app.models.watched_folder import WatchedFolder
from app.pipeline.ingest_stage import AWAITING_EXTRACTION_STEP
from app.pipeline.state_machine import transition
from app.storage.db import get_session


@pytest.fixture
def client(schema_engine: Engine) -> Iterator[TestClient]:
    previous = getattr(app.state, "engine", None)
    app.state.engine = schema_engine
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.state.engine = previous


def _seed(schema_engine: Engine) -> None:
    """Semeia Documents em estados variados + um original com duplicate_hits."""
    with get_session(schema_engine) as session:
        original = IngestedOriginal(
            original_hash="f" * 64,
            original_filename="orig.pdf",
            source_folder_id=None,
            block_count=2,
            duplicate_hits=3,
        )
        session.add(original)
        session.flush()

        # Doc 1: estado terminal da fase (PROCESSANDO + aguardando_extracao).
        d1 = Document(
            content_hash="1" * 64,
            original_filename="orig.pdf",
            origin_original_id=original.id,
        )
        session.add(d1)
        session.flush()
        transition(session, d1, DocState.PROCESSANDO, completed_step=AWAITING_EXTRACTION_STEP)

        # Doc 2: RECEBIDO (default).
        d2 = Document(content_hash="2" * 64, original_filename="orig.pdf")
        session.add(d2)

        # Doc 3: QUARENTENA.
        d3 = Document(content_hash="3" * 64, original_filename="scan.png")
        session.add(d3)
        session.flush()
        transition(session, d3, DocState.QUARENTENA)

        session.commit()


def test_list_documents_with_counts(client: TestClient, schema_engine: Engine) -> None:
    _seed(schema_engine)

    resp = client.get("/documents")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == 3
    assert len(body["items"]) == 3
    # Counts por estado, todos os estados presentes.
    assert body["counts"]["processando"] == 1
    assert body["counts"]["recebido"] == 1
    assert body["counts"]["quarentena"] == 1
    assert body["counts"]["concluido"] == 0
    assert sum(body["counts"].values()) == 3

    # last_completed_step exposto para a UI distinguir "Aguardando extração".
    proc = next(i for i in body["items"] if i["state"] == "processando")
    assert proc["last_completed_step"] == AWAITING_EXTRACTION_STEP


def test_duplicates_count(client: TestClient, schema_engine: Engine) -> None:
    _seed(schema_engine)
    resp = client.get("/documents/duplicates-count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 3


def test_duplicates_count_zero_when_empty(client: TestClient) -> None:
    resp = client.get("/documents/duplicates-count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_list_excludes_duplicates_as_rows(client: TestClient, schema_engine: Engine) -> None:
    """duplicate_hits>0 não vira linha: só Documents reais aparecem (D-10)."""
    _seed(schema_engine)
    body = client.get("/documents").json()
    # 3 Documents semeados; o original com duplicate_hits=3 NÃO adiciona linhas.
    assert body["total"] == 3


def test_rescan_empty_folder_returns_zero(
    client: TestClient, schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    with get_session(schema_engine) as session:
        session.add(WatchedFolder(path=str(folder.resolve()), pages_per_block=None, active=True))
        session.commit()

    resp = client.post("/rescan")
    assert resp.status_code == 200, resp.text
    assert resp.json()["enqueued"] == 0


def test_rescan_enqueues_present_file(
    client: TestClient,
    schema_engine: Engine,
    data_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pikepdf

    from app import config

    monkeypatch.setenv("STABILIZATION_WINDOW_SECONDS", "0.0")
    config.get_settings.cache_clear()

    folder = tmp_path / "hot"
    folder.mkdir()
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.save(folder / "doc.pdf")
    pdf.close()

    with get_session(schema_engine) as session:
        session.add(WatchedFolder(path=str(folder.resolve()), pages_per_block=None, active=True))
        session.commit()

    resp = client.post("/rescan")
    assert resp.status_code == 200
    assert resp.json()["enqueued"] == 1

    config.get_settings.cache_clear()


# --- GET /documents/{id} — detalhe de classificação (somente leitura, S4) ---
#
# NOTA: este plano (Wave 2) roda ANTES do classify_stage (04-05, Wave 3); os testes
# POPULAM ClassificationResult/FilledField diretamente no banco via fixtures, SEM
# depender do stage. Só o endpoint de leitura é exercitado aqui.


def test_detail_classified_document(client: TestClient, schema_engine: Engine) -> None:
    """Doc classificado → template casado + campos com bruto/normalizado/marca."""
    with get_session(schema_engine) as session:
        template = Template(name="Nota Fiscal", doc_type="Fiscal", signals_json="[]")
        session.add(template)
        doc = Document(content_hash="a" * 64, original_filename="nf.pdf")
        session.add(doc)
        session.flush()
        result = ClassificationResult(
            document_id=doc.id, template_id=template.id, confidence=0.92
        )
        session.add(result)
        session.flush()
        session.add_all(
            [
                FilledField(
                    classification_result_id=result.id,
                    field_name="CNPJ emitente",
                    raw_value="12.345.678/0001-99",
                    normalized_value="12345678000199",
                    valid=True,
                ),
                FilledField(
                    classification_result_id=result.id,
                    field_name="Data de emissão",
                    raw_value="32/13/2026",
                    normalized_value=None,
                    valid=False,
                    invalid_reason="data inválida",
                ),
            ]
        )
        session.commit()
        doc_id = doc.id
        template_id = template.id

    resp = client.get(f"/documents/{doc_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == doc_id
    assert body["original_filename"] == "nf.pdf"
    cls = body["classification"]
    assert cls is not None
    assert cls["template_id"] == template_id
    assert cls["template_name"] == "Nota Fiscal"
    assert cls["confidence"] == 0.92
    assert len(cls["fields"]) == 2
    cnpj = next(f for f in cls["fields"] if f["field_name"] == "CNPJ emitente")
    assert cnpj["raw_value"] == "12.345.678/0001-99"
    assert cnpj["normalized_value"] == "12345678000199"
    assert cnpj["valid"] is True
    data = next(f for f in cls["fields"] if f["field_name"] == "Data de emissão")
    assert data["valid"] is False
    assert data["invalid_reason"] == "data inválida"


def test_detail_quarantine_document(client: TestClient, schema_engine: Engine) -> None:
    """Doc em quarentena (template_id null) → classification com template null."""
    with get_session(schema_engine) as session:
        doc = Document(content_hash="b" * 64, original_filename="scan.png")
        session.add(doc)
        session.flush()
        transition(session, doc, DocState.QUARENTENA)
        result = ClassificationResult(
            document_id=doc.id, template_id=None, confidence=None
        )
        session.add(result)
        session.commit()
        doc_id = doc.id

    resp = client.get(f"/documents/{doc_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "quarentena"
    cls = body["classification"]
    assert cls is not None
    assert cls["template_id"] is None
    assert cls["template_name"] is None
    assert cls["fields"] == []


def test_detail_unclassified_document(client: TestClient, schema_engine: Engine) -> None:
    """Doc sem ClassificationResult → classification null ("Aguardando classificação")."""
    with get_session(schema_engine) as session:
        doc = Document(content_hash="c" * 64, original_filename="pend.pdf")
        session.add(doc)
        session.commit()
        doc_id = doc.id

    resp = client.get(f"/documents/{doc_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["classification"] is None


def test_detail_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.get("/documents/999999")
    assert resp.status_code == 404


def test_list_does_not_include_classification(
    client: TestClient, schema_engine: Engine
) -> None:
    """A lista GET /documents permanece LEVE — sem o bloco classification."""
    _seed(schema_engine)
    body = client.get("/documents").json()
    assert body["items"]
    assert all("classification" not in item for item in body["items"])

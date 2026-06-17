"""Endpoints de revisão da Fase 5 (Plan 03) — ações de triagem + GET /attention.

Cobre os 4 endpoints de ação sobre documentos parados + o endpoint dedicado de
triagem (3 baldes num payload só, Open Q3) + o limiar global de config:

- POST /documents/{id}/retry      (FALHA→PROCESSANDO, reenfileira o step)
- POST /documents/{id}/reclassify (QUARENTENA→PROCESSANDO, forced_template_id;
  apaga CR de quarentena ANTES — Pitfall 3)
- PATCH /documents/{id}/fields/{field_name} (revalida SEM IA, manually_corrected=True,
  recalcula confidence_score — Pitfall 4)
- POST /documents/{id}/approve    (EM_REVISAO→CONCLUIDO; guard obrigatórios válidos)
- GET /documents/attention        (3 baldes: falha/quarentena/em_revisao, sem N+1)

Reusa o molde da fixture de `test_api_documents.py` e o respx de
`tests/classification/conftest.py` (prova sem-IA no patch — call_count==0).
"""

import json
import warnings
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import respx
from httpx import Response as HxResponse
from sqlalchemy import Engine, select

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.main import app
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState, JobStatus
from app.models.job import Job
from app.models.template import Template, TemplateField
from app.pipeline.ingest_stage import AWAITING_EXTRACTION_STEP
from app.pipeline.state_machine import transition
from app.storage.db import get_session


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


# --- Helpers de seeding -----------------------------------------------------


def _make_template(
    session,
    *,
    name: str,
    fields: list[tuple[str, str, bool]],
) -> Template:
    """Cria um Template com (field_name, field_type, required) por tupla."""
    template = Template(name=name, doc_type="Fiscal", signals_json="[]")
    session.add(template)
    session.flush()
    for fname, ftype, freq in fields:
        session.add(
            TemplateField(
                template_id=template.id,
                name=fname,
                field_type=ftype,
                required=freq,
            )
        )
    session.flush()
    return template


def _make_doc(session, *, content_hash: str, filename: str = "doc.pdf") -> Document:
    doc = Document(content_hash=content_hash, original_filename=filename)
    session.add(doc)
    session.flush()
    return doc


# --- POST /documents/{id}/retry ---------------------------------------------


def test_retry_non_failed_returns_409(client: TestClient, schema_engine: Engine) -> None:
    """retry de documento que não está em FALHA → 409 (transição fora da allowlist)."""
    with get_session(schema_engine) as session:
        doc = _make_doc(session, content_hash="a" * 64)
        transition(session, doc, DocState.QUARENTENA)
        doc_id = doc.id

    resp = client.post(f"/documents/{doc_id}/retry")
    assert resp.status_code == 409, resp.text

    with get_session(schema_engine) as session:
        doc = session.get(Document, doc_id)
        assert doc.state == DocState.QUARENTENA  # estado inalterado


def test_retry_failed_requeues_classify_when_extracted(
    client: TestClient, schema_engine: Engine
) -> None:
    """retry de doc FALHA com last_completed_step='extraido' → PROCESSANDO + classify."""
    ch = "b" * 64
    with get_session(schema_engine) as session:
        doc = _make_doc(session, content_hash=ch)
        transition(session, doc, DocState.PROCESSANDO, completed_step="extraido")
        transition(session, doc, DocState.FALHA)
        doc_id = doc.id

    resp = client.post(f"/documents/{doc_id}/retry")
    assert resp.status_code == 200, resp.text

    with get_session(schema_engine) as session:
        doc = session.get(Document, doc_id)
        assert doc.state == DocState.PROCESSANDO
        job = session.scalar(select(Job).where(Job.original_hash == ch))
        assert job is not None
        assert job.step == "classify"
        assert job.status == JobStatus.PENDING


def test_retry_failed_requeues_extract_when_awaiting(
    client: TestClient, schema_engine: Engine
) -> None:
    """retry de doc FALHA aguardando extração → PROCESSANDO + extract reenfileirado."""
    ch = "c" * 64
    with get_session(schema_engine) as session:
        doc = _make_doc(session, content_hash=ch)
        transition(session, doc, DocState.PROCESSANDO, completed_step=AWAITING_EXTRACTION_STEP)
        transition(session, doc, DocState.FALHA)
        doc_id = doc.id

    resp = client.post(f"/documents/{doc_id}/retry")
    assert resp.status_code == 200, resp.text

    with get_session(schema_engine) as session:
        job = session.scalar(select(Job).where(Job.original_hash == ch))
        assert job is not None
        assert job.step == "extract"
        assert job.status == JobStatus.PENDING


def test_retry_nonexistent_returns_404(client: TestClient) -> None:
    resp = client.post("/documents/999999/retry")
    assert resp.status_code == 404


# --- POST /documents/{id}/reclassify ----------------------------------------


def test_reclassify_deletes_cr_and_requeues(client: TestClient, schema_engine: Engine) -> None:
    """reclassify apaga o CR de quarentena e reenfileira (não no-op da idempotência)."""
    ch = "d" * 64
    with get_session(schema_engine) as session:
        template = _make_template(session, name="Boleto", fields=[("valor", "moeda", True)])
        doc = _make_doc(session, content_hash=ch)
        transition(session, doc, DocState.QUARENTENA)
        cr = ClassificationResult(document_id=doc.id, template_id=None, confidence=None)
        session.add(cr)
        session.flush()
        # Job classify pré-existente 'done' (simula 1a classificação concluída).
        session.add(
            Job(
                original_hash=ch,
                step="classify",
                payload=json.dumps({"content_hash": ch}),
                status=JobStatus.DONE,
                next_run_at=datetime.now(UTC),
            )
        )
        session.commit()
        doc_id = doc.id
        template_id = template.id

    resp = client.post(f"/documents/{doc_id}/reclassify", json={"template_id": template_id})
    assert resp.status_code == 200, resp.text

    with get_session(schema_engine) as session:
        doc = session.get(Document, doc_id)
        assert doc.state == DocState.PROCESSANDO
        # CR de quarentena apagado.
        cr = session.scalar(
            select(ClassificationResult).where(ClassificationResult.document_id == doc_id)
        )
        assert cr is None
        # Job classify resetado para pending com forced_template_id no payload.
        job = session.scalar(select(Job).where(Job.original_hash == ch, Job.step == "classify"))
        assert job is not None
        assert job.status == JobStatus.PENDING
        assert json.loads(job.payload)["forced_template_id"] == template_id


def test_reclassify_unknown_template_returns_404(client: TestClient, schema_engine: Engine) -> None:
    """reclassify com template_id inexistente → 404, sem mudar estado."""
    with get_session(schema_engine) as session:
        doc = _make_doc(session, content_hash="e" * 64)
        transition(session, doc, DocState.QUARENTENA)
        doc_id = doc.id

    resp = client.post(f"/documents/{doc_id}/reclassify", json={"template_id": 99999})
    assert resp.status_code == 404, resp.text

    with get_session(schema_engine) as session:
        doc = session.get(Document, doc_id)
        assert doc.state == DocState.QUARENTENA


def test_reclassify_non_quarantine_returns_409(client: TestClient, schema_engine: Engine) -> None:
    """reclassify de doc que não está em QUARENTENA → 409."""
    with get_session(schema_engine) as session:
        template = _make_template(session, name="NF", fields=[("cnpj", "cpf_cnpj", True)])
        doc = _make_doc(session, content_hash="f" * 64)
        transition(session, doc, DocState.PROCESSANDO, completed_step="extraido")
        transition(session, doc, DocState.EM_REVISAO)
        doc_id = doc.id
        template_id = template.id

    resp = client.post(f"/documents/{doc_id}/reclassify", json={"template_id": template_id})
    assert resp.status_code == 409, resp.text


# --- PATCH /documents/{id}/fields/{field_name} ------------------------------


def _seed_em_revisao(session, *, content_hash: str) -> tuple[int, int, int]:
    """Doc EM_REVISAO com 1 obrigatório inválido (cnpj) — retorna (doc, cr, template)."""
    template = _make_template(
        session,
        name="Nota Fiscal",
        fields=[("cnpj", "cpf_cnpj", True), ("obs", "texto", False)],
    )
    doc = _make_doc(session, content_hash=content_hash)
    transition(session, doc, DocState.PROCESSANDO, completed_step="extraido")
    transition(session, doc, DocState.EM_REVISAO)
    cr = ClassificationResult(
        document_id=doc.id, template_id=template.id, confidence=0.9, confidence_score=0.0
    )
    session.add(cr)
    session.flush()
    session.add_all(
        [
            FilledField(
                classification_result_id=cr.id,
                field_name="cnpj",
                raw_value="00.000.000/0000-00",
                normalized_value=None,
                valid=False,
                invalid_reason="CPF/CNPJ inválido (dígito verificador)",
            ),
            FilledField(
                classification_result_id=cr.id,
                field_name="obs",
                raw_value="qualquer",
                normalized_value="qualquer",
                valid=True,
            ),
        ]
    )
    session.flush()
    return doc.id, cr.id, template.id


def test_patch_field_revalidates_without_ai(client: TestClient, schema_engine: Engine) -> None:
    """patch revalida o campo, marca manually_corrected e NÃO chama a IA (respx==0)."""
    with get_session(schema_engine) as session:
        doc_id, cr_id, _ = _seed_em_revisao(session, content_hash="1" * 64)
        session.commit()

    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses").mock(return_value=HxResponse(200, json={}))
        resp = client.patch(
            f"/documents/{doc_id}/fields/cnpj",
            json={"raw_value": "11.444.777/0001-61"},
        )
        assert resp.status_code == 200, resp.text
        assert route.call_count == 0  # D-08: patch NÃO chama a IA

    with get_session(schema_engine) as session:
        ff = session.scalar(
            select(FilledField).where(
                FilledField.classification_result_id == cr_id,
                FilledField.field_name == "cnpj",
            )
        )
        assert ff.valid is True
        assert ff.normalized_value == "11444777000161"
        assert ff.manually_corrected is True
        cr = session.get(ClassificationResult, cr_id)
        assert cr.confidence_score == 1.0  # único obrigatório agora válido


def test_patch_field_nonexistent_field_returns_404(
    client: TestClient, schema_engine: Engine
) -> None:
    with get_session(schema_engine) as session:
        doc_id, _, _ = _seed_em_revisao(session, content_hash="2" * 64)
        session.commit()

    resp = client.patch(f"/documents/{doc_id}/fields/inexistente", json={"raw_value": "x"})
    assert resp.status_code == 404


# --- POST /documents/{id}/approve -------------------------------------------


def test_approve_blocks_invalid_required_then_succeeds(
    client: TestClient, schema_engine: Engine
) -> None:
    """approve → 409 com obrigatório inválido; → 200 (CONCLUIDO) após a correção."""
    with get_session(schema_engine) as session:
        doc_id, _, _ = _seed_em_revisao(session, content_hash="3" * 64)
        session.commit()

    # 1) obrigatório (cnpj) inválido → approve 409, estado inalterado.
    resp = client.post(f"/documents/{doc_id}/approve")
    assert resp.status_code == 409, resp.text
    with get_session(schema_engine) as session:
        assert session.get(Document, doc_id).state == DocState.EM_REVISAO

    # 2) corrige o obrigatório via patch → approve passa (200, CONCLUIDO).
    fix = client.patch(f"/documents/{doc_id}/fields/cnpj", json={"raw_value": "11.444.777/0001-61"})
    assert fix.status_code == 200, fix.text

    ok = client.post(f"/documents/{doc_id}/approve")
    assert ok.status_code == 200, ok.text
    with get_session(schema_engine) as session:
        assert session.get(Document, doc_id).state == DocState.CONCLUIDO


def test_approve_non_em_revisao_returns_409(client: TestClient, schema_engine: Engine) -> None:
    """approve de doc fora de EM_REVISAO (ex.: QUARENTENA) → 409."""
    with get_session(schema_engine) as session:
        doc = _make_doc(session, content_hash="4" * 64)
        transition(session, doc, DocState.QUARENTENA)
        cr = ClassificationResult(document_id=doc.id, template_id=None, confidence=None)
        session.add(cr)
        session.commit()
        doc_id = doc.id

    resp = client.post(f"/documents/{doc_id}/approve")
    assert resp.status_code == 409, resp.text


# --- GET /documents/attention -----------------------------------------------


def test_attention_three_buckets(client: TestClient, schema_engine: Engine) -> None:
    """GET /attention devolve os 3 baldes; EM_REVISAO traz campos; fora-de-balde some."""
    with get_session(schema_engine) as session:
        # FALHA
        f = _make_doc(session, content_hash="a1" + "0" * 62, filename="falhou.pdf")
        transition(session, f, DocState.PROCESSANDO, completed_step="extraido")
        transition(session, f, DocState.FALHA)

        # QUARENTENA
        q = _make_doc(session, content_hash="b1" + "0" * 62, filename="quar.png")
        transition(session, q, DocState.QUARENTENA)
        session.add(ClassificationResult(document_id=q.id, template_id=None, confidence=None))

        # EM_REVISAO com campos
        doc_id, _, _ = _seed_em_revisao(session, content_hash="c1" + "0" * 62)

        # PROCESSANDO (não deve aparecer)
        p = _make_doc(session, content_hash="d1" + "0" * 62)
        transition(session, p, DocState.PROCESSANDO, completed_step=AWAITING_EXTRACTION_STEP)

        # CONCLUIDO (não deve aparecer)
        c = _make_doc(session, content_hash="e1" + "0" * 62)
        transition(session, c, DocState.PROCESSANDO, completed_step="extraido")
        transition(session, c, DocState.CONCLUIDO)

        session.commit()

    resp = client.get("/documents/attention")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["falha"]) == 1
    assert body["falha"][0]["motivo"]  # tem um motivo (persistido ou fallback)
    assert len(body["quarentena"]) == 1
    assert "Nenhum template" in body["quarentena"][0]["motivo"]

    assert len(body["em_revisao"]) == 1
    rev = body["em_revisao"][0]
    assert rev["id"] == doc_id
    assert rev["confidence_score"] == 0.0
    field_names = {fld["field_name"] for fld in rev["fields"]}
    assert {"cnpj", "obs"} <= field_names
    cnpj = next(fld for fld in rev["fields"] if fld["field_name"] == "cnpj")
    assert cnpj["valid"] is False
    assert "manually_corrected" in cnpj

    # Contagens por balde.
    assert body["counts"]["falha"] == 1
    assert body["counts"]["quarentena"] == 1
    assert body["counts"]["em_revisao"] == 1

    # PROCESSANDO/CONCLUIDO NÃO aparecem em nenhum balde.
    all_ids = (
        {i["id"] for i in body["falha"]}
        | {i["id"] for i in body["quarentena"]}
        | {i["id"] for i in body["em_revisao"]}
    )
    with get_session(schema_engine) as session:
        proc_id = session.scalar(select(Document.id).where(Document.state == DocState.PROCESSANDO))
        conc_id = session.scalar(select(Document.id).where(Document.state == DocState.CONCLUIDO))
    assert proc_id not in all_ids
    assert conc_id not in all_ids

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
from sqlalchemy import Engine, func, select

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from app.main import app
from app.models.audit_log import AuditLog
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.models.ingested_original import IngestedOriginal
from app.models.job import Job
from app.models.template import Template
from app.models.watched_folder import WatchedFolder
from app.pipeline.ingest_stage import AWAITING_EXTRACTION_STEP
from app.pipeline.state_machine import transition
from app.queue import repo
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
    assert resp.json()["skipped_duplicates"] == 0


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
    assert resp.json()["skipped_duplicates"] == 0

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


# --- POST /documents/delete — remoção em LOTE (só registro, nunca o arquivo) ---
#
# Constraint forte do projeto: remover um documento NUNCA pode tocar no arquivo
# físico do cliente. Os testes verificam o efeito no banco (Document + cascata +
# Jobs órfãos + IngestedOriginal sem blocos restantes) e que nenhum arquivo é
# tocado (o endpoint não importa os/shutil/Path.unlink — verificado por grep no
# bloco de verificação do plano; aqui garantimos que o arquivo seed permanece).


def test_delete_removes_only_record_not_file(
    client: TestClient, schema_engine: Engine, tmp_path: Path
) -> None:
    """Remover um id existente → 200 {deleted:1}; some do banco; arquivo intacto."""
    # Arquivo físico que NUNCA pode ser tocado pela remoção.
    physical = tmp_path / "cliente.pdf"
    physical.write_bytes(b"%PDF-1.4 conteudo do cliente")

    with get_session(schema_engine) as session:
        doc = Document(content_hash="d" * 64, original_filename="cliente.pdf")
        session.add(doc)
        session.commit()
        doc_id = doc.id

    resp = client.post("/documents/delete", json={"ids": [doc_id]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 1

    with get_session(schema_engine) as session:
        assert session.get(Document, doc_id) is None

    # O arquivo do cliente permanece intocado (constraint forte).
    assert physical.exists()
    assert physical.read_bytes() == b"%PDF-1.4 conteudo do cliente"


def test_delete_batch_multiple_ids(client: TestClient, schema_engine: Engine) -> None:
    """Remover vários ids → todos somem; deleted = quantidade real."""
    with get_session(schema_engine) as session:
        ids = []
        for i in range(3):
            d = Document(content_hash=str(i) * 64, original_filename=f"d{i}.pdf")
            session.add(d)
            session.flush()
            ids.append(d.id)
        session.commit()

    resp = client.post("/documents/delete", json={"ids": ids})
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 3
    with get_session(schema_engine) as session:
        assert all(session.get(Document, i) is None for i in ids)


def test_delete_ignores_nonexistent_ids(client: TestClient, schema_engine: Engine) -> None:
    """ids inexistentes são ignorados silenciosamente; não derruba o lote."""
    with get_session(schema_engine) as session:
        d = Document(content_hash="e" * 64, original_filename="existe.pdf")
        session.add(d)
        session.commit()
        doc_id = d.id

    resp = client.post("/documents/delete", json={"ids": [doc_id, 999999, 888888]})
    assert resp.status_code == 200
    # Só 1 Document realmente existia.
    assert resp.json()["deleted"] == 1
    with get_session(schema_engine) as session:
        assert session.get(Document, doc_id) is None


def test_delete_empty_list_returns_zero(client: TestClient) -> None:
    resp = client.post("/documents/delete", json={"ids": []})
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0


def test_delete_cascade_removes_classification(client: TestClient, schema_engine: Engine) -> None:
    """Cascade apaga ClassificationResult + FilledFields do Document (sem órfãos)."""
    with get_session(schema_engine) as session:
        template = Template(name="NF", doc_type="Fiscal", signals_json="[]")
        session.add(template)
        doc = Document(content_hash="c" * 64, original_filename="nf.pdf")
        session.add(doc)
        session.flush()
        cr = ClassificationResult(document_id=doc.id, template_id=template.id, confidence=0.9)
        session.add(cr)
        session.flush()
        session.add(
            FilledField(
                classification_result_id=cr.id,
                field_name="CNPJ",
                raw_value="x",
                normalized_value="x",
                valid=True,
            )
        )
        session.commit()
        doc_id = doc.id
        cr_id = cr.id

    resp = client.post("/documents/delete", json={"ids": [doc_id]})
    assert resp.status_code == 200

    with get_session(schema_engine) as session:
        assert session.get(Document, doc_id) is None
        assert session.get(ClassificationResult, cr_id) is None
        assert (
            session.scalar(
                select(func.count(FilledField.id)).where(
                    FilledField.classification_result_id == cr_id
                )
            )
            == 0
        )


def test_delete_removes_orphan_jobs(client: TestClient, schema_engine: Engine) -> None:
    """Jobs com original_hash == content_hash do bloco são removidos junto."""
    chash = "b" * 64
    with get_session(schema_engine) as session:
        doc = Document(content_hash=chash, original_filename="b.pdf")
        session.add(doc)
        session.commit()
        doc_id = doc.id
    with get_session(schema_engine) as session:
        repo.enqueue(session, original_hash=chash, step="extract", payload="{}")

    resp = client.post("/documents/delete", json={"ids": [doc_id]})
    assert resp.status_code == 200
    with get_session(schema_engine) as session:
        assert (
            session.scalar(select(func.count(Job.id)).where(Job.original_hash == chash)) == 0
        )


def test_delete_last_block_removes_ingested_original(
    client: TestClient, schema_engine: Engine
) -> None:
    """Remover o ÚLTIMO bloco de um IngestedOriginal apaga o original + seus jobs."""
    ohash = "a" * 64
    with get_session(schema_engine) as session:
        original = IngestedOriginal(
            original_hash=ohash,
            original_filename="orig.pdf",
            source_folder_id=None,
            block_count=1,
        )
        session.add(original)
        session.flush()
        doc = Document(
            content_hash="9" * 64,
            original_filename="orig.pdf",
            origin_original_id=original.id,
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id
        original_id = original.id
    # Job do original (gate) — deve ser limpo junto para liberar re-ingestão.
    with get_session(schema_engine) as session:
        repo.enqueue(session, original_hash=ohash, step="ingest", payload="{}")

    resp = client.post("/documents/delete", json={"ids": [doc_id]})
    assert resp.status_code == 200
    with get_session(schema_engine) as session:
        assert session.get(IngestedOriginal, original_id) is None
        assert (
            session.scalar(select(func.count(Job.id)).where(Job.original_hash == ohash)) == 0
        )


def test_delete_preserves_ingested_original_with_remaining_blocks(
    client: TestClient, schema_engine: Engine
) -> None:
    """Se OUTRO bloco ainda aponta para o original (split), o original é PRESERVADO."""
    ohash = "7" * 64
    with get_session(schema_engine) as session:
        original = IngestedOriginal(
            original_hash=ohash,
            original_filename="multi.pdf",
            source_folder_id=None,
            block_count=2,
        )
        session.add(original)
        session.flush()
        d1 = Document(
            content_hash="5" * 64, original_filename="multi.pdf", origin_original_id=original.id
        )
        d2 = Document(
            content_hash="6" * 64, original_filename="multi.pdf", origin_original_id=original.id
        )
        session.add_all([d1, d2])
        session.commit()
        d1_id = d1.id
        original_id = original.id

    # Remove só um dos dois blocos.
    resp = client.post("/documents/delete", json={"ids": [d1_id]})
    assert resp.status_code == 200
    with get_session(schema_engine) as session:
        # O original é preservado porque d2 ainda o referencia.
        assert session.get(IngestedOriginal, original_id) is not None


# --- D-02 (item 7): remover doc de SPLIT libera a entrada de gate do BLOCO ---
#
# A materialização de split registra o hash do BLOCO no gate de dedup (anti-loop)
# como entrada SEPARADA do original: IngestedOriginal.original_hash == content_hash
# do Document do bloco. Sem limpar essa entrada, "remover + forçar varredura"
# dedupa o arquivo de bloco e NÃO re-ingere. A limpeza só apaga REGISTROS — o
# arquivo na pasta e o blob CAS permanecem (constraint sagrada).


def test_delete_split_block_clears_block_gate_entry(
    client: TestClient, schema_engine: Engine
) -> None:
    """D-02: remover um doc de SPLIT apaga a entrada de gate do BLOCO
    (IngestedOriginal.original_hash == content_hash), liberando a re-ingestão."""
    block_hash = "a" * 64
    with get_session(schema_engine) as session:
        # ORIGINAL referenciado pelo bloco via origin_original_id.
        original = IngestedOriginal(
            original_hash="f" * 64,
            original_filename="multi.pdf",
            source_folder_id=None,
            block_count=1,
        )
        session.add(original)
        session.flush()
        # Entrada de gate do BLOCO (anti-loop do split): chave == content_hash do bloco.
        block_gate = IngestedOriginal(
            original_hash=block_hash,
            original_filename="multi_bloco_1.pdf",
            source_folder_id=None,
            block_count=0,
        )
        session.add(block_gate)
        # Document do bloco.
        doc = Document(
            content_hash=block_hash,
            original_filename="multi_bloco_1.pdf",
            origin_original_id=original.id,
        )
        session.add(doc)
        session.commit()
        doc_id = doc.id

    resp = client.post("/documents/delete", json={"ids": [doc_id]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 1
    with get_session(schema_engine) as session:
        # A entrada de gate do bloco sumiu → re-varredura re-ingere (não dedupa).
        assert (
            session.scalar(
                select(func.count(IngestedOriginal.id)).where(
                    IngestedOriginal.original_hash == block_hash
                )
            )
            == 0
        )


def test_delete_non_split_doc_does_not_remove_unrelated_gate(
    client: TestClient, schema_engine: Engine
) -> None:
    """Regressão: doc SEM entrada de gate de bloco própria → o delete extra é no-op;
    NÃO apaga o IngestedOriginal de outro fluxo (hashes distintos por conteúdo)."""
    other_hash = "c" * 64
    with get_session(schema_engine) as session:
        # IngestedOriginal de OUTRO fluxo, não relacionado ao doc removido.
        other_gate = IngestedOriginal(
            original_hash=other_hash,
            original_filename="outro.pdf",
            source_folder_id=None,
            block_count=0,
        )
        session.add(other_gate)
        # Doc sem split: content_hash distinto, sem entrada de gate própria.
        doc = Document(content_hash="d" * 64, original_filename="simples.pdf")
        session.add(doc)
        session.commit()
        doc_id = doc.id
        other_id = other_gate.id

    resp = client.post("/documents/delete", json={"ids": [doc_id]})
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    with get_session(schema_engine) as session:
        # A entrada de gate alheia permanece (delete extra é no-op para esse doc).
        assert session.get(IngestedOriginal, other_id) is not None


def test_delete_endpoint_does_not_import_filesystem_ops() -> None:
    """A limpeza de dedup é PURAMENTE de registros: o módulo do endpoint não pode
    importar os/shutil (constraint sagrada 'nunca perder arquivos')."""
    import app.api.documents as documents_module

    assert not hasattr(documents_module, "os")
    assert not hasattr(documents_module, "shutil")


# ---------------------------------------------------------------------------
# REPROCESS (Plano 10-03 — D-10/D-11/D-12): re-roda matcher→(IA)→filler com os
# templates ATUAIS, SEM forçar template, para tirar docs de QUARENTENA/EM_REVISAO.
# Single (POST /documents/{id}/reprocess) e batch por bucket (POST /documents/reprocess).
# ---------------------------------------------------------------------------


def _seed_doc_with_cr(
    schema_engine: Engine,
    *,
    content_hash: str,
    state: DocState,
) -> int:
    """Semeia um Document no estado pedido com um ClassificationResult + FilledField.

    Devolve o id do Document. O CR existe para provar que o reprocess o APAGA
    (Pitfall 3). A transição passa por PROCESSANDO quando necessário (a allowlist
    não tem RECEBIDO→EM_REVISAO direto).
    """
    with get_session(schema_engine) as session:
        template = Template(name=f"T-{content_hash[:4]}", doc_type="Fiscal", signals_json="[]")
        session.add(template)
        doc = Document(content_hash=content_hash, original_filename=f"{content_hash[:4]}.pdf")
        session.add(doc)
        session.flush()
        cr = ClassificationResult(document_id=doc.id, template_id=template.id, confidence=0.9)
        session.add(cr)
        session.flush()
        session.add(
            FilledField(
                classification_result_id=cr.id,
                field_name="CNPJ",
                raw_value="x",
                normalized_value="x",
                valid=True,
            )
        )
        # Levar o doc ao estado pedido respeitando a allowlist.
        if state == DocState.QUARENTENA:
            transition(session, doc, DocState.QUARENTENA)
        elif state == DocState.EM_REVISAO:
            transition(session, doc, DocState.PROCESSANDO)
            transition(session, doc, DocState.EM_REVISAO)
        elif state == DocState.CONCLUIDO:
            transition(session, doc, DocState.PROCESSANDO)
            transition(session, doc, DocState.CONCLUIDO)
        session.commit()
        return doc.id


def _pending_classify_payload(schema_engine: Engine, content_hash: str) -> dict:
    """Carrega o payload (dict) do Job (content_hash, 'classify')."""
    with get_session(schema_engine) as session:
        raw = session.scalar(
            select(Job.payload).where(Job.original_hash == content_hash, Job.step == "classify")
        )
    assert raw is not None, "Job classify não foi enfileirado"
    import json

    return json.loads(raw)


def test_reprocess_single_quarantine_deletes_cr_and_requeues_without_forced(
    client: TestClient, schema_engine: Engine
) -> None:
    """(a) QUARENTENA + CR → 200; estado PROCESSANDO, CR apagado, Job classify
    pending cujo payload NÃO contém forced_template_id (D-11)."""
    chash = "a" * 64
    doc_id = _seed_doc_with_cr(schema_engine, content_hash=chash, state=DocState.QUARENTENA)

    resp = client.post(f"/documents/{doc_id}/reprocess")
    assert resp.status_code == 200, resp.text

    with get_session(schema_engine) as session:
        doc = session.get(Document, doc_id)
        assert doc.state == DocState.PROCESSANDO
        # CR apagado (Pitfall 3).
        assert (
            session.scalar(
                select(func.count(ClassificationResult.id)).where(
                    ClassificationResult.document_id == doc_id
                )
            )
            == 0
        )

    # D-11: o requeue NÃO força template.
    payload = _pending_classify_payload(schema_engine, chash)
    assert "forced_template_id" not in payload
    assert payload["content_hash"] == chash


def test_reprocess_single_em_revisao(client: TestClient, schema_engine: Engine) -> None:
    """(b) EM_REVISAO → 200 idem (PROCESSANDO + requeue classify sem forced)."""
    chash = "b" * 64
    doc_id = _seed_doc_with_cr(schema_engine, content_hash=chash, state=DocState.EM_REVISAO)

    resp = client.post(f"/documents/{doc_id}/reprocess")
    assert resp.status_code == 200, resp.text

    with get_session(schema_engine) as session:
        assert session.get(Document, doc_id).state == DocState.PROCESSANDO
    payload = _pending_classify_payload(schema_engine, chash)
    assert "forced_template_id" not in payload


def test_reprocess_single_concluido_returns_409(
    client: TestClient, schema_engine: Engine
) -> None:
    """(c) doc CONCLUIDO → 409 (Pitfall 4: guard semântico, não 500)."""
    chash = "c" * 64
    doc_id = _seed_doc_with_cr(schema_engine, content_hash=chash, state=DocState.CONCLUIDO)

    resp = client.post(f"/documents/{doc_id}/reprocess")
    assert resp.status_code == 409, resp.text
    with get_session(schema_engine) as session:
        # Estado intacto; CR preservado (nada foi tocado).
        assert session.get(Document, doc_id).state == DocState.CONCLUIDO


def test_reprocess_single_nonexistent_returns_404(client: TestClient) -> None:
    """(d) id inexistente → 404."""
    resp = client.post("/documents/999999/reprocess")
    assert resp.status_code == 404, resp.text


def test_reprocess_batch_bucket_quarantine(
    client: TestClient, schema_engine: Engine
) -> None:
    """(e) bucket=quarentena reprocessa os 2 QUARENTENA; o EM_REVISAO fica intacto."""
    q1 = _seed_doc_with_cr(schema_engine, content_hash="1" * 64, state=DocState.QUARENTENA)
    q2 = _seed_doc_with_cr(schema_engine, content_hash="2" * 64, state=DocState.QUARENTENA)
    rev = _seed_doc_with_cr(schema_engine, content_hash="3" * 64, state=DocState.EM_REVISAO)

    resp = client.post("/documents/reprocess", json={"bucket": "quarentena"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["reprocessed"] == 2

    with get_session(schema_engine) as session:
        assert session.get(Document, q1).state == DocState.PROCESSANDO
        assert session.get(Document, q2).state == DocState.PROCESSANDO
        # O de EM_REVISAO não foi tocado pelo bucket quarentena.
        assert session.get(Document, rev).state == DocState.EM_REVISAO


def test_reprocess_batch_bucket_em_revisao(
    client: TestClient, schema_engine: Engine
) -> None:
    """(f) bucket=em_revisao reprocessa só o de revisão; QUARENTENA intacto."""
    q1 = _seed_doc_with_cr(schema_engine, content_hash="1" * 64, state=DocState.QUARENTENA)
    rev = _seed_doc_with_cr(schema_engine, content_hash="3" * 64, state=DocState.EM_REVISAO)

    resp = client.post("/documents/reprocess", json={"bucket": "em_revisao"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["reprocessed"] == 1

    with get_session(schema_engine) as session:
        assert session.get(Document, rev).state == DocState.PROCESSANDO
        assert session.get(Document, q1).state == DocState.QUARENTENA


def test_reprocess_batch_ids_ignores_ineligible(
    client: TestClient, schema_engine: Engine
) -> None:
    """(g) ids com um id fora dos estados elegíveis → ignorado (idempotente); a
    contagem reflete só os válidos."""
    q1 = _seed_doc_with_cr(schema_engine, content_hash="1" * 64, state=DocState.QUARENTENA)
    done = _seed_doc_with_cr(schema_engine, content_hash="c" * 64, state=DocState.CONCLUIDO)

    resp = client.post("/documents/reprocess", json={"ids": [q1, done, 999999]})
    assert resp.status_code == 200, resp.text
    # Só o elegível (q1) conta; CONCLUIDO e id inexistente são ignorados.
    assert resp.json()["reprocessed"] == 1

    with get_session(schema_engine) as session:
        assert session.get(Document, q1).state == DocState.PROCESSANDO
        assert session.get(Document, done).state == DocState.CONCLUIDO


def test_reprocess_batch_invalid_body_returns_422(
    client: TestClient, schema_engine: Engine
) -> None:
    """(h) body inválido (ambos ou nenhum de bucket+ids) → 422."""
    # Nenhum dos dois.
    resp = client.post("/documents/reprocess", json={})
    assert resp.status_code == 422, resp.text
    # Ambos preenchidos.
    resp = client.post(
        "/documents/reprocess", json={"bucket": "quarentena", "ids": [1]}
    )
    assert resp.status_code == 422, resp.text


# --- GET /documents/{id}/audit — auditoria por documento (read-only, D-02) ---


def test_audit_nonexistent_document_returns_404(client: TestClient) -> None:
    """Documento inexistente → 404 (mesmo guard do detalhe)."""
    resp = client.get("/documents/9999/audit")
    assert resp.status_code == 404, resp.text


def test_audit_returns_operations_and_can_undo(
    client: TestClient, schema_engine: Engine
) -> None:
    """Doc com AuditLog status=done → 200, can_undo=true, itens com origem→destino."""
    with get_session(schema_engine) as session:
        doc = Document(content_hash="a" * 64, original_filename="nf.pdf")
        session.add(doc)
        session.flush()
        session.add(
            AuditLog(
                document_id=doc.id,
                action="apply",
                status="done",
                source_path="/in/nf.pdf",
                dest_path="/out/2026/nf.pdf",
                run_id="run-123",
                content_hash="a" * 64,
            )
        )
        session.commit()
        doc_id = doc.id

    resp = client.get(f"/documents/{doc_id}/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["can_undo"] is True
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["source_path"] == "/in/nf.pdf"
    assert item["dest_path"] == "/out/2026/nf.pdf"
    assert item["run_id"] == "run-123"
    assert item["status"] == "done"
    # created_at sai tz-aware (offset UTC) via _as_utc.
    assert item["created_at"].endswith("+00:00") or item["created_at"].endswith("Z")


def test_audit_can_undo_false_when_only_undone(
    client: TestClient, schema_engine: Engine
) -> None:
    """Doc cujo único registro já foi revertido → can_undo=false, mas item aparece."""
    with get_session(schema_engine) as session:
        doc = Document(content_hash="b" * 64, original_filename="bol.pdf")
        session.add(doc)
        session.flush()
        session.add(
            AuditLog(
                document_id=doc.id,
                action="apply",
                status="undone",
                source_path="/in/bol.pdf",
                dest_path="/out/bol.pdf",
            )
        )
        session.commit()
        doc_id = doc.id

    resp = client.get(f"/documents/{doc_id}/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["can_undo"] is False
    assert len(body["items"]) == 1


def test_audit_empty_when_no_operations(
    client: TestClient, schema_engine: Engine
) -> None:
    """Doc sem nenhum AuditLog → 200 com lista vazia e can_undo=false."""
    with get_session(schema_engine) as session:
        doc = Document(content_hash="c" * 64, original_filename="x.pdf")
        session.add(doc)
        session.commit()
        doc_id = doc.id

    resp = client.get(f"/documents/{doc_id}/audit")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["can_undo"] is False

"""RED (Wave 0) — desfazer automações aplicadas (AUT-05).

Alvo: `app.automation.undo` (a criar; molde `fileops` + `cas.read_bytes`). Cobre:
- undo por-DOC: reverte dst→origem de um documento;
- undo por-RUN: reverte tudo que uma execução (run_id) aplicou de uma vez;
- `cas_fallback`: destino sumiu/mudou → restaura `cas.read_bytes(content_hash)`;
- pós-undo REABRE o documento aplicado: transita CONCLUIDO→PROCESSANDO (aresta nova).

`importorskip` evita ImportError fatal na coleta enquanto `undo` não existe.
"""

from pathlib import Path

import pytest
from sqlalchemy import Engine

undo = pytest.importorskip("app.automation.undo")

from app.models.audit_log import AuditLog  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.enums import DocState  # noqa: E402
from app.storage.db import get_session  # noqa: E402

from .conftest import ClassifiedDoc  # noqa: E402


def _seed_done(
    session, doc_id: int, content_hash: str, src: Path, dst: Path, run_id: str
) -> None:
    """Semeia um AuditLog(status='done') simulando uma automação já aplicada."""
    session.add(
        AuditLog(
            document_id=doc_id,
            action="apply",
            status="done",
            source_path=str(src),
            dest_path=str(dst),
            run_id=run_id,
            content_hash=content_hash,
        )
    )


def test_undo_per_doc_restores_source(
    schema_engine: Engine, classified_doc: ClassifiedDoc, src_dir: Path, dst_dir: Path
) -> None:
    """AUT-05: undo por-doc devolve o arquivo do destino para a origem."""
    src = src_dir / "in.pdf"
    dst = dst_dir / "saida.pdf"
    dst.write_bytes(b"aplicado")  # estado pós-apply: arquivo no destino
    with get_session(schema_engine) as session:
        _seed_done(session, classified_doc.document_id, classified_doc.content_hash, src, dst, "run-1")
        session.commit()
    with get_session(schema_engine) as session:
        undo.undo_document(session, document_id=classified_doc.document_id)
    assert src.exists()
    assert not dst.exists()


def test_undo_per_run_restores_all(
    schema_engine: Engine, classified_doc: ClassifiedDoc, src_dir: Path, dst_dir: Path
) -> None:
    """AUT-05: undo por-run reverte todos os 'done' daquele run_id."""
    src = src_dir / "in.pdf"
    dst = dst_dir / "saida.pdf"
    dst.write_bytes(b"aplicado")
    with get_session(schema_engine) as session:
        _seed_done(session, classified_doc.document_id, classified_doc.content_hash, src, dst, "run-batch")
        session.commit()
    with get_session(schema_engine) as session:
        revertidos = undo.undo_run(session, run_id="run-batch")
        assert revertidos >= 1
    assert src.exists()


def test_undo_cas_fallback(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    src_dir: Path,
    dst_dir: Path,
    data_dir,
    monkeypatch,
) -> None:
    """AUT-05: destino sumiu/mudou → restaura da rede final do CAS (read_bytes)."""
    src = src_dir / "in.pdf"
    dst = dst_dir / "sumiu.pdf"  # destino NÃO existe (sumiu)
    import app.automation.undo as undo_mod

    monkeypatch.setattr(undo_mod, "read_bytes_from_cas", lambda h: b"do cas")
    with get_session(schema_engine) as session:
        _seed_done(session, classified_doc.document_id, classified_doc.content_hash, src, dst, "run-cas")
        session.commit()
    with get_session(schema_engine) as session:
        undo.undo_document(session, document_id=classified_doc.document_id)
    assert src.exists()
    assert src.read_bytes() == b"do cas"


def test_undo_reopens_concluded_document(
    schema_engine: Engine, classified_doc: ClassifiedDoc, src_dir: Path, dst_dir: Path
) -> None:
    """Pós-undo: doc CONCLUIDO volta a PROCESSANDO via a aresta nova da allowlist."""
    src = src_dir / "in.pdf"
    dst = dst_dir / "saida.pdf"
    dst.write_bytes(b"aplicado")
    with get_session(schema_engine) as session:
        doc = session.get(Document, classified_doc.document_id)
        doc.state = DocState.CONCLUIDO
        _seed_done(session, doc.id, classified_doc.content_hash, src, dst, "run-1")
        session.commit()
    with get_session(schema_engine) as session:
        undo.undo_document(session, document_id=classified_doc.document_id)
    with get_session(schema_engine) as session:
        doc = session.get(Document, classified_doc.document_id)
        assert doc.state == DocState.PROCESSANDO

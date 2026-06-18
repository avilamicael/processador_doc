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
from sqlalchemy import Engine, select

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


def _seed_copy_done(
    session, doc_id: int, content_hash: str, src: Path, dst: Path, run_id: str
) -> None:
    """Semeia um AuditLog(action='copy', status='done') — uma cópia já aplicada."""
    session.add(
        AuditLog(
            document_id=doc_id,
            action="copy",
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


# --------------------------------------------------------------------------- #
# Fase 06.2 — undo de COPIAR (D-06): apaga a cópia, NUNCA toca o original.      #
# --------------------------------------------------------------------------- #


def test_undo_copy_deletes_copy_keeps_original(
    schema_engine: Engine, classified_doc: ClassifiedDoc, src_dir: Path, dst_dir: Path
) -> None:
    """D-06: undo de copy APAGA a cópia no dest_path; o original na source_path
    PERMANECE intacto (nunca foi tocado); audit.status='undone'."""
    src = src_dir / "original.pdf"
    src.write_bytes(b"original-intacto")  # o original existe e NÃO deve ser tocado
    dst = dst_dir / "copia.pdf"
    dst.write_bytes(b"a-copia")
    with get_session(schema_engine) as session:
        _seed_copy_done(
            session, classified_doc.document_id, classified_doc.content_hash, src, dst, "run-cp"
        )
        session.commit()
    with get_session(schema_engine) as session:
        undo.undo_document(session, document_id=classified_doc.document_id)
    # cópia apagada; original intacto.
    assert not dst.exists()
    assert src.exists()
    assert src.read_bytes() == b"original-intacto"
    with get_session(schema_engine) as session:
        audit = session.scalars(select(AuditLog)).first()
        assert audit.status == "undone"


def test_undo_run_copy_and_move_reverts_all(
    schema_engine: Engine, classified_doc: ClassifiedDoc, src_dir: Path, dst_dir: Path
) -> None:
    """D-06: undo por-run sobre copy(N)+move(1) → cópias apagadas E original movido
    restaurado, num só undo; reverted conta todas as operações."""
    src = src_dir / "in.pdf"  # origem do MOVE (restaurada pelo undo do move)
    copy_dst = dst_dir / "copia.pdf"
    copy_dst.write_bytes(b"a-copia")
    move_dst = dst_dir / "movido.pdf"
    move_dst.write_bytes(b"movido")
    with get_session(schema_engine) as session:
        _seed_copy_done(
            session, classified_doc.document_id, classified_doc.content_hash, src, copy_dst, "run-mix"
        )
        _seed_done(
            session, classified_doc.document_id, classified_doc.content_hash, src, move_dst, "run-mix"
        )
        session.commit()
    with get_session(schema_engine) as session:
        reverted = undo.undo_run(session, run_id="run-mix")
        assert reverted == 2
    # cópia apagada; original do move restaurado à origem.
    assert not copy_dst.exists()
    assert src.exists()


def test_undo_copy_missing_dest_is_safe_noop(
    schema_engine: Engine, classified_doc: ClassifiedDoc, src_dir: Path, dst_dir: Path
) -> None:
    """D-06: undo de cópia cujo dest já sumiu → no-op seguro (missing_ok),
    audit.status='undone', original NUNCA tocado (não restaura do CAS p/ cópia)."""
    src = src_dir / "original.pdf"
    src.write_bytes(b"original-intacto")
    dst = dst_dir / "sumiu.pdf"  # cópia já apagada pelo usuário
    with get_session(schema_engine) as session:
        _seed_copy_done(
            session, classified_doc.document_id, classified_doc.content_hash, src, dst, "run-gone"
        )
        session.commit()
    with get_session(schema_engine) as session:
        undo.undo_document(session, document_id=classified_doc.document_id)
    # original intacto; sem restauração de CAS para cópia.
    assert src.exists()
    assert src.read_bytes() == b"original-intacto"
    with get_session(schema_engine) as session:
        audit = session.scalars(select(AuditLog)).first()
        assert audit.status == "undone"

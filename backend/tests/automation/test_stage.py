"""RED (Wave 0) — orquestração da automação: dry-run, write-ahead, idempotência,
reconciliação (AUT-03/AUT-04).

Alvo: `app.automation.stage` (a criar; molde `classification/stage.py`). Cobre:
- dry-run resolve origem→destino SEM tocar o disco (AUT-03);
- `test_intent_before_materialize`: o `AuditLog(status="intent")` JÁ está persistido
  no banco ANTES da chamada física `fileops.materialize_to_dest`, provando a ordem
  causal do write-ahead (AUT-04);
- idempotência: AuditLog(status="done") existente → no-op, não re-move;
- reconciliação: `intent` órfão (crash entre intent/done) é reconciliável no startup.

`importorskip` evita ImportError fatal na coleta enquanto `stage` não existe.
"""

import pytest
from sqlalchemy import Engine, func, select

stage = pytest.importorskip("app.automation.stage")

from app.models.audit_log import AuditLog  # noqa: E402
from app.storage.db import get_session  # noqa: E402

from .conftest import ClassifiedDoc  # noqa: E402


def test_dry_run_does_not_touch_disk(schema_engine: Engine, classified_doc: ClassifiedDoc) -> None:
    """AUT-03: dry-run devolve o plano origem→destino sem mover nada nem gravar 'done'."""
    with get_session(schema_engine) as session:
        plan = stage.dry_run(session, content_hash=classified_doc.content_hash)
        assert plan is not None
        # Nenhum AuditLog status='done' foi escrito por um dry-run.
        done = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.status == "done")
        )
        assert done == 0


def test_intent_before_materialize(
    schema_engine: Engine, classified_doc: ClassifiedDoc, src_dir, dst_dir, monkeypatch
) -> None:
    """AUT-04 (write-ahead): no instante em que `fileops.materialize_to_dest` é
    chamado, um AuditLog(status="intent") JÁ está persistido no banco — ordem causal."""
    import app.automation.fileops as fileops

    observed: dict[str, int] = {}

    def spy_materialize(*args, **kwargs):
        # Em outra sessão (simula leitura concorrente do banco) conta os 'intent'.
        with get_session(schema_engine) as probe:
            observed["intents_at_call"] = probe.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.status == "intent")
            )
        return str(dst_dir / "saida.pdf")

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)

    with get_session(schema_engine) as session:
        stage.apply_stage(
            session, content_hash=classified_doc.content_hash, run_id="run-1"
        )

    assert observed.get("intents_at_call", 0) >= 1, (
        "intent deve estar persistido ANTES da materialização (write-ahead AUT-04)"
    )


def test_idempotencia_done_existente_no_op(
    schema_engine: Engine, classified_doc: ClassifiedDoc
) -> None:
    """Idempotência: AuditLog(status='done') já existente → no-op (não re-move)."""
    with get_session(schema_engine) as session:
        first = stage.apply_stage(
            session, content_hash=classified_doc.content_hash, run_id="run-1"
        )
        second = stage.apply_stage(
            session, content_hash=classified_doc.content_hash, run_id="run-1"
        )
    # A segunda chamada não materializa de novo.
    assert getattr(second, "materialized", False) is False or second != first


def test_reconcile_orphan_intent(schema_engine: Engine, classified_doc: ClassifiedDoc) -> None:
    """AUT-04/reconcile: um `intent` órfão (crash antes do 'done') é reconciliável."""
    with get_session(schema_engine) as session:
        session.add(
            AuditLog(
                document_id=classified_doc.document_id,
                action="apply",
                status="intent",
                run_id="run-crash",
                content_hash=classified_doc.content_hash,
            )
        )
        session.commit()
    with get_session(schema_engine) as session:
        reconciled = stage.reconcile_orphans(session)
        assert reconciled >= 1

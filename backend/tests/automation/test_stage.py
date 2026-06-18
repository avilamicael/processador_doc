"""GREEN (Wave 2) — orquestração da automação sobre o PIPELINE: dry-run, write-ahead,
idempotência, reconciliação, route (P9) e no-match (P10).

Alvo: `app.automation.stage` reescrito sobre `pipeline.run_pipeline`. Cobre:
- dry-run simula o pipeline inteiro SEM tocar o disco (AUT-03);
- `test_intent_before_materialize`: o `AuditLog(status="intent")` JÁ está persistido
  ANTES da chamada física `fileops.materialize_to_dest` (write-ahead AUT-04);
- idempotência: AuditLog(status="done") existente → no-op, não re-move;
- reconciliação: `intent` órfão (crash entre intent/done) é reconciliável no startup;
- NOVOS: route interrompe e NÃO materializa (P9); no-match não materializa p/ raiz (P10).

`apply_stage` é COROUTINE (espelha classify_stage) → os testes usam `asyncio.run`.
"""

import asyncio

import pytest
from sqlalchemy import Engine, func, select

stage = pytest.importorskip("app.automation.stage")

from app.models.audit_log import AuditLog  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.enums import DocState  # noqa: E402
from app.storage.db import get_session  # noqa: E402

from .conftest import ClassifiedDoc  # noqa: E402


def _rename_pipeline(pipeline_factory) -> int:
    """Pipeline com UM step rename que casa todo doc (sem filtros)."""
    return pipeline_factory(
        name="P-rename",
        steps=[
            {
                "action_type": "rename",
                "params_json": '{"name_pattern": "{cliente}_{numero}"}',
            }
        ],
    )


def test_dry_run_does_not_touch_disk(
    schema_engine: Engine, classified_doc: ClassifiedDoc, pipeline_factory
) -> None:
    """AUT-03: dry-run simula o pipeline e não grava 'done' nem move."""
    _rename_pipeline(pipeline_factory)
    with get_session(schema_engine) as session:
        plan = stage.dry_run(session, content_hash=classified_doc.content_hash)
        assert plan is not None
        assert plan.materialized is False
        done = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.status == "done")
        )
        assert done == 0


def test_intent_before_materialize(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    src_dir,
    dst_dir,
    pipeline_factory,
    monkeypatch,
) -> None:
    """AUT-04 (write-ahead): quando `materialize_to_dest` é chamado, um
    AuditLog(status="intent") JÁ está persistido — ordem causal (materialização única)."""
    import app.automation.fileops as fileops

    _rename_pipeline(pipeline_factory)
    observed: dict[str, int] = {}

    def spy_materialize(*args, **kwargs):
        with get_session(schema_engine) as probe:
            observed["intents_at_call"] = probe.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.status == "intent")
            )
        return str(dst_dir / "saida.pdf")

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)

    with get_session(schema_engine) as session:
        asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-1"
            )
        )

    assert observed.get("intents_at_call", 0) >= 1, (
        "intent deve estar persistido ANTES da materialização (write-ahead AUT-04)"
    )


def test_idempotencia_done_existente_no_op(
    schema_engine: Engine, classified_doc: ClassifiedDoc, pipeline_factory, monkeypatch
) -> None:
    """Idempotência: AuditLog(status='done') já existente → no-op (não re-move)."""
    import app.automation.fileops as fileops

    _rename_pipeline(pipeline_factory)
    monkeypatch.setattr(fileops, "materialize_to_dest", lambda *a, **k: str(a[1]))
    monkeypatch.setattr(fileops, "remove_original", lambda *a, **k: None)

    with get_session(schema_engine) as session:
        first = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-1"
            )
        )
        second = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-1"
            )
        )
    assert first.materialized is True
    assert second.materialized is False


def test_reconcile_orphan_intent(
    schema_engine: Engine, classified_doc: ClassifiedDoc
) -> None:
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


def test_route_stops_no_materialize(
    schema_engine: Engine, classified_doc: ClassifiedDoc, pipeline_factory, monkeypatch
) -> None:
    """Pitfall 9: step Rotear interrompe o pipeline e NÃO materializa."""
    import app.automation.fileops as fileops

    def fail_materialize(*args, **kwargs):  # pragma: no cover
        raise AssertionError("route NÃO deve materializar")

    monkeypatch.setattr(fileops, "materialize_to_dest", fail_materialize)

    pipeline_factory(
        name="P-route",
        steps=[
            {"action_type": "route", "params_json": '{"target": "em_revisao"}'},
            {"action_type": "move", "params_json": '{"folder_pattern": "NUNCA"}'},
        ],
    )

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-r"
            )
        )
        assert result.routed is True
        assert result.route_target == "em_revisao"
        assert result.materialized is False
        # Nenhum AuditLog 'done' (não materializou).
        done = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.status == "done")
        )
        assert done == 0
        doc = session.get(Document, classified_doc.document_id)
        assert doc.state == DocState.EM_REVISAO


def test_gate_identify_file_no_match_stops_no_materialize(
    schema_engine: Engine, classified_doc: ClassifiedDoc, pipeline_factory, monkeypatch
) -> None:
    """D-17/D-18: gate identify_file cuja extensão NÃO casa interrompe o pipeline
    e NÃO materializa (doc mantido na origem, estado inalterado)."""
    import app.automation.fileops as fileops

    def fail_materialize(*args, **kwargs):  # pragma: no cover
        raise AssertionError("gate parado NÃO deve materializar")

    monkeypatch.setattr(fileops, "materialize_to_dest", fail_materialize)

    # O doc semeado é entrada.pdf; o gate exige .xlsx → não casa → para.
    pipeline_factory(
        name="P-gatefile",
        steps=[
            {
                "action_type": "identify_file",
                "params_json": '{"extensions": [".xlsx"]}',
            },
            {"action_type": "move", "params_json": '{"folder_pattern": "NUNCA"}'},
        ],
    )

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-gf"
            )
        )
        assert result.no_match is True
        assert result.materialized is False
        done = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.status == "done")
        )
        assert done == 0
        doc = session.get(Document, classified_doc.document_id)
        assert doc.state == DocState.PROCESSANDO
        assert doc.last_completed_step == "classificado"


def test_gate_identify_file_match_proceeds(
    schema_engine: Engine, classified_doc: ClassifiedDoc, pipeline_factory, monkeypatch
) -> None:
    """D-17: gate identify_file cuja extensão CASA deixa o pipeline seguir e a etapa
    de ação seguinte materializa normalmente."""
    import app.automation.fileops as fileops

    moved = {"called": False}

    def spy_materialize(content_hash, dst):
        moved["called"] = True
        return str(dst)

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)
    monkeypatch.setattr(fileops, "remove_original", lambda *a, **k: None)

    pipeline_factory(
        name="P-gatefile-ok",
        steps=[
            {
                "action_type": "identify_file",
                "params_json": '{"extensions": ["PDF"]}',
            },
            {
                "action_type": "rename",
                "params_json": '{"name_pattern": "{cliente}_{numero}"}',
            },
        ],
    )

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-gfok"
            )
        )
        assert result.no_match is False
        assert result.materialized is True
        assert moved["called"] is True


def test_no_match_keeps_origin_no_materialize(
    schema_engine: Engine, classified_doc: ClassifiedDoc, pipeline_factory, monkeypatch
) -> None:
    """Pitfall 10: nenhuma etapa casa → doc mantido na origem, SEM transição, SEM disco."""
    import app.automation.fileops as fileops

    def fail_materialize(*args, **kwargs):  # pragma: no cover
        raise AssertionError("no-match NÃO deve materializar p/ a raiz")

    monkeypatch.setattr(fileops, "materialize_to_dest", fail_materialize)

    # Step com filtro que NÃO casa (cliente != valor semeado).
    pipeline_factory(
        name="P-nomatch",
        steps=[
            {
                "action_type": "move",
                "params_json": '{"folder_pattern": "NF"}',
                "filters": [
                    {
                        "filter_type": "field",
                        "field_name": "cliente",
                        "operator": "eq",
                        "value": "Outra Empresa",
                    }
                ],
            }
        ],
    )

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-n"
            )
        )
        assert result.no_match is True
        assert result.materialized is False
        done = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.status == "done")
        )
        assert done == 0
        doc = session.get(Document, classified_doc.document_id)
        # Estado inalterado (permanece PROCESSANDO + último marcador).
        assert doc.state == DocState.PROCESSANDO
        assert doc.last_completed_step == "classificado"

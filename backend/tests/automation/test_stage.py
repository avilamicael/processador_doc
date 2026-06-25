"""Orquestração da automação sobre o MODELO FINAL: dry-run, write-ahead,
idempotência, reconciliação, no-match (D-25) e blocked (D-07).

Alvo: `app.automation.stage` sobre `executor.evaluate_automations`. Cobre:
- dry-run simula as automações SEM tocar o disco (AUT-03);
- `test_intent_before_materialize`: o `AuditLog(status="intent")` JÁ está persistido
  ANTES da chamada física `fileops.materialize_to_dest` (write-ahead AUT-04);
- idempotência: AuditLog(status="done") existente → no-op, não re-move;
- reconciliação: `intent` órfão (crash entre intent/done) é reconciliável no startup;
- no-match: nenhuma automação casa → não materializa, doc fica na origem (D-25);
- blocked: campo faltante no padrão → rebaixa para revisão sem mover (D-07);
- first-match-wins: a primeira automação que casa vence (D-25).

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


def _rename_automation(automation_factory) -> int:
    """Automação com UM rename + uma condição que casa todo doc (.pdf semeado)."""
    return automation_factory(
        name="A-rename",
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[
            {
                "action_type": "rename",
                "params_json": '{"name_pattern": "{cliente}_{numero}"}',
            }
        ],
    )


def test_dry_run_does_not_touch_disk(
    schema_engine: Engine, classified_doc: ClassifiedDoc, automation_factory
) -> None:
    """AUT-03: dry-run simula as automações e não grava 'done' nem move."""
    _rename_automation(automation_factory)
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
    automation_factory,
    monkeypatch,
) -> None:
    """AUT-04 (write-ahead): quando `materialize_to_dest` é chamado, um
    AuditLog(status="intent") JÁ está persistido — ordem causal (materialização única)."""
    import app.automation.fileops as fileops

    _rename_automation(automation_factory)
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
    schema_engine: Engine, classified_doc: ClassifiedDoc, automation_factory, monkeypatch
) -> None:
    """Idempotência: AuditLog(status='done') já existente → no-op (não re-move)."""
    import app.automation.fileops as fileops

    _rename_automation(automation_factory)
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


def test_split_audit_does_not_block_apply(
    schema_engine: Engine, classified_doc: ClassifiedDoc, automation_factory, monkeypatch
) -> None:
    """Regressão (deploy 2026-06-25): o AuditLog 'done' da materialização de split
    (action='apply' + details com SPLIT_MATERIALIZE_DETAILS_PREFIX) NÃO pode contar
    como 'automação já aplicada'. Antes do fix, `_has_done` casava esse audit e o apply
    virava no-op eterno — docs de pasta com split nunca aplicavam a automação."""
    import app.automation.fileops as fileops
    from app.models.audit_log import SPLIT_MATERIALIZE_DETAILS_PREFIX

    _rename_automation(automation_factory)
    monkeypatch.setattr(fileops, "materialize_to_dest", lambda *a, **k: str(a[1]))
    monkeypatch.setattr(fileops, "remove_original", lambda *a, **k: None)

    # Semeia o audit deixado pela materialização do split (bloco gravado na pasta).
    with get_session(schema_engine) as session:
        session.add(
            AuditLog(
                document_id=classified_doc.document_id,
                action="apply",
                status="done",
                details=f"{SPLIT_MATERIALIZE_DETAILS_PREFIX} grava bloco na pasta",
                content_hash=classified_doc.content_hash,
            )
        )
        session.commit()
        # O audit de split é ignorado pela idempotência.
        assert stage._has_done(session, classified_doc.document_id) is False

    # apply_stage roda a automação real (materializa) APESAR do audit de split presente.
    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-split"
            )
        )
    assert result.materialized is True
    assert result.no_match is False


def test_plan_dest_preserva_extensao_com_valor_pontuado() -> None:
    """Bug 2 (deploy 2026-06-25): Numero_NF '000.076.737' tem pontos; o sistema NÃO pode
    confundir '.737' com extensão — deve preservar a extensão real do original (.pdf)."""
    from pathlib import Path

    from app.automation.executor import AutomationPlan

    source = Path("/mon/TESTE/nota_p1.pdf")
    plan = AutomationPlan(
        target_folder=Path("/dest/LABORATORIO"),
        target_name="LABORATORIO OPTICO UPLAB LTDA_000.076.737",
        matched=True,
    )
    assert stage._plan_dest(source, plan).name == (
        "LABORATORIO OPTICO UPLAB LTDA_000.076.737.pdf"
    )


def test_plan_dest_respeita_extensao_do_usuario() -> None:
    """Se o padrão de rename trouxe uma extensão REAL (.txt), respeita — não acrescenta
    a do original."""
    from pathlib import Path

    from app.automation.executor import AutomationPlan

    source = Path("/mon/TESTE/file.pdf")
    plan = AutomationPlan(
        target_folder=Path("/dest"), target_name="nota_123.txt", matched=True
    )
    assert stage._plan_dest(source, plan).name == "nota_123.txt"


def test_source_path_resolve_bloco_de_split_pelo_content_hash(
    schema_engine: Engine,
) -> None:
    """Bug 1 (deploy 2026-06-25): para doc de split, _source_path resolve o BLOCO real
    no disco ('nota_p1.pdf', gate por content_hash), NÃO o original pré-split apontado
    por origin_original_id (já removido). Sem isso, remove_original mira arquivo
    inexistente e o bloco fica órfão após o move."""
    from pathlib import Path

    from app.models.document import Document
    from app.models.ingested_original import IngestedOriginal
    from app.models.watched_folder import WatchedFolder

    block_hash = "b" * 64
    with get_session(schema_engine) as session:
        folder = WatchedFolder(path="/mon/TESTE")
        session.add(folder)
        session.flush()
        # Gate do ORIGINAL pré-split (origin_original_id aponta aqui).
        orig = IngestedOriginal(
            original_hash="o" * 64,
            original_filename="nota.pdf",
            source_folder_id=folder.id,
            block_count=1,
        )
        session.add(orig)
        # Gate do BLOCO (nome real no disco) — original_hash == content_hash do doc.
        session.add(
            IngestedOriginal(
                original_hash=block_hash,
                original_filename="nota_p1.pdf",
                source_folder_id=folder.id,
                block_count=0,
            )
        )
        session.flush()
        doc = Document(
            content_hash=block_hash,
            original_filename="nota.pdf",
            origin_original_id=orig.id,
            state=DocState.PROCESSANDO,
            last_completed_step=stage.CLASSIFIED_STEP,
        )
        session.add(doc)
        session.commit()
        src = stage._source_path(session, doc)
    assert src == Path("/mon/TESTE") / "nota_p1.pdf"


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


def test_blocked_missing_field_goes_to_review(
    schema_engine: Engine, classified_doc: ClassifiedDoc, automation_factory, monkeypatch
) -> None:
    """D-07: token p/ campo faltante → rebaixa para EM_REVISAO sem mover."""
    import app.automation.fileops as fileops

    def fail_materialize(*args, **kwargs):  # pragma: no cover
        raise AssertionError("blocked NÃO deve materializar")

    monkeypatch.setattr(fileops, "materialize_to_dest", fail_materialize)

    automation_factory(
        name="A-blocked",
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[
            {
                "action_type": "rename",
                "params_json": '{"name_pattern": "{obrigatorio_faltante}"}',
            }
        ],
    )

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-b"
            )
        )
        assert result.blocked is True
        assert result.materialized is False
        done = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.status == "done")
        )
        assert done == 0
        doc = session.get(Document, classified_doc.document_id)
        assert doc.state == DocState.EM_REVISAO


def test_first_matching_automation_wins(
    schema_engine: Engine, classified_doc: ClassifiedDoc, automation_factory, monkeypatch
) -> None:
    """D-25: a PRIMEIRA automação (menor position) cujas condições casam executa
    suas ações; as demais NÃO rodam."""
    import app.automation.fileops as fileops

    captured = {}

    def spy_materialize(content_hash, dst):
        captured["dst"] = str(dst)
        return str(dst)

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)
    monkeypatch.setattr(fileops, "remove_original", lambda *a, **k: None)

    # Específica (position 0) e genérica (position 1) ambas casam .pdf; a primeira vence.
    automation_factory(
        name="Específica",
        position=0,
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[{"action_type": "move", "params_json": '{"dest_folder": "ESPECIFICA"}'}],
    )
    automation_factory(
        name="Genérica",
        position=1,
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[{"action_type": "move", "params_json": '{"dest_folder": "GENERICA"}'}],
    )

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-fm"
            )
        )
        assert result.materialized is True
        assert "ESPECIFICA" in captured["dst"]
        assert "GENERICA" not in captured["dst"]


def test_match_proceeds_and_materializes(
    schema_engine: Engine, classified_doc: ClassifiedDoc, automation_factory, monkeypatch
) -> None:
    """Automação cujas condições casam executa a ação e materializa normalmente."""
    import app.automation.fileops as fileops

    moved = {"called": False}

    def spy_materialize(content_hash, dst):
        moved["called"] = True
        return str(dst)

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)
    monkeypatch.setattr(fileops, "remove_original", lambda *a, **k: None)

    automation_factory(
        name="A-ok",
        conditions=[{"field": "extension", "operator": "eq", "value": "PDF"}],
        actions=[
            {
                "action_type": "rename",
                "params_json": '{"name_pattern": "{cliente}_{numero}"}',
            }
        ],
    )

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-ok"
            )
        )
        assert result.no_match is False
        assert result.materialized is True
        assert moved["called"] is True


def test_no_match_keeps_origin_no_materialize(
    schema_engine: Engine, classified_doc: ClassifiedDoc, automation_factory, monkeypatch
) -> None:
    """D-25: nenhuma automação casa → doc mantido na origem, SEM transição, SEM disco."""
    import app.automation.fileops as fileops

    def fail_materialize(*args, **kwargs):  # pragma: no cover
        raise AssertionError("no-match NÃO deve materializar p/ a raiz")

    monkeypatch.setattr(fileops, "materialize_to_dest", fail_materialize)

    # Condição que NÃO casa (cliente != valor semeado).
    automation_factory(
        name="A-nomatch",
        conditions=[
            {
                "field": "field",
                "field_name": "cliente",
                "operator": "eq",
                "value": "Outra Empresa",
            }
        ],
        actions=[{"action_type": "move", "params_json": '{"dest_folder": "NF"}'}],
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


def test_no_automations_is_no_match(
    schema_engine: Engine, classified_doc: ClassifiedDoc, monkeypatch
) -> None:
    """Sem nenhuma automação cadastrada → no-match (doc fica na origem)."""
    import app.automation.fileops as fileops

    def fail_materialize(*args, **kwargs):  # pragma: no cover
        raise AssertionError("sem automações NÃO deve materializar")

    monkeypatch.setattr(fileops, "materialize_to_dest", fail_materialize)

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-empty"
            )
        )
        assert result.no_match is True
        assert result.materialized is False


# --------------------------------------------------------------------------- #
# Fase 06.2 — ação COPIAR (multi-saída): materializa cada cópia SEM remover o   #
# original; write-ahead por cópia (D-07); cópias antes do move (D-03);          #
# anti-colisão por cópia (D-07/D-09/D-10); undo discrimina copy.                #
# --------------------------------------------------------------------------- #


def _copy_only_automation(automation_factory, dest="ARQUIVO") -> int:
    """Automação com UMA ação copy (sem move/rename) que casa todo .pdf semeado."""
    return automation_factory(
        name="A-copy",
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[
            {"action_type": "copy", "params_json": f'{{"dest_folder": "{dest}"}}'}
        ],
    )


def test_copy_only_materializes_and_keeps_original(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    automation_factory,
    monkeypatch,
) -> None:
    """D-01: copy materializa no destino E o original PERMANECE (remove_original NÃO
    é chamado); doc vai a CONCLUIDO; AuditLog(action='copy', status='done')."""
    import app.automation.fileops as fileops

    copied: list[str] = []
    remove_calls: list[str] = []

    def spy_materialize(content_hash, dst):
        copied.append(str(dst))
        return str(dst)

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)
    monkeypatch.setattr(
        fileops, "remove_original", lambda src: remove_calls.append(str(src))
    )

    _copy_only_automation(automation_factory)

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-c1"
            )
        )
        assert result.materialized is True
        assert result.no_match is False
        assert len(copied) == 1
        # D-01: copy NUNCA remove o original.
        assert remove_calls == []
        copy_done = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "copy", AuditLog.status == "done")
        )
        assert copy_done == 1
        doc = session.get(Document, classified_doc.document_id)
        assert doc.state == DocState.CONCLUIDO


def test_copy_write_ahead_intent_before_materialize(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    automation_factory,
    monkeypatch,
) -> None:
    """D-07: o AuditLog(action='copy', status='intent') já está persistido ANTES da
    chamada física `materialize_to_dest` da cópia."""
    import app.automation.fileops as fileops

    observed: dict[str, int] = {}

    def spy_materialize(content_hash, dst):
        with get_session(schema_engine) as probe:
            observed["copy_intents"] = probe.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "copy", AuditLog.status == "intent")
            )
        return str(dst)

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)
    monkeypatch.setattr(fileops, "remove_original", lambda *a, **k: None)

    _copy_only_automation(automation_factory)

    with get_session(schema_engine) as session:
        asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-c2"
            )
        )
    assert observed.get("copy_intents", 0) >= 1


def test_n_copies_yield_n_audit_logs(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    automation_factory,
    monkeypatch,
) -> None:
    """N cópias → N AuditLog(action='copy', status='done'), mesmo run_id/document_id."""
    import app.automation.fileops as fileops

    copied: list[str] = []
    monkeypatch.setattr(
        fileops, "materialize_to_dest", lambda h, dst: copied.append(str(dst)) or str(dst)
    )
    monkeypatch.setattr(fileops, "remove_original", lambda *a, **k: None)

    automation_factory(
        name="A-2copies",
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[
            {"action_type": "copy", "params_json": '{"dest_folder": "A"}'},
            {"action_type": "copy", "params_json": '{"dest_folder": "B"}'},
        ],
    )

    with get_session(schema_engine) as session:
        asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-c3"
            )
        )
        rows = session.scalars(
            select(AuditLog).where(
                AuditLog.action == "copy", AuditLog.status == "done"
            )
        ).all()
        assert len(rows) == 2
        assert len(copied) == 2
        assert all(r.run_id == "run-c3" for r in rows)
        assert all(r.document_id == classified_doc.document_id for r in rows)


def test_copies_before_move_order(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    automation_factory,
    monkeypatch,
) -> None:
    """D-03: as cópias materializam PRIMEIRO; o move é o ÚLTIMO e só então remove
    o original (remove_original chamado DEPOIS de todas as cópias)."""
    import app.automation.fileops as fileops

    events: list[str] = []

    def spy_materialize(content_hash, dst):
        events.append(f"materialize:{Path(dst).parent.name}")
        return str(dst)

    def spy_remove(src):
        events.append("remove_original")

    from pathlib import Path

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)
    monkeypatch.setattr(fileops, "remove_original", spy_remove)

    automation_factory(
        name="A-copy-move",
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[
            {"action_type": "copy", "params_json": '{"dest_folder": "ARQUIVO"}'},
            {"action_type": "move", "params_json": '{"dest_folder": "PROCESSADOS"}'},
        ],
    )

    with get_session(schema_engine) as session:
        asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-c4"
            )
        )
        # remove_original (do move) só pode acontecer DEPOIS da cópia.
        assert "remove_original" in events
        assert events.index("materialize:ARQUIVO") < events.index("remove_original")
        copy_done = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "copy", AuditLog.status == "done")
        )
        move_done = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "apply", AuditLog.status == "done")
        )
        assert copy_done == 1
        assert move_done == 1


def test_rename_copy_no_move_keeps_original(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    automation_factory,
    monkeypatch,
) -> None:
    """CR-01 / D-01: rename + copy SEM move NÃO remove o original.

    Regressão do BLOCKER: a heurística antiga inferia o "move efetivo" do (folder,
    name) final; com rename+copy o nome mudava → `is_default_target=False` →
    `has_effective_move=True` → o caminho de move rodava e REMOVIA o original (perda
    de arquivo). Com o flag explícito `has_explicit_move` (que SÓ a ação move liga),
    rename+copy sem move continua copy-only: o original PERMANECE, o doc conclui e a
    cópia é criada já com o nome RENOMEADO (D-03).

    Sem o fix este teste FALHA: `remove_original` seria chamado (remove_calls != [])
    e o doc passaria pelo caminho de move (não copy-only).
    """
    import app.automation.fileops as fileops

    copied: list[str] = []
    remove_calls: list[str] = []

    def spy_materialize(content_hash, dst):
        copied.append(str(dst))
        return str(dst)

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)
    monkeypatch.setattr(
        fileops, "remove_original", lambda src: remove_calls.append(str(src))
    )

    automation_factory(
        name="A-rename-copy-no-move",
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[
            {
                "action_type": "rename",
                "params_json": '{"name_pattern": "{cliente}_{numero}"}',
            },
            {"action_type": "copy", "params_json": '{"dest_folder": "ARQUIVO"}'},
        ],
    )

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-rc"
            )
        )
        # D-01: o original NUNCA é removido (a essência do BLOCKER CR-01).
        assert remove_calls == []
        # Copy-only: apenas a cópia foi materializada (sem saída de move).
        assert len(copied) == 1
        # A cópia herdou o nome RENOMEADO (rename antes da copy, D-03).
        assert "ACME Ltda_1234" in copied[0]
        assert "ARQUIVO" in copied[0]
        # O documento conclui mesmo sem move (copy-only, D-05).
        doc = session.get(Document, classified_doc.document_id)
        assert doc.state == DocState.CONCLUIDO
        # Não há saída de move no resultado — só a cópia.
        kinds = [o.kind for o in result.outputs]
        assert kinds == ["copy"]


def test_move_copy_removes_original_after_copy(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    automation_factory,
    monkeypatch,
) -> None:
    """D-03 (guarda): move + copy AINDA remove o original — DEPOIS da cópia.

    Contraponto ao teste CR-01: quando HÁ uma ação move explícita, o move efetivo
    roda e `remove_original` é chamado (uma vez), porém só APÓS a cópia materializar.
    """
    from pathlib import Path

    import app.automation.fileops as fileops

    events: list[str] = []
    remove_calls: list[str] = []

    def spy_materialize(content_hash, dst):
        events.append(f"materialize:{Path(dst).parent.name}")
        return str(dst)

    def spy_remove(src):
        events.append("remove_original")
        remove_calls.append(str(src))

    monkeypatch.setattr(fileops, "materialize_to_dest", spy_materialize)
    monkeypatch.setattr(fileops, "remove_original", spy_remove)

    automation_factory(
        name="A-move-copy",
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[
            {"action_type": "copy", "params_json": '{"dest_folder": "ARQUIVO"}'},
            {"action_type": "move", "params_json": '{"dest_folder": "PROCESSADOS"}'},
        ],
    )

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-mc"
            )
        )
        # D-03: o original É removido (move efetivo), mas DEPOIS da cópia.
        assert len(remove_calls) == 1
        assert events.index("materialize:ARQUIVO") < events.index("remove_original")
        kinds = [o.kind for o in result.outputs]
        assert "copy" in kinds
        assert "move" in kinds


def test_copy_collision_suffix(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    automation_factory,
    monkeypatch,
    tmp_path,
) -> None:
    """D-07/D-09: destino de cópia ocupado por conteúdo diferente → sufixo; nunca
    sobrescreve."""
    from pathlib import Path

    import app.automation.fileops as real_fileops
    import app.automation.stage as stage_mod

    base = tmp_path / "organizados"
    monkeypatch.setattr(stage_mod, "_base_root", lambda: base)

    # destino pré-ocupado com conteúdo DIFERENTE para forçar sufixo.
    dest_dir = base / "ARQUIVO"
    dest_dir.mkdir(parents=True)
    occupied = dest_dir / "entrada.pdf"
    occupied.write_bytes(b"conteudo-diferente-pre-existente")

    materialized: list[str] = []

    def spy_materialize(content_hash, dst):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(b"conteudo-da-copia")
        materialized.append(str(dst))
        return str(dst)

    monkeypatch.setattr(real_fileops, "materialize_to_dest", spy_materialize)
    monkeypatch.setattr(real_fileops, "remove_original", lambda *a, **k: None)

    # hash_file determinístico: o destino ocupado ("ARQUIVO/entrada.pdf") tem hash
    # diferente da origem → resolve_collision deve gerar sufixo "_1" (D-09).
    def fake_hash(p):
        return "DST" if "ARQUIVO" in str(p) else "SRC"

    monkeypatch.setattr(real_fileops, "hash_file", fake_hash)

    _copy_only_automation(automation_factory)

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-c5"
            )
        )
        assert result.materialized is True
        # destino original pré-existente intacto + cópia com sufixo.
        assert occupied.read_bytes() == b"conteudo-diferente-pre-existente"
        assert any("entrada_1.pdf" in m for m in materialized)


def test_copy_idempotent_no_rematerialize(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    automation_factory,
    monkeypatch,
) -> None:
    """Idempotência: re-rodar apply_stage com cópias já 'done' → no-op (não re-materializa)."""
    import app.automation.fileops as fileops

    calls = {"n": 0}
    monkeypatch.setattr(
        fileops, "materialize_to_dest", lambda h, dst: calls.update(n=calls["n"] + 1) or str(dst)
    )
    monkeypatch.setattr(fileops, "remove_original", lambda *a, **k: None)

    _copy_only_automation(automation_factory)

    with get_session(schema_engine) as session:
        asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-c6"
            )
        )
        second = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-c6"
            )
        )
    assert calls["n"] == 1
    assert second.materialized is False


# --------------------------------------------------------------------------- #
# Fase 9 (D-05): destino cuja RAIZ/anchor NÃO existe bloqueia no dry-run E no   #
# apply — nunca tenta criar a unidade nem chamar mkdir.                          #
# --------------------------------------------------------------------------- #


def _missing_root_automation(automation_factory) -> int:
    """Automação move para um drive Windows fictício cujo anchor não existe (Z:\\)."""
    return automation_factory(
        name="A-missing-root",
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[
            {
                "action_type": "move",
                "params_json": '{"dest_folder": "Z:\\\\inexistente\\\\{cliente}"}',
            }
        ],
    )


def test_missing_root_blocks_dry_run(
    schema_engine: Engine, classified_doc: ClassifiedDoc, automation_factory
) -> None:
    """D-05: destino cujo anchor (drive Z:\\) não existe → dry_run.blocked=True,
    sem exceção e sem tocar o disco."""
    _missing_root_automation(automation_factory)
    with get_session(schema_engine) as session:
        plan = stage.dry_run(session, content_hash=classified_doc.content_hash)
        assert plan is not None
        assert plan.blocked is True
        assert plan.materialized is False


def test_missing_root_blocks_apply(
    schema_engine: Engine, classified_doc: ClassifiedDoc, automation_factory, monkeypatch
) -> None:
    """D-05: o mesmo no apply_stage → blocked=True, doc → EM_REVISAO, SEM AuditLog de
    operação e SEM mkdir/materialize."""
    import app.automation.fileops as fileops

    def fail_materialize(*args, **kwargs):  # pragma: no cover
        raise AssertionError("anchor inexistente NÃO deve materializar/mkdir")

    monkeypatch.setattr(fileops, "materialize_to_dest", fail_materialize)

    _missing_root_automation(automation_factory)

    with get_session(schema_engine) as session:
        result = asyncio.run(
            stage.apply_stage(
                session, content_hash=classified_doc.content_hash, run_id="run-mr"
            )
        )
        assert result.blocked is True
        assert result.materialized is False
        done = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.status == "done")
        )
        assert done == 0
        doc = session.get(Document, classified_doc.document_id)
        assert doc.state == DocState.EM_REVISAO


def test_dry_run_copy_move_multi_output(
    schema_engine: Engine,
    classified_doc: ClassifiedDoc,
    automation_factory,
) -> None:
    """Dry-run de copy+move expõe N saídas (cópia + move) com discriminador de tipo,
    SEM escrever AuditLog nem tocar o disco (AUT-03)."""
    automation_factory(
        name="A-copy-move-dry",
        conditions=[{"field": "extension", "operator": "eq", "value": ".pdf"}],
        actions=[
            {"action_type": "copy", "params_json": '{"dest_folder": "ARQUIVO"}'},
            {"action_type": "move", "params_json": '{"dest_folder": "PROCESSADOS"}'},
        ],
    )

    with get_session(schema_engine) as session:
        plan = stage.dry_run(session, content_hash=classified_doc.content_hash)
        assert plan is not None
        assert plan.materialized is False
        # Multi-saída: deve haver ao menos uma saída copy e uma move.
        kinds = [o.kind for o in plan.outputs]
        assert "copy" in kinds
        assert "move" in kinds
        # AUT-03: nenhum AuditLog escrito.
        any_audit = session.scalar(select(func.count()).select_from(AuditLog))
        assert any_audit == 0

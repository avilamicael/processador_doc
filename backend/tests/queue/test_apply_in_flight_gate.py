"""Gate do APPLY_STEP para auto-apply EM VOO (Fase 12, WR-03 / A).

O gate do sweep (`enqueue_pending_applications`) só decide se ENFILEIRA novos jobs
de auto-apply. Mas um job de auto-apply JÁ enfileirado (sweep anterior, payload SEM
`run_id`) escapa desse gate: se o usuário liga o modo de aprovação DEPOIS do
enfileiramento, o job pendente ainda rodaria e auto-aplicaria — violando o modo e,
pior, MOVENDO/RENOMEANDO o arquivo do cliente indevidamente.

Este segundo gate vive no ramo `APPLY_STEP` do `_dispatch`: ANTES de chamar
`apply_stage`, se o payload NÃO tem `run_id` (= auto-apply) E o modo de aprovação
está LIGADO (lido FRESCO, WR-01) → trata como no-op concluído (done), sem mover.
Jobs COM `run_id` (aprovação manual) caem direto no `apply_stage` — SEMPRE aplicam
(D-06 preservado: aprovar = apply).

A `apply_stage` é espiada (monkeypatch) para provar que NÃO é chamada no caso
suprimido sem tocar no disco.
"""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from app import config
from app.classification.stage import CLASSIFIED_STEP
from app.models import DocState, Document, Job, JobStatus
from app.models.classification import ClassificationResult
from app.queue import repo, worker
from app.storage.db import get_session

APPLY_STEP = "apply"
HASH_DOC = "c" * 64  # bloco classificado pronto p/ apply


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isola o toggle: `.env` temporário + sem APPROVAL_MODE_ENABLED no ambiente.

    Espelha a fixture de `test_approval_gate.py`. Como o gate lê o toggle FRESCO
    (read_approval_mode_fresh), ligar via `monkeypatch.setenv` basta — sem depender
    de `get_settings.cache_clear()` (cobre o cruzamento com WR-01).
    """
    env = tmp_path / ".env"
    monkeypatch.setattr(config, "env_file_path", lambda: env)
    monkeypatch.setitem(config.Settings.model_config, "env_file", str(env))
    monkeypatch.delenv("APPROVAL_MODE_ENABLED", raising=False)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _seed_classified(session, content_hash: str, score: float = 0.95) -> None:
    """Bloco classificado pronto: PROCESSANDO + 'classificado' + ClassificationResult."""
    doc = Document(
        content_hash=content_hash,
        original_filename="classificado.pdf",
        state=DocState.PROCESSANDO,
        last_completed_step=CLASSIFIED_STEP,
    )
    session.add(doc)
    session.commit()
    session.add(
        ClassificationResult(
            document_id=doc.id,
            template_id=None,
            confidence=score,
            confidence_score=score,
        )
    )
    session.commit()


def _enqueue_apply(session, content_hash: str, *, run_id: str | None) -> None:
    """Enfileira um job de apply (com/sem run_id no payload)."""
    payload: dict = {"content_hash": content_hash}
    if run_id is not None:
        payload["run_id"] = run_id
    repo.enqueue(
        session,
        original_hash=content_hash,
        step=APPLY_STEP,
        payload=json.dumps(payload),
    )


def _make_apply_spy() -> tuple:
    """Coroutine-espiã que registra as chamadas a apply_stage sem tocar no disco."""
    calls: list[dict] = []

    async def spy(session, *, content_hash: str, run_id: str | None = None, **_) -> None:
        calls.append({"content_hash": content_hash, "run_id": run_id})

    return spy, calls


def _job(session, content_hash: str) -> Job:
    return session.scalar(
        select(Job).where(Job.original_hash == content_hash, Job.step == APPLY_STEP)
    )


def test_auto_apply_em_voo_modo_on_e_suprimido(
    schema_engine: Engine, isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem run_id + modo ON: apply_stage NÃO é chamado; job DONE; doc segue classificado."""
    monkeypatch.setenv("APPROVAL_MODE_ENABLED", "true")  # gate lê fresco, sem cache_clear
    spy, calls = _make_apply_spy()
    monkeypatch.setattr(worker, "apply_stage", spy)

    with get_session(schema_engine) as s:
        _seed_classified(s, HASH_DOC)
        _enqueue_apply(s, HASH_DOC, run_id=None)

    processed = asyncio.run(worker._run_once(schema_engine))

    assert processed is True
    # apply_stage NÃO foi chamado — arquivo intacto (T-g6x-01).
    assert calls == []
    with get_session(schema_engine) as s:
        # Job concluído como no-op (sem retry, T-g6x-03).
        assert _job(s, HASH_DOC).status == JobStatus.DONE
        # Doc segue classificado-pronto (aguardando aprovação na DryRunPage).
        doc = s.scalar(select(Document).where(Document.content_hash == HASH_DOC))
        assert doc.state == DocState.PROCESSANDO
        assert doc.last_completed_step == CLASSIFIED_STEP


def test_auto_apply_em_voo_modo_off_aplica(
    schema_engine: Engine, isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem run_id + modo OFF: apply_stage É chamado (comportamento atual preservado)."""
    spy, calls = _make_apply_spy()
    monkeypatch.setattr(worker, "apply_stage", spy)

    with get_session(schema_engine) as s:
        _seed_classified(s, HASH_DOC)
        _enqueue_apply(s, HASH_DOC, run_id=None)

    asyncio.run(worker._run_once(schema_engine))

    assert len(calls) == 1
    assert calls[0]["content_hash"] == HASH_DOC
    assert calls[0]["run_id"] is None
    with get_session(schema_engine) as s:
        assert _job(s, HASH_DOC).status == JobStatus.DONE


def test_aprovacao_manual_com_run_id_aplica_mesmo_com_modo_on(
    schema_engine: Engine, isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com run_id + modo ON: apply_stage É chamado (D-06 — aprovar = apply sempre)."""
    monkeypatch.setenv("APPROVAL_MODE_ENABLED", "true")
    spy, calls = _make_apply_spy()
    monkeypatch.setattr(worker, "apply_stage", spy)

    with get_session(schema_engine) as s:
        _seed_classified(s, HASH_DOC)
        _enqueue_apply(s, HASH_DOC, run_id="run-123")

    asyncio.run(worker._run_once(schema_engine))

    assert len(calls) == 1
    assert calls[0]["run_id"] == "run-123"
    with get_session(schema_engine) as s:
        assert _job(s, HASH_DOC).status == JobStatus.DONE

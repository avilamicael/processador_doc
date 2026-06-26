"""Gate do modo de aprovação (Fase 12, D-05) em `enqueue_pending_applications`.

`enqueue_pending_applications` (queue/worker.py) é o ÚNICO ponto de auto-apply de
alta confiança (decisão 06-04). O toggle global `approval_mode_enabled` gateia ESTE
sweep:

- OFF (default, D-04): auto-aplica os docs de ALTA confiança como hoje — a trava de
  confiança/limiar segue intacta (baixa confiança nunca é capturada pelo sweep).
- ON (D-05): curto-circuito no TOPO da função — NÃO enfileira nada; os docs de alta
  confiança ficam pendentes aguardando aprovação humana via DryRunPage.

O gate vive SÓ aqui, NUNCA em `apply_stage` (executor compartilhado com a aprovação
manual — gateá-lo quebraria D-06: aprovar = apply).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from app import config
from app.classification.stage import CLASSIFIED_STEP
from app.models import DocState, Document, Job
from app.models.classification import ClassificationResult
from app.queue import worker
from app.storage.db import get_session

HASH_HIGH = "a" * 64  # bloco classificado de ALTA confiança, pronto p/ auto-apply
HASH_LOW = "b" * 64  # bloco classificado de BAIXA confiança (abaixo do limiar)

APPLY_STEP = "apply"


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isola o toggle: `.env` temporário + sem APPROVAL_MODE_ENABLED no ambiente.

    Garante que o default-OFF não seja poluído por um `.env` real do CWD e permite
    flipar o toggle via env var + `get_settings.cache_clear()` dentro do teste.
    """
    env = tmp_path / ".env"
    monkeypatch.setattr(config, "env_file_path", lambda: env)
    monkeypatch.setitem(config.Settings.model_config, "env_file", str(env))
    monkeypatch.delenv("APPROVAL_MODE_ENABLED", raising=False)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _seed_classified(session, content_hash: str, score: float) -> None:
    """Bloco classificado pronto: PROCESSANDO + 'classificado' + ClassificationResult.

    `score` é o `confidence_score`; >= review_confidence_threshold (default 0.8) é
    ALTA confiança (candidato ao auto-apply); abaixo é BAIXA (nunca capturado pelo
    sweep). Sem AuditLog(status="done") → ainda não aplicado.
    """
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


def _apply_jobs(session) -> set[str]:
    """Conjunto de `original_hash` dos jobs de step 'apply' na fila."""
    return {
        j.original_hash
        for j in session.scalars(select(Job).where(Job.step == APPLY_STEP)).all()
    }


def test_off_auto_aplica_alta_confianca(
    schema_engine: Engine, isolated_env: None
) -> None:
    """OFF (default): doc de alta confiança é enfileirado p/ apply (comportamento atual)."""
    with get_session(schema_engine) as s:
        _seed_classified(s, HASH_HIGH, score=0.95)

    with get_session(schema_engine) as s:
        created = worker.enqueue_pending_applications(s)

    assert created == 1
    with get_session(schema_engine) as s:
        assert HASH_HIGH in _apply_jobs(s)


def test_on_nao_auto_aplica_nada(
    schema_engine: Engine, isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ON: o sweep curto-circuita (retorna 0) e NÃO enfileira apply (docs pendentes)."""
    monkeypatch.setenv("APPROVAL_MODE_ENABLED", "true")
    config.get_settings.cache_clear()

    with get_session(schema_engine) as s:
        _seed_classified(s, HASH_HIGH, score=0.95)

    with get_session(schema_engine) as s:
        created = worker.enqueue_pending_applications(s)

    assert created == 0
    with get_session(schema_engine) as s:
        assert _apply_jobs(s) == set()


def test_gate_do_sweep_le_o_toggle_fresco(
    schema_engine: Engine, isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O gate do sweep enxerga o toggle novo SEM cache_clear (WR-01).

    Em modo servidor/arq o worker roda em OUTRO processo: o `cache_clear()` que o
    endpoint PUT /config/approval-mode dispara roda no processo da API e NÃO chega
    ao worker, que ficaria lendo o valor velho até reiniciar. Prendemos o cache de
    get_settings em False (chamando get_settings() ANTES do flip) e ligamos o env
    SEM novo cache_clear: o sweep deve enxergar ON (fresco) e retornar 0.
    """
    # Prende o cache de get_settings em OFF.
    assert config.get_settings().approval_mode_enabled is False
    # Liga o env SEM cache_clear (o flip não cruza ao processo do worker).
    monkeypatch.setenv("APPROVAL_MODE_ENABLED", "true")

    with get_session(schema_engine) as s:
        _seed_classified(s, HASH_HIGH, score=0.95)

    with get_session(schema_engine) as s:
        created = worker.enqueue_pending_applications(s)

    assert created == 0
    with get_session(schema_engine) as s:
        assert _apply_jobs(s) == set()


def test_trava_de_confianca_intacta_em_ambos_os_modos(
    schema_engine: Engine, isolated_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Baixa confiança nunca é auto-aplicada pelo sweep — independente do toggle.

    OFF: o filtro de confiança do sweep já o exclui. ON: o curto-circuito o exclui.
    O gate não altera o filtro de confiança — só decide se o sweep roda.
    """
    # OFF: baixa confiança não é capturada (filtro de confiança).
    with get_session(schema_engine) as s:
        _seed_classified(s, HASH_LOW, score=0.3)
    with get_session(schema_engine) as s:
        created_off = worker.enqueue_pending_applications(s)
    assert created_off == 0
    with get_session(schema_engine) as s:
        assert HASH_LOW not in _apply_jobs(s)

    # ON: continua não capturado (agora pelo curto-circuito).
    monkeypatch.setenv("APPROVAL_MODE_ENABLED", "true")
    config.get_settings.cache_clear()
    with get_session(schema_engine) as s:
        created_on = worker.enqueue_pending_applications(s)
    assert created_on == 0
    with get_session(schema_engine) as s:
        assert HASH_LOW not in _apply_jobs(s)

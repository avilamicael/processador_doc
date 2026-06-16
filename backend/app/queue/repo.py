"""Repositório da fila durável SQLite — claim atômico + backoff + resume.

Fronteira única de acesso à tabela `jobs` (modelo `app.models.job.Job`). No modo
padrão (Windows, single-tenant) NÃO há broker externo: a fila é uma tabela SQLite
consumida por UM worker asyncio no próprio processo (D-11). Como há um único
writer, o claim é uma instrução `UPDATE ... RETURNING` atômica (SQLite ≥ 3.35;
ambiente confirmado 3.50.4) — sem corrida de dois consumidores (Pattern 1).

Garantias materializadas:
- PROC-03 (idempotência): `enqueue` é no-op para um (original_hash, step) já
  enfileirado — a UNIQUE `uq_jobs_hash_step` é a barreira; capturamos
  `IntegrityError` e retornamos `None`.
- PROC-02 (retry/backoff/dead-letter): `schedule_retry` empurra `next_run_at` com
  backoff exponencial + jitter enquanto `attempts < max_attempts`; ao esgotar, o
  job vira `failed` (dead-letter — NÃO some; o worker leva o documento a FALHA).
- Resume após crash: `requeue_running` reverte todos os `running`→`pending` no
  startup; a idempotência (gate de dedup + content_hash único dos blocos) garante
  que reprocessar não duplica trabalho nem cobrança.

Funções de módulo (estilo `cas.py`/`state_machine.py`), sem classe.

Interface pública: enqueue, claim_next, mark_done, schedule_retry, mark_failed,
requeue_running.
"""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enums import JobStatus
from app.models.job import Job


def _utcnow() -> datetime:
    return datetime.now(UTC)


def enqueue(
    session: Session,
    *,
    original_hash: str,
    step: str = "ingest",
    payload: str,
    max_attempts: int | None = None,
) -> Job | None:
    """Enfileira um job `pending` elegível agora; no-op se já enfileirado.

    A UNIQUE `(original_hash, step)` (PROC-03) é a barreira de idempotência:
    re-enfileirar o mesmo trabalho (ex.: rescan do mesmo original) viola a
    constraint e retorna `None` (já existe), sem criar duplicado. Em sucesso
    retorna o `Job` recém-criado.
    """
    if max_attempts is None:
        max_attempts = get_settings().queue_max_attempts

    job = Job(
        original_hash=original_hash,
        step=step,
        payload=payload,
        status=JobStatus.PENDING,
        max_attempts=max_attempts,
        next_run_at=_utcnow(),
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        # Já enfileirado para esta (hash, step) — idempotência PROC-03.
        session.rollback()
        return None
    session.refresh(job)
    return job


def claim_next(session: Session) -> Row | None:
    """Reivindica atomicamente UM job devido agora; retorna seus campos ou None.

    Executa um único `UPDATE ... WHERE id=(SELECT ... LIMIT 1) RETURNING` (Pattern
    1). É atômico e seguro porque o worker é o ÚNICO writer (D-11): não há corrida
    de dois consumidores; mesmo com 2 workers no futuro, o `UPDATE` condicional só
    "ganha" uma vez por linha. Marca `running` e incrementa `attempts`.

    RETURNING exige SQLite ≥ 3.35 (A1; ambiente 3.50.4). Se algum dia faltar, o
    fallback é `UPDATE` condicional + `SELECT` na mesma transação (writer único).
    """
    # Comparamos `next_run_at` contra um instante BIND-ado em Python (`:now`), não
    # contra `CURRENT_TIMESTAMP` do SQLite: o SQLAlchemy persiste datetimes
    # tz-aware como `YYYY-MM-DD HH:MM:SS.ffffff+00:00`, enquanto `CURRENT_TIMESTAMP`
    # rende segundos sem offset — a comparação lexicográfica entre os dois formatos
    # é incorreta (jobs devidos "agora" não seriam reivindicados). Bind-ar o mesmo
    # `_utcnow()` que `enqueue`/`schedule_retry` usam mantém ambos os lados no
    # formato idêntico de armazenamento.
    row = session.execute(
        text(
            """
            UPDATE jobs
               SET status='running',
                   attempts = attempts + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = (
                SELECT id FROM jobs
                 WHERE status='pending' AND next_run_at <= :now
                 ORDER BY next_run_at
                 LIMIT 1
             )
            RETURNING id, original_hash, step, payload, attempts, max_attempts
            """
        ),
        {"now": _utcnow()},
    ).first()
    session.commit()
    return row


def mark_done(session: Session, job_id: int) -> None:
    """Marca o job como `done` (concluído com sucesso)."""
    session.execute(
        text("UPDATE jobs SET status='done', updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
        {"id": job_id},
    )
    session.commit()


def schedule_retry(
    session: Session,
    job_id: int,
    attempts: int,
    max_attempts: int,
    error: str,
) -> None:
    """Reagenda o job com backoff exponencial+jitter, ou dead-letter se esgotado.

    Se `attempts >= max_attempts`: o job vira `failed` (dead-letter — PROC-02; NÃO
    some, o worker leva o documento a FALHA). Caso contrário: volta a `pending` com
    `next_run_at = agora + min(BASE * 2**attempts, MAX) + jitter` (Pattern 2),
    evitando tempestade de retries (T-02-07).
    """
    if attempts >= max_attempts:
        mark_failed(session, job_id, error)
        return

    settings = get_settings()
    base = settings.queue_backoff_base_seconds
    cap = settings.queue_backoff_max_seconds
    delay = min(base * (2**attempts), cap)
    delay += random.uniform(0, delay * 0.25)  # jitter
    next_run = _utcnow() + timedelta(seconds=delay)

    session.execute(
        text(
            """
            UPDATE jobs
               SET status='pending',
                   next_run_at=:next_run,
                   last_error=:error,
                   updated_at=CURRENT_TIMESTAMP
             WHERE id=:id
            """
        ),
        {"id": job_id, "next_run": next_run, "error": error},
    )
    session.commit()


def mark_failed(session: Session, job_id: int, error: str) -> None:
    """Marca o job como `failed` (dead-letter) com a mensagem de erro."""
    session.execute(
        text(
            """
            UPDATE jobs
               SET status='failed', last_error=:error, updated_at=CURRENT_TIMESTAMP
             WHERE id=:id
            """
        ),
        {"id": job_id, "error": error},
    )
    session.commit()


def requeue_running(session: Session) -> int:
    """Reverte todos os jobs `running`→`pending` (resume após crash).

    Chamado UMA vez no startup do worker: jobs que estavam em execução quando o
    processo morreu voltam à fila. A idempotência (gate de dedup + content_hash
    único dos blocos) garante que reprocessar não duplica (Pattern 1; T-02-08).
    Retorna quantos jobs foram re-enfileirados.
    """
    result = session.execute(
        text(
            "UPDATE jobs SET status='pending', updated_at=CURRENT_TIMESTAMP "
            "WHERE status='running'"
        )
    )
    session.commit()
    return result.rowcount

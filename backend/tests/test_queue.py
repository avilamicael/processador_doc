"""Testes do repositório de fila durável SQLite + worker async (PROC-02/PROC-03).

Prova:
- `enqueue` é idempotente por (original_hash, step) — UNIQUE (PROC-03).
- `claim_next` reivindica atomicamente exatamente 1 job devido (UPDATE...RETURNING),
  marca `running` e incrementa `attempts` (D-11 single-writer).
- `schedule_retry` empurra `next_run_at` com backoff+jitter enquanto há tentativas;
  ao esgotar `max_attempts` o job vira `failed` (dead-letter — PROC-02).
- `requeue_running` reverte `running`→`pending` no startup (resume após crash).
- O worker (`_run_once`) processa um job (done + Documents criados), reagenda em
  falha e, ao esgotar as tentativas, leva o(s) Document(s) a FALHA.

Schema dos testes via `Base.metadata.create_all` num SQLite temporário (D-10:
permitido SOMENTE em teste). Releitura numa segunda sessão prova persistência.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pikepdf
from sqlalchemy import Engine, select

from app.models import DocState, Document, IngestedOriginal, Job, JobStatus
from app.queue import repo
from app.storage.db import get_session

HASH_A = "a" * 64
HASH_B = "b" * 64


def _payload(source_path: Path) -> str:
    return json.dumps(
        {"source_path": str(source_path), "folder_id": None, "pages_per_block": None}
    )


def _make_pdf(path: Path, pages: int) -> Path:
    """Cria um PDF com `pages` páginas byte-distintas em `path`."""
    pdf = pikepdf.Pdf.new()
    for i in range(pages):
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pikepdf.Stream(
            pdf, f"BT /F1 12 Tf 20 100 Td (pagina {i}) Tj ET".encode()
        )
    pdf.save(path)
    pdf.close()
    return path


# --------------------------------------------------------------------------- #
# Repo: enqueue idempotente
# --------------------------------------------------------------------------- #


def test_idempotent(schema_engine: Engine) -> None:
    with get_session(schema_engine) as s:
        repo.enqueue(s, original_hash=HASH_A, step="ingest", payload="{}")
    with get_session(schema_engine) as s:
        # Segundo enqueue do MESMO (hash, step) é no-op — UNIQUE não cria duplicado.
        repo.enqueue(s, original_hash=HASH_A, step="ingest", payload="{}")

    with get_session(schema_engine) as s:
        jobs = s.scalars(select(Job).where(Job.original_hash == HASH_A)).all()
        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.PENDING
        assert jobs[0].next_run_at is not None


# --------------------------------------------------------------------------- #
# Repo: claim atômico
# --------------------------------------------------------------------------- #


def test_claim_atomico(schema_engine: Engine) -> None:
    with get_session(schema_engine) as s:
        repo.enqueue(s, original_hash=HASH_A, step="ingest", payload="{}")

    with get_session(schema_engine) as s:
        row = repo.claim_next(s)
        assert row is not None
        assert row.original_hash == HASH_A
        assert row.attempts == 1  # incrementado no claim

    # Segunda sessão: o job está running e persistido.
    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == HASH_A))
        assert job is not None
        assert job.status == JobStatus.RUNNING
        assert job.attempts == 1


def test_claim_sem_job_devido_retorna_none(schema_engine: Engine) -> None:
    with get_session(schema_engine) as s:
        assert repo.claim_next(s) is None


def test_claim_apenas_um_por_vez(schema_engine: Engine) -> None:
    with get_session(schema_engine) as s:
        repo.enqueue(s, original_hash=HASH_A, step="ingest", payload="{}")
        repo.enqueue(s, original_hash=HASH_B, step="ingest", payload="{}")

    claimed = []
    with get_session(schema_engine) as s:
        row = repo.claim_next(s)
        assert row is not None
        claimed.append(row.original_hash)
    with get_session(schema_engine) as s:
        row = repo.claim_next(s)
        assert row is not None
        claimed.append(row.original_hash)
    # Nenhum job foi reivindicado duas vezes.
    assert set(claimed) == {HASH_A, HASH_B}


# --------------------------------------------------------------------------- #
# Repo: backoff + dead-letter
# --------------------------------------------------------------------------- #


def test_backoff(schema_engine: Engine) -> None:
    with get_session(schema_engine) as s:
        repo.enqueue(
            s, original_hash=HASH_A, step="ingest", payload="{}", max_attempts=3
        )
    with get_session(schema_engine) as s:
        row = repo.claim_next(s)
        assert row.attempts == 1

    # Retry com attempts < max_attempts: volta a pending com next_run_at no futuro.
    with get_session(schema_engine) as s:
        repo.schedule_retry(
            s, job_id=row.id, attempts=1, max_attempts=3, error="boom"
        )
    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.id == row.id))
        assert job.status == JobStatus.PENDING
        assert job.next_run_at > datetime.now(UTC)
        assert job.last_error == "boom"


def test_backoff_esgota_vira_failed(schema_engine: Engine) -> None:
    with get_session(schema_engine) as s:
        repo.enqueue(
            s, original_hash=HASH_A, step="ingest", payload="{}", max_attempts=2
        )
    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == HASH_A))
        job_id = job.id

    # attempts >= max_attempts → dead-letter (failed), NÃO some.
    with get_session(schema_engine) as s:
        repo.schedule_retry(
            s, job_id=job_id, attempts=2, max_attempts=2, error="último erro"
        )
    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.id == job_id))
        assert job.status == JobStatus.FAILED
        assert job.last_error == "último erro"


def test_mark_done(schema_engine: Engine) -> None:
    with get_session(schema_engine) as s:
        repo.enqueue(s, original_hash=HASH_A, step="ingest", payload="{}")
    with get_session(schema_engine) as s:
        row = repo.claim_next(s)
        repo.mark_done(s, row.id)
    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.id == row.id))
        assert job.status == JobStatus.DONE


def test_mark_failed(schema_engine: Engine) -> None:
    with get_session(schema_engine) as s:
        repo.enqueue(s, original_hash=HASH_A, step="ingest", payload="{}")
    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == HASH_A))
        repo.mark_failed(s, job.id, "fatal")
    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == HASH_A))
        assert job.status == JobStatus.FAILED
        assert job.last_error == "fatal"


# --------------------------------------------------------------------------- #
# Repo: resume após crash
# --------------------------------------------------------------------------- #


def test_resume_on_startup(schema_engine: Engine) -> None:
    with get_session(schema_engine) as s:
        repo.enqueue(s, original_hash=HASH_A, step="ingest", payload="{}")
        repo.enqueue(s, original_hash=HASH_B, step="ingest", payload="{}")
    # Simula crash: 2 jobs ficaram running.
    with get_session(schema_engine) as s:
        repo.claim_next(s)
    with get_session(schema_engine) as s:
        repo.claim_next(s)

    with get_session(schema_engine) as s:
        n = repo.requeue_running(s)
        assert n == 2

    with get_session(schema_engine) as s:
        jobs = s.scalars(select(Job)).all()
        assert all(j.status == JobStatus.PENDING for j in jobs)


# --------------------------------------------------------------------------- #
# Worker: iteração única (poll→claim→process→done / falha→FALHA)
# --------------------------------------------------------------------------- #


def test_worker_run_once_done(schema_engine: Engine, tmp_path: Path) -> None:
    from app.queue import worker

    src = _make_pdf(tmp_path / "doc.pdf", pages=2)
    # Hash do original precisa bater com o que o ingest computa; usamos o helper.
    from app.ingest.hashing import sha256_file

    original_hash = sha256_file(src)
    with get_session(schema_engine) as s:
        repo.enqueue(
            s, original_hash=original_hash, step="ingest", payload=_payload(src)
        )

    processed = asyncio.run(worker._run_once(schema_engine))
    assert processed is True

    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == original_hash))
        assert job.status == JobStatus.DONE
        docs = s.scalars(select(Document)).all()
        assert len(docs) >= 1
        assert all(d.state == DocState.PROCESSANDO for d in docs)


def test_worker_run_once_sem_job(schema_engine: Engine) -> None:
    from app.queue import worker

    processed = asyncio.run(worker._run_once(schema_engine))
    assert processed is False


def test_worker_falha_esgotada_leva_documento_a_falha(
    schema_engine: Engine, tmp_path: Path
) -> None:
    from app.queue import worker

    # PDF corrompido → split_pdf levanta ValueError → falha.
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"%PDF-1.4 not a real pdf")
    from app.ingest.hashing import sha256_file

    original_hash = sha256_file(bad)
    with get_session(schema_engine) as s:
        repo.enqueue(
            s,
            original_hash=original_hash,
            step="ingest",
            payload=_payload(bad),
            max_attempts=1,
        )

    # Uma iteração: claim (attempts→1), process falha, schedule_retry com
    # attempts>=max_attempts → failed.
    asyncio.run(worker._run_once(schema_engine))

    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == original_hash))
        assert job.status == JobStatus.FAILED
        # O original ainda pode existir no gate; mas nenhum bloco/Document concluído.
        ing = s.scalar(
            select(IngestedOriginal).where(
                IngestedOriginal.original_hash == original_hash
            )
        )
        # Se um IngestedOriginal foi registrado, seus Documents devem estar em FALHA.
        if ing is not None:
            docs = s.scalars(
                select(Document).where(Document.origin_original_id == ing.id)
            ).all()
            assert all(d.state == DocState.FALHA for d in docs)

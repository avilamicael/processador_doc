"""Worker assíncrono in-process — loop poll→claim→processa→backoff (PROC-02).

UM worker asyncio (subido no `lifespan` do FastAPI no Plano 04) consome a tabela
`jobs` sem broker externo (D-11). Reusa o repositório (`queue.repo`) para o claim
atômico/backoff/resume e o `ingest_stage.process_ingest` para o trabalho real.

Fluxo (Pattern 1/6):
- No startup, `requeue_running` UMA vez: jobs presos em `running` (crash) voltam a
  `pending` — a idempotência do gate/blocos torna reprocessar um no-op (T-02-08).
- Loop: `claim_next`; com job → processa e `mark_done`; em exceção →
  `schedule_retry` (backoff/jitter) e, quando as tentativas se esgotam (job vira
  `failed`), leva o(s) Document(s) associado(s) a FALHA via `transition` (NUNCA
  seta `document.state` direto — Anti-Pattern). Sem job → dorme o intervalo de poll.
- Encerra limpo quando o `stop` Event é setado.

Pitfall 4: o split de PDF é CPU/IO-bound; `process_ingest` (que o invoca) é
despachado via `asyncio.to_thread` para NÃO bloquear o event loop (a API/health não
congelam durante um split grande — T-02-09). Cada thread usa SUA própria sessão
(sessões SQLAlchemy não cruzam threads).

Interface pública: `run_worker`. (`_run_once` é testável: uma única iteração.)
"""

import asyncio
import json
import logging
from pathlib import Path

from openai import AuthenticationError
from sqlalchemy import Engine, select

from app.config import get_settings
from app.extraction.stage import extract_stage
from app.models.document import Document
from app.models.enums import DocState
from app.models.ingested_original import IngestedOriginal
from app.pipeline import ingest_stage
from app.pipeline.state_machine import transition
from app.queue import repo
from app.storage.db import get_session

logger = logging.getLogger(__name__)

# Step do job de extração (a fila enfileira (block.content_hash, EXTRACT_STEP)).
INGEST_STEP = "ingest"
EXTRACT_STEP = "extract"


def _process_job_blocking(engine: Engine, *, original_hash: str, payload: str) -> None:
    """Executa o trabalho pesado (split + DB) de um job — roda num THREAD.

    Abre a SUA própria sessão (sessões não cruzam threads). Parseia o payload e
    delega ao `ingest_stage.process_ingest`. Levanta em falha — o chamador
    (coroutine) captura e roteia para `schedule_retry`/FALHA.
    """
    data = json.loads(payload)
    source_path = Path(data["source_path"])
    folder_id = data.get("folder_id")
    pages_per_block = data.get("pages_per_block")

    with get_session(engine) as session:
        ingest_stage.process_ingest(
            session,
            source_path=source_path,
            folder_id=folder_id,
            pages_per_block=pages_per_block,
            original_hash=original_hash,
        )


def _fail_documents_for_original(engine: Engine, original_hash: str) -> None:
    """Leva todos os Documents do original a FALHA (dead-letter esgotada).

    Usa SEMPRE `transition` (allowlist: RECEBIDO→FALHA e PROCESSANDO→FALHA) — nunca
    seta `document.state` direto (Anti-Pattern). Tolerante: documentos já em FALHA
    ou em estado sem aresta para FALHA são ignorados sem corromper o estado.
    """
    with get_session(engine) as session:
        original = session.scalar(
            select(IngestedOriginal).where(
                IngestedOriginal.original_hash == original_hash
            )
        )
        if original is None:
            return
        docs = session.scalars(
            select(Document).where(Document.origin_original_id == original.id)
        ).all()
        for doc in docs:
            if doc.state == DocState.FALHA:
                continue
            try:
                transition(session, doc, DocState.FALHA)
            except Exception:
                # Estado sem aresta para FALHA (ex.: CONCLUIDO terminal) — não
                # corrompe; o `transition` já fez rollback. Segue para o próximo.
                logger.warning(
                    "Não foi possível levar Document %s a FALHA (estado %s)",
                    doc.id,
                    doc.state,
                )


def _fail_document_for_content_hash(engine: Engine, content_hash: str) -> None:
    """Leva o Document de UM bloco (achado por content_hash) a FALHA.

    Variante de `_fail_documents_for_original` para o job de extract, cuja
    identidade é o `content_hash` do BLOCO (não o `original_hash` do original —
    Pitfall 2). Usa SEMPRE `transition` (allowlist PROCESSANDO→FALHA, states.py) —
    nunca seta `document.state` direto. Tolerante: bloco ausente ou em estado sem
    aresta para FALHA é ignorado sem corromper o estado (re-tentável depois).
    """
    with get_session(engine) as session:
        doc = session.scalar(
            select(Document).where(Document.content_hash == content_hash)
        )
        if doc is None:
            return
        if doc.state == DocState.FALHA:
            return
        try:
            transition(session, doc, DocState.FALHA)
        except Exception:
            # Estado sem aresta para FALHA (ex.: CONCLUIDO terminal) — `transition`
            # já fez rollback, estado intacto. Só registramos metadados.
            logger.warning(
                "Não foi possível levar Document %s a FALHA (estado %s)",
                doc.id,
                doc.state,
            )


async def _dispatch(engine: Engine, *, step: str, original_hash: str, payload: str) -> None:
    """Despacha o trabalho real conforme o `step` (Pitfall 1: async-vs-thread).

    - `ingest`: o split é CPU/IO-bound → `asyncio.to_thread(_process_job_blocking)`
      (inalterado; a thread usa SUA própria sessão).
    - `extract`: `extract_stage` é uma COROUTINE (chamada OpenAI async) → `await`
      direto no loop, com sessão própria. NUNCA `asyncio.to_thread` (não há event
      loop na thread → RuntimeError) nem `asyncio.run` (já estamos num loop). Só o
      PyMuPDF interno do stage vai a `to_thread`.

    Levanta em falha — o chamador (`_run_once`) captura e roteia para
    `schedule_retry`/FALHA (o stage NÃO faz retry, D-08).
    """
    if step == EXTRACT_STEP:
        # content_hash do bloco == original_hash do job de extract (Pitfall 2).
        with get_session(engine) as session:
            await extract_stage(session, content_hash=original_hash)
    else:
        await asyncio.to_thread(
            _process_job_blocking,
            engine,
            original_hash=original_hash,
            payload=payload,
        )


def _fail_for_step(engine: Engine, *, step: str, original_hash: str) -> None:
    """Roteia a variante de FALHA por step ao esgotar retries (dead-letter→FALHA).

    `ingest`→Documents do original (por `origin_original_id`); `extract`→Document do
    bloco (por `content_hash`, Pitfall 2).
    """
    if step == EXTRACT_STEP:
        _fail_document_for_content_hash(engine, original_hash)
    else:
        _fail_documents_for_original(engine, original_hash)


async def _run_once(engine: Engine) -> bool:
    """Executa UMA iteração do loop: claim→processa→done/backoff. Testável.

    Retorna True se um job foi reivindicado (e processado/reagendado), False se não
    havia job devido. Não dorme — o `sleep` do poll fica no `run_worker`.
    """
    with get_session(engine) as session:
        row = repo.claim_next(session)
    if row is None:
        return False

    job_id = row.id
    original_hash = row.original_hash
    step = row.step
    attempts = row.attempts
    max_attempts = row.max_attempts

    try:
        # Dispatch bifurcado por step (Pitfall 1): ingest→to_thread; extract→await
        # coroutine no loop. Cada caminho abre SUA própria sessão.
        await _dispatch(
            engine, step=step, original_hash=original_hash, payload=row.payload
        )
    except AuthenticationError:
        # Chave OpenAI inválida NÃO é retryável (T-03-14): backoff só queimaria
        # tempo/dinheiro e nunca curaria. Dead-letter IMEDIATO + FALHA no bloco,
        # re-tentável manualmente após corrigir a chave. Log só metadados (nunca a
        # chave nem o conteúdo, V7/V8). `mark_failed` é direto (não `schedule_retry`).
        logger.error(
            "Job %s (step=%s) dead-letter imediato: credenciais OpenAI inválidas",
            job_id,
            step,
        )
        with get_session(engine) as session:
            repo.mark_failed(session, job_id, "AuthenticationError (chave OpenAI inválida)")
        _fail_for_step(engine, step=step, original_hash=original_hash)
        return True
    except Exception as exc:  # noqa: BLE001 — qualquer falha vira retry/dead-letter
        logger.warning(
            "Job %s (step=%s) falhou (tentativa %s): %s",
            job_id,
            step,
            attempts,
            exc,
        )
        with get_session(engine) as session:
            repo.schedule_retry(
                session,
                job_id=job_id,
                attempts=attempts,
                max_attempts=max_attempts,
                error=str(exc),
            )
        # Se a tentativa esgotou as chances (job agora 'failed'), o(s) Document(s)
        # associado(s) vão a FALHA (PROC-02 dead-letter → FALHA no documento),
        # roteado por step: ingest→original; extract→content_hash (Pitfall 2).
        if attempts >= max_attempts:
            _fail_for_step(engine, step=step, original_hash=original_hash)
        return True

    with get_session(engine) as session:
        repo.mark_done(session, job_id)
    return True


async def run_worker(engine: Engine, stop: asyncio.Event) -> None:
    """Loop do worker: resume no startup, então poll→claim→processa até `stop`.

    Encerra limpo quando `stop` é setado (sai do loop sem deixar tarefa pendente),
    permitindo ao `lifespan` (Plano 04) fazer `gather`.
    """
    # Resume após crash (Pattern 1): re-fila jobs presos em running.
    with get_session(engine) as session:
        requeued = repo.requeue_running(session)
    if requeued:
        logger.info("Resume: %s job(s) running re-enfileirados como pending", requeued)

    poll = get_settings().queue_poll_interval_seconds
    while not stop.is_set():
        processed = await _run_once(engine)
        if processed:
            # Há trabalho — não dorme; tenta o próximo imediatamente.
            continue
        # Sem job devido: dorme o intervalo de poll, mas acorda cedo se `stop`.
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll)
        except TimeoutError:
            pass

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
from sqlalchemy.orm import Session

from app.automation.stage import APPLY_STEP, apply_stage, reconcile_orphans
from app.classification.stage import CLASSIFIED_STEP, classify_stage
from app.config import get_settings
from app.extraction.stage import EXTRACTED_STEP, extract_stage
from app.models.audit_log import AuditLog
from app.models.classification import ClassificationResult
from app.models.document import Document
from app.models.enums import DocState
from app.models.extraction import Extraction
from app.models.ingested_original import IngestedOriginal
from app.pipeline import ingest_stage
from app.pipeline.ingest_stage import AWAITING_EXTRACTION_STEP
from app.pipeline.state_machine import transition
from app.queue import repo
from app.storage.db import get_session

logger = logging.getLogger(__name__)

# Step do job de extração (a fila enfileira (block.content_hash, EXTRACT_STEP)).
INGEST_STEP = "ingest"
EXTRACT_STEP = "extract"
# Step do job de classificação (Fase 4): a fila enfileira (block.content_hash,
# CLASSIFY_STEP) após o bloco ficar last_completed_step="extraido".
CLASSIFY_STEP = "classify"
# Step do job de AUTOMAÇÃO (Fase 6): a fila enfileira (block.content_hash,
# APPLY_STEP) quando o doc está classificado e pronto para aplicar. APPLY_STEP é
# importado de automation.stage (fonte única do contrato).


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
    # Opt-in de separação física na pasta (quick 260623-pzy). Default False
    # preserva o comportamento atual de payloads legados (sem a chave).
    split_to_files = data.get("split_to_files", False)

    with get_session(engine) as session:
        ingest_stage.process_ingest(
            session,
            source_path=source_path,
            folder_id=folder_id,
            pages_per_block=pages_per_block,
            original_hash=original_hash,
            split_to_files=split_to_files,
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
    elif step == CLASSIFY_STEP:
        # `classify_stage` é uma COROUTINE (chamadas OpenAI async de desempate/
        # faltantes) → `await` DIRETO no loop, com sessão própria. NUNCA
        # `asyncio.to_thread` (não há event loop na thread → RuntimeError) nem
        # `asyncio.run` (já estamos num loop). content_hash do bloco == original_hash.
        #
        # `forced_template_id` (reclassify de quarentena, D-09): o endpoint de
        # reclassify (Plan 03) usa `repo.requeue_step` com payload
        # `{"forced_template_id": N}`; o classify NORMAL usa `{"content_hash": ...}`
        # (sem a chave) → `.get` devolve None e o caminho atual fica INALTERADO.
        # NOTA sweep: `requeue_step` reseta a linha existente; `_sweep_pending`/
        # `enqueue_pending_classifications` só usa `enqueue` (no-op por UNIQUE quando
        # a linha existe), logo NÃO sobrescreve o payload forçado.
        forced = json.loads(payload).get("forced_template_id")
        with get_session(engine) as session:
            await classify_stage(
                session, content_hash=original_hash, forced_template_id=forced
            )
    elif step == APPLY_STEP:
        # `apply_stage` é uma COROUTINE (espelha classify_stage) → `await` DIRETO no
        # loop, com sessão própria. NUNCA `asyncio.to_thread` (o fileops interno é
        # IO síncrono mas roda dentro do stage; não há event loop na thread). O
        # `run_id` do lote (apply por-run, D-03) viaja no payload; ausente = None.
        run_id = json.loads(payload).get("run_id")
        with get_session(engine) as session:
            await apply_stage(
                session, content_hash=original_hash, run_id=run_id
            )
    else:
        await asyncio.to_thread(
            _process_job_blocking,
            engine,
            original_hash=original_hash,
            payload=payload,
        )


def _fail_for_step(engine: Engine, *, step: str, original_hash: str) -> None:
    """Roteia a variante de FALHA por step ao esgotar retries (dead-letter→FALHA).

    `ingest`→Documents do original (por `origin_original_id`); `extract`/`classify`/
    `apply`→Document do bloco (por `content_hash`, Pitfall 2).
    """
    if step in (EXTRACT_STEP, CLASSIFY_STEP, APPLY_STEP):
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


def enqueue_pending_extractions(session: Session) -> int:
    """Enfileira um job de extract para cada bloco pronto que ainda não tem job.

    Resolve a Open Question 1 (enqueue inline no ingest quebraria o commit único —
    `repo.enqueue` comita por si): em vez disso, varremos no STARTUP do worker (UMA
    vez, análogo a `requeue_running`) todos os Documents em estado terminal da Fase 2
    — `state == PROCESSANDO` e `last_completed_step == "aguardando_extracao"` — que
    ainda NÃO têm uma `Extraction` persistida, e enfileiramos
    `(block.content_hash, "extract")` para cada um.

    Idempotente por desenho: a chave do job é o `content_hash` do bloco e a UNIQUE
    `uq_jobs_hash_step` garante 1 job por (hash, "extract"); `repo.enqueue` é no-op
    (retorna None) quando o job já existe. Rodar o sweep 2x não duplica. Cobre os
    Documents LEGADOS deixados pela Fase 2 antes desta fase (Runtime State Inventory).
    Documents já extraídos (com `Extraction`) são excluídos — não re-cobramos a IA.

    Retorna quantos jobs NOVOS foram criados (no-ops não contam).
    """
    docs = session.scalars(
        select(Document)
        .where(
            Document.state == DocState.PROCESSANDO,
            Document.last_completed_step == AWAITING_EXTRACTION_STEP,
            ~Document.content_hash.in_(select(Document.content_hash).join(Extraction)),
        )
    ).all()

    created = 0
    for doc in docs:
        job = repo.enqueue(
            session,
            original_hash=doc.content_hash,
            step=EXTRACT_STEP,
            payload=json.dumps({"content_hash": doc.content_hash}),
        )
        if job is not None:
            created += 1
    return created


def enqueue_pending_classifications(session: Session) -> int:
    """Enfileira um job de classify para cada bloco extraído que ainda não foi classificado.

    Espelha `enqueue_pending_extractions`, um passo adiante no pipeline: varremos
    no STARTUP do worker (UMA vez, idempotente) todos os Documents em `state ==
    PROCESSANDO` e `last_completed_step == "extraido"` (EXTRACTED_STEP) que ainda
    NÃO têm um `ClassificationResult` persistido, e enfileiramos
    `(block.content_hash, "classify")` para cada um.

    NÃO enfileiramos dentro do `extract_stage` (quebraria o commit único —
    `repo.enqueue` comita por si, Pitfall 4); o sweep no startup + a re-execução do
    sweep cobrem o fluxo, inclusive os Documents LEGADOS já extraídos antes desta
    fase. Idempotente: a chave do job é o `content_hash` e a UNIQUE
    `uq_jobs_hash_step` garante 1 job por (hash, "classify"); `repo.enqueue` é no-op
    quando já existe. Rodar 2x não duplica. Documents já classificados (com
    `ClassificationResult`) são excluídos — não re-cobramos a IA.

    Retorna quantos jobs NOVOS foram criados (no-ops não contam).
    """
    docs = session.scalars(
        select(Document)
        .where(
            Document.state == DocState.PROCESSANDO,
            Document.last_completed_step == EXTRACTED_STEP,
            ~Document.content_hash.in_(
                select(Document.content_hash).join(ClassificationResult)
            ),
        )
    ).all()

    created = 0
    for doc in docs:
        job = repo.enqueue(
            session,
            original_hash=doc.content_hash,
            step=CLASSIFY_STEP,
            payload=json.dumps({"content_hash": doc.content_hash}),
        )
        if job is not None:
            created += 1
    return created


def enqueue_pending_applications(session: Session) -> int:
    """Enfileira um job de apply p/ cada doc classificado de ALTA confiança pronto (D-01).

    Auto-aplica (06-RESEARCH Open Q3): varremos os Documents em `state ==
    PROCESSANDO` e `last_completed_step == "classificado"` (CLASSIFIED_STEP) cujo
    `ClassificationResult.confidence_score >= review_confidence_threshold` (alta
    confiança, D-01) e que ainda NÃO têm `AuditLog(status="done")` — e enfileiramos
    `(block.content_hash, "apply")` para cada um. Documentos de BAIXA confiança
    (abaixo do limiar) ficaram em EM_REVISAO no classify_stage e só aplicam após
    aprovação humana (D-02) — este sweep NÃO os captura (filtro de estado +
    confiança).

    Idempotente por desenho: a chave do job é o `content_hash` e a UNIQUE
    `uq_jobs_hash_step` garante 1 job por (hash, "apply"); `repo.enqueue` é no-op
    quando já existe. A exclusão por `AuditLog(status="done")` evita re-enfileirar um
    doc já aplicado. Rodar 2x não duplica.

    Retorna quantos jobs NOVOS foram criados (no-ops não contam).

    GATE do modo de aprovação (Fase 12, D-05): com `approval_mode_enabled` LIGADO,
    curto-circuitamos no TOPO — NÃO auto-aplicamos nada. Os docs de alta confiança
    ficam pendentes aguardando aprovação humana via DryRunPage (modo de teste). A
    trava de confiança (D-04) segue no `classify_stage`, fora deste sweep — docs de
    baixa confiança continuam indo a EM_REVISAO independentemente do toggle. O gate
    vive SÓ aqui, NUNCA em `apply_stage` (executor compartilhado com a aprovação
    manual — gateá-lo quebraria D-06: aprovar = apply).
    """
    if get_settings().approval_mode_enabled:
        return 0

    threshold = get_settings().review_confidence_threshold
    docs = session.scalars(
        select(Document)
        .join(ClassificationResult, ClassificationResult.document_id == Document.id)
        .where(
            Document.state == DocState.PROCESSANDO,
            Document.last_completed_step == CLASSIFIED_STEP,
            ClassificationResult.confidence_score.is_not(None),
            ClassificationResult.confidence_score >= threshold,
            ~Document.id.in_(
                select(AuditLog.document_id).where(AuditLog.status == "done")
            ),
        )
    ).all()

    created = 0
    for doc in docs:
        job = repo.enqueue(
            session,
            original_hash=doc.content_hash,
            step=APPLY_STEP,
            payload=json.dumps({"content_hash": doc.content_hash}),
        )
        if job is not None:
            created += 1
    return created


def _sweep_pending(engine: Engine) -> int:
    """Roda os três sweeps idempotentes (extract + classify + apply) e loga o que criou.

    Reusado no STARTUP e a cada ciclo OCIOSO do worker. Rodá-lo quando a fila
    esvazia é o que faz documentos avançarem ingest→extract→classify EM RUNTIME
    (não só os legados varridos no startup): após o ingest marcar blocos como
    `aguardando_extracao`, o próximo ciclo ocioso enfileira o extract; após o
    extract marcar `extraido`, o ciclo ocioso seguinte enfileira o classify.
    Idempotente por desenho (UNIQUE(content_hash, step) + os sweeps excluem blocos
    já adiantados), então rodá-lo repetidamente não duplica trabalho nem re-cobra IA.
    Retorna quantos jobs NOVOS foram criados (0 = nada pendente).
    """
    with get_session(engine) as session:
        enqueued = enqueue_pending_extractions(session)
    if enqueued:
        logger.info("Sweep: %s job(s) de extract enfileirados (blocos pendentes)", enqueued)

    with get_session(engine) as session:
        enqueued_cls = enqueue_pending_classifications(session)
    if enqueued_cls:
        logger.info(
            "Sweep: %s job(s) de classify enfileirados (blocos extraídos pendentes)",
            enqueued_cls,
        )

    with get_session(engine) as session:
        enqueued_apply = enqueue_pending_applications(session)
    if enqueued_apply:
        logger.info(
            "Sweep: %s job(s) de apply enfileirados (docs alta confiança pendentes, D-01)",
            enqueued_apply,
        )
    return enqueued + enqueued_cls + enqueued_apply


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

    # Reconciliação de intents órfãos de automação (Pitfall 7, T-06-13): um crash
    # entre o write-ahead (intent) e o `done` deixa um AuditLog(status="intent")
    # pendurado. UMA vez no startup, adjudicamos: destino íntegro → done; senão →
    # orphaned (o doc segue sem 'done' e o sweep de apply o re-captura).
    with get_session(engine) as session:
        reconciled = reconcile_orphans(session)
    if reconciled:
        logger.info("Reconcile: %s intent(s) órfão(s) de automação adjudicados", reconciled)

    # Sweep no startup (cobre legados sem job — Fases 2/3/4). A MESMA rotina roda
    # a cada ciclo ocioso abaixo, encadeando os estágios para docs processados ao vivo.
    _sweep_pending(engine)

    poll = get_settings().queue_poll_interval_seconds
    while not stop.is_set():
        processed = await _run_once(engine)
        if processed:
            # Há trabalho — não dorme; tenta o próximo imediatamente.
            continue
        # Fila vazia: re-roda os sweeps para encadear ingest→extract→classify dos
        # docs adiantados NESTA sessão (não só legados do startup). Se enfileirou
        # algo, NÃO dorme — processa já no próximo ciclo.
        if _sweep_pending(engine) > 0:
            continue
        # Nada pendente: dorme o intervalo de poll, mas acorda cedo se `stop`.
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll)
        except TimeoutError:
            pass

"""Watcher de pastas monitoradas — awatch → estabiliza → hash → gate → enqueue.

Costura a ingestão de ponta a ponta (ING-02): observa as pastas ATIVAS do banco
(`watched_folders.active`), e para cada arquivo novo/modificado que passe pela
allowlist de extensão (ING-04) executa o caminho determinístico:

    estabiliza (`wait_stable`) → hash SHA-256 do ORIGINAL (D-09) → gate de dedup
    (`ingested_originals`) → `enqueue` de um job `ingest`.

O watcher NÃO faz o trabalho pesado (store/split/Documents) — isso é do worker
(`queue.worker.run_worker` + `pipeline.ingest_stage`, Plano 03). Aqui só
estabilizamos, calculamos o hash do original e enfileiramos; a UNIQUE
`(original_hash, step)` da fila (PROC-03) e o gate pré-split (D-09/D-10) tornam
re-emitir o mesmo arquivo idempotente.

## Reconfiguração de pastas (D-02 / RESEARCH A5)

Pastas vivem no banco (D-02) e podem mudar pela API a qualquer momento. A
estratégia adotada é um **supervisor que relê a lista de pastas ativas do DB
periodicamente** (`_supervisor_interval_seconds`) e (re)inicia o `awatch` quando
o conjunto de paths muda. É a opção mais robusta: não exige acoplamento entre a
API e a task do watcher, tolera adição/remoção de pastas em runtime e reinicia o
`awatch` (que recebe os paths na construção) com o novo conjunto. Paths
inexistentes são pulados (log) sem derrubar o watcher.

## 1 worker uvicorn (Pitfall 5 / T-02-12)

O watcher sobe como `asyncio.Task` no `lifespan` (um por PROCESSO). Rodar uvicorn
com múltiplos workers duplicaria o watcher e o worker. O modo padrão (Windows,
single-tenant) DEVE usar `uvicorn --workers 1` — documentado em `main.py`.

Interface pública: `run_watcher`, `scan_and_enqueue`, `active_folder_paths`.
"""

import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from watchfiles import Change, awatch

from app.config import get_settings
from app.ingest.hashing import sha256_file
from app.ingest.splitter import is_supported_ext
from app.ingest.stabilizer import wait_stable
from app.models.ingested_original import IngestedOriginal
from app.models.watched_folder import WatchedFolder
from app.queue import repo
from app.storage.db import get_session

logger = logging.getLogger(__name__)

# Intervalo do supervisor: de quanto em quanto tempo o watcher relê as pastas
# ativas do DB para detectar reconfiguração (add/remove/ativar pasta — A5).
_SUPERVISOR_INTERVAL_SECONDS = 5.0


def active_folder_paths(session: Session) -> dict[Path, WatchedFolder]:
    """Mapa {path resolvido → WatchedFolder} das pastas ATIVAS e existentes.

    Lê `watched_folders` onde `active is True`. Paths inexistentes/inválidos são
    pulados (log) — uma pasta apagada do FS não deve derrubar o watcher. A chave
    é o `Path` resolvido; o valor carrega `pages_per_block`/`id` para o enqueue.
    """
    folders = session.scalars(
        select(WatchedFolder).where(WatchedFolder.active.is_(True))
    ).all()
    out: dict[Path, WatchedFolder] = {}
    for folder in folders:
        try:
            p = Path(folder.path).resolve()
        except (OSError, ValueError):
            logger.warning("Pasta monitorada com path inválido, pulando: %r", folder.path)
            continue
        if not p.is_dir():
            logger.warning("Pasta monitorada inexistente, pulando: %s", p)
            continue
        out[p] = folder
    return out


def _folder_for_path(file_path: Path, folders: dict[Path, WatchedFolder]) -> WatchedFolder | None:
    """Acha a WatchedFolder que contém `file_path` (match por prefixo de pasta)."""
    for folder_path, folder in folders.items():
        try:
            file_path.relative_to(folder_path)
        except ValueError:
            continue
        return folder
    return None


async def _stabilize_hash_gate_enqueue(
    engine: Engine,
    file_path: Path,
    folder_id: int | None,
    pages_per_block: int | None,
) -> bool:
    """Caminho de um candidato: estabiliza → hash → dedup gate → enqueue.

    Retorna True se um job foi enfileirado (candidato novo); False se o arquivo
    não estabilizou, é duplicata (gate) ou já estava enfileirado (idempotência).
    """
    if not is_supported_ext(file_path):
        return False

    # (1) Estabiliza: só prossegue quando size/mtime pararam e o arquivo abre sem
    # lock. Parcial/removido → descarta (Pitfall 1 / T-02-03).
    if not await wait_stable(file_path):
        logger.debug("Candidato não estabilizou, descartando: %s", file_path)
        return False

    # (2) Hash do ORIGINAL pré-split (D-09) — em thread (IO-bound); o mesmo
    # algoritmo do CAS, então o hash do gate coincide com o do conteúdo.
    try:
        original_hash = await asyncio.to_thread(sha256_file, file_path)
    except (OSError, FileNotFoundError):
        logger.debug("Falha ao ler candidato para hash, descartando: %s", file_path)
        return False

    # (3) Gate de dedup + (4) enqueue, na MESMA sessão. Se o original já foi
    # ingerido, incrementa duplicate_hits (D-10) e NÃO enfileira. Senão enfileira
    # um job ingest com o payload que o worker consome.
    with get_session(engine) as session:
        existing = session.scalar(
            select(IngestedOriginal).where(
                IngestedOriginal.original_hash == original_hash
            )
        )
        if existing is not None:
            existing.duplicate_hits += 1
            session.commit()
            logger.debug("Duplicata ignorada (gate): %s", file_path)
            return False

        payload = json.dumps(
            {
                "source_path": str(file_path),
                "folder_id": folder_id,
                "pages_per_block": pages_per_block,
            }
        )
        job = repo.enqueue(session, original_hash=original_hash, step="ingest", payload=payload)

    if job is None:
        # Já enfileirado para (hash, ingest) — idempotência PROC-03.
        logger.debug("Já enfileirado (idempotente): %s", file_path)
        return False
    logger.info("Candidato enfileirado: %s (job %s)", file_path, job.id)
    return True


async def scan_and_enqueue(engine: Engine, paths: list[Path]) -> int:
    """Varre `paths` recursivamente e enfileira cada candidato novo.

    Usado no startup e pelo endpoint `/rescan` (idempotente por dedup). Percorre
    os arquivos das pastas e passa cada um pelo caminho
    estabiliza→hash→gate→enqueue. Retorna quantos jobs foram realmente
    enfileirados (duplicatas/já-enfileirados não contam).
    """
    # Mapeia cada pasta de varredura à sua config (pages_per_block) — lido uma vez.
    folder_map: dict[Path, WatchedFolder] = {}
    with get_session(engine) as session:
        active = active_folder_paths(session)
        for p in paths:
            try:
                rp = Path(p).resolve()
            except (OSError, ValueError):
                logger.warning("Path de varredura inválido, pulando: %r", p)
                continue
            folder = active.get(rp) or _folder_for_path(rp, active)
            if folder is not None:
                folder_map[rp] = folder

    enqueued = 0
    for folder_path, folder in folder_map.items():
        if not folder_path.is_dir():
            logger.warning("Pasta de varredura inexistente, pulando: %s", folder_path)
            continue
        for file_path in sorted(folder_path.rglob("*")):
            if not file_path.is_file() or not is_supported_ext(file_path):
                continue
            if await _stabilize_hash_gate_enqueue(
                engine, file_path, folder.id, folder.pages_per_block
            ):
                enqueued += 1
    return enqueued


async def run_watcher(engine: Engine, stop: asyncio.Event) -> None:
    """Loop do watcher: supervisiona pastas ativas e observa mudanças até `stop`.

    No startup faz um `scan_and_enqueue` inicial (pega arquivos que já estavam na
    pasta). Em seguida entra num loop de supervisão: a cada ciclo relê as pastas
    ativas do DB e roda `awatch(*paths, stop_event=stop)`; se o conjunto de paths
    mudar (reconfiguração via API — A5), o `awatch` é reiniciado com o novo
    conjunto. Encerra limpo quando `stop` é setado.
    """
    # Scan inicial: arquivos já presentes nas pastas quando o app sobe.
    with get_session(engine) as session:
        initial_paths = list(active_folder_paths(session).keys())
    if initial_paths:
        try:
            n = await scan_and_enqueue(engine, initial_paths)
            if n:
                logger.info("Scan inicial enfileirou %s candidato(s)", n)
        except Exception:  # noqa: BLE001 — scan inicial nunca derruba o watcher
            logger.exception("Falha no scan inicial do watcher")

    while not stop.is_set():
        with get_session(engine) as session:
            folders = active_folder_paths(session)
        current_paths = set(folders.keys())

        if not current_paths:
            # Sem pastas ativas: aguarda o supervisor e reavalia (acorda em stop).
            try:
                await asyncio.wait_for(stop.wait(), timeout=_SUPERVISOR_INTERVAL_SECONDS)
            except TimeoutError:
                pass
            continue

        # Observa o conjunto atual; sai do awatch quando os paths mudam (relê o
        # DB) ou quando `stop` é setado. `awatch` recebe um stop_event próprio
        # para o reinício por reconfiguração sem matar o loop externo.
        local_stop = asyncio.Event()
        supervisor = asyncio.create_task(
            _watch_for_reconfig(engine, current_paths, stop, local_stop)
        )
        try:
            async for changes in awatch(*current_paths, stop_event=local_stop):
                await _handle_changes(engine, changes, folders)
        except FileNotFoundError:
            # Uma pasta sumiu durante a observação — relê o DB no próximo ciclo.
            logger.warning("Pasta observada sumiu; recarregando configuração")
        finally:
            local_stop.set()
            supervisor.cancel()
            await asyncio.gather(supervisor, return_exceptions=True)


async def _watch_for_reconfig(
    engine: Engine,
    observed: set[Path],
    stop: asyncio.Event,
    local_stop: asyncio.Event,
) -> None:
    """Sinaliza `local_stop` quando o conjunto de pastas ativas muda ou `stop`.

    Permite ao `awatch` (que fixa os paths na construção) ser reiniciado com o
    novo conjunto sem derrubar o loop externo do `run_watcher` (reconfiguração
    em runtime — A5).
    """
    while not stop.is_set() and not local_stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=_SUPERVISOR_INTERVAL_SECONDS)
        except TimeoutError:
            pass
        if stop.is_set():
            local_stop.set()
            return
        with get_session(engine) as session:
            current = set(active_folder_paths(session).keys())
        if current != observed:
            logger.info("Conjunto de pastas mudou — reiniciando observação")
            local_stop.set()
            return


async def _handle_changes(
    engine: Engine,
    changes: set[tuple[Change, str]],
    folders: dict[Path, WatchedFolder],
) -> None:
    """Processa um lote de mudanças do `awatch`: enfileira candidatos novos."""
    for change, raw_path in changes:
        if change == Change.deleted:
            continue
        file_path = Path(raw_path)
        if not is_supported_ext(file_path):
            continue
        folder = _folder_for_path(file_path.resolve(), folders) if folders else None
        folder_id = folder.id if folder is not None else None
        pages_per_block = folder.pages_per_block if folder is not None else None
        try:
            await _stabilize_hash_gate_enqueue(
                engine, file_path, folder_id, pages_per_block
            )
        except Exception:  # noqa: BLE001 — um candidato ruim não derruba o watcher
            logger.exception("Falha ao processar candidato %s", file_path)

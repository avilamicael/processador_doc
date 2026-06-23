"""Estágio de ingestão — orquestra gate→store→split→Documents→estado terminal.

Coração idempotente da Fase 2. Reusa o CAS (`cas.store`), o separador
(`split_pdf`/`is_supported_ext`) e a máquina de estados (`transition`) — aqui só a
orquestração (sem HTTP, mesmo papel de `state_machine.py`). Materializa:

- ING-04: allowlist de extensão — arquivo não suportado é IGNORADO (sem Document
  nem registro), retornando "ignored".
- ING-06 / D-09 / D-10: gate de dedup PRÉ-split sobre `ingested_originals`. Um
  original já visto (mesmo `original_hash`) é no-op — NÃO re-separa, NÃO cria
  blocos; só incrementa `duplicate_hits` e retorna "duplicate".
- PROC-03 / CR-02: reprocessar (resume após crash) é idempotente E atômico. A
  ingestão de um original — registro do `IngestedOriginal` (gate) + criação de
  TODOS os `Document`s dos blocos — acontece numa ÚNICA transação, com um único
  `session.commit()` ao final. Um crash no meio do loop de blocos faz ROLLBACK
  TOTAL: o gate de dedup nunca enxerga um original "meio-criado", então o resume
  recria todos os blocos do zero. Sem perda silenciosa (constraint da CLAUDE.md:
  "nunca pode causar perda"), sem duplicata (gate + `content_hash` único).
- Estado terminal da fase (Pitfall 6): cada bloco vira um Document INDEPENDENTE
  (seu próprio `content_hash`, ligado ao original por `origin_original_id`), que
  termina em PROCESSANDO com `last_completed_step = "aguardando_extracao"`. NUNCA
  CONCLUIDO — a extração/classificação são fases posteriores.

Rede de segurança (D-07/A4): o original INTEIRO é `cas.store`-ado antes do split,
e cada bloco é escrito num temporário no mesmo volume de `data_dir` e `cas.store`-ado
(o `store` é idempotente, então re-store é no-op). Temporários são sempre limpos.

Interface pública: `process_ingest`, `IngestResult`, `AWAITING_EXTRACTION_STEP`.
"""

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation import fileops
from app.automation.naming import sanitize_component
from app.config import get_settings
from app.ingest.splitter import is_supported_ext, split_pdf
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import DocState
from app.models.ingested_original import IngestedOriginal
from app.pipeline.states import InvalidTransition, is_valid_transition
from app.storage import cas

logger = logging.getLogger(__name__)

# Marcador interno terminal da Fase 2 (D-05). A UI (Plano 05) lê este valor via
# API para mostrar "aguardando extração". NÃO é um estado de topo (DocState).
AWAITING_EXTRACTION_STEP = "aguardando_extracao"

# Extensões tratadas como imagem (1 documento, sem split — D-07). PDF é o único
# formato que passa pelo separador.
_PDF_EXT = ".pdf"

IngestStatus = Literal["ingested", "duplicate", "ignored", "failed"]


@dataclass(frozen=True)
class IngestResult:
    """Resultado de `process_ingest`: status + nº de blocos/Documents gerados."""

    status: IngestStatus
    block_count: int = 0


def process_ingest(
    session: Session,
    *,
    source_path: Path,
    folder_id: int | None,
    pages_per_block: int | None,
    original_hash: str,
    split_to_files: bool = False,
) -> IngestResult:
    """Ingere um original: gate de dedup, store, split e criação de Documents.

    Passos:
      1. Allowlist (ING-04): extensão não suportada → "ignored" (sem efeitos).
      2. Gate de dedup (D-09): original já registrado → incrementa `duplicate_hits`
         e retorna "duplicate" (NÃO re-separa — D-10).
      3. Store do original inteiro no CAS (rede de segurança — D-07/A4).
      4. Registra `IngestedOriginal`.
      5. Separa: PDF → `split_pdf`; imagem → 1 bloco = o próprio arquivo.
      6. Cada bloco → `cas.store` → `Document` em PROCESSANDO +
         `last_completed_step="aguardando_extracao"` (NUNCA CONCLUIDO).

    Atomicidade (CR-02): os passos 4–6 são UMA transação com um único
    `session.commit()` no final. Não há commit por bloco — um crash no meio do
    loop faz rollback total e o gate jamais vê um original parcial, garantindo que
    o resume recrie todos os blocos (sem perda) e o `content_hash` único evite
    duplicatas.

    Separação física opt-in (passo 7, só se `split_to_files=True`, quick 260623-pzy):
    DEPOIS do commit único, se a pasta tem o opt-in LIGADO e é um PDF com blocos,
    materializa cada bloco como arquivo na PRÓPRIA pasta do original e remove o
    original do disco — de forma segura, reversível e sem loop do watcher. A ordem
    é a garantia (ver `_materialize_blocks_to_folder`): registra o gate anti-loop
    de cada bloco ANTES de gravar, grava com verificação por hash (`materialize_to_dest`)
    sob AuditLog write-ahead, e SÓ depois de TODOS verificados remove o original (que
    permanece recuperável do CAS — constraint sagrada). Default OFF = comportamento
    atual idêntico.

    Retorna `IngestResult(status, block_count)`.
    """
    source_path = Path(source_path)

    # (1) Allowlist de extensão (ING-04). Ignorado silenciosamente (log leve);
    # sem Document, sem registro — reduz superfície (T-02-06).
    if not is_supported_ext(source_path):
        logger.debug("Ignorando arquivo de extensão não suportada: %s", source_path.name)
        return IngestResult(status="ignored")

    # (2) Gate de dedup PRÉ-split (D-09/D-10). Um original já visto é no-op:
    # incrementa o contador e retorna sem re-separar nem recriar blocos.
    existing = session.scalar(
        select(IngestedOriginal).where(
            IngestedOriginal.original_hash == original_hash
        )
    )
    if existing is not None:
        existing.duplicate_hits += 1
        session.commit()
        return IngestResult(status="duplicate", block_count=existing.block_count)

    # (3) Rede de segurança: o original INTEIRO vai ao CAS antes do split (D-07/A4).
    # `store` é idempotente por conteúdo.
    cas.store(source_path)

    # (4) Registra o original (gate). `flush` para obter o id e ligar os blocos.
    original = IngestedOriginal(
        original_hash=original_hash,
        original_filename=source_path.name,
        source_folder_id=folder_id,
        block_count=0,
    )
    session.add(original)
    session.flush()

    # (5) Separar em blocos. PDF → split_pdf; imagem → 1 bloco = o arquivo inteiro.
    is_pdf = source_path.suffix.lower() == _PDF_EXT
    if is_pdf:
        blocks = split_pdf(source_path, pages_per_block)
    else:
        # Imagem (JPG/PNG): nunca separa — 1 documento (D-07).
        blocks = [source_path.read_bytes()]

    # (6) Por bloco: store no CAS + cria Document terminal "aguardando extração".
    # Cada bloco nasce em RECEBIDO e vai a PROCESSANDO. Validamos a aresta da
    # allowlist UMA vez (todos os blocos seguem o mesmo caminho RECEBIDO→
    # PROCESSANDO) e setamos o estado em memória — sem `transition` (que commita
    # por chamada e quebraria a atomicidade do CR-02). O commit único é no fim.
    if not is_valid_transition(DocState.RECEBIDO, DocState.PROCESSANDO):
        raise InvalidTransition(DocState.RECEBIDO, DocState.PROCESSANDO)

    created = 0
    data_dir = get_settings().data_dir
    # Hashes dos blocos NA ORDEM do split (base do nome `_p{a}-{b}` e do gate
    # anti-loop no passo 7). Acumulado mesmo no caminho opt-in OFF (custo nulo).
    block_hashes: list[str] = []
    for block_bytes in blocks:
        block_hash = _store_block(block_bytes, data_dir)
        block_hashes.append(block_hash)

        # Idempotência de resume (PROC-03): se já existe um Document para este
        # content_hash, não recria (re-processar o mesmo job é no-op).
        already = session.scalar(
            select(Document).where(Document.content_hash == block_hash)
        )
        if already is not None:
            created += 1
            continue

        # Estado terminal da fase em memória; NUNCA CONCLUIDO (Pitfall 6) — a
        # extração é fase posterior. Persistido no commit único do passo (7).
        doc = Document(
            content_hash=block_hash,
            original_filename=source_path.name,
            origin_original_id=original.id,
            state=DocState.PROCESSANDO,
            last_completed_step=AWAITING_EXTRACTION_STEP,
        )
        session.add(doc)
        created += 1

    # (7) Registra quantos blocos o original gerou e commita TUDO atomicamente
    # (IngestedOriginal + todos os Documents). Crash antes daqui = rollback total.
    original.block_count = len(blocks)
    session.commit()

    # (8) Separação física opt-in (quick 260623-pzy). Só roda com o opt-in LIGADO,
    # para um PDF com blocos numa pasta conhecida. Os blocos+IngestedOriginal já
    # estão persistidos (commit acima); aqui materializamos os blocos NA PASTA e
    # removemos o original — de forma segura/anti-loop (ver a função).
    if split_to_files and is_pdf and folder_id is not None and block_hashes:
        _materialize_blocks_to_folder(
            session,
            source_path=source_path,
            folder_id=folder_id,
            pages_per_block=pages_per_block,
            block_hashes=block_hashes,
            original_hash=original_hash,
        )

    return IngestResult(status="ingested", block_count=created)


def _block_page_ranges(total_pages: int, pages_per_block: int | None) -> list[tuple[int, int]]:
    """Reproduz as faixas de páginas do `split_pdf` (1-based, inclusivas).

    Espelha o range do `splitter.split_pdf`: blocos de até N páginas
    (`step = total_pages` quando `pages_per_block` é None/0). Para 5 páginas com
    N=2 → `[(1, 2), (3, 4), (5, 5)]`. Usado só para rotular os arquivos de bloco.
    """
    step = total_pages if not pages_per_block else pages_per_block
    ranges: list[tuple[int, int]] = []
    for start in range(0, total_pages, step):
        end = min(start + step, total_pages)
        ranges.append((start + 1, end))  # 1-based inclusivo
    return ranges


def _block_filename(stem: str, start: int, end: int) -> str:
    """Nome do arquivo de bloco derivado do stem do original + faixa de páginas.

    `_p{a}` para 1 página, `_p{a}-{b}` para faixa. Sanitizado p/ Windows (o stem
    do original é entrada do usuário — defesa de path/nome inválido, T-pzy-03).
    """
    label = f"_p{start}" if start == end else f"_p{start}-{end}"
    return sanitize_component(f"{stem}{label}.pdf")


def _materialize_blocks_to_folder(
    session: Session,
    *,
    source_path: Path,
    folder_id: int,
    pages_per_block: int | None,
    block_hashes: list[str],
    original_hash: str,
) -> None:
    """Materializa os blocos como arquivos na pasta e remove o original (260623-pzy).

    A ORDEM É a garantia de segurança e anti-loop (constraint sagrada da CLAUDE.md):

    (A) ANTI-LOOP PRIMEIRO — registra o gate de cada bloco em `ingested_originals`
        (keyed por hash; sha256_file de um arquivo de bloco == content_hash do bloco)
        e COMMITA esse registro ANTES de gravar qualquer arquivo. Assim, no instante
        em que o arquivo de bloco aparece na pasta observada, o watcher já o reconhece
        como duplicata → no-op (não re-ingere/re-separa). Reusa a MESMA tabela e
        semântica de "hash já visto" que o watcher e o passo 2 já consultam — mais
        limpo que um mecanismo dedicado. UNIQUE(original_hash) já existente → re-run
        é idempotente (pula a linha existente).

    (B) Deriva o nome de cada bloco do stem do original + faixa de páginas (sanitizado
        p/ Windows). A anti-colisão de nome é coberta por `materialize_to_dest` +
        `resolve_collision` do fileops — não reimplementada aqui.

    (C) Por bloco (na ordem de `block_hashes`): AuditLog write-ahead status="intent"
        (action="apply", source/dest = caminho do bloco, content_hash = block_hash,
        document_id do bloco) → commit → `fileops.materialize_to_dest` (escreve do CAS,
        verifica hash) → marca status="done". IntegrityError propaga (o worker roteia
        a FALHA; o original NÃO é removido — preservação).

    (D) SÓ DEPOIS de TODOS os blocos gravados+verificados: AuditLog write-ahead da
        remoção (action="apply", source_path = original, content_hash = original_hash,
        dest_path = None) → commit → `fileops.remove_original` → status="done". Se
        qualquer bloco falhou em (C), NÃO chega aqui — o original permanece (rede de
        segurança; ele também está no CAS por original_hash).

    Escolha de `action="apply"`: o undo de "apply" restaura via destino ou via CAS
    (apagar o bloco e restaurar o original do CAS) — a reversão desejada. A propriedade
    obrigatória garantida é: reversível e nunca perde (o original está no CAS).

    Crash-safety: UNIQUE(original_hash) do gate + UNIQUE(content_hash) dos blocos +
    `resolve_collision` (D-10 pula bloco idêntico já gravado) + `remove_original`
    idempotente (missing_ok). `reconcile_orphans` (startup do worker) adjudica
    intents pendurados. NÃO loga conteúdo (só paths/hashes — LGPD V7/V9).
    """
    dest_dir = source_path.parent
    stem = Path(source_path.name).stem

    # Faixas de páginas para rotular os arquivos (mesmo nº de blocos do split).
    total_pages = _pdf_page_count(original_hash, block_hashes)
    ranges = _block_page_ranges(total_pages, pages_per_block)
    # Defesa: se a contagem divergir do nº de blocos (PDF degenerado), rotula por
    # índice sequencial para nunca quebrar — o nome é genérico de qualquer modo.
    if len(ranges) != len(block_hashes):
        ranges = [(i + 1, i + 1) for i in range(len(block_hashes))]

    # (A) Gate anti-loop ANTES de qualquer escrita — commit isolado por bloco.
    for block_hash, (start, end) in zip(block_hashes, ranges, strict=True):
        block_name = _block_filename(stem, start, end)
        try:
            session.add(
                IngestedOriginal(
                    original_hash=block_hash,
                    original_filename=block_name,
                    source_folder_id=folder_id,
                    block_count=0,
                )
            )
            session.commit()
        except Exception:  # noqa: BLE001 — UNIQUE já existente = re-run idempotente
            session.rollback()

    # (C) Materializa cada bloco com write-ahead + verificação por hash.
    for block_hash, (start, end) in zip(block_hashes, ranges, strict=True):
        block_name = _block_filename(stem, start, end)
        dest = dest_dir / block_name
        doc = session.scalar(
            select(Document).where(Document.content_hash == block_hash)
        )
        audit = AuditLog(
            document_id=doc.id if doc is not None else None,
            action="apply",
            status="intent",
            source_path=str(dest),
            dest_path=str(dest),
            content_hash=block_hash,
            details="split_to_files: grava bloco na pasta (260623-pzy)",
        )
        session.add(audit)
        session.commit()

        # Escreve do CAS verificando o hash. IntegrityError propaga (FALHA; o
        # original é PRESERVADO — não chegamos ao passo D).
        fileops.materialize_to_dest(block_hash, dest)

        audit.status = "done"
        session.commit()

    # (D) SÓ após TODOS os blocos gravados+verificados: remove o original do disco.
    removal = AuditLog(
        document_id=None,
        action="apply",
        status="intent",
        source_path=str(source_path),
        dest_path=None,
        content_hash=original_hash,
        details="split_to_files: remove o original (recuperável do CAS, 260623-pzy)",
    )
    session.add(removal)
    session.commit()

    fileops.remove_original(source_path)

    removal.status = "done"
    session.commit()


def _pdf_page_count(original_hash: str, block_hashes: list[str]) -> int:
    """Conta as páginas do PDF original (lido do CAS) para rotular os blocos.

    Lê o blob imutável do CAS por `original_hash` (rede de verdade — o original já
    está lá) e conta as páginas via pikepdf. Em qualquer falha, devolve o nº de
    blocos (fallback seguro: rótulo sequencial). NÃO loga conteúdo.
    """
    try:
        import io

        import pikepdf

        blob = cas.read_bytes(original_hash)
        with pikepdf.Pdf.open(io.BytesIO(blob)) as pdf:
            return len(pdf.pages)
    except Exception:  # noqa: BLE001 — fallback para rótulo sequencial
        return len(block_hashes)


def _store_block(block_bytes: bytes, data_dir: Path) -> str:
    """Escreve `block_bytes` num temporário no volume de `data_dir` e o armazena.

    Caminho de menor risco (A4): a assinatura atual de `cas.store` recebe um
    `Path`; escrevemos cada bloco num arquivo temporário NO MESMO VOLUME da pasta
    de dados (para o `os.replace` interno do CAS ser um rename atômico) e chamamos
    `cas.store`. O temporário é sempre removido. Retorna o `content_hash` do bloco.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=data_dir, suffix=".block.tmp")
    tmp_path = Path(tmp_name)
    try:
        with Path(tmp_name).open("wb") as fh:
            fh.write(block_bytes)
        os.close(fd)
        fd = -1
        return cas.store(tmp_path)
    finally:
        if fd != -1:
            os.close(fd)
        tmp_path.unlink(missing_ok=True)

"""Estágio de ingestão — orquestra gate→store→split→Documents→estado terminal.

Coração idempotente da Fase 2. Reusa o CAS (`cas.store`), o separador
(`split_pdf`/`is_supported_ext`) e a máquina de estados (`transition`) — aqui só a
orquestração (sem HTTP, mesmo papel de `state_machine.py`). Materializa:

- ING-04: allowlist de extensão — arquivo não suportado é IGNORADO (sem Document
  nem registro), retornando "ignored".
- ING-06 / D-09 / D-10: gate de dedup PRÉ-split sobre `ingested_originals`. Um
  original já visto (mesmo `original_hash`) é no-op — NÃO re-separa, NÃO cria
  blocos; só incrementa `duplicate_hits` e retorna "duplicate".
- PROC-03: reprocessar (resume após crash) é idempotente — o gate pega o original;
  e mesmo que não pegasse, o `content_hash` único dos blocos torna re-criar um
  Document um no-op (checagem prévia).
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

from app.config import get_settings
from app.ingest.splitter import is_supported_ext, split_pdf
from app.models.document import Document
from app.models.enums import DocState
from app.models.ingested_original import IngestedOriginal
from app.pipeline.state_machine import transition
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
    created = 0
    data_dir = get_settings().data_dir
    for block_bytes in blocks:
        block_hash = _store_block(block_bytes, data_dir)

        # Idempotência de resume (PROC-03): se já existe um Document para este
        # content_hash, não recria (re-processar o mesmo job é no-op).
        already = session.scalar(
            select(Document).where(Document.content_hash == block_hash)
        )
        if already is not None:
            created += 1
            continue

        doc = Document(
            content_hash=block_hash,
            original_filename=source_path.name,
            origin_original_id=original.id,
        )
        session.add(doc)
        session.flush()
        # RECEBIDO→PROCESSANDO está na allowlist; marca o estado terminal da fase.
        # NUNCA transiciona para CONCLUIDO (Pitfall 6) — extração é fase posterior.
        transition(
            session,
            doc,
            DocState.PROCESSANDO,
            completed_step=AWAITING_EXTRACTION_STEP,
        )
        created += 1

    # (7) Registra quantos blocos o original gerou e commita.
    original.block_count = len(blocks)
    session.commit()

    return IngestResult(status="ingested", block_count=created)


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

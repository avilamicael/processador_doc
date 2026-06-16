"""Gate de deduplicação pré-split (D-09/D-10/ING-06) via `ingest_stage`.

Prova:
- A 1ª ingestão de um original novo cria N Documents e registra o
  `IngestedOriginal` (status "ingested").
- A 2ª ingestão do MESMO `original_hash` é no-op: NÃO cria Documents nem
  re-separa; incrementa `duplicate_hits` e retorna "duplicate" (D-10).
- Reprocessar (resume após crash) é idempotente.

Schema via `Base.metadata.create_all` (D-10: só em teste); `data_dir` (conftest)
isola o CAS num diretório temporário.
"""

from pathlib import Path

import pikepdf
from sqlalchemy import Engine, func, select

from app.ingest.hashing import sha256_file
from app.models import Document, IngestedOriginal
from app.pipeline import ingest_stage
from app.storage.db import get_session


def _make_pdf(path: Path, pages: int) -> Path:
    """PDF com `pages` páginas byte-distintas (conteúdo único por página)."""
    pdf = pikepdf.Pdf.new()
    for i in range(pages):
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pikepdf.Stream(
            pdf, f"BT /F1 12 Tf 20 100 Td (pagina {i}) Tj ET".encode()
        )
    pdf.save(path)
    pdf.close()
    return path


def test_dedup_gate_segunda_ingestao_nao_cria_documentos(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    src = _make_pdf(tmp_path / "original.pdf", pages=4)
    original_hash = sha256_file(src)

    # 1ª ingestão: separa em blocos (1 página/bloco → 4 Documents).
    with get_session(schema_engine) as s:
        r1 = ingest_stage.process_ingest(
            s,
            source_path=src,
            folder_id=None,
            pages_per_block=1,
            original_hash=original_hash,
        )
    assert r1.status == "ingested"
    assert r1.block_count == 4

    with get_session(schema_engine) as s:
        n_docs = s.scalar(select(func.count()).select_from(Document))
        assert n_docs == 4

    # 2ª ingestão do MESMO original: no-op, incrementa duplicate_hits.
    with get_session(schema_engine) as s:
        r2 = ingest_stage.process_ingest(
            s,
            source_path=src,
            folder_id=None,
            pages_per_block=1,
            original_hash=original_hash,
        )
    assert r2.status == "duplicate"

    with get_session(schema_engine) as s:
        # Nenhum Document novo.
        n_docs = s.scalar(select(func.count()).select_from(Document))
        assert n_docs == 4
        ing = s.scalar(
            select(IngestedOriginal).where(
                IngestedOriginal.original_hash == original_hash
            )
        )
        assert ing is not None
        assert ing.duplicate_hits == 1
        assert ing.block_count == 4


def test_reprocesso_idempotente_nao_duplica(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    src = _make_pdf(tmp_path / "doc.pdf", pages=2)
    original_hash = sha256_file(src)

    with get_session(schema_engine) as s:
        ingest_stage.process_ingest(
            s,
            source_path=src,
            folder_id=None,
            pages_per_block=1,
            original_hash=original_hash,
        )
    # Reprocessar o mesmo job (gate pega) — sem novos Documents.
    with get_session(schema_engine) as s:
        r = ingest_stage.process_ingest(
            s,
            source_path=src,
            folder_id=None,
            pages_per_block=1,
            original_hash=original_hash,
        )
        assert r.status == "duplicate"

    with get_session(schema_engine) as s:
        n_docs = s.scalar(select(func.count()).select_from(Document))
        assert n_docs == 2

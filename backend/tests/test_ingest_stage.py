"""Orquestração de ingestão: gate→store→split→Documents→estado terminal.

Prova (Plano 02-03 Task 2):
- Allowlist de extensão (ING-04): `.txt` → "ignored", sem Document nem registro.
- Estado terminal: após `process_ingest`, todo Document está em PROCESSANDO com
  `last_completed_step == "aguardando_extracao"`; NENHUM CONCLUIDO (Pitfall 6).
- Split de PDF multi-página: `ceil(M/N)` Documents, cada um com
  `origin_original_id` setado e `content_hash` próprio.
- Imagem (JPG/PNG): 1 Document, sem split (D-07).

`data_dir` (conftest) isola o CAS; schema via create_all (D-10: só em teste).
"""

import math
from pathlib import Path

import pikepdf
from sqlalchemy import Engine, select

from app.ingest.hashing import sha256_file
from app.models import DocState, Document, IngestedOriginal
from app.pipeline import ingest_stage
from app.pipeline.ingest_stage import AWAITING_EXTRACTION_STEP
from app.storage.db import get_session


def _make_pdf(path: Path, pages: int) -> Path:
    """PDF com `pages` páginas BYTE-DISTINTAS (conteúdo único por página).

    Páginas distintas garantem que cada bloco de 1 página tenha `content_hash`
    próprio (documentos reais diferem por página; páginas idênticas seriam
    deduplicadas pelo CAS, o que é correto, mas não é o que estes testes medem).
    """
    pdf = pikepdf.Pdf.new()
    for i in range(pages):
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pikepdf.Stream(
            pdf, f"BT /F1 12 Tf 20 100 Td (pagina {i}) Tj ET".encode()
        )
    pdf.save(path)
    pdf.close()
    return path


def _make_image(path: Path) -> Path:
    # PNG mínimo válido (1x1) — basta a extensão para a allowlist + bytes p/ store.
    png_1x1 = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d4944415478da6360000002000100ffff03000006000557bfabd400"
        "0000004945454e44ae426082"
    )
    path.write_bytes(png_1x1)
    return path


def test_extension_allowlist(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    txt = tmp_path / "nota.txt"
    txt.write_text("isto não é um documento suportado")
    original_hash = sha256_file(txt)

    with get_session(schema_engine) as s:
        r = ingest_stage.process_ingest(
            s,
            source_path=txt,
            folder_id=None,
            pages_per_block=None,
            original_hash=original_hash,
        )
    assert r.status == "ignored"

    with get_session(schema_engine) as s:
        assert s.scalars(select(Document)).all() == []
        assert s.scalars(select(IngestedOriginal)).all() == []


def test_terminal_state(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    src = _make_pdf(tmp_path / "doc.pdf", pages=3)
    original_hash = sha256_file(src)

    with get_session(schema_engine) as s:
        ingest_stage.process_ingest(
            s,
            source_path=src,
            folder_id=None,
            pages_per_block=1,
            original_hash=original_hash,
        )

    with get_session(schema_engine) as s:
        docs = s.scalars(select(Document)).all()
        assert len(docs) == 3
        for d in docs:
            # Estado terminal da Fase 2: PROCESSANDO + marcador, NUNCA CONCLUIDO.
            assert d.state == DocState.PROCESSANDO
            assert d.last_completed_step == AWAITING_EXTRACTION_STEP
            assert d.state != DocState.CONCLUIDO


def test_split_multipagina_cria_n_documentos(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    src = _make_pdf(tmp_path / "multi.pdf", pages=5)
    original_hash = sha256_file(src)

    with get_session(schema_engine) as s:
        r = ingest_stage.process_ingest(
            s,
            source_path=src,
            folder_id=None,
            pages_per_block=2,
            original_hash=original_hash,
        )
    expected = math.ceil(5 / 2)
    assert r.status == "ingested"
    assert r.block_count == expected

    with get_session(schema_engine) as s:
        ing = s.scalar(
            select(IngestedOriginal).where(
                IngestedOriginal.original_hash == original_hash
            )
        )
        docs = s.scalars(select(Document)).all()
        assert len(docs) == expected
        # Cada bloco tem content_hash próprio e aponta para o original.
        hashes = {d.content_hash for d in docs}
        assert len(hashes) == expected
        assert all(d.origin_original_id == ing.id for d in docs)
        assert ing.block_count == expected


def test_imagem_gera_um_documento_sem_split(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    img = _make_image(tmp_path / "scan.png")
    original_hash = sha256_file(img)

    with get_session(schema_engine) as s:
        r = ingest_stage.process_ingest(
            s,
            source_path=img,
            folder_id=None,
            pages_per_block=None,
            original_hash=original_hash,
        )
    assert r.status == "ingested"
    assert r.block_count == 1

    with get_session(schema_engine) as s:
        docs = s.scalars(select(Document)).all()
        assert len(docs) == 1
        assert docs[0].state == DocState.PROCESSANDO

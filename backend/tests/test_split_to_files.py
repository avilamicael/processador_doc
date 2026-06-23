"""Separação física opt-in dos blocos na pasta (split_to_files) — segurança/corretude.

Foco do quick 260623-pzy. Quando uma pasta monitorada tem `split_to_files=True`,
ao ingerir um PDF multipágina o `process_ingest` MATERIALIZA os blocos como
arquivos na PRÓPRIA pasta (faixas de páginas no nome, sanitizadas p/ Windows),
registra o gate anti-loop ANTES de gravar, escreve cada bloco via `materialize_to_dest`
(verificação por hash), registra AuditLog write-ahead e SÓ DEPOIS remove o original
— que permanece SEMPRE recuperável do CAS (constraint sagrada da CLAUDE.md).

Invariantes cobertas (RED→GREEN):
- N arquivos de bloco gravados + original removido do disco;
- original recuperável do CAS (nunca perde);
- gate anti-loop: cada bloco tem IngestedOriginal(original_hash==content_hash)
  registrado, fechando o loop do watcher (re-ver um bloco = duplicata, no-op);
- AuditLog write-ahead intent→done por bloco e pela remoção do original;
- opt-in OFF (default) = comportamento atual idêntico (nada gravado/removido);
- idempotência/crash-safety: re-rodar não duplica arquivos nem perde o original.

`data_dir` (conftest) isola o CAS; `schema_engine` cria o schema via create_all.
"""

from pathlib import Path

import pikepdf
from sqlalchemy import Engine, select

from app.ingest.hashing import sha256_file
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.ingested_original import IngestedOriginal
from app.pipeline import ingest_stage
from app.storage import cas
from app.storage.db import get_session


def _make_pdf(path: Path, pages: int) -> Path:
    """PDF com `pages` páginas BYTE-DISTINTAS (content_hash próprio por bloco)."""
    pdf = pikepdf.Pdf.new()
    for i in range(pages):
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pikepdf.Stream(
            pdf, f"BT /F1 12 Tf 20 100 Td (pagina unica {i}) Tj ET".encode()
        )
    pdf.save(path)
    pdf.close()
    return path


def _ingest(
    engine: Engine,
    src: Path,
    *,
    folder_id: int | None,
    pages_per_block: int | None,
    split_to_files: bool,
) -> ingest_stage.IngestResult:
    original_hash = sha256_file(src)
    with get_session(engine) as session:
        return ingest_stage.process_ingest(
            session,
            source_path=src,
            folder_id=folder_id,
            pages_per_block=pages_per_block,
            original_hash=original_hash,
            split_to_files=split_to_files,
        )


def test_opt_in_grava_n_arquivos_e_remove_original(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    """split_to_files=True, pages_per_block=2, PDF 5pp → 3 blocos na pasta, original some."""
    folder = tmp_path / "hot"
    folder.mkdir()
    src = _make_pdf(folder / "doc.pdf", pages=5)

    result = _ingest(
        schema_engine, src, folder_id=1, pages_per_block=2, split_to_files=True
    )
    assert result.status == "ingested"

    # O original NÃO existe mais no disco; 3 arquivos de bloco no lugar.
    assert not src.exists(), "o original deveria ter sido removido do disco"
    pdfs = sorted(p.name for p in folder.glob("*.pdf"))
    assert len(pdfs) == 3, f"esperados 3 blocos na pasta, achei: {pdfs}"
    assert pdfs == ["doc_p1-2.pdf", "doc_p3-4.pdf", "doc_p5.pdf"], pdfs

    # block_count do original == 3.
    with get_session(schema_engine) as session:
        orig = session.scalar(
            select(IngestedOriginal).where(
                IngestedOriginal.original_filename == "doc.pdf"
            )
        )
        assert orig is not None
        assert orig.block_count == 3


def test_original_recuperavel_do_cas(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    """Após a substituição, o original é recuperável do CAS byte-a-byte (não perde)."""
    folder = tmp_path / "hot"
    folder.mkdir()
    src = folder / "doc.pdf"
    _make_pdf(src, pages=5)
    original_bytes = src.read_bytes()
    original_hash = sha256_file(src)

    _ingest(schema_engine, src, folder_id=1, pages_per_block=2, split_to_files=True)

    assert not src.exists()
    # O original inteiro continua no CAS, recuperável pelo hash.
    assert cas.exists(original_hash)
    assert cas.read_bytes(original_hash) == original_bytes


def test_anti_loop_gate_reconhece_blocos(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    """Cada bloco gravado tem IngestedOriginal(original_hash==content_hash do bloco).

    Isso fecha o loop do watcher: o watcher faz sha256_file do arquivo de bloco e
    consulta IngestedOriginal — encontra a linha → no-op (não re-ingere/re-separa).
    """
    folder = tmp_path / "hot"
    folder.mkdir()
    src = _make_pdf(folder / "doc.pdf", pages=5)

    _ingest(schema_engine, src, folder_id=1, pages_per_block=2, split_to_files=True)

    # Para cada arquivo de bloco no disco: seu sha256 == content_hash, e existe um
    # IngestedOriginal com original_hash == esse hash (o gate reconhece o bloco).
    block_paths = sorted(folder.glob("*.pdf"))
    assert len(block_paths) == 3
    with get_session(schema_engine) as session:
        for bp in block_paths:
            block_hash = sha256_file(bp)
            gate = session.scalar(
                select(IngestedOriginal).where(
                    IngestedOriginal.original_hash == block_hash
                )
            )
            assert gate is not None, (
                f"bloco {bp.name} (hash {block_hash[:8]}) não está no gate anti-loop"
            )


def test_audit_write_ahead_intent_done(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    """Há AuditLog 'done' por bloco gravado E pela remoção do original (reversível)."""
    folder = tmp_path / "hot"
    folder.mkdir()
    src = src = _make_pdf(folder / "doc.pdf", pages=5)
    original_hash = sha256_file(src)

    _ingest(schema_engine, src, folder_id=1, pages_per_block=2, split_to_files=True)

    with get_session(schema_engine) as session:
        logs = session.scalars(select(AuditLog)).all()
        # Nenhum AuditLog pode ficar pendurado em 'intent' (todos concluídos).
        assert all(log.status == "done" for log in logs), (
            f"AuditLog não-concluído: {[(l.action, l.status) for l in logs]}"
        )
        # 3 gravações de bloco + 1 remoção do original = 4 registros 'done'.
        assert len(logs) == 4, f"esperados 4 AuditLog, achei {len(logs)}"

        # As gravações de bloco têm dest_path preenchido (o arquivo na pasta).
        writes = [l for l in logs if l.dest_path is not None]
        assert len(writes) == 3
        for w in writes:
            assert w.content_hash is not None
            assert w.source_path is not None

        # A remoção do original referencia o original_hash e não tem dest_path.
        removal = [l for l in logs if l.dest_path is None]
        assert len(removal) == 1
        assert removal[0].content_hash == original_hash
        assert removal[0].source_path == str(src)


def test_opt_in_off_comportamento_atual(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    """split_to_files=False (default) → nada gravado na pasta, original intacto."""
    folder = tmp_path / "hot"
    folder.mkdir()
    src = _make_pdf(folder / "doc.pdf", pages=5)
    original_bytes = src.read_bytes()

    result = _ingest(
        schema_engine, src, folder_id=1, pages_per_block=2, split_to_files=False
    )
    assert result.status == "ingested"

    # O original PERMANECE intacto; NENHUM arquivo novo na pasta.
    assert src.exists()
    assert src.read_bytes() == original_bytes
    pdfs = sorted(p.name for p in folder.glob("*.pdf"))
    assert pdfs == ["doc.pdf"], f"opt-in OFF não pode gravar blocos na pasta: {pdfs}"

    # Os Documents/blocos continuam sendo criados como hoje (3 blocos = ceil(5/2)).
    with get_session(schema_engine) as session:
        docs = session.scalars(select(Document)).all()
        assert len(docs) == 3
        # Sem AuditLog (nenhuma materialização-na-pasta aconteceu).
        assert session.scalars(select(AuditLog)).all() == []
        # Sem linhas de gate extras (só o original; nenhum bloco registrado no gate).
        gates = session.scalars(select(IngestedOriginal)).all()
        assert len(gates) == 1


def test_opt_in_off_default_sem_argumento(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    """O parâmetro split_to_files tem default False — callers atuais ficam intactos."""
    folder = tmp_path / "hot"
    folder.mkdir()
    src = _make_pdf(folder / "doc.pdf", pages=4)
    original_hash = sha256_file(src)

    # Chamada SEM passar split_to_files (assinatura atual dos callers/testes).
    with get_session(schema_engine) as session:
        result = ingest_stage.process_ingest(
            session,
            source_path=src,
            folder_id=1,
            pages_per_block=2,
            original_hash=original_hash,
        )
    assert result.status == "ingested"
    assert src.exists()  # original intacto por default
    assert sorted(p.name for p in folder.glob("*.pdf")) == ["doc.pdf"]


def test_idempotencia_crash_safety(
    schema_engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    """Rodar process_ingest 2x não duplica arquivos nem perde o original."""
    folder = tmp_path / "hot"
    folder.mkdir()
    src = _make_pdf(folder / "doc.pdf", pages=5)

    _ingest(schema_engine, src, folder_id=1, pages_per_block=2, split_to_files=True)
    blocos_1 = sorted(p.name for p in folder.glob("*.pdf"))
    assert len(blocos_1) == 3

    # 2ª execução: o original já não está na pasta; re-rodar o MESMO original cai no
    # gate de duplicata (passo 2) e é no-op — nada é re-separado/re-gravado.
    original_hash = sha256_file_for_recover(schema_engine)
    with get_session(schema_engine) as session:
        result2 = ingest_stage.process_ingest(
            session,
            source_path=src,  # não existe mais no disco, mas o gate barra antes
            folder_id=1,
            pages_per_block=2,
            original_hash=original_hash,
            split_to_files=True,
        )
    assert result2.status == "duplicate"

    # Os arquivos na pasta não mudaram (sem duplicação).
    blocos_2 = sorted(p.name for p in folder.glob("*.pdf"))
    assert blocos_2 == blocos_1

    # O original continua recuperável do CAS (nunca perde).
    assert cas.exists(original_hash)


def sha256_file_for_recover(engine: Engine) -> str:
    """Recupera o original_hash da única linha-original (block_count>0) do gate."""
    with get_session(engine) as session:
        orig = session.scalar(
            select(IngestedOriginal).where(IngestedOriginal.block_count > 0)
        )
        assert orig is not None
        return orig.original_hash

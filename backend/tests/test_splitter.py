"""Testes do separador de PDF em blocos (pikepdf) e da allowlist de extensão.

Cobre o contrato de `app.ingest.splitter` (ING-04 / ING-05 / D-05/D-06/D-07):
- split_pdf gera ceil(M/N) blocos com a contagem de páginas correta por bloco;
- "não separar" (pages_per_block None ou 0) → 1 bloco com o PDF inteiro;
- cada bloco é um PDF válido reabrível por pikepdf;
- PDF malformado levanta exceção controlada (o worker do Plano 03 roteia p/ retry);
- is_supported_ext aceita PDF/JPG/JPEG/PNG (case-insensitive) e rejeita o resto.

Fixtures de PDF são geradas em runtime (nenhum binário commitado em tests/).
"""

import io
from pathlib import Path

import pikepdf
import pytest

from app.ingest.splitter import SUPPORTED_EXTENSIONS, is_supported_ext, split_pdf


def _make_pdf(tmp_path: Path, n_pages: int, name: str = "doc.pdf") -> Path:
    """Cria um PDF de `n_pages` páginas em branco em `tmp_path` e retorna o path."""
    pdf = pikepdf.Pdf.new()
    for _ in range(n_pages):
        pdf.add_blank_page(page_size=(200, 200))
    out = tmp_path / name
    pdf.save(out)
    pdf.close()
    return out


def _page_counts(blocks: list[bytes]) -> list[int]:
    """Reabre cada bloco com pikepdf e devolve a contagem de páginas de cada um."""
    counts = []
    for data in blocks:
        with pikepdf.Pdf.open(io.BytesIO(data)) as p:
            counts.append(len(p.pages))
    return counts


def test_split_uma_pagina_por_bloco(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path, 10)
    blocks = split_pdf(src, pages_per_block=1)
    assert len(blocks) == 10
    assert _page_counts(blocks) == [1] * 10


def test_split_tres_paginas_por_bloco_ceil(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path, 10)
    blocks = split_pdf(src, pages_per_block=3)
    # ceil(10/3) == 4 blocos com [3, 3, 3, 1]
    assert len(blocks) == 4
    assert _page_counts(blocks) == [3, 3, 3, 1]


def test_no_split(tmp_path: Path) -> None:
    # pages_per_block=None → "não separar" (D-05 default): 1 bloco com tudo.
    src = _make_pdf(tmp_path, 10)
    blocks = split_pdf(src, pages_per_block=None)
    assert len(blocks) == 1
    assert _page_counts(blocks) == [10]


def test_no_split_com_zero(tmp_path: Path) -> None:
    # pages_per_block=0 tratado igual a "não separar".
    src = _make_pdf(tmp_path, 7)
    blocks = split_pdf(src, pages_per_block=0)
    assert len(blocks) == 1
    assert _page_counts(blocks) == [7]


def test_blocos_sao_pdfs_validos(tmp_path: Path) -> None:
    src = _make_pdf(tmp_path, 5)
    blocks = split_pdf(src, pages_per_block=2)
    # Cada bloco deve reabrir sem erro (PDF válido) — já coberto por _page_counts,
    # mas asseguramos explicitamente que nenhum bloco está vazio/corrompido.
    assert all(len(b) > 0 for b in blocks)
    assert _page_counts(blocks) == [2, 2, 1]


def test_pdf_malformado_levanta_excecao_controlada(tmp_path: Path) -> None:
    bad = tmp_path / "ruim.pdf"
    bad.write_bytes(b"isto nao e um PDF valido")
    # T-02-04: split sobre PDF malformado levanta exceção (não trava o processo);
    # o worker do Plano 03 a converte em retry/FALHA.
    with pytest.raises(Exception):
        split_pdf(bad, pages_per_block=1)


def test_is_supported_ext_aceita_e_rejeita() -> None:
    assert is_supported_ext(Path("a.pdf")) is True
    assert is_supported_ext(Path("a.PDF")) is True
    assert is_supported_ext(Path("foto.PNG")) is True
    assert is_supported_ext(Path("scan.jpeg")) is True
    assert is_supported_ext(Path("scan.JPG")) is True
    assert is_supported_ext(Path("nota.txt")) is False
    assert is_supported_ext(Path("planilha.docx")) is False
    assert is_supported_ext(Path("sem_extensao")) is False


def test_supported_extensions_set() -> None:
    assert SUPPORTED_EXTENSIONS == {".pdf", ".jpg", ".jpeg", ".png"}

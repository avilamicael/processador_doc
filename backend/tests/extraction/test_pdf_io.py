"""Testes do `pdf_io` (Fase 3) — texto nativo, heurística, render, magic bytes.

Exercita as primitivas PyMuPDF puras (sem DB nem HTTP) com as fixtures sintéticas
de `conftest.py`:
- `detect_blob_type`: distingue pdf/jpeg/png por magic bytes (CAS guarda só o
  hash, sem extensão — Pitfall 5 / Open Question 2).
- `extract_text_and_decide`: heurística texto-vs-visão (EXT-01/D-04).
- `render_pages_png`: 1 PNG por página; imagem nunca aberta como PDF.
"""

import fitz  # PyMuPDF
import pytest

from app.extraction import pdf_io

# --- detect_blob_type (magic bytes) ---


def test_detect_blob_type_pdf(text_pdf_bytes: bytes) -> None:
    assert pdf_io.detect_blob_type(text_pdf_bytes) == "pdf"


def test_detect_blob_type_jpeg(jpeg_bytes: bytes) -> None:
    assert pdf_io.detect_blob_type(jpeg_bytes) == "jpeg"


def test_detect_blob_type_png(png_bytes: bytes) -> None:
    assert pdf_io.detect_blob_type(png_bytes) == "png"


def test_detect_blob_type_unknown_raises() -> None:
    with pytest.raises(ValueError):
        pdf_io.detect_blob_type(b"isto nao e um documento")


def test_detect_blob_type_empty_raises() -> None:
    with pytest.raises(ValueError):
        pdf_io.detect_blob_type(b"")


# --- extract_text_and_decide (heurística texto-vs-visão) ---


def test_extract_text_and_decide_native_text(text_pdf_bytes: bytes) -> None:
    text, route = pdf_io.extract_text_and_decide(text_pdf_bytes, min_chars_per_page=16)
    assert route == "native_text"
    assert "12345" in text  # texto nativo realmente lido


def test_extract_text_and_decide_scanned_is_vision(scanned_pdf_bytes: bytes) -> None:
    text, route = pdf_io.extract_text_and_decide(
        scanned_pdf_bytes, min_chars_per_page=16
    )
    assert route == "vision"
    assert len(text.strip()) < 16  # quase nenhum texto extraível


def test_extract_text_and_decide_threshold_forces_vision(
    text_pdf_bytes: bytes,
) -> None:
    # Limiar absurdamente alto → mesmo um PDF com texto cai no caminho visão.
    _text, route = pdf_io.extract_text_and_decide(
        text_pdf_bytes, min_chars_per_page=10_000
    )
    assert route == "vision"


def test_extract_text_and_decide_malformed_raises() -> None:
    # PDF inválido levanta exceção controlada do fitz (T-03-06) — o stage a
    # transforma em FALHA, não derruba o worker.
    with pytest.raises(fitz.FileDataError):
        pdf_io.extract_text_and_decide(b"%PDF-quebrado", min_chars_per_page=16)


# --- render_pages_png ---


def test_render_pages_png_one_per_page(text_pdf_bytes: bytes) -> None:
    pngs = pdf_io.render_pages_png(text_pdf_bytes)
    assert len(pngs) == 1
    assert pdf_io.detect_blob_type(pngs[0]) == "png"  # cada item é um PNG válido


def test_render_pages_png_multipage() -> None:
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.new_page()
    data = doc.tobytes()
    doc.close()

    pngs = pdf_io.render_pages_png(data)
    assert len(pngs) == 3
    assert all(pdf_io.detect_blob_type(p) == "png" for p in pngs)

"""Testes do `router.choose` (Fase 3) — seam de extração D-03.

`choose(blob)` decide a rota a partir do conteúdo (via `pdf_io`), sem embutir
lógica de OpenAI nem de DB:
- PDF com texto nativo → "native_text"
- PDF escaneado (sem texto) → "vision"
- imagem (jpeg/png) → "vision" (a imagem já é a página; nunca aberta como PDF)
"""

import pytest

from app.extraction import router


def test_choose_pdf_com_texto_e_native_text(text_pdf_bytes: bytes) -> None:
    assert router.choose(text_pdf_bytes) == "native_text"


def test_choose_pdf_escaneado_e_vision(scanned_pdf_bytes: bytes) -> None:
    assert router.choose(scanned_pdf_bytes) == "vision"


def test_choose_jpeg_e_vision(jpeg_bytes: bytes) -> None:
    assert router.choose(jpeg_bytes) == "vision"


def test_choose_png_e_vision(png_bytes: bytes) -> None:
    assert router.choose(png_bytes) == "vision"


def test_choose_blob_desconhecido_levanta(monkeypatch: pytest.MonkeyPatch) -> None:
    # Blob que não é PDF/imagem → ValueError de detect_blob_type, não um chute.
    with pytest.raises(ValueError):
        router.choose(b"isto nao e um documento")


def test_choose_e_documentado_como_seam_d03() -> None:
    # O seam D-03 deve estar documentado no docstring (Fases 4/7 estendem aqui).
    assert "D-03" in (router.choose.__doc__ or "")

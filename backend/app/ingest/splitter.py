"""Separador de PDF em blocos de N páginas + allowlist de extensão (ING-04/ING-05).

`split_pdf` quebra um PDF de M páginas em `ceil(M/N)` novos PDFs de no máximo N
páginas cada — cada bloco vira um documento independente downstream (D-05/D-06).
A regra "não separar" (default sugerido — D-05) é `pages_per_block=None` (ou `0`):
gera um único bloco com o PDF inteiro. Imagens (JPG/PNG) nunca passam por aqui —
são sempre 1 documento (D-07).

Robustez (T-02-04): a abertura/parse é envolta em try/except e *re-levanta* uma
exceção controlada. pikepdf (qpdf) é resistente a PDFs malformados, mas um arquivo
realmente corrompido deve falhar de forma previsível para o worker do Plano 03
roteá-lo a retry/FALHA — nunca derrubar o processo.

`is_supported_ext` / `SUPPORTED_EXTENSIONS` materializam a allowlist de formatos de
entrada (ING-04). O consumo (ignorar silenciosamente o resto) é no Plano 03.

Nota de licença: usamos **pikepdf** (MPL-2.0, permissiva) para split — não PyMuPDF
(AGPL-3.0), evitando a implicação de licença comercial num produto vendido.

Utilidade pura: sem HTTP, sem DB. CPU/IO-bound — o worker a despacha via
`asyncio.to_thread` para não bloquear o event loop.
"""

import io
from pathlib import Path

import pikepdf

# Allowlist de formatos de entrada aceitos na ingestão (ING-04). Comparada sempre
# em minúsculas (`Path.suffix.lower()`), então só letras minúsculas aqui.
SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".jpg", ".jpeg", ".png"}


def is_supported_ext(path: Path) -> bool:
    """True se a extensão de `path` está na allowlist (case-insensitive)."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def split_pdf(src_path: Path, pages_per_block: int | None) -> list[bytes]:
    """Separa `src_path` em blocos de até `pages_per_block` páginas.

    Args:
        src_path: PDF de origem (não é modificado — só leitura).
        pages_per_block: páginas por bloco. `None` ou `0` significa "não separar"
            (D-05 default) → 1 bloco com todas as páginas.

    Returns:
        Lista de blocos, cada um os bytes de um PDF válido. `ceil(M/N)` blocos;
        o último pode ter menos páginas.

    Raises:
        Exception: se `src_path` não for um PDF abrível (T-02-04) — o chamador
            (worker, Plano 03) roteia para retry/FALHA. A mensagem inclui o nome
            do arquivo para diagnóstico.
    """
    blocks: list[bytes] = []
    try:
        with pikepdf.Pdf.open(src_path) as src:
            n = len(src.pages)
            # None/0 → "não separar": um único bloco com todas as páginas (D-05).
            step = n if not pages_per_block else pages_per_block
            # PDF sem páginas: nada a extrair → zero blocos (degenerado, mas seguro).
            for start in range(0, n, step):
                dst = pikepdf.Pdf.new()
                dst.pages.extend(src.pages[start : start + step])
                buf = io.BytesIO()
                dst.save(buf)
                dst.close()
                blocks.append(buf.getvalue())
    except pikepdf.PdfError as exc:
        # Re-levanta como exceção controlada com contexto do arquivo. O worker do
        # Plano 03 captura e roteia para retry/FALHA sem derrubar o processo.
        raise ValueError(f"PDF inválido ou corrompido: {src_path.name}") from exc
    return blocks

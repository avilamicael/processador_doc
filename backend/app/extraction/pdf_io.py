"""Primitivas PyMuPDF da extração (Fase 3) — texto nativo, heurística, render.

Módulo de funções PURAS (estilo `cas.py`/`repo.py`, sem classe): recebem `bytes`
e devolvem dados, sem tocar DB nem HTTP. O `extract_stage` (Plan 03) as envolve em
`asyncio.to_thread` de dentro do worker async — aqui são SÍNCRONAS (CPU-bound).

Responsabilidades:
- `detect_blob_type`: distingue PDF de imagem por MAGIC BYTES (Pitfall 5 /
  Open Question 2). A Fase 2 ingere imagem como bloco de bytes crus e o CAS guarda
  só o hash, SEM extensão (`cas.py`) — então o tipo precisa vir do conteúdo.
  `fitz.open(filetype="pdf")` falha numa imagem, por isso imagem nunca é aberta
  como PDF: vai direto ao caminho visão (a imagem já é a página).
- `extract_text_and_decide`: lê o texto nativo de TODAS as páginas e decide o
  caminho texto-vs-visão (EXT-01/D-04) — sem custo de IA na leitura.
- `render_pages_png`: renderiza cada página → PNG (uma imagem por página) para o
  caminho visão (`input_image` da Responses API).

Import obrigatório: `import fitz` (NÃO `import pymupdf`).
"""

import fitz  # PyMuPDF

# Magic bytes dos formatos suportados (allowlist de ingestão da Fase 2: PDF + imagem).
_PDF_MAGIC = b"%PDF-"
_JPEG_MAGIC = b"\xff\xd8"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def detect_blob_type(blob: bytes) -> str:
    """Identifica o tipo de um blob por magic bytes: "pdf" | "jpeg" | "png".

    O CAS guarda só o hash do conteúdo, sem extensão (D-08), então o roteador
    descobre o tipo pelo conteúdo, não pelo nome. Resolve Pitfall 5: imagem
    (jpeg/png) NÃO deve ser aberta como PDF — vai direto ao caminho visão.

    Levanta `ValueError` para conteúdo desconhecido (não é nenhum dos formatos
    da allowlist) — o stage (Plan 03) transforma isso em FALHA controlada.
    """
    if blob.startswith(_PDF_MAGIC):
        return "pdf"
    if blob.startswith(_JPEG_MAGIC):
        return "jpeg"
    if blob.startswith(_PNG_MAGIC):
        return "png"
    raise ValueError("tipo de blob desconhecido (não é PDF/JPEG/PNG por magic bytes)")


def extract_text_and_decide(pdf_bytes: bytes, min_chars_per_page: int) -> tuple[str, str]:
    """Lê o texto nativo do PDF e decide o caminho texto-vs-visão (EXT-01/D-04).

    Soma os caracteres extraíveis (`page.get_text()`) de TODAS as páginas e devolve
    `(texto_concatenado, rota)`:
    - `"native_text"` se `total >= min_chars_per_page * page_count` (há texto
      suficiente → caminho barato, sem visão);
    - `"vision"` caso contrário (PDF escaneado / só imagem → render página→imagem).

    `pdf_bytes` deve ser um PDF (detectado a montante por `detect_blob_type`). Um
    PDF malformado levanta exceção do fitz (T-03-06), tratada como FALHA pelo stage.
    """
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        texts = [page.get_text() for page in doc]
        page_count = doc.page_count
    total = sum(len(t.strip()) for t in texts)
    route = "native_text" if total >= min_chars_per_page * page_count else "vision"
    return "\n".join(texts), route


def render_pages_png(pdf_bytes: bytes) -> list[bytes]:
    """Renderiza cada página do PDF para PNG (uma imagem por página).

    Devolve a lista de bytes PNG (todas as páginas do bloco) para o caminho visão
    — cada imagem vira um bloco `input_image` na chamada à Responses API. Uma só
    chamada por bloco envia todas as páginas (AI-SPEC §3/§4).
    """
    pngs: list[bytes] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap()
            pngs.append(pix.tobytes("png"))
    return pngs

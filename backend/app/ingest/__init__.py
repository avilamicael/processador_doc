"""Pacote de ingestão — utilidades puras de filesystem/PDF da Fase 2.

Expõe as utilidades isoláveis (sem HTTP, sem DB) usadas pelo worker/ingest_stage
(Plano 03) e pelo watcher (Plano 04):
- `stabilizer.wait_stable`: decide quando um arquivo da pasta monitorada parou de
  ser escrito (quiescência size/mtime + lock-test Windows — Pitfall 1 / ING-02);
- `splitter.split_pdf`: quebra um PDF em blocos de N páginas via pikepdf (ING-05);
- `splitter.is_supported_ext` / `SUPPORTED_EXTENSIONS`: allowlist de formatos de
  entrada PDF/JPG/PNG (ING-04).
"""

from app.ingest.splitter import SUPPORTED_EXTENSIONS, is_supported_ext, split_pdf
from app.ingest.stabilizer import wait_stable

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "is_supported_ext",
    "split_pdf",
    "wait_stable",
]

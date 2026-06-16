"""Hash de arquivo por SHA-256 (streaming) — identidade do original (D-09).

O gate de dedup (`ingested_originals.original_hash`) e a fila (`jobs.original_hash`)
identificam um arquivo de entrada pelo SHA-256 do seu CONTEÚDO. O watcher (Plano 04)
calcula esse hash após a estabilização e o carrega no job; o `cas.store` produz o
MESMO valor ao copiar o original (mesmo algoritmo, mesmo conteúdo) — então o hash
do gate e o do CAS coincidem por construção.

Streaming em chunks (não carrega o arquivo inteiro em memória) — alinhado ao CAS.
Utilidade pura da stdlib (`hashlib`): roda em Windows sem infra adicional (DIST-01).
"""

import hashlib
from pathlib import Path

# Mesmo tamanho de chunk do CAS (64 KiB) — leitura por streaming.
_CHUNK_SIZE = 64 * 1024


def sha256_file(path: Path) -> str:
    """Retorna o SHA-256 hex do conteúdo de `path`, lido em chunks."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()

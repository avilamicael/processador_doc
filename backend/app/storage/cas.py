"""CAS — Content-Addressable Storage por hash SHA-256 (fronteira única).

Armazena os arquivos ingeridos de forma IMUTÁVEL e endereçada pelo hash SHA-256
do seu conteúdo, dentro da pasta de dados única (`data_dir/cas`). A ingestão
COPIA o original (preservando o arquivo de origem — D-07); o conteúdo é
recuperável pelo hash a qualquer momento (rede de segurança/undo — D-08); e o
mesmo conteúdo nunca é duplicado (idempotência por conteúdo).

Garantias e decisões materializadas:
- D-01: o CAS vive dentro da pasta de dados única (junto ao banco) — "backup =
  copiar uma pasta só".
- D-07: `store` COPIA o arquivo de entrada; o original na pasta de origem nunca é
  aberto em escrita, modificado ou removido por este módulo.
- D-08: blobs são mantidos para sempre no v1 — NÃO há API de delete/update aqui.
- DIST-01: usa apenas a stdlib (`hashlib`, `pathlib`, `os`) — roda em Windows sem
  infra adicional; `os.replace` dá rename atômico portável (Windows/POSIX).

Pitfalls tratados:
- Performance: hashing e cópia por streaming em chunks (não carrega o arquivo
  inteiro em memória).
- Atomicidade: grava num temporário no mesmo diretório do destino e faz
  `os.replace` para o caminho final — nunca expõe um blob meio-escrito.

Interface pública: `store`, `path_for`, `exists`, `read_bytes`, `open_blob`.
"""

import hashlib
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from app.config import get_settings

# Tamanho do chunk de leitura para hashing/cópia por streaming (64 KiB).
_CHUNK_SIZE = 64 * 1024

# Nome da subpasta do CAS dentro da pasta de dados única (D-01).
_CAS_DIRNAME = "cas"


def cas_root() -> Path:
    """Raiz do CAS, derivada da pasta de dados única (`data_dir/cas` — D-01)."""
    return get_settings().data_dir / _CAS_DIRNAME


def path_for(content_hash: str) -> Path:
    """Caminho do blob para um hash, com sharding por prefixo.

    Distribui os blobs em subpastas (`<root>/ab/cd/<hash>`) para evitar diretórios
    com milhares de arquivos no mesmo nível (degradação em NTFS/ext4).
    """
    root = cas_root()
    return root / content_hash[:2] / content_hash[2:4] / content_hash


def exists(content_hash: str) -> bool:
    """True se já existe um blob armazenado para o hash dado."""
    return path_for(content_hash).is_file()


def store(src: Path) -> str:
    """Copia `src` para o CAS e retorna o SHA-256 hex do seu conteúdo.

    Lê `src` em chunks calculando o SHA-256 e, simultaneamente, escreve a cópia
    num arquivo temporário no diretório do destino. Ao final:
    - se já existe um blob para o hash (mesmo conteúdo), descarta o temporário
      (idempotência — não reescreve blob imutável — D-08);
    - senão, faz `os.replace(tmp, final)` (rename atômico portável).

    O arquivo de ORIGEM nunca é modificado nem removido (cópia, não move — D-07).
    """
    src = Path(src)

    hasher = hashlib.sha256()
    # Diretório temporário inicial: a raiz do CAS (mesmo volume do destino final,
    # garantindo que o os.replace posterior seja um rename atômico, não um copy).
    root = cas_root()
    root.mkdir(parents=True, exist_ok=True)
    tmp_path = root / f".{uuid.uuid4().hex}.tmp"

    try:
        with src.open("rb") as fin, tmp_path.open("wb") as fout:
            while chunk := fin.read(_CHUNK_SIZE):
                hasher.update(chunk)
                fout.write(chunk)

        content_hash = hasher.hexdigest()
        final_path = path_for(content_hash)

        if final_path.is_file():
            # Mesmo conteúdo já armazenado: descarta o temporário (idempotência).
            tmp_path.unlink(missing_ok=True)
            return content_hash

        final_path.parent.mkdir(parents=True, exist_ok=True)
        # Move o temporário para o diretório de shard final antes do replace, de
        # modo que tmp e destino fiquem no mesmo diretório (rename atômico local).
        staged_tmp = final_path.parent / tmp_path.name
        os.replace(tmp_path, staged_tmp)
        tmp_path = staged_tmp
        os.replace(tmp_path, final_path)
        return content_hash
    finally:
        # Limpa qualquer temporário remanescente (ex.: exceção no meio da cópia).
        if tmp_path.exists() and tmp_path.name.endswith(".tmp"):
            tmp_path.unlink(missing_ok=True)


def read_bytes(content_hash: str) -> bytes:
    """Retorna o conteúdo completo do blob como bytes."""
    return path_for(content_hash).read_bytes()


@contextmanager
def open_blob(content_hash: str) -> Iterator[BinaryIO]:
    """Abre o blob para leitura binária (streaming), fechando ao final."""
    fh = path_for(content_hash).open("rb")
    try:
        yield fh
    finally:
        fh.close()

"""Operação física de arquivo atômica e segura (AUT-04/AUT-06, D-09/D-10).

Molde: `app/storage/cas.py` (`store`: temp no MESMO diretório do destino +
`os.replace` atômico; hashing por streaming em chunks; limpeza defensiva que
JAMAIS remove o arquivo final). Esta camada nunca pode causar perda de um
documento do cliente (CLAUDE.md): a verificação de integridade por hash + a
preservação da origem até o destino estar íntegro + o CAS como rede final
(undo) fecham AUT-04/05/06.

Garantias materializadas:
- AUT-04: NUNCA sobrescreve um destino preexistente — a anti-colisão é resolvida
  A MONTANTE (`resolve_collision`) e a escrita ocorre só num caminho livre.
- D-09: colisão de NOME com conteúdo DIFERENTE → sufixo incremental `_1`/`_2`
  (ambos os arquivos sobrevivem).
- D-10: colisão de NOME com conteúdo IDÊNTICO (mesmo SHA-256) → pula (skip),
  não duplica.
- AUT-06: cross-device (EXDEV) materializa via copy→fsync→verifica-hash antes de
  considerar feito; hash divergente → ABORTA, remove o temporário, NÃO cria/
  corrompe o destino e NÃO remove a origem (a origem é a garantia até o destino
  estar íntegro).
- AUT-06 crit 5 ("copia, verifica, só então remove a origem"): após a verificação
  do destino passar, a ORIGEM é removida (move, não cópia); se a verificação
  falhar, a origem é preservada.

NOTA DE DIVERGÊNCIA (registrada em SUMMARY): os testes RED da Wave 0
(`test_fileops.py`) fixam a interface real desta camada — `safe_move(src, dst)`,
`resolve_collision(dst, src)` e `hash_file(path)`. O PLAN descrevia nomes
alternativos (`materialize_to_dest`/`remove_original`/`cas.read_bytes`) sob a
política D-11 (materializar do CAS). Os testes são a fonte de verdade (RED→GREEN):
implementamos `safe_move`/`resolve_collision`/`hash_file`. Para preservar a intenção
do PLAN e seus critérios de aceite, expomos também `materialize_to_dest`
(escreve do CAS para o destino, D-11) e `remove_original` (AUT-06 crit 5) como
fachadas finas sobre a mesma máquina segura, ligadas ao CAS (`cas.read_bytes`).

Logging: só metadados (paths/ids) — NUNCA conteúdo do documento (V7/V9, LGPD).
"""

import errno
import hashlib
import os
import uuid
from pathlib import Path

from app.storage import cas

# Mesmo tamanho de chunk do CAS/ingest (64 KiB) — leitura por streaming.
_CHUNK_SIZE = 64 * 1024

# Teto de tentativas de sufixo anti-colisão (D-09) — defesa contra laço infinito.
_MAX_COLLISION_SUFFIX = 10_000


class IntegrityError(Exception):
    """Hash do destino divergiu do esperado pós-escrita (AUT-06).

    Sinaliza que a materialização do conteúdo NÃO pode ser considerada feita: o
    chamador (apply_stage/worker) trata como FALHA retryável e a origem é
    PRESERVADA (nunca remover a origem com o destino corrompido).
    """


def _inline_sha256(path: Path) -> str:
    """SHA-256 hex do conteúdo de `path` (streaming), independente de `hash_file`.

    Usado para computar a identidade ESPERADA do conteúdo de origem. Mantê-lo
    separado de `hash_file` (o ponto de verificação do destino) garante que a
    verificação de integridade detecte um destino corrompido mesmo se `hash_file`
    estiver instrumentado/monkeypatchado (AUT-06).
    """
    hasher = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_file(path: Path) -> str:
    """Retorna o SHA-256 hex do conteúdo de `path`, lido em chunks (streaming).

    Mesmo algoritmo do CAS e de `ingest/hashing.py` — o hash do destino coincide
    por construção com o `content_hash` do bloco. Ponto único de verificação de
    integridade (monkeypatchável nos testes).
    """
    hasher = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def resolve_collision(dst: Path, src: Path) -> Path | None:
    """Resolve a colisão de NOME no destino ANTES de qualquer escrita (D-09/D-10).

    - destino livre → devolve `dst` (escreve direto);
    - destino ocupado por conteúdo IDÊNTICO (mesmo SHA-256 do `src`) → `None`
      (D-10: pula, não duplica — operação já-feita);
    - destino ocupado por conteúdo DIFERENTE → procura `{stem}_1{suffix}`,
      `{stem}_2{suffix}`, … até achar um caminho livre OU um cujo conteúdo já
      seja idêntico ao `src` (então também `None`, D-10). (D-09: ambos sobrevivem.)

    NUNCA decide sobrescrever: `os.replace` sobrescreve por design, então a defesa
    é a montante — `safe_move` só escreve num caminho que esta função liberou.
    """
    dst = Path(dst)
    if not dst.exists():
        return dst

    src_hash = hash_file(src)
    if hash_file(dst) == src_hash:
        return None  # D-10: idêntico, pula

    stem = dst.stem
    suffix = dst.suffix
    parent = dst.parent
    for i in range(1, _MAX_COLLISION_SUFFIX + 1):
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        if hash_file(candidate) == src_hash:
            return None  # já existe um irmão idêntico (D-10)
    # Esgotou o teto de sufixos — caso patológico; trata como falha controlada.
    raise OSError(f"sem caminho livre para anti-colisão em {parent}")


def _verified_write(content_iter, dst: Path, expected_hash: str) -> Path:
    """Escreve `content_iter` (chunks) num tmp no dir do `dst`, verifica e replace.

    Padrão do CAS (cas.py:88-122): grava num temporário no MESMO diretório do
    destino, faz `fsync`, recomputa o SHA-256 do temporário e compara com
    `expected_hash`. Hash igual → `os.replace(tmp, dst)` (rename atômico
    same-volume). Hash divergente → remove o tmp e levanta `IntegrityError`,
    SEM criar/corromper o `dst`. O `finally` limpa só o tmp desta chamada —
    JAMAIS o destino final (defesa contra perda).
    """
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cleanup_target: Path | None = dst.parent / f".{uuid.uuid4().hex}.tmp"
    try:
        with cleanup_target.open("wb") as fout:
            for chunk in content_iter:
                fout.write(chunk)
            fout.flush()
            os.fsync(fout.fileno())

        # Verificação de integridade pós-escrita (AUT-06) — ponto único `hash_file`.
        if hash_file(cleanup_target) != expected_hash:
            cleanup_target.unlink(missing_ok=True)
            cleanup_target = None
            raise IntegrityError(
                "hash do destino divergiu do esperado — abortado sem corromper"
            )

        try:
            os.replace(cleanup_target, dst)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            # Cross-device (AUT-06): rename atômico não cruza volumes. O temporário
            # JÁ está verificado (hash conferido acima); copiamos seu conteúdo para
            # o destino e re-verificamos o destino antes de considerar feito. O tmp
            # já está no MESMO dir do destino (mesmo volume), então este copy é
            # local — o EXDEV simulado/real é só no caminho final.
            with cleanup_target.open("rb") as fin, dst.open("wb") as fout:
                while chunk := fin.read(_CHUNK_SIZE):
                    fout.write(chunk)
                fout.flush()
                os.fsync(fout.fileno())
            if hash_file(dst) != expected_hash:
                # Destino corrompido na cópia cross-device → remove e aborta.
                dst.unlink(missing_ok=True)
                raise IntegrityError(
                    "hash do destino (cross-device) divergiu — abortado"
                ) from exc
            cleanup_target.unlink(missing_ok=True)
        # tmp consumido (replace) ou copiado+removido (EXDEV): nada mais a limpar; o
        # destino final NUNCA é candidato a remoção.
        cleanup_target = None
        return dst
    finally:
        if cleanup_target is not None and cleanup_target.exists():
            cleanup_target.unlink(missing_ok=True)


def _stream_file(path: Path):
    """Gera os bytes de `path` em chunks (streaming, não carrega em memória)."""
    with Path(path).open("rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            yield chunk


def remove_original(source_path: Path) -> None:
    """Remove o arquivo original da pasta de origem (AUT-06 crit 5).

    Chamado SOMENTE após o destino ter sido materializado E verificado por hash
    (a verificação acontece dentro de `safe_move`/`_verified_write`). `missing_ok`
    cobre a idempotência (já removido). NUNCA remove nada do CAS.
    """
    Path(source_path).unlink(missing_ok=True)


def safe_move(src: Path, dst: Path) -> Path:
    """Move `src` para `dst` com segurança total (AUT-04/AUT-06, D-09/D-10).

    Sequência (copia→verifica→remove a origem, AUT-06 crit 5):
    1. resolve a colisão a MONTANTE (`resolve_collision`): destino livre → `dst`;
       conteúdo idêntico (mesmo SHA) → SKIP (D-10, devolve o caminho idêntico
       existente e NÃO remove a origem — operação já-feita); diferente → sufixo
       `_1`/`_2` (D-09);
    2. escreve o conteúdo do `src` num temporário no dir do destino, verifica o
       SHA-256 (AUT-06) e faz `os.replace` (same-volume) OU, se o replace falhar
       com EXDEV (cross-device), a escrita já É a cópia verificada — o mesmo
       caminho de código cobre ambos os volumes (D-11: materialização verificada);
    3. hash divergente → `IntegrityError`, destino não criado/corrompido, ORIGEM
       PRESERVADA;
    4. sucesso → remove a origem (move, não cópia).

    Erros de disco (`PermissionError`/`OSError` ≠ EXDEV, ex.: WinError 32 lock no
    Windows) propagam SEM captura — o worker (Plan 04) os roteia como FALHA
    retryável. NÃO loga conteúdo.

    Retorna o caminho final efetivo do arquivo.
    """
    src = Path(src)
    # Hash ESPERADO computado de forma independente do ponto de verificação
    # (`hash_file`): o `expected_hash` é a identidade real do conteúdo de origem,
    # enquanto `_verified_write` confere o DESTINO via `hash_file`. Se a verificação
    # do destino divergir do conteúdo real (corrupção/cross-device falho), aborta —
    # mesmo que `hash_file` esteja instrumentado. (AUT-06 / teste integrity.)
    expected_hash = _inline_sha256(src)

    resolved = resolve_collision(dst, src)
    if resolved is None:
        # D-10: destino já contém conteúdo idêntico — operação já-feita. NÃO
        # remove a origem aqui (decisão do caller); devolve o caminho existente.
        return Path(dst)

    final = _verified_write(_stream_file(src), resolved, expected_hash)

    # Verificação passou (dentro de _verified_write) → remove a origem (AUT-06).
    remove_original(src)
    return final


def materialize_to_dest(content_hash: str, dst: Path) -> Path:
    """Materializa o conteúdo do CAS para `dst` e verifica o hash (D-11/AUT-06).

    Lê o blob imutável do CAS (`cas.read_bytes(content_hash)` — rede de verdade) e
    o escreve no destino com a MESMA máquina verificada de `safe_move`
    (`_verified_write`): tmp no dir do destino → fsync → confere SHA-256 ==
    `content_hash` → `os.replace`. Hash divergente → `IntegrityError`, destino não
    corrompido. Como o destino é uma CÓPIA do CAS, cross-device deixa de ser caso
    especial: a verificação de hash É a salvaguarda. NÃO move/destrói o original na
    pasta de origem (isso é responsabilidade de `remove_original`, chamado pelo
    apply_stage SOMENTE após esta função retornar sem erro). NÃO loga conteúdo.

    Devolve o caminho final efetivo.
    """
    blob = cas.read_bytes(content_hash)
    return _verified_write([blob], Path(dst), content_hash)

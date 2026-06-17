"""RED (Wave 0) — operação física de arquivo atômica e segura (AUT-04/06, D-09/10).

Alvo: `app.automation.fileops` (a criar; molde `storage/cas.py`). Cobre:
- nunca sobrescreve um destino existente (no_overwrite, AUT-04);
- colisão com conteúdo DIFERENTE → sufixo `_1`/`_2`, ambos sobrevivem (D-09);
- colisão com conteúdo IDÊNTICO (mesmo SHA) → pula, não duplica (D-10);
- materialização cross-device (EXDEV) com verificação de hash (AUT-06);
- hash divergente pós-cópia → aborta, NÃO remove a origem (integridade, AUT-06);
- após apply bem-sucedido a origem é removida (move, não cópia) — original_removed_after_apply.

`importorskip` evita ImportError fatal na coleta enquanto `fileops` não existe.
"""

from pathlib import Path

import pytest

fileops = pytest.importorskip("app.automation.fileops")


def _write(p: Path, data: bytes) -> Path:
    p.write_bytes(data)
    return p


def test_no_overwrite(src_dir: Path, dst_dir: Path) -> None:
    """AUT-04: safe_move NUNCA sobrescreve um destino pré-existente."""
    src = _write(src_dir / "in.pdf", b"novo")
    existing = _write(dst_dir / "saida.pdf", b"ja existe")
    result = fileops.safe_move(src, dst_dir / "saida.pdf")
    # O conteúdo original do destino preexistente é preservado.
    assert existing.read_bytes() == b"ja existe"
    # E o move foi resolvido para outro caminho (anti-colisão a montante).
    assert Path(result).read_bytes() == b"novo"


def test_collision_suffix(src_dir: Path, dst_dir: Path) -> None:
    """D-09: colisão de NOME com conteúdo DIFERENTE → `_1`; ambos sobrevivem."""
    _write(dst_dir / "doc.pdf", b"conteudo A")
    src = _write(src_dir / "in.pdf", b"conteudo B")
    final = Path(fileops.resolve_collision(dst_dir / "doc.pdf", src))
    assert final.name != "doc.pdf"
    assert "_1" in final.name or "_2" in final.name


def test_collision_duplicate(src_dir: Path, dst_dir: Path) -> None:
    """D-10: colisão de NOME com conteúdo IDÊNTICO (mesmo SHA) → pula (skip)."""
    _write(dst_dir / "doc.pdf", b"identico")
    src = _write(src_dir / "in.pdf", b"identico")
    decision = fileops.resolve_collision(dst_dir / "doc.pdf", src)
    assert decision is None  # idêntico → não cria duplicata


def test_cross_device(src_dir: Path, dst_dir: Path, monkeypatch) -> None:
    """AUT-06: ramo EXDEV (cross-device) materializa via copy+fsync+verifica hash."""
    import errno
    import os

    src = _write(src_dir / "in.pdf", b"payload cross device")
    real_replace = os.replace

    def fake_replace(a, b):
        # Simula volumes distintos só no rename final do destino.
        if str(b).startswith(str(dst_dir)):
            raise OSError(errno.EXDEV, "cross-device link not permitted")
        return real_replace(a, b)

    monkeypatch.setattr(os, "replace", fake_replace)
    final = fileops.safe_move(src, dst_dir / "saida.pdf")
    assert Path(final).read_bytes() == b"payload cross device"


def test_integrity_divergent_hash_aborts(src_dir: Path, dst_dir: Path, monkeypatch) -> None:
    """AUT-06: hash divergente pós-cópia → aborta e NÃO remove a origem."""
    src = _write(src_dir / "in.pdf", b"original intacto")
    # Força a verificação de hash a divergir.
    monkeypatch.setattr(fileops, "hash_file", lambda *a, **k: "0" * 64)
    with pytest.raises(Exception):
        fileops.safe_move(src, dst_dir / "saida.pdf")
    # A origem permanece — nunca perda (CLAUDE.md).
    assert src.exists()
    assert src.read_bytes() == b"original intacto"


def test_original_removed_after_apply(src_dir: Path, dst_dir: Path) -> None:
    """AUT-06 crit 5: após apply bem-sucedido a ORIGEM é removida (move, não cópia)."""
    src = _write(src_dir / "in.pdf", b"mover isto")
    final = fileops.safe_move(src, dst_dir / "saida.pdf")
    assert Path(final).exists()
    assert not src.exists()

"""RED (Wave 0) — resolução de nome/pasta a partir de tokens {campo} (AUT-01/02).

Alvo: `app.automation.naming` (a criar na wave de lógica). Cobre:
- tokens {campo} → nome sanitizado (AUT-01);
- campo obrigatório FALTANTE → None (caller transita EM_REVISAO, D-07);
- sanitização dos 9 chars proibidos do Windows + nomes reservados + {data:aaaa-mm} (D-08);
- pasta-destino resolvida + confinamento sob raiz-base (AUT-02, V4 path traversal).

`importorskip` evita ImportError fatal na coleta enquanto `naming` não existe.
"""

import pytest

naming = pytest.importorskip("app.automation.naming")


def _fields() -> dict[str, str]:
    """Campos normalizados típicos (espelha o `classified_doc` do conftest)."""
    return {
        "cliente": "ACME Ltda",
        "numero": "1234",
        "valor": "1500.00",
        "data": "2026-06-17",
    }


def test_tokens_resolved_to_name() -> None:
    """AUT-01: `{cliente}_{numero}` → nome com os valores interpolados."""
    out = naming.resolve_pattern("{cliente}_{numero}", _fields())
    assert out is not None
    assert "ACME" in out and "1234" in out


def test_missing_field_blocks() -> None:
    """AUT-01/D-07: token referenciando campo faltante → None (→ revisão)."""
    out = naming.resolve_pattern("{cliente}_{inexistente}", _fields())
    assert out is None


def test_sanitize_removes_windows_forbidden_chars() -> None:
    """AUT-01/D-08: remove/sanitiza os 9 chars proibidos do Windows (< > : " / \\ | ? *)."""
    dirty = 'a<b>c:d"e/f\\g|h?i*j'
    clean = naming.sanitize_component(dirty)
    for ch in '<>:"/\\|?*':
        assert ch not in clean


def test_sanitize_reserved_names() -> None:
    """AUT-01/D-08: nomes reservados do Windows (CON, PRN, NUL, ...) são sanitizados."""
    for reserved in ("CON", "PRN", "NUL", "COM1", "LPT1"):
        out = naming.sanitize_component(reserved)
        assert out.upper() != reserved


def test_sanitize_data_aaaa_mm_token() -> None:
    """D-08: token de data com formato `{data:aaaa-mm}` → fatia ano-mês do ISO."""
    out = naming.resolve_pattern("{data:aaaa-mm}", _fields())
    assert out == "2026-06"


def test_folder_pattern_resolved_and_confined(tmp_path) -> None:
    """AUT-02: pasta-destino resolvida sob raiz-base; traversal é confinado (V4)."""
    dest = naming.resolve_dest_folder(
        "NotasFiscais/{cliente}/{data:aaaa-mm}", _fields(), base_root=tmp_path
    )
    assert dest is not None
    assert dest.is_relative_to(tmp_path)


def test_folder_traversal_blocked(tmp_path) -> None:
    """AUT-02/V4: tentativa de subir fora da raiz-base via valor malicioso é bloqueada."""
    malicious = {"cliente": "../../etc"}
    dest = naming.resolve_dest_folder("{cliente}", malicious, base_root=tmp_path)
    # Bloqueio = None OU permanece confinado sob a raiz (a sanitização neutralizou).
    assert dest is None or dest.is_relative_to(tmp_path)

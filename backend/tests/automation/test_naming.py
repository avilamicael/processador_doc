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


# ---- D-21: normalização de aspas nas pontas de caminhos -------------------- #


def test_strip_quotes_double_and_single() -> None:
    """D-21: remove aspas duplas/simples nas PONTAS + trim de espaços."""
    assert naming.strip_quotes('"C:\\Users\\Análise"') == "C:\\Users\\Análise"
    assert naming.strip_quotes("'/home/user/docs'") == "/home/user/docs"
    assert naming.strip_quotes('  "x"  ') == "x"


def test_strip_quotes_preserves_inner_content() -> None:
    """D-21: NÃO altera o miolo (aspas internas permanecem)."""
    assert naming.strip_quotes('a"b') == 'a"b'
    assert naming.strip_quotes("semaspas") == "semaspas"


def test_strip_quotes_handles_none_and_empty() -> None:
    assert naming.strip_quotes(None) == ""
    assert naming.strip_quotes('""') == ""
    assert naming.strip_quotes("   ") == ""


def test_folder_pattern_with_quotes_normalized(tmp_path) -> None:
    """D-21: padrão de pasta colado com aspas (estilo Windows) é normalizado e
    o confinamento V4 segue valendo DEPOIS da normalização."""
    dest = naming.resolve_dest_folder(
        '"NotasFiscais/{cliente}"', _fields(), base_root=tmp_path
    )
    assert dest is not None
    assert dest.is_relative_to(tmp_path)
    # A pasta resultante não contém aspas em nenhum segmento.
    assert '"' not in str(dest)


# ---- Fase 9 (D-01..D-05): política de destino absoluto/relativo ------------ #
# A detecção absoluto-vs-relativo usa semântica Windows (ntpath/PureWindowsPath)
# e roda no CI Linux/WSL — NUNCA os.path.isabs (que falha para "C:\\..." no Linux).


def test_dest_absolute_kept_literal(tmp_path) -> None:
    """D-01/D-03: destino com drive Windows é LITERAL — começa em "C:\\Users\\x\\NF\\",
    sem prefixo do base_root (CWD) e sem mutilar o anchor (C: → C_)."""
    dest = naming.resolve_dest_folder(
        "C:\\Users\\x\\NF\\{cliente}", _fields(), base_root=tmp_path
    )
    assert dest is not None
    out = str(dest)
    assert out.startswith("C:\\Users\\x\\NF\\")
    # O base_root (CWD do backend) NÃO é prefixado no ramo absoluto.
    assert str(tmp_path) not in out
    # O anchor NUNCA é sanitizado (sem "C_").
    assert "C_" not in out


def test_dest_unc_absolute(tmp_path) -> None:
    """D-01: destino UNC preserva o anchor "\\\\srv\\share\\" literal (não mutilado)."""
    dest = naming.resolve_dest_folder(
        "\\\\srv\\share\\{cliente}", _fields(), base_root=tmp_path
    )
    assert dest is not None
    out = str(dest)
    # O anchor UNC é preservado (não vira segmento sanitizado nem ganha base_root).
    assert "srv" in out and "share" in out
    assert str(tmp_path) not in out
    assert "ACME" in out


def test_dest_relative_uses_base(tmp_path) -> None:
    """D-02: destino SEM drive/UNC continua relativo → juntado ao base_root."""
    dest = naming.resolve_dest_folder(
        "NotasFiscais/{cliente}", _fields(), base_root=tmp_path
    )
    assert dest is not None
    assert str(dest).startswith(str(tmp_path))


def test_abs_detection_cross_os(tmp_path) -> None:
    """Pitfall 1: a detecção de "C:\\x" como absoluto vale RODANDO EM LINUX/WSL —
    não usa os.path.isabs (que retorna False para drive Windows no Linux)."""
    # No Linux, os.path.isabs falharia; o resultado correto exige ntpath/PureWindowsPath.
    dest = naming.resolve_dest_folder("C:\\dados\\{cliente}", _fields(), base_root=tmp_path)
    assert dest is not None
    out = str(dest)
    assert out.startswith("C:\\dados\\")
    assert str(tmp_path) not in out


def test_segments_sanitized_anchor_kept(tmp_path) -> None:
    """D-03/D-08: os SEGMENTOS após o anchor são sanitizados; o anchor "C:\\" intacto."""
    dest = naming.resolve_dest_folder(
        "C:\\NF\\{cliente}", {"cliente": "a:b/c"}, base_root=tmp_path
    )
    assert dest is not None
    out = str(dest)
    # anchor preservado.
    assert out.startswith("C:\\NF\\")
    # o segmento do campo foi sanitizado: nenhum char proibido remanesce no final.
    last = out.split("\\")[-1]
    for ch in ':/':
        assert ch not in last
    assert "a_b_c" == last


def test_abs_missing_field_blocks(tmp_path) -> None:
    """D-07: token de campo faltante no ramo ABSOLUTO → None (bloqueio preservado)."""
    dest = naming.resolve_dest_folder(
        "C:\\NF\\{inexistente}", _fields(), base_root=tmp_path
    )
    assert dest is None


def test_abs_no_confinement(tmp_path) -> None:
    """D-03/Pitfall 3: destino absoluto FORA da base NÃO vira None (sem is_relative_to
    no ramo absoluto) — escreve onde o processo tiver permissão (single-tenant)."""
    dest = naming.resolve_dest_folder(
        "D:\\fora\\da\\base\\{cliente}", _fields(), base_root=tmp_path
    )
    assert dest is not None
    out = str(dest)
    assert out.startswith("D:\\fora\\da\\base\\")
    assert str(tmp_path) not in out


# ---- Fase 9 Plano 02 (BL-11 / D-06..D-08): filtros inline encadeáveis ------- #
# Engine de transformação de valores: pipeline de filtros no token
# `{campo:filtro=arg:filtro}`, com dispatch explícito (nunca eval) e sanitização
# DEPOIS dos filtros (D-08). Funções puras de naming — sem disco.


def test_filter_palavras() -> None:
    """D-07: `palavras=N` mantém as N primeiras palavras do valor."""
    out = naming.resolve_pattern(
        "{fornecedor:palavras=1}", {"fornecedor": "IGUACU DIST. DE PROD."}
    )
    assert out is not None
    assert "IGUACU" in out
    assert "DIST" not in out


def test_filter_letras() -> None:
    """D-07: `letras=N` trunca aos N primeiros caracteres."""
    out = naming.resolve_pattern("{x:letras=8}", {"x": "ABCDEFGHIJ"})
    assert out == "ABCDEFGH"


def test_filter_truncar() -> None:
    """D-07: `truncar=N` é alias de `letras=N` (trunca aos N primeiros chars)."""
    out = naming.resolve_pattern("{x:truncar=8}", {"x": "ABCDEFGHIJ"})
    assert out == "ABCDEFGH"


def test_filter_maiusc() -> None:
    """D-07: `maiusc` coloca o valor em caixa alta."""
    out = naming.resolve_pattern("{x:maiusc}", {"x": "iguacu"})
    assert out == "IGUACU"


def test_filter_minusc() -> None:
    """D-07: `minusc` coloca o valor em caixa baixa."""
    out = naming.resolve_pattern("{x:minusc}", {"x": "IGUACU"})
    assert out == "iguacu"


def test_filter_sem_acento() -> None:
    """D-07: `sem_acento` remove diacríticos (NFKD)."""
    out = naming.resolve_pattern("{x:sem_acento}", {"x": "IGUAÇU AÇÃO"})
    assert out == "IGUACU ACAO"


def test_filter_substituir() -> None:
    """D-07: `substituir=de>para` faz substituição literal simples."""
    out = naming.resolve_pattern("{x:substituir=LTDA>}", {"x": "ACME LTDA"})
    assert out is not None
    assert "LTDA" not in out
    assert "ACME" in out
    # substituição de char por char
    out2 = naming.resolve_pattern("{x:substituir=a>e}", {"x": "banana"})
    assert out2 == "benene"


def test_filter_padrao_default_when_missing() -> None:
    """D-07/A3: campo AUSENTE + `padrao=Geral` → "Geral" (NÃO bloqueia, não None)."""
    out = naming.resolve_pattern("{tipo:padrao=Geral}", {"cliente": "ACME"})
    assert out == "Geral"


def test_filter_padrao_keeps_value_when_present() -> None:
    """D-07: `padrao=X` NÃO sobrepõe um valor presente."""
    out = naming.resolve_pattern("{tipo:padrao=Geral}", {"tipo": "NotaFiscal"})
    assert out == "NotaFiscal"


def test_filter_formato_explicit() -> None:
    """D-07: `formato=aaaa-mm-dd`/`formato=aaaa-mm` expõe _fmt_date como filtro."""
    out = naming.resolve_pattern("{data:formato=aaaa-mm-dd}", {"data": "2026-06-17"})
    assert out == "2026-06-17"
    out2 = naming.resolve_pattern("{data:formato=aaaa-mm}", {"data": "2026-06-17"})
    assert out2 == "2026-06"


def test_legacy_date_shortcut_still_works() -> None:
    """A1: atalho legado `{data:aaaa-mm}` (sem `formato=`) continua formatando."""
    out = naming.resolve_pattern("{data:aaaa-mm}", {"data": "2026-06-17"})
    assert out == "2026-06"


def test_filter_chain() -> None:
    """D-06: filtros encadeáveis — `{x:maiusc:palavras=2}` aplica em pipeline."""
    out = naming.resolve_pattern("{x:maiusc:palavras=2}", {"x": "iguacu dist prod"})
    assert out == "IGUACU DIST"


def test_sanitize_after_filter() -> None:
    """D-08: sanitização roda DEPOIS dos filtros — um `/` introduzido vira `_`."""
    out = naming.resolve_pattern("{x:substituir=a>/}", {"x": "banana"})
    assert out is not None
    # O `/` produzido pelo filtro foi sanitizado para `_` (não permanece).
    assert "/" not in out
    assert out == "b_n_n_"


def test_unknown_filter_is_inert() -> None:
    """T-09-05: filtro desconhecido é INERTE — não quebra o token (nunca eval)."""
    out = naming.resolve_pattern("{x:filtroinexistente}", {"x": "IGUACU"})
    assert out == "IGUACU"


def test_plain_token_unchanged() -> None:
    """Não-regressão: `{campo}` simples (sem filtro) segue idêntico ao atual."""
    out = naming.resolve_pattern("{cliente}_{numero}", _fields())
    assert out is not None
    assert "ACME" in out and "1234" in out


def test_filter_chain_invalid_int_is_inert() -> None:
    """T-09-05: `int()` inválido no arg (`palavras=abc`) é inerte (não quebra)."""
    out = naming.resolve_pattern("{x:palavras=abc}", {"x": "um dois tres"})
    # Filtro inválido inerte → valor cru passa (sanitizado).
    assert out is not None
    assert "um dois tres" in out


def test_filter_in_dest_folder_segment(tmp_path) -> None:
    """D-06/D-08: filtros valem por SEGMENTO de pasta também (não só no nome)."""
    dest = naming.resolve_dest_folder(
        "NF/{fornecedor:palavras=1}", {"fornecedor": "IGUACU DIST DE PROD"},
        base_root=tmp_path,
    )
    assert dest is not None
    assert str(dest).endswith("IGUACU")


def test_no_eval_in_naming_module() -> None:
    """T-09-05: nenhum eval/exec no módulo (dispatch explícito, falha-fechada)."""
    import inspect

    src = inspect.getsource(naming)
    assert "eval(" not in src
    assert "exec(" not in src

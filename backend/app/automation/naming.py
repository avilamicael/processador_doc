"""Resolução de padrões `{campo}` → nome/pasta sanitizado (Fase 6 + Fase 9).

Função PURA — sem IA, sem disco, sem banco (espelha `validation/dates.py` e
`validation/money.py`: parse→normalizado-ou-`None`, nunca chuta).

AUT-01/AUT-02: o cliente configura padrões como `"{cliente}_{numero}.pdf"` (nome) e
`"NotasFiscais/{cliente}/{data:aaaa-mm}"` (pasta). Os tokens são substituídos pelos
valores extraídos do documento.

D-07 (bloqueio → revisão): se um token referencia um campo FALTANTE/vazio, a
resolução devolve `None`. O caller (apply_stage, Plan 04) rebaixa o documento para
EM_REVISAO em vez de aplicar um nome quebrado — NUNCA inventa um valor.

Política de destino (Fase 9 — D-01..D-03): `resolve_dest_folder` tem DOIS ramos.
- **Absoluto** (`C:\\...` ou UNC `\\\\srv\\share\\...`): o caminho é LITERAL — o
  anchor (drive/UNC) é preservado SEM sanitizar, os SEGMENTOS após o anchor são
  resolvidos+sanitizados, e o resultado NÃO recebe a base padrão. NÃO se chama
  `.resolve()` (canonizaria contra o CWD do backend, reintroduzindo o lixo
  `backend\\C:\\...` — lição de `watched_folders`) e NÃO se chama `is_relative_to`
  (o confinamento V4 foi REMOVIDO para o ramo absoluto — D-03).
- **Relativo** (sem drive/UNC): juntado à `base_root` (a `AUTOMATION_DEST_ROOT` se
  setada, senão `data_dir/organizados`), com cada segmento sanitizado.

A detecção absoluto-vs-relativo usa semântica **Windows** (`ntpath`/`PureWindowsPath`),
NUNCA `os.path.isabs`/`Path.is_absolute()` — estes dependem do OS do runner e
retornariam `False` para `C:\\...` rodando em Linux/WSL (dev/CI), jogando o destino do
cliente sob a base por engano (Pitfall 1).

**Mudança consciente de postura (D-03):** single-tenant, na máquina do cliente — a
automação pode escrever em QUALQUER caminho absoluto com permissão do processo. A
sanitização por SEGMENTO (chars proibidos do Windows, `..`, reservados) continua como
única defesa V4 residual; o anchor (drive/`\\`) NÃO vem de campo, então não é vetor.

NÃO cria pasta no disco (criar diretório é responsabilidade do fileops, Plan 03) — módulo PURO.
NUNCA loga valores de campo (V7/V9 — dados sensíveis LGPD).
"""

import re
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.config import get_settings

# Os 9 caracteres proibidos em nomes de arquivo no Windows (D-08). Cada um vira "_".
_WIN_FORBIDDEN = '<>:"/\\|?*'
_FORBIDDEN_RE = re.compile(r'[<>:"/\\|?*]')

# Nomes de dispositivo reservados do Windows (case-insensitive) — um arquivo chamado
# "CON"/"NUL"/"COM1" etc. é inválido mesmo com extensão (Pitfall 4).
_WIN_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Token `{nome}` ou `{nome:formato}` no padrão.
_TOKEN_RE = re.compile(r"\{([^{}:]+)(?::([^{}]+))?\}")


class _MissingField(Exception):
    """Interno: token referencia campo faltante/vazio → resolução devolve None (D-07)."""


def _max_len() -> int:
    """Teto de comprimento por componente (MAX_PATH/Pitfall 5), da config."""
    return get_settings().automation_max_component_len


# Aspas removidas nas PONTAS de qualquer caminho recebido (D-21). O usuário cola
# caminhos do Windows com aspas (ex.: `"C:\\...\\Análise"`); normalizamos antes de
# usar. Helper CENTRAL — reusar em todo ponto que recebe um caminho do usuário.
_EDGE_QUOTES = "\"'"


def strip_quotes(value: str | None) -> str:
    """Remove aspas (`"`/`'`) nas PONTAS de um caminho + trim de espaços (D-21).

    Defesa de produto: o usuário cola caminhos do Windows entre aspas. Só mexe nas
    PONTAS — o miolo do caminho é preservado intacto (aspas internas permanecem).
    `None`/vazio → "". NÃO loga o valor. O confinamento V4 roda DEPOIS desta
    normalização (responsabilidade de `resolve_dest_folder`).
    """
    if value is None:
        return ""
    return str(value).strip().strip(_EDGE_QUOTES).strip()


def sanitize_component(value: str, max_len: int | None = None) -> str:
    """Sanitiza UM componente (segmento) de caminho para ser seguro no Windows.

    - substitui os 9 chars proibidos (`< > : " / \\ | ? *`) por "_" — isso já
      neutraliza separadores de caminho embutidos no valor (defesa V4 camada 1);
    - colapsa qualquer sequência remanescente de "." que formaria `..`/`.`
      (traversal) — um componente "puro pontos" vira "_";
    - remove espaço/ponto no fim (o Windows os ignora silenciosamente → ambiguidade);
    - se o stem (sem extensão) casa um nome reservado (CON/NUL/COM1…), prefixa "_";
    - trunca ao `max_len` preservando a extensão (Pitfall 5 / MAX_PATH).

    Componente vazio após sanitizar → "_" (nunca devolve string vazia que sumiria
    do caminho). NÃO loga o valor.
    """
    if max_len is None:
        max_len = _max_len()

    # Camada 1 (V4): mata os 9 chars proibidos — inclui `/` e `\\`, então um valor
    # como "..\\..\\Windows" perde os separadores aqui.
    cleaned = _FORBIDDEN_RE.sub("_", value)

    # Neutraliza traversal: um componente que é só pontos ("." / "..") é perigoso e
    # inútil como nome → vira "_".
    if cleaned.strip(". ") == "":
        cleaned = "_"

    # O Windows ignora espaço/ponto finais → remover evita "arquivo " vs "arquivo".
    cleaned = cleaned.rstrip(" .")
    if cleaned == "":
        cleaned = "_"

    # Nome reservado: comparar o STEM (parte antes da última extensão) case-insensitive.
    stem = cleaned.rsplit(".", 1)[0] if "." in cleaned else cleaned
    if stem.upper() in _WIN_RESERVED:
        cleaned = "_" + cleaned

    # Truncamento MAX_PATH preservando a extensão (Pitfall 5).
    if len(cleaned) > max_len:
        if "." in cleaned:
            base, ext = cleaned.rsplit(".", 1)
            ext_with_dot = "." + ext
            keep = max_len - len(ext_with_dot)
            if keep > 0:
                cleaned = base[:keep] + ext_with_dot
            else:
                # Extensão sozinha já estoura o teto → trunca tudo (sem preservar ext).
                cleaned = cleaned[:max_len]
        else:
            cleaned = cleaned[:max_len]
        cleaned = cleaned.rstrip(" .") or "_"

    return cleaned


def _strip_accents(s: str) -> str:
    """Remove diacríticos via NFKD + drop dos combining (`IGUAÇU AÇÃO`→`IGUACU ACAO`).

    Stdlib pura (`unicodedata`), sem tabela própria — cobre Latin-1/Unicode. Filtro
    `sem_acento` (D-07). NÃO loga o valor.
    """
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


# Detecta o atalho LEGADO de data `{data:aaaa-mm}` (spec sem `=` contendo
# aaaa/mm/dd) — mantido por retrocompat (A1 RESOLVED). `formato=` é a forma canônica.
_DATE_SHORTCUT_RE = re.compile(r"aaaa|mm|dd")


def _has_padrao(filters: list[str]) -> str | None:
    """Se a cadeia de filtros contém `padrao=X`, devolve `X` (senão None).

    A3 (RESOLVED): `padrao=` deve SUPRIMIR o bloqueio D-07 quando o campo está
    ausente/vazio — por isso é detectado ANTES de levantar `_MissingField`.
    """
    for f in filters:
        f = f.strip()
        if f.startswith("padrao="):
            return f[len("padrao=") :]
    return None


def _apply_filter(value: str, f: str) -> str:
    """Aplica UM filtro `f` ao `value` via DISPATCH EXPLÍCITO (T-09-05, nunca eval).

    Conjunto v1 (D-07): palavras / letras / truncar / maiusc / minusc / sem_acento /
    substituir / formato / padrao. Filtro desconhecido OU arg inválido (`int()`) →
    INERTE (devolve o value cru) — falha-fechada amigável que não quebra o token.
    `formato=` que não casa data levanta `_MissingField` (pediu formato e o valor não
    é ISO → bloqueio D-07). NÃO loga valores.
    """
    f = f.strip()
    if f.startswith("palavras="):
        arg = f[len("palavras=") :]
        try:
            n = int(arg)
        except ValueError:
            return value  # inerte
        return " ".join(value.split()[:n])
    if f.startswith("letras=") or f.startswith("truncar="):
        arg = f.split("=", 1)[1]
        try:
            n = int(arg)
        except ValueError:
            return value  # inerte
        return value[:n]
    if f == "maiusc":
        return value.upper()
    if f == "minusc":
        return value.lower()
    if f == "sem_acento":
        return _strip_accents(value)
    if f.startswith("substituir="):
        arg = f[len("substituir=") :]
        de, _, para = arg.partition(">")
        return value.replace(de, para)
    if f.startswith("formato="):
        spec = f[len("formato=") :]
        formatted = _fmt_date(value, spec)
        if formatted is None:
            # Pediu formato de data e o valor não é ISO → bloqueio (não chuta).
            raise _MissingField(f)
        return formatted
    if f.startswith("padrao="):
        # padrao= já foi resolvido em _has_padrao (campo presente → no-op aqui).
        return value
    # Filtro desconhecido → inerte (nunca eval; espelha rules._OPERATORS / V5).
    return value


def _apply_filter_pipeline(value: str, filters: list[str]) -> str:
    """Aplica os filtros em ORDEM (pipeline, D-06). Cada um via dispatch explícito."""
    for f in filters:
        value = _apply_filter(value, f)
    return value


def _fmt_date(iso: str, spec: str) -> str | None:
    """Aplica um formato `{data:...}` sobre um valor ISO `YYYY-MM-DD`.

    Reconhece `aaaa` (ano), `mm` (mês), `dd` (dia) no `spec` (ex.: "aaaa-mm" →
    "2026-06"). Valor não-ISO → None (sinal de bloqueio, D-07).
    """
    parts = iso.split("-")
    if len(parts) != 3:
        return None
    y, m, d = parts
    if not (len(y) == 4 and y.isdigit() and m.isdigit() and d.isdigit()):
        return None
    out = spec.replace("aaaa", y).replace("mm", m).replace("dd", d)
    return out


def _substitute(pattern: str, fields: dict[str, str], *, sanitize: bool) -> str:
    """Substitui os tokens `{campo}`/`{campo:fmt}` no padrão.

    Levanta `_MissingField` (capturado pelo caller → None, D-07) quando o token
    referencia um campo ausente/vazio. Quando `sanitize=True`, o valor interpolado
    é sanitizado como componente (nome de arquivo). Para pasta, a sanitização é por
    segmento e fica a cargo de `resolve_dest_folder` (aqui `sanitize=False`).
    """

    def repl(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        spec = match.group(2)

        # spec é tudo após o 1º ':' (group(2)); a cadeia de filtros é o split por ':'.
        filters = [f.strip() for f in spec.split(":")] if spec is not None else []

        raw = fields.get(name)
        missing = raw is None or not str(raw).strip()

        if missing:
            # A3 (D-07): `padrao=X` na cadeia SUPRIME o bloqueio e injeta o default.
            default = _has_padrao(filters)
            if default is None:
                raise _MissingField(name)
            value = default
        else:
            value = str(raw)

        if spec is not None:
            spec_str = spec.strip()
            if not missing and "=" not in spec_str and _DATE_SHORTCUT_RE.search(spec_str):
                # Atalho LEGADO `{data:aaaa-mm}` (sem `=`): trata o spec inteiro como
                # formato de data (A1 RESOLVED, retrocompat). None → bloqueio.
                formatted = _fmt_date(value, spec_str)
                if formatted is None:
                    raise _MissingField(name)
                value = formatted
            else:
                # PIPELINE de filtros inline (D-06/D-07), dispatch explícito sem eval.
                value = _apply_filter_pipeline(value, filters)

        return sanitize_component(value) if sanitize else value

    return _TOKEN_RE.sub(repl, pattern)


def resolve_pattern(pattern: str, fields: dict[str, str]) -> str | None:
    """Resolve um padrão de NOME (`"{cliente}_{numero}.pdf"`) para um nome sanitizado.

    Substitui os tokens pelos valores de `fields`, sanitiza o resultado como UM
    componente de arquivo (9 chars Windows + reservados + truncamento, D-08) e
    devolve o nome. Token referenciando campo faltante/vazio (ou `{data:fmt}` sobre
    valor não-ISO) → `None` (D-07: caller rebaixa para revisão, nunca aplica nome
    quebrado). NÃO loga valores.
    """
    # D-21: normaliza aspas nas pontas do padrão recebido antes de qualquer uso.
    pattern = strip_quotes(pattern)
    try:
        substituted = _substitute(pattern, fields, sanitize=False)
    except _MissingField:
        return None
    # O nome final é UM componente — sanitiza o todo (separadores que viessem do
    # padrão literal também são neutralizados; nome é arquivo, não caminho).
    return sanitize_component(substituted)


def _is_abs_windows(p: str) -> bool:
    """True se `p` é um caminho ABSOLUTO Windows com DRIVE (`C:\\`) ou UNC, D-02.

    Usa `PureWindowsPath().drive` (não-vazio só com drive `C:` ou UNC `\\\\srv\\share`),
    NUNCA `os.path.isabs`/`Path.is_absolute()` — estes dependem do OS do runner e
    dariam `False` para `C:\\...` em Linux/WSL (Pitfall 1). Um leading-slash puro
    (`/...` ou `\\algo` SEM drive/UNC) NÃO conta aqui (PureWindowsPath o lê como anchor
    `'\\'` mas sem drive) — é tratado pelo ramo POSIX-absoluto (`_is_abs_posix`),
    evitando converter um caminho POSIX em Windows e quebrar os separadores.
    """
    return bool(PureWindowsPath(p).drive)


def _is_abs_posix(p: str) -> bool:
    """True se `p` é um caminho POSIX-absoluto (`/...`) — conveniência do dev Linux/WSL.

    A2 (RESEARCH, RESOLVED): suportar POSIX-absoluto é opcional/discrição; habilitado
    para que o dev/CI em Linux use destinos absolutos reais (`/tmp/...`) e o dry-run
    mostre o caminho literal (D-04). Em Windows, o alvo de produção, o ramo Windows
    cobre `C:\\`/UNC. Excludente: só conta quando NÃO há drive/UNC Windows.
    """
    return not PureWindowsPath(p).drive and PurePosixPath(p).is_absolute()


def _resolve_segments(
    segments: list[str], fields: dict[str, str]
) -> list[str] | None:
    """Resolve tokens + sanitiza CADA segmento. Campo faltante → None (D-07).

    Um único campo pode ter trazido `..` ou um separador; `sanitize_component`
    neutraliza por segmento (vira "_"), garantindo que NENHUM segmento navegue para
    cima (defesa V4 residual — D-03/D-08). NÃO loga valores.
    """
    safe: list[str] = []
    for seg in segments:
        try:
            substituted = _substitute(seg, fields, sanitize=False)
        except _MissingField:
            return None  # D-07
        safe.append(sanitize_component(substituted))
    return safe


def resolve_dest_folder(
    pattern: str, fields: dict[str, str], *, base_root: Path
) -> Path | None:
    """Resolve um padrão de PASTA-destino: ABSOLUTO literal OU relativo+`base_root`.

    `pattern` pode ser:
    - ABSOLUTO (D-01/D-02): `"C:\\Users\\x\\NF\\{cliente}"` ou UNC
      `"\\\\srv\\share\\{cliente}"` — o anchor (drive/UNC) é preservado LITERAL (NÃO
      sanitizado), os SEGMENTOS após o anchor são resolvidos+sanitizados, e o
      resultado NÃO recebe `base_root`. SEM `.resolve()` (Pitfall 2) e SEM
      `is_relative_to` (confinamento V4 REMOVIDO no ramo absoluto — D-03).
    - RELATIVO: `"NotasFiscais/{cliente}/{data:aaaa-mm}"` — juntado a `base_root`,
      cada segmento sanitizado.

    A detecção usa `_is_abs_windows` (semântica Windows OS-independente, Pitfall 1).
    Campo faltante/inválido (D-07) → `None` em AMBOS os ramos. NÃO cria a pasta no
    disco (PURO). NÃO loga valores (V7/V9).
    """
    # D-21: normaliza aspas nas pontas do padrão recebido (usuário cola caminho do
    # Windows entre aspas) ANTES de fatiar/decidir absoluto-vs-relativo.
    pattern = strip_quotes(pattern)
    if not pattern:
        return None

    # ----- RAMO ABSOLUTO (D-01/D-03): caminho literal, anchor preservado -----
    if _is_abs_windows(pattern):
        win = PureWindowsPath(pattern)
        anchor = win.anchor  # 'C:\\' ou '\\srv\share\\' — NUNCA sanitizado
        # parts[0] é o anchor; os demais são os segmentos a resolver+sanitizar.
        safe_parts = _resolve_segments(list(win.parts[1:]), fields)
        if safe_parts is None:
            return None  # D-07 preservado também no ramo absoluto
        # Monta o caminho Windows literal; SEM .resolve() (não canonizar contra o CWD)
        # e SEM is_relative_to (D-03 — absoluto escreve onde houver permissão).
        dest = PureWindowsPath(anchor, *safe_parts)
        return Path(str(dest))

    # ----- RAMO POSIX-ABSOLUTO (`/...`): literal, anchor "/" preservado (A2) -----
    if _is_abs_posix(pattern):
        posix = PurePosixPath(pattern)
        safe_parts = _resolve_segments(list(posix.parts[1:]), fields)
        if safe_parts is None:
            return None  # D-07
        dest = PurePosixPath(posix.anchor, *safe_parts)
        return Path(str(dest))

    # ----- RAMO RELATIVO (D-02): junta à base padrão, cada segmento sanitizado -----
    raw_segments = [
        chunk for chunk in re.split(r"[/\\]", pattern) if chunk not in ("", ".")
    ]
    safe_segments = _resolve_segments(raw_segments, fields)
    if safe_segments is None:
        return None  # D-07
    if not safe_segments:
        return None

    candidate = base_root
    for seg in safe_segments:
        candidate = candidate / seg
    # A sanitização por segmento já neutralizou separadores/`..`; mantemos o ramo
    # relativo simples (sem is_relative_to — discrição D-03: traversal não escapa).
    return candidate

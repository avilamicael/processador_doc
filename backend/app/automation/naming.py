"""Resolução de padrões `{campo}` → nome/pasta sanitizado e confinado (Fase 6).

Função PURA — sem IA, sem disco, sem banco (espelha `validation/dates.py` e
`validation/money.py`: parse→normalizado-ou-`None`, nunca chuta).

AUT-01/AUT-02: o cliente configura padrões como `"{cliente}_{numero}.pdf"` (nome) e
`"NotasFiscais/{cliente}/{data:aaaa-mm}"` (pasta). Os tokens são substituídos pelos
valores extraídos do documento.

D-07 (bloqueio → revisão): se um token referencia um campo FALTANTE/vazio, a
resolução devolve `None`. O caller (apply_stage, Plan 04) rebaixa o documento para
EM_REVISAO em vez de aplicar um nome quebrado — NUNCA inventa um valor.

Segurança (V4, path traversal): o valor de um campo vem da IA/documento — é
NÃO-CONFIÁVEL ao virar caminho. Duas defesas em camadas:
1. `sanitize_component` remove os 9 chars proibidos do Windows (incluindo `\\ / :`),
   neutraliza `..`, nomes reservados e trailing dot/space, e trunca ao teto MAX_PATH;
2. `resolve_dest_folder` confina o destino resolvido sob a raiz-base via
   `resolved.is_relative_to(base.resolve())` — campo com `..` ou caminho absoluto NÃO
   escapa (devolve `None`).

NÃO cria pasta no disco (criar diretório é responsabilidade do fileops, Plan 03) — módulo PURO.
NUNCA loga valores de campo (V7/V9 — dados sensíveis LGPD).
"""

import re
from pathlib import Path

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
        raw = fields.get(name)
        if raw is None or not str(raw).strip():
            raise _MissingField(name)
        value = str(raw)
        if spec is not None:
            formatted = _fmt_date(value, spec.strip())
            if formatted is None:
                # Formato pedido mas valor não é ISO → bloqueio (não chuta).
                raise _MissingField(name)
            value = formatted
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


def resolve_dest_folder(
    pattern: str, fields: dict[str, str], *, base_root: Path
) -> Path | None:
    """Resolve um padrão de PASTA-destino e confina o resultado sob `base_root` (V4).

    `pattern` é uma pasta relativa com tokens, ex.: `"NotasFiscais/{cliente}/{data:aaaa-mm}"`.
    Cada SEGMENTO é resolvido e sanitizado individualmente (um valor de campo NÃO
    pode introduzir um separador de caminho nem `..`). O destino é então confinado:

        resolved = (base_root / *segmentos).resolve()
        resolved.is_relative_to(base_root.resolve())  # V4 — não escapa

    Campo faltante/inválido (D-07) OU destino que escaparia da raiz-base → `None`.
    NÃO cria a pasta no disco (PURO — sem efeito de filesystem). NÃO loga valores.
    """
    # D-21: normaliza aspas nas pontas do padrão recebido (usuário cola caminho do
    # Windows entre aspas) ANTES de fatiar/confinar. O confinamento V4 roda depois.
    pattern = strip_quotes(pattern)
    # Aceita separadores `/` e `\\` no padrão literal; cada segmento vira componente.
    raw_segments: list[str] = []
    for chunk in re.split(r"[/\\]", pattern):
        if chunk == "" or chunk == ".":
            continue
        raw_segments.append(chunk)

    safe_segments: list[str] = []
    for seg in raw_segments:
        try:
            substituted = _substitute(seg, fields, sanitize=False)
        except _MissingField:
            return None  # D-07
        # Um único campo pode ter trazido `..` ou `/`; sanitizar o segmento inteiro
        # neutraliza (vira "_"), garantindo que NENHUM segmento navegue para cima.
        safe = sanitize_component(substituted)
        safe_segments.append(safe)

    if not safe_segments:
        return None

    base_resolved = base_root.resolve()
    candidate = base_resolved
    for seg in safe_segments:
        candidate = candidate / seg
    resolved = candidate.resolve()

    # Confinamento V4: o destino DEVE permanecer sob a raiz-base. A sanitização já
    # neutralizou separadores/`..`, mas confirmamos por prefixo resolvido (defesa
    # em profundidade — symlinks/edge cases de plataforma).
    try:
        if not resolved.is_relative_to(base_resolved):
            return None
    except ValueError:
        return None

    return resolved

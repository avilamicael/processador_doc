"""Matcher local por sinais (Fase 06.1, D-T1/D-T2) — motor CUSTO ZERO.

Função PURA de módulo (estilo `extraction/router.choose`: sem DB, sem IA dentro —
recebe os templates já carregados). Resolve a MAIORIA dos documentos sem custo de
IA pontuando cada template por **avaliação booleana de grupos E/OU** de condições.

Forma canônica de `signals_json` (definida nesta fase, consumida pelos Planos 02 e
03) — lista de GRUPOS; cada grupo é uma lista de CONDIÇÕES:

    [
      [ {"mode": "texto", "value": "DANFE"}, {"mode": "regex", "value": "\\\\d{44}"} ],
      [ {"mode": "texto", "value": "12.345.678/0001-99"} ]
    ]

Semântica booleana (D-T1):
- **OU** entre grupos (qualquer grupo que case já basta);
- **E** dentro do grupo (todas as condições do grupo precisam casar);
- grupo vazio NÃO casa e ausência de grupos NÃO casa (falha fechada).

Condições (D-T2), avaliadas sobre o `full_text` do documento (alvo primário A2):
- `texto` (default): substring case-insensitive (`value.lower() in haystack`);
- `regex`: `regex.search` (lib `regex`, drop-in do `re`) com `IGNORECASE`. Endurecida
  contra ReDoS/regex colada pelo operador (single-tenant, T-06.1-01/02): a proteção
  REAL é o `timeout=_REGEX_TIMEOUT_S` no `.search` — aborta o backtracking catastrófico
  (que os tetos de tamanho NÃO impedem, pois o custo vem da estrutura LOCAL do pattern,
  não do tamanho do input) e levanta `TimeoutError`, tratado como não casa (falha
  fechada, V5). Os tetos de PATTERN (`_MAX_SIGNAL_REGEX_LEN`) e de INPUT
  (`_MAX_HAYSTACK_LEN`) permanecem apenas como defesa em profundidade (cheap pre-check
  que descarta patterns/inputs absurdos antes do compile/search). `regex.error` também
  → não casa. NUNCA `eval`.

O parser é forward-compatible (T-06.1-03): JSON malformado → []; a forma legada
plana `list[str]` é mapeada para 1 grupo OU por termo (preserva "qualquer termo
basta"); grupos são normalizados mantendo só `dict`.

A confiança é BOOLEANA: 1.0 se algum grupo casa, senão 0.0. A política de desempate
(D-03) vive em `decide()` — separada de `match_templates` para PRESERVAR o seam que
a Fase 5 e o pipeline de revisão consomem. NÃO embutir isto em
`extraction/router.choose` (mata o seam D-03 — Anti-Pattern).

LGPD/V7: o matcher NÃO loga `full_text` nem valores de sinal.
"""

import json
import re as _re  # stdlib, SÓ para a regex de NORMALIZAÇÃO (NÃO o ReDoS abaixo)
import unicodedata
from dataclasses import dataclass

import regex  # drop-in do `re` com timeout REAL de casamento (CR-01)

from app.models.template import Template

# Regex de NORMALIZAÇÃO (stdlib `_re`, sem timeout — operam sobre tamanho fixo já
# limitado). Pontuação (qualquer não-alfanumérico/não-espaço) vira espaço; espaços
# em sequência colapsam em um só.
_PUNCT_RE = _re.compile(r"[^\w\s]", _re.UNICODE)
_WS_RE = _re.compile(r"\s+")

# Teto do PATTERN de regex colado pelo operador (caracteres). Defesa em profundidade:
# corta patterns absurdos antes do `regex.compile` (cheap pre-check, T-06.1-06).
_MAX_SIGNAL_REGEX_LEN = 512
# Teto do INPUT (haystack) antes de aplicar a regex. Defesa em profundidade: `full_text`
# pode ser enorme, então cortamos o input como cheap pre-check. NÃO neutraliza ReDoS —
# o backtracking catastrófico vem da estrutura LOCAL do pattern, não do tamanho do input
# (CR-01). A proteção REAL contra ReDoS é o `timeout=_REGEX_TIMEOUT_S` no `.search`.
_MAX_HAYSTACK_LEN = 200_000
# Deadline REAL de casamento por condição regex (segundos), via lib `regex`. Aborta o
# backtracking catastrófico que os tetos de tamanho NÃO impedem → `TimeoutError`, tratado
# como não casa (falha fechada). Single-tenant: 0.25s é folgado p/ patterns legítimos;
# calibrável se algum cliente tiver regex/full_text muito grandes (T-06.1-01).
_REGEX_TIMEOUT_S = 0.25
# Margem mínima entre os dois melhores para considerar a decisão NÃO-ambígua. Abaixo
# disto (ambos acima do piso) a IA desempata (D-03). PRESERVAR.
_AMBIGUITY_MARGIN = 0.1


@dataclass(frozen=True)
class TemplateMatch:
    """Confiança do matcher local para um template (sem efeitos colaterais)."""

    template_id: int
    confidence: float


@dataclass(frozen=True)
class MatchDecision:
    """Decisão de roteamento do matcher (D-03).

    `status`:
    - "matched"    → casou direto, custo 0 (`template_id` preenchido);
    - "ambiguous"  → zona cinzenta, a IA precisa desempatar (`template_id` None);
    - "quarantine" → nenhum sinal/abaixo do piso (`template_id` None, D-03).
    """

    status: str
    template_id: int | None


@dataclass(frozen=True)
class ConditionReport:
    """Resultado por-condição do preview de sinais (D-09). Sem efeitos colaterais."""

    mode: str
    value: str
    matched: bool


@dataclass(frozen=True)
class GroupReport:
    """Resultado por-grupo: `matched` é o E das condições (D-T1). Base do preview."""

    matched: bool
    conditions: list[ConditionReport]


def _normalize_text(s: str) -> str:
    """Normaliza texto para casamento MECÂNICO-tolerante (D-02). PURA, NÃO loga (V7).

    Pipeline simétrico (aplicado a value E haystack — Pitfall 2): NFKD-decompõe,
    remove combinantes (diacríticos — corpo COPIADO de `naming._strip_accents`,
    NÃO importado, Pitfall 8), `.lower()`, pontuação→espaço, colapsa espaços/quebras
    de linha num único espaço e `.strip()`. Resolve acento/caixa/quebra/pontuação —
    NÃO resolve palavra trocada (D-04, tradeoff aceito).
    """
    decomposed = unicodedata.normalize("NFKD", s or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = stripped.lower()
    no_punct = _PUNCT_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", no_punct).strip()


def _parse_groups(raw: str | None) -> list[list[dict]]:
    """Lê `signals_json` como lista de grupos de condições (forward-compatible).

    - JSON inválido/ausente → [] (T-06.1-03: nunca propaga erro);
    - forma legada plana `list[str]` → cada termo vira `[{"mode":"texto","value":s}]`
      (1 grupo OU por termo, preserva "qualquer termo basta");
    - forma de grupos `list[list[dict]]` → normaliza mantendo só os `dict`.
    """
    try:
        parsed = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []

    # Forma legada plana: lista de strings → 1 grupo OU por termo.
    if all(isinstance(item, str) for item in parsed):
        return [[{"mode": "texto", "value": item}] for item in parsed]

    # Forma de grupos: lista de listas de condições (dict).
    groups: list[list[dict]] = []
    for group in parsed:
        if isinstance(group, list):
            groups.append([cond for cond in group if isinstance(cond, dict)])
    return groups


def _condition_matches(cond: dict, haystack_norm: str, haystack_lower: str) -> bool:
    """Avalia UMA condição. Bifurca CEDO por modo (Pitfall 1). Falha fechada.

    `regex`: roda contra `haystack_lower` (NÃO normalizado, D-03) — corpo byte-a-byte
    preservado: `regex.search` IGNORECASE com timeout REAL (`_REGEX_TIMEOUT_S`) que
    aborta backtracking catastrófico, tetos de pattern/input como defesa em
    profundidade, `try/except (regex.error, TimeoutError)` → não casa
    (V5/T-06.1-01/02). NUNCA `eval` (dispatch explícito por etiqueta).

    `texto`/default: substring sobre o haystack NORMALIZADO, com o `value` passando
    pela MESMA `_normalize_text` (simetria D-02, Pitfall 2). Needle vazio → não casa.
    """
    value = str(cond.get("value", ""))
    mode = cond.get("mode", "texto")

    if mode == "regex":
        # Defesa em profundidade (cheap pre-check): teto do pattern antes de compilar.
        if not value or len(value) > _MAX_SIGNAL_REGEX_LEN:
            return False
        try:
            pattern = regex.compile(value, regex.IGNORECASE)
            # Defesa em profundidade: corte do haystack (cheap pre-check). Proteção
            # REAL contra ReDoS: timeout que aborta o backtracking → TimeoutError.
            return (
                pattern.search(
                    haystack_lower[:_MAX_HAYSTACK_LEN], timeout=_REGEX_TIMEOUT_S
                )
                is not None
            )
        except (regex.error, TimeoutError):
            return False  # falha fechada (regex inválida OU ReDoS estourado)

    # "texto" e desconhecidos: substring sobre o haystack NORMALIZADO (simetria D-02).
    needle = _normalize_text(value)
    if not needle:
        return False
    return needle in haystack_norm


def _group_matches(
    group: list[dict], haystack_norm: str, haystack_lower: str
) -> bool:
    """E: todas as condições do grupo casam. Grupo vazio NÃO casa (falha fechada)."""
    return bool(group) and all(
        _condition_matches(cond, haystack_norm, haystack_lower) for cond in group
    )


def _template_matches(
    groups: list[list[dict]], haystack_norm: str, haystack_lower: str
) -> bool:
    """OU: algum grupo casa. Sem grupos NÃO casa (falha fechada)."""
    return any(
        _group_matches(group, haystack_norm, haystack_lower) for group in groups
    )


def evaluate_groups(groups: list[list[dict]], full_text: str) -> list[GroupReport]:
    """Detalhamento por-grupo/condição reusando a MESMA preparação de haystack do
    `match_templates` (D-09) — FONTE-ÚNICA do preview de sinais (Plano 02).

    Para cada grupo, avalia cada condição via `_condition_matches` (ramo texto sobre
    o haystack normalizado, ramo regex sobre o lowercase-só) e monta o relatório;
    `matched` do grupo = E das condições. PURA, NÃO loga `full_text`/valores (V7).
    """
    haystack_lower, haystack_norm = _prepare_haystacks(full_text)

    reports: list[GroupReport] = []
    for group in groups:
        conditions: list[ConditionReport] = []
        for cond in group:
            mode = str(cond.get("mode", "texto"))
            value = str(cond.get("value", ""))
            matched = _condition_matches(cond, haystack_norm, haystack_lower)
            conditions.append(ConditionReport(mode=mode, value=value, matched=matched))
        group_matched = bool(group) and all(c.matched for c in conditions)
        reports.append(GroupReport(matched=group_matched, conditions=conditions))
    return reports


def _prepare_haystacks(full_text: str) -> tuple[str, str]:
    """Prepara os dois haystacks UMA vez: lowercase-só (ramo regex, D-03) e
    normalizado (ramo texto, D-02). Fonte-única compartilhada por `match_templates`
    e `evaluate_groups` para garantir resultado idêntico (D-09)."""
    text = full_text or ""
    return text.lower(), _normalize_text(text)


def match_templates(
    *,
    fields_json: str,
    full_text: str,
    doc_type_guess: str,
    templates: list[Template],
) -> list[TemplateMatch]:
    """Avalia cada template por grupos E/OU texto|regex (D-T1/D-T2). PURA.

    Confiança BOOLEANA: 1.0 se algum grupo do template casa o `full_text`, senão
    0.0. Resultado ORDENADO por confiança desc — maior vence (D-03).

    `doc_type_guess` é mantido na assinatura por compat (a Fase 5 e `stage.py`
    passam o parâmetro), mas é IGNORADO: o doc_type saiu do formulário de templates
    (D-T5/A3) e o bônus por doc_type foi removido. `fields_json` também não compõe
    mais o alvo dos sinais — os sinais casam contra o `full_text` (A2/D-T2).
    """
    del fields_json, doc_type_guess  # mantidos na assinatura por compat; não usados.

    # MESMA preparação consumida por evaluate_groups (D-09): ramo regex usa o
    # lowercase-só (D-03), ramo texto usa o normalizado (D-02).
    haystack_lower, haystack_norm = _prepare_haystacks(full_text)

    matches: list[TemplateMatch] = []
    for tpl in templates:
        groups = _parse_groups(tpl.signals_json)
        confidence = (
            1.0 if _template_matches(groups, haystack_norm, haystack_lower) else 0.0
        )
        matches.append(TemplateMatch(template_id=tpl.id, confidence=confidence))

    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches


def decide(matches: list[TemplateMatch], *, threshold: float) -> MatchDecision:
    """Aplica a política de roteamento (D-03) sobre os matches já ordenados.

    - lista vazia, melhor confiança 0.0 (NENHUM sinal casou) ou melhor < `threshold`
      → "quarantine";
    - melhor ≥ `threshold` e o segundo está dentro de `_AMBIGUITY_MARGIN` (também
      ≥ threshold) → "ambiguous" (a IA desempata);
    - caso contrário → "matched" no melhor template.

    Falha fechada (WR-01): exige confiança ESTRITAMENTE positiva — um documento sem
    nenhum sinal (confiança 0.0) NUNCA é "matched"/"ambiguous", independente do
    threshold (incluindo 0 e negativo). A faixa válida do threshold ([0.0, 1.0]) é
    garantida na borda por `config.classify_match_threshold`.
    """
    if (
        not matches
        or matches[0].confidence <= 0.0
        or matches[0].confidence < threshold
    ):
        return MatchDecision(status="quarantine", template_id=None)

    best = matches[0]
    if len(matches) > 1:
        second = matches[1]
        if (
            second.confidence >= threshold
            and (best.confidence - second.confidence) < _AMBIGUITY_MARGIN
        ):
            return MatchDecision(status="ambiguous", template_id=None)

    return MatchDecision(status="matched", template_id=best.template_id)

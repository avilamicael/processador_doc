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
- `regex`: `re.search` com `IGNORECASE`. Endurecida contra ReDoS/regex colada pelo
  operador (single-tenant, T-06.1-01/02): teto de PATTERN (`_MAX_SIGNAL_REGEX_LEN`)
  antes de compilar, teto de INPUT (`_MAX_HAYSTACK_LEN`) cortando o haystack antes
  do `.search`, e `try/except re.error` → não casa (falha fechada, V5). NUNCA `eval`.

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
import re
from dataclasses import dataclass

from app.models.template import Template

# Teto do PATTERN de regex colado pelo operador (caracteres). Acima disto não
# compilamos — corta patterns absurdos antes do `re.compile` (T-06.1-01).
_MAX_SIGNAL_REGEX_LEN = 512
# Teto do INPUT (haystack) antes de aplicar a regex. `full_text` pode ser enorme;
# cortar o input neutraliza patterns catastróficos (ReDoS) — `re` stdlib sem timeout
# é aceito pelo threat model single-tenant (A5/T-06.1-01).
_MAX_HAYSTACK_LEN = 200_000
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


def _condition_matches(cond: dict, haystack: str) -> bool:
    """Avalia UMA condição contra o haystack (já em lower). Falha fechada.

    `texto`/default: substring case-insensitive. `regex`: `re.search` IGNORECASE
    com teto de pattern + teto de input + `try/except re.error` (V5/T-06.1-01/02).
    Valor vazio → não casa. NUNCA `eval` (dispatch explícito por etiqueta).
    """
    value = str(cond.get("value", ""))
    mode = cond.get("mode", "texto")

    if mode == "regex":
        if not value or len(value) > _MAX_SIGNAL_REGEX_LEN:
            return False
        try:
            pattern = re.compile(value, re.IGNORECASE)
        except re.error:
            return False
        return pattern.search(haystack[:_MAX_HAYSTACK_LEN]) is not None

    # "texto" e desconhecidos: substring case-insensitive.
    needle = value.strip().lower()
    if not needle:
        return False
    return needle in haystack


def _group_matches(group: list[dict], haystack: str) -> bool:
    """E: todas as condições do grupo casam. Grupo vazio NÃO casa (falha fechada)."""
    return bool(group) and all(_condition_matches(cond, haystack) for cond in group)


def _template_matches(groups: list[list[dict]], haystack: str) -> bool:
    """OU: algum grupo casa. Sem grupos NÃO casa (falha fechada)."""
    return any(_group_matches(group, haystack) for group in groups)


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

    haystack = (full_text or "").lower()

    matches: list[TemplateMatch] = []
    for tpl in templates:
        groups = _parse_groups(tpl.signals_json)
        confidence = 1.0 if _template_matches(groups, haystack) else 0.0
        matches.append(TemplateMatch(template_id=tpl.id, confidence=confidence))

    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches


def decide(matches: list[TemplateMatch], *, threshold: float) -> MatchDecision:
    """Aplica a política de roteamento (D-03) sobre os matches já ordenados.

    - lista vazia ou melhor confiança < `threshold` → "quarantine";
    - melhor ≥ `threshold` e o segundo está dentro de `_AMBIGUITY_MARGIN` (também
      ≥ threshold) → "ambiguous" (a IA desempata);
    - caso contrário → "matched" no melhor template.
    """
    if not matches or matches[0].confidence < threshold:
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

"""Matcher local por sinais (Fase 4, D-02) — motor de classificação CUSTO ZERO.

Função PURA de módulo (estilo `extraction/router.choose`: sem DB, sem IA dentro —
recebe os templates já carregados). É a peça que resolve a MAIORIA dos documentos
sem custo de IA (Pitfall 5 / T-04-08): pontua cada template pela fração de sinais
identificadores presentes na extração já feita (Fase 3).

Pontuação (Open Question 2): `Template.signals_json` é uma lista de termos. A
confiança de um template = fração desses termos presentes (case-insensitive) em
ALGUMA `key` de `fields_json` OU no `full_text`. Some-se um bônus quando
`doc_type_guess` casa com `Template.doc_type` (atalho D-01).

Política de desempate (D-03) vive em `decide()` — separada de `match_templates`
para preservar o seam: maior confiança ≥ limiar → casa direto (custo 0); zona
cinzenta entre os dois melhores → "ambíguo" (a IA desempata, Plan seguinte); zero
sinais / abaixo do piso → "quarentena" (template_id null). NÃO embutir isto em
`extraction/router.choose` (mata o seam D-03 — Anti-Pattern).
"""

import json
from dataclasses import dataclass

from app.models.template import Template

# Bônus somado à fração de sinais quando `doc_type_guess` casa com `Template.doc_type`
# (atalho D-01). Mantido pequeno para não dominar a evidência dos sinais.
_DOC_TYPE_BONUS = 0.15
# Margem mínima entre os dois melhores para considerar a decisão NÃO-ambígua. Abaixo
# disto (ambos acima do piso) a IA desempata (D-03).
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


def _signals(template: Template) -> list[str]:
    """Lê `Template.signals_json` como lista de termos (tolerante a vazio/inválido)."""
    raw = template.signals_json or "[]"
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(s) for s in parsed]


def _haystack(fields_json: str, full_text: str) -> str:
    """Junta as `key` dos pares extraídos + o full_text num texto único (lower)."""
    keys: list[str] = []
    try:
        pairs = json.loads(fields_json or "[]")
        if isinstance(pairs, list):
            keys = [str(p.get("key", "")) for p in pairs if isinstance(p, dict)]
    except (ValueError, TypeError):
        keys = []
    return (" ".join(keys) + " " + (full_text or "")).lower()


def match_templates(
    *,
    fields_json: str,
    full_text: str,
    doc_type_guess: str,
    templates: list[Template],
) -> list[TemplateMatch]:
    """Pontua cada template por sinais + bônus de doc_type (D-02). PURA.

    Confiança = fração de sinais presentes (case-insensitive em key/full_text) +
    `_DOC_TYPE_BONUS` se `doc_type_guess` casar com `Template.doc_type` (limitada a
    1.0). Resultado ORDENADO por confiança desc — maior vence (D-03). Templates
    sem sinais ficam com confiança 0 (só o eventual bônus).
    """
    haystack = _haystack(fields_json, full_text)
    guess = (doc_type_guess or "").strip().lower()

    matches: list[TemplateMatch] = []
    for tpl in templates:
        signals = _signals(tpl)
        if signals:
            present = sum(1 for s in signals if s.strip().lower() in haystack)
            score = present / len(signals)
        else:
            score = 0.0
        if guess and tpl.doc_type and guess == tpl.doc_type.strip().lower():
            score += _DOC_TYPE_BONUS
        matches.append(TemplateMatch(template_id=tpl.id, confidence=min(score, 1.0)))

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

"""Estágio de classificação — matcher → (IA desempate) → filler → (IA faltantes) →
validação/normalização → persistência atômica (Fase 4, coração: TPL-03/TPL-04/EXT-04).

Espelha `extraction/stage.py` em forma e garantias: função async, isolável (sem
HTTP), idempotente e com persistência ATÔMICA. Liga as peças puras do Plan 03
(`matcher`, `filler`, `openai_client`, `schema`) e o validador do Plan 02
(`validation.fields`) à persistência do Plan 01 (`ClassificationResult` +
`FilledField` + `Usage`).

Garantias materializadas:
- **Idempotência / não cobrar duas vezes (T-04-13 / risco #1):** checa
  `ClassificationResult` existente por `document_id` ANTES de QUALQUER chamada paga
  (desempate D-01 ou faltantes D-06). Já existe → no-op (NÃO re-chama a IA). A
  UNIQUE(document_id) é a rede no banco; a checagem prévia evita as chamadas pagas.
- **Atomicidade (caminho casou):** `ClassificationResult` + `FilledField`s +
  `Usage(step="classify")` por chamada paga + o avanço do marcador "classificado"
  são persistidos no MESMO `session.commit()` ao final. Set-em-memória + commit
  único (NÃO `mark_step`, que comitaria sozinho; NÃO `transition` PROCESSANDO→
  PROCESSANDO, auto-laço fora da allowlist).
- **Quarentena via state machine (T-04-14):** nenhum template casa → ORDEM
  OBRIGATÓRIA: PRIMEIRO `session.add(ClassificationResult(template_id=None))` +
  `Usage` se houve desempate pago, DEPOIS `transition(QUARENTENA)`, que faz
  `session.commit()` INTERNO (state_machine.py linha 61) comitando TUDO junto num
  commit atômico. NUNCA `transition` antes do add (deixaria o doc em QUARENTENA sem
  registro). NUNCA `session.commit()` manual nesse ramo.
- **Estado terminal correto (D-04):** casou → state permanece PROCESSANDO + marcador
  "classificado"; NUNCA CONCLUIDO.
- **Marca não bloqueia (D-10):** campo inválido (DV CNPJ falho/data não parseável) →
  FilledField.valid=False + invalid_reason; o documento SEGUE (não vai para
  quarentena por isso).
- **Recusa/erro propaga:** `ClassificationRefused`, erros de rede NÃO são capturados
  aqui — sobem para o worker (Plan 04). Como ocorrem antes do commit único, nada
  parcial é persistido.
- **Não vazar conteúdo (V7/V8 / T-04-16):** loga só metadados (document_id/
  template_id/route); NUNCA chave/full_text/fields/chave NF-e.

LACUNA CONSCIENTE DE IDEMPOTÊNCIA (v1, RESEARCH Open Question 1): se o stage falhar
ENTRE a chamada paga de desempate e a de faltantes, o retry re-executa ambas e
re-cobra o desempate. ACEITO no v1 (raro) — a rede dura cobre o caso comum (stage
já completou → ClassificationResult existe → no-op). Documentado em test_stage.py.

Interface pública: `classify_stage`, `ClassifyStageResult`, `CLASSIFIED_STEP`,
`USAGE_STEP`.
"""

import logging
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classification import filler, matcher, openai_client
from app.classification.confidence import compute_confidence
from app.config import get_settings
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.models.extraction import Extraction
from app.models.template import Template
from app.models.usage import Usage
from app.pipeline.state_machine import transition
from app.validation.fields import validate_field

logger = logging.getLogger(__name__)

# Marcador interno avançado em caso de casamento (D-04). NÃO é um estado de topo
# (DocState); o `state` permanece PROCESSANDO. A UI/worker leem este valor.
CLASSIFIED_STEP = "classificado"

# Etapa atribuída ao consumo de tokens no modelo `Usage` (base da cobrança, USE-02).
USAGE_STEP = "classify"


@dataclass(frozen=True)
class ClassifyStageResult:
    """Resultado de `classify_stage`: casou?, qual template e se a IA foi chamada.

    `called_ai=False` indica que nenhuma chamada paga ocorreu — seja porque o
    matcher local resolveu (custo 0), seja porque foi no-op idempotente
    (ClassificationResult já existia). Útil para o worker e os testes provarem a
    não-cobrança-dupla (call_count inalterado).
    """

    matched: bool
    template_id: int | None
    called_ai: bool


def _norm(name: str) -> str:
    """Normaliza um nome de campo para o merge D-06 (mesma regra do filler).

    casefold + remoção de diacríticos (NFKD) + colapso de espaços/underscores.
    Replica `filler._norm` para casar o `ExtractedField.key` devolvido pela IA com
    o `field_name` do template (case-insensitive, mesma normalização).
    """
    decomposed = unicodedata.normalize("NFKD", name or "")
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    collapsed = no_accents.replace("_", " ").casefold()
    return " ".join(collapsed.split())


def _candidates_summary(templates: list[Template]) -> str:
    """Resumo (id + sinais) dos templates candidatos para o prompt de desempate.

    Só metadados de configuração do operador (id e sinais do template) — não há
    conteúdo do documento aqui (V7/V8).
    """
    lines = []
    for tpl in templates:
        signals = tpl.signals_json or "[]"
        lines.append(f"- id={tpl.id} nome={tpl.name} sinais={signals}")
    return "\n".join(lines)


def _missing_field_specs(template: Template, missing_names: list[str]) -> str:
    """Especificação dos campos faltantes para o prompt D-06.

    Passa os `field_name` EXATOS do template (chave do merge por nome) + tipo/hint,
    instruindo implicitamente a IA a devolver `ExtractedField.key` == field_name.
    """
    by_name = {f.name: f for f in template.fields}
    lines = []
    for name in missing_names:
        field = by_name.get(name)
        ftype = field.field_type if field else "texto"
        hint = f" (dica: {field.hint})" if field and field.hint else ""
        lines.append(f"- {name} [tipo={ftype}]{hint}")
    return "\n".join(lines)


async def classify_stage(
    session: Session, *, content_hash: str, forced_template_id: int | None = None
) -> ClassifyStageResult:
    """Classifica o bloco `content_hash`, preenche/valida os campos e persiste atômico.

    Fluxo (04-RESEARCH.md):
      1. Localiza o `Document` do bloco por `content_hash` (None → ValueError).
      2. IDEMPOTÊNCIA: `ClassificationResult` existente → no-op SEM chamar a IA.
      3. Lê a `Extraction` do bloco (None → ValueError, o worker re-tenta).
      4. `matcher.match_templates` pontua os templates carregados.
      5. `matcher.decide` (limiar global): matched/ambiguous/quarantine.
      6. Quarentena → add(ClassificationResult(template_id=None)) [+Usage se houve
         desempate] e DEPOIS `transition(QUARENTENA)` (que comita tudo junto).
      7. Casou → `filler.map_fields`; faltantes obrigatórios → `fill_missing_fields`
         (pago) só para eles; merge por field_name (D-06).
      8. `validate_field` por campo do template → FilledField (D-10/D-11).
      9. COMMIT ATÔMICO ÚNICO: ClassificationResult + FilledFields + Usage por
         chamada paga + marcador "classificado" EM MEMÓRIA.

    Recusa/erro PROPAGAM para o worker (sem try/catch aqui).
    """
    # (1) Localizar o bloco. Documento ausente é erro de orquestração — propaga.
    doc = session.scalar(
        select(Document).where(Document.content_hash == content_hash)
    )
    if doc is None:
        raise ValueError("Document inexistente para content_hash informado")

    # (2) IDEMPOTÊNCIA (T-04-13 / risco #1): ClassificationResult já existente →
    # no-op. NÃO re-chamar a IA (não re-cobrar). A UNIQUE(document_id) garante no
    # banco; esta checagem evita QUALQUER chamada paga.
    existing = session.scalar(
        select(ClassificationResult).where(
            ClassificationResult.document_id == doc.id
        )
    )
    if existing is not None:
        logger.debug("Classificação já existe para document_id=%s — no-op", doc.id)
        return ClassifyStageResult(
            matched=existing.template_id is not None,
            template_id=existing.template_id,
            called_ai=False,
        )

    # (3) Ler a Extraction do bloco (INTACTA, D-07). Sem Extraction → erro de
    # orquestração (o worker re-tenta), alinhado ao extract_stage.
    extraction = session.scalar(
        select(Extraction).where(Extraction.document_id == doc.id)
    )
    if extraction is None:
        raise ValueError("Extraction inexistente para o bloco — fora de ordem")

    settings = get_settings()
    called_ai = False
    usages: list[Usage] = []
    confidence: float | None = None
    matched_template_id: int | None = None

    if forced_template_id is not None:
        # (4'/5') CAMINHO FORÇADO (D-09 — reclassificação de quarentena): o operador
        # escolheu o template explicitamente. PULA matcher/decide/desempate por
        # completo e vai direto ao filler+IA-faltantes+validação com o template
        # forçado. `confidence` (score do matcher) fica None: não houve casamento
        # automático. Template inexistente → ValueError ANTES de qualquer
        # persistência (T-05-03) — o worker roteia a FALHA via dead-letter.
        template = session.get(Template, forced_template_id)
        if template is None:
            raise ValueError("Template forçado inexistente")
        matched_template_id = forced_template_id
        confidence = None
        by_id = {template.id: template}
    else:
        # (4) Carregar os templates e pontuar (matcher PURO, custo 0).
        templates = list(session.scalars(select(Template)).all())
        matches = matcher.match_templates(
            fields_json=extraction.fields_json,
            full_text=extraction.full_text,
            doc_type_guess=extraction.doc_type_guess,
            templates=templates,
        )

        # (5) Política (limiar GLOBAL classify_match_threshold).
        decision = matcher.decide(
            matches, threshold=settings.classify_match_threshold
        )

        by_id = {tpl.id: tpl for tpl in templates}
        conf_by_id = {m.template_id: m.confidence for m in matches}

        if decision.status == "ambiguous":
            # Zona cinzenta → desempate PAGO (D-01). A IA escolhe o id (ou null).
            candidates = [
                by_id[m.template_id]
                for m in matches
                if m.confidence >= settings.classify_match_threshold
                and m.template_id in by_id
            ]
            result, usage = await openai_client.disambiguate(
                _candidates_summary(candidates),
                extraction.full_text,
            )
            called_ai = True
            usages.append(
                Usage(
                    document_id=doc.id,
                    step=USAGE_STEP,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                )
            )
            confidence = result.confidence
            if (
                result.matched_template_id is not None
                and result.matched_template_id in by_id
            ):
                matched_template_id = result.matched_template_id
        elif decision.status == "matched":
            matched_template_id = decision.template_id
            confidence = conf_by_id.get(matched_template_id)
        # "quarantine" → matched_template_id permanece None.

    # (6) Quarentena (nenhum template casou). ATOMICIDADE: add ANTES do transition;
    # o transition faz o commit interno e persiste TUDO junto (T-04-14). NUNCA
    # avançar o marcador "classificado". NUNCA commit manual aqui.
    if matched_template_id is None:
        session.add(
            ClassificationResult(
                document_id=doc.id,
                template_id=None,
                confidence=confidence,
            )
        )
        for u in usages:
            session.add(u)
        transition(session, doc, DocState.QUARENTENA)
        logger.info("Documento %s → QUARENTENA (nenhum template casou)", doc.id)
        return ClassifyStageResult(
            matched=False, template_id=None, called_ai=called_ai
        )

    # (7) Casou → mapear pares→campos (filler PURO). Faltantes obrigatórios → IA.
    template = by_id[matched_template_id]
    fill = filler.map_fields(
        template_fields=list(template.fields),
        fields_json=extraction.fields_json,
    )
    raw_by_name = dict(fill.filled)  # {field_name: raw_value}

    if fill.missing_required:
        ai_result, usage = await openai_client.fill_missing_fields(
            _missing_field_specs(template, fill.missing_required),
            extraction.full_text,
        )
        called_ai = True
        usages.append(
            Usage(
                document_id=doc.id,
                step=USAGE_STEP,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
        )
        # MERGE D-06 por NOME: casar cada ExtractedField.key com o field_name
        # faltante (case-insensitive, mesma normalização do filler). Campos que a
        # IA não devolver permanecem ausentes (validados como faltante no passo 8).
        missing_by_norm = {_norm(n): n for n in fill.missing_required}
        for pair in ai_result.fields:
            target = missing_by_norm.get(_norm(pair.key))
            if target is not None:
                raw_by_name[target] = pair.value

    # (8) Validar/normalizar cada campo do template (D-10/D-11).
    cr = ClassificationResult(
        document_id=doc.id,
        template_id=matched_template_id,
        confidence=confidence,
    )
    session.add(cr)
    for field in template.fields:
        raw = raw_by_name.get(field.name)
        validation = validate_field(
            field_type=field.field_type,
            raw=raw,
            required=field.required,
            regex=field.regex,
        )
        cr.filled_fields.append(
            FilledField(
                field_name=field.name,
                raw_value=validation.raw_value,
                normalized_value=validation.normalized_value,
                valid=validation.valid,
                invalid_reason=validation.invalid_reason,
            )
        )

    # (9) ROTEAMENTO DE ESTADO POR SCORE (Fase 5, D-01/D-04) num COMMIT ATÔMICO
    # ÚNICO: ClassificationResult (+confidence_score) + FilledFields + Usage(s) + o
    # destino de estado. `compute_confidence` é a fração de obrigatórios válidos +
    # `has_invalid_required` (qualquer obrigatório inválido força revisão mesmo com
    # score alto, D-04). `below_threshold` aplica o limiar global (REV-02).
    score, has_invalid_required = compute_confidence(
        cr.filled_fields, list(template.fields)
    )
    cr.confidence_score = score
    for u in usages:
        session.add(u)
    below_threshold = score < settings.review_confidence_threshold

    if has_invalid_required or below_threshold:
        # Precisa de atenção humana → EM_REVISAO. NUNCA `session.commit()` antes do
        # `transition` (Pitfall 2): o `transition` comita TUDO junto (CR +
        # FilledFields + Usages + estado) atomicamente. A allowlist valida
        # PROCESSANDO→EM_REVISAO (T-05-04); inválida faz rollback sem corromper.
        transition(session, doc, DocState.EM_REVISAO, completed_step=CLASSIFIED_STEP)
        logger.info(
            "Documento %s → EM_REVISAO (score=%.3f has_invalid_required=%s)",
            doc.id,
            score,
            has_invalid_required,
        )
        return ClassifyStageResult(
            matched=True, template_id=matched_template_id, called_ai=called_ai
        )

    # Passou (score >= limiar e nenhum obrigatório inválido). Mantém o comportamento
    # terminal da Fase 4: state permanece PROCESSANDO + marcador "classificado".
    # NUNCA transita para CONCLUIDO (Open Q1 RESOLVIDA, T-05-05): CONCLUIDO é
    # terminal e é a Fase 6 que captura docs prontos para aplicar automações;
    # auto-CONCLUIR aqui pularia esse ponto de captura. A conclusão só ocorre via
    # aprovação humana (Plan 03).
    doc.last_completed_step = CLASSIFIED_STEP
    session.commit()

    logger.info(
        "Classificação concluída document_id=%s template_id=%s called_ai=%s score=%.3f",
        doc.id,
        matched_template_id,
        called_ai,
        score,
    )
    return ClassifyStageResult(
        matched=True, template_id=matched_template_id, called_ai=called_ai
    )

"""Caminho forced_template_id do classify_stage (Fase 5, Plan 02 — Task 1, parte A).

Cobre o `<behavior>` do Plan 02:
- `classify_stage(..., forced_template_id=N)` pula matcher/decide/desempate e casa o
  template forçado direto (caminho do reclassify humano de quarentena, D-09) — prova:
  o template forçado é DIFERENTE do que o matcher escolheria, e o resultado usa o forçado;
- template forçado inexistente → ValueError (T-05-03, antes de qualquer persistência);
- `confidence` (do matcher) fica None quando o template é forçado manualmente.

A OpenAI é mockada via respx — 0 token (o caminho forçado não chama desempate, e os
campos presentes evitam a IA de faltantes).
"""

import json

import pytest
import respx
from sqlalchemy import Engine, select

from app import config
from app.classification.stage import CLASSIFIED_STEP, classify_stage
from app.models import (
    ClassificationResult,
    DocState,
    Document,
    Extraction,
    FilledField,
    Template,
    TemplateField,
)
from app.storage.db import get_session


@pytest.fixture(autouse=True)
def _openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-forced")
    monkeypatch.setenv("REVIEW_CONFIDENCE_THRESHOLD", "0.8")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _seed_doc(
    session,
    *,
    content_hash: str,
    fields_json: str,
    full_text: str,
    doc_type_guess: str = "nota_fiscal",
) -> Document:
    doc = Document(
        content_hash=content_hash,
        original_filename="exemplo.pdf",
        state=DocState.PROCESSANDO,
        last_completed_step="extraido",
    )
    session.add(doc)
    session.commit()
    session.add(
        Extraction(
            document_id=doc.id,
            fields_json=fields_json,
            full_text=full_text,
            doc_type_guess=doc_type_guess,
            doc_type_confidence=0.8,
            route="native_text",
        )
    )
    session.commit()
    return doc


def _template(
    session,
    *,
    name: str,
    doc_type: str,
    signals: list[str],
    fields: list[tuple[str, str, bool]] | None = None,
) -> Template:
    tpl = Template(name=name, doc_type=doc_type, signals_json=json.dumps(signals))
    session.add(tpl)
    session.commit()
    for fname, ftype, required in fields or []:
        session.add(
            TemplateField(
                template_id=tpl.id,
                name=fname,
                field_type=ftype,
                required=required,
            )
        )
    session.commit()
    return tpl


def _pairs_json(pairs: list[tuple[str, str]]) -> str:
    return json.dumps([{"key": k, "value": v, "confidence": 0.9} for k, v in pairs])


async def test_forced_template_skips_matcher(schema_engine: Engine) -> None:
    """forced_template_id casa o template forçado direto, sem matcher/IA.

    O documento tem os sinais do template A (o matcher escolheria A), mas forçamos
    o template B. O resultado DEVE usar B — prova que o matcher foi pulado. B tem um
    campo `codigo` que está presente nos pares → filler resolve sem IA de faltantes.
    """
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            tpl_a = _template(
                s,
                name="Nota A",
                doc_type="nota_fiscal",
                signals=["nota fiscal", "numero_nota"],
                fields=[("numero_nota", "texto", True)],
            )
            tpl_b = _template(
                s,
                name="Boleto B",
                doc_type="boleto",
                signals=["linha digitavel", "beneficiario"],
                fields=[("codigo", "texto", True)],
            )
            tpl_a_id = tpl_a.id
            tpl_b_id = tpl_b.id
            doc = _seed_doc(
                s,
                content_hash="A" * 64,
                # sinais de A presentes; matcher escolheria A. codigo presente para B.
                fields_json=_pairs_json([("numero_nota", "555"), ("codigo", "XYZ")]),
                full_text="NOTA FISCAL numero_nota 555",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(
                s, content_hash="A" * 64, forced_template_id=tpl_b_id
            )

        # usou o template FORÇADO (B), não o que o matcher escolheria (A)
        assert result.matched is True
        assert result.template_id == tpl_b_id
        assert result.template_id != tpl_a_id
        assert result.called_ai is False
        assert route.call_count == 0  # sem desempate nem faltantes pagos

    with get_session(schema_engine) as s:
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr.template_id == tpl_b_id
        # filler+validação rodaram para o template forçado
        ffs = s.scalars(
            select(FilledField).where(
                FilledField.classification_result_id == cr.id
            )
        ).all()
        by_name = {f.field_name: f for f in ffs}
        assert by_name["codigo"].raw_value == "XYZ"
        reloaded = s.get(Document, doc_id)
        # codigo válido (único obrigatório) → score 1.0 → permanece PROCESSANDO
        assert reloaded.state == DocState.PROCESSANDO
        assert reloaded.last_completed_step == CLASSIFIED_STEP


async def test_forced_template_inexistente_raises(schema_engine: Engine) -> None:
    """Template forçado inexistente → ValueError (antes de qualquer persistência)."""
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False):
        with get_session(schema_engine) as s:
            doc = _seed_doc(
                s,
                content_hash="B" * 64,
                fields_json=_pairs_json([("x", "1")]),
                full_text="documento qualquer",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            with pytest.raises(ValueError, match="Template forçado inexistente"):
                await classify_stage(
                    s, content_hash="B" * 64, forced_template_id=999999
                )

    with get_session(schema_engine) as s:
        # nada persistido: nenhum ClassificationResult criado
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is None


async def test_forced_template_confidence_none(schema_engine: Engine) -> None:
    """Sem score de matcher quando o template é forçado (confidence do matcher None)."""
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False):
        with get_session(schema_engine) as s:
            tpl = _template(
                s,
                name="Nota Fiscal",
                doc_type="nota_fiscal",
                signals=["nota fiscal"],
                fields=[("numero_nota", "texto", True)],
            )
            tpl_id = tpl.id
            doc = _seed_doc(
                s,
                content_hash="C" * 64,
                fields_json=_pairs_json([("numero_nota", "42")]),
                full_text="NOTA FISCAL numero_nota 42",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(
                s, content_hash="C" * 64, forced_template_id=tpl_id
            )
        assert result.matched is True
        assert result.template_id == tpl_id

    with get_session(schema_engine) as s:
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        # confidence do matcher é None no caminho forçado (não houve casamento auto)
        assert cr.confidence is None
        # mas confidence_score (qualidade de extração) É calculado e persistido
        assert cr.confidence_score is not None

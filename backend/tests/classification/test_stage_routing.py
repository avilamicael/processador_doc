"""Roteamento de estado do classify_stage por score (Fase 5, Plan 02).

Cobre o `<behavior>` do Plan 02 — Task 1 (parte B):
- score < review_confidence_threshold → transita para EM_REVISAO;
- obrigatório inválido (DV CNPJ falho) força EM_REVISAO mesmo com score alto (D-04);
- score >= limiar e nenhum obrigatório inválido → PROCESSANDO + last_completed_step
  "classificado" (NUNCA CONCLUIDO — Open Q1 resolvida; CONCLUIDO só via approve humano);
- `confidence_score` persistido em `classification_results` no commit atômico.

A OpenAI é mockada via respx — 0 token (os casos abaixo casam pelo matcher local ou
preenchem por par determinístico, sem chamada paga).
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
    Template,
    TemplateField,
)
from app.storage.db import get_session


@pytest.fixture(autouse=True)
def _openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chave OpenAI fictícia + limiar de revisão default determinístico (0.8)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-routing")
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


async def test_routes_to_em_revisao_below_threshold(schema_engine: Engine) -> None:
    """Score < review_confidence_threshold → transita para EM_REVISAO.

    Template com 2 obrigatórios; só 1 presente e válido → score 0.5 < 0.8. O
    obrigatório ausente é texto (sem chamar IA de faltantes? — `valor_total`
    obrigatório ausente dispara fill_missing_fields). Para manter custo-zero e o
    score baixo de forma determinística, marcamos AMBOS como faltantes via texto
    presente só num: usamos campos de tipo `texto` e deixamos a IA devolver vazio.
    """
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        # IA de faltantes devolve nada → valor_total permanece ausente/inválido.
        from httpx import Response as HxResponse

        from tests.classification.test_stage import _envelope

        with get_session(schema_engine) as s:
            _template(
                s,
                name="Nota Fiscal",
                doc_type="nota_fiscal",
                signals=["nota fiscal", "numero_nota"],
                fields=[
                    ("numero_nota", "texto", True),
                    ("valor_total", "texto", True),
                ],
            )
            doc = _seed_doc(
                s,
                content_hash="1" * 64,
                fields_json=_pairs_json([("numero_nota", "12345")]),
                full_text="NOTA FISCAL numero_nota 12345",
            )
            doc_id = doc.id

        router.post("/responses").mock(
            return_value=HxResponse(200, json=_envelope({"fields": []}, "resp_empty"))
        )

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="1" * 64)
        assert result.matched is True

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.EM_REVISAO
        assert reloaded.last_completed_step == CLASSIFIED_STEP
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr.confidence_score == pytest.approx(0.5)


async def test_routes_to_ready_above_threshold(schema_engine: Engine) -> None:
    """Score >= threshold e sem obrigatório inválido → PROCESSANDO+classificado
    (NUNCA CONCLUIDO — Open Q1 resolvida)."""
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            _template(
                s,
                name="Nota Fiscal",
                doc_type="nota_fiscal",
                signals=["nota fiscal", "numero_nota"],
                fields=[
                    ("numero_nota", "texto", True),
                    ("valor_total", "moeda", True),
                ],
            )
            doc = _seed_doc(
                s,
                content_hash="2" * 64,
                fields_json=_pairs_json(
                    [("numero_nota", "12345"), ("valor_total", "1.234,56")]
                ),
                full_text="NOTA FISCAL numero_nota 12345",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="2" * 64)
        assert result.matched is True
        assert route.call_count == 0

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        # passou: permanece PROCESSANDO + marcador classificado; nunca CONCLUIDO
        assert reloaded.state == DocState.PROCESSANDO
        assert reloaded.last_completed_step == CLASSIFIED_STEP
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr.confidence_score == pytest.approx(1.0)


async def test_invalid_required_forces_em_revisao(schema_engine: Engine) -> None:
    """Obrigatório inválido (DV CNPJ falho) força EM_REVISAO mesmo com score alto (D-04)."""
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            _template(
                s,
                name="Nota Fiscal",
                doc_type="nota_fiscal",
                signals=["nota fiscal", "cnpj_emitente"],
                fields=[("cnpj_emitente", "cpf_cnpj", True)],
            )
            doc = _seed_doc(
                s,
                content_hash="3" * 64,
                # CNPJ com DV inválido → FilledField.valid=False → has_invalid_required
                fields_json=_pairs_json([("cnpj_emitente", "11.111.111/1111-11")]),
                full_text="NOTA FISCAL cnpj_emitente 11.111.111/1111-11",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="3" * 64)
        assert result.matched is True
        assert route.call_count == 0

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        # D-04: obrigatório inválido → revisão (mesmo que o score fosse calculado alto)
        assert reloaded.state == DocState.EM_REVISAO
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        # único obrigatório inválido → score 0.0
        assert cr.confidence_score == pytest.approx(0.0)


async def test_persists_confidence_score(schema_engine: Engine) -> None:
    """confidence_score é gravado em classification_results no commit atômico.

    Template SEM campos obrigatórios → compute_confidence devolve (1.0, False) →
    permanece PROCESSANDO+classificado e confidence_score=1.0 persistido.
    """
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            _template(
                s,
                name="Generico",
                doc_type="generico",
                signals=["documento", "referencia"],
                fields=[("referencia", "texto", False)],
            )
            doc = _seed_doc(
                s,
                content_hash="4" * 64,
                fields_json=_pairs_json([("referencia", "ABC-1")]),
                full_text="documento referencia ABC-1",
                doc_type_guess="generico",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="4" * 64)
        assert result.matched is True
        assert route.call_count == 0

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.PROCESSANDO
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr.confidence_score is not None
        assert cr.confidence_score == pytest.approx(1.0)

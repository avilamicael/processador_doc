"""IA-fallback opt-in no classify_stage (Fase 10, Plano 04 — D-05/D-06).

Toggle GLOBAL `classify_ai_fallback_enabled` (default OFF): quando o matcher local
não casa NENHUM template (confiança 0.0, sem template forçado), o `classify_stage`
— e SOMENTE quando o toggle está ON — chama a IA contra TODOS os templates ANTES
de quarentenar, reusando o caminho de IA existente (`disambiguate`). A decisão de
chamar IA vive no STAGE, nunca no `matcher.decide` (seam D-06).

Prova o `<behavior>` do plano (espelha test_stage.py em forma/garantias):

- OFF (default): doc cujos templates não casam → QUARENTENA direta; `POST /responses`
  `call_count == 0`; ClassificationResult(template_id=None) criado.
- ON + nada casou + IA casa: matcher não casa, `disambiguate` (respx) devolve um
  matched_template_id existente → o doc NÃO vai para quarentena; segue o caminho de
  casamento; Usage(step="classify") persistido; called_ai=True; call_count==1.
- ON + nada casou + IA NÃO casa (matched_template_id=None): doc vai para QUARENTENA,
  MAS o Usage da tentativa É persistido (Pitfall 5: a chamada foi paga); call_count==1.
- ON + forced_template_id presente: o ramo de fallback NÃO dispara (gate
  `forced_template_id is None`); nenhuma chamada de fallback.
- ON mas matcher CASOU: comportamento inalterado (fallback só quando nada casou).

A OpenAI é mockada via respx — 0 token. O toggle é forçado por env + cache_clear.
"""

import json

import pytest
import respx
from httpx import Response as HxResponse
from sqlalchemy import Engine, func, select

from app import config
from app.classification.stage import USAGE_STEP, classify_stage
from app.models import (
    ClassificationResult,
    DocState,
    Document,
    Extraction,
    Template,
    TemplateField,
    Usage,
)
from app.storage.db import get_session


@pytest.fixture(autouse=True)
def _openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chave OpenAI fictícia no env (respx mocka o transporte — 0 token)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fallback")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _set_fallback(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    """Liga/desliga o toggle global via env e invalida o cache de settings."""
    monkeypatch.setenv("CLASSIFY_AI_FALLBACK_ENABLED", "true" if enabled else "false")
    config.get_settings.cache_clear()


def _seed_doc(
    session,
    *,
    content_hash: str,
    fields_json: str,
    full_text: str,
    doc_type_guess: str = "desconhecido",
) -> Document:
    """Cria um Document (bloco) em PROCESSANDO+'extraido' com a sua Extraction."""
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
    """Cria um Template com sinais e campos (name, field_type, required)."""
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
    """Serializa pares (key, value) como list-of-pairs com confidence (Fase 3)."""
    return json.dumps([{"key": k, "value": v, "confidence": 0.9} for k, v in pairs])


def _envelope(structured: dict, resp_id: str) -> dict:
    """Envelope JSON da Responses API que o SDK pós-processa em output_parsed."""
    return {
        "id": resp_id,
        "object": "response",
        "created_at": 0,
        "model": "gpt-4o-2024-08-06",
        "status": "completed",
        "output": [
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(structured),
                        "annotations": [],
                    }
                ],
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "usage": {"input_tokens": 80, "output_tokens": 24, "total_tokens": 104},
        "metadata": {},
    }


async def test_off_quarentena_direta_sem_ia(
    schema_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OFF (default): nada casa → QUARENTENA direta, 0 chamadas, CR(template_id=None)."""
    _set_fallback(monkeypatch, enabled=False)
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            _template(
                s,
                name="Boleto",
                doc_type="boleto",
                signals=["linha digitavel", "beneficiario"],
                fields=[("valor", "moeda", True)],
            )
            doc = _seed_doc(
                s,
                content_hash="1" * 64,
                fields_json=_pairs_json([("algo", "irrelevante")]),
                full_text="documento sem nenhum sinal conhecido",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="1" * 64)

        assert result.matched is False
        assert result.template_id is None
        assert result.called_ai is False
        assert route.call_count == 0  # OFF → quarentena direta, sem IA

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.QUARENTENA
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is not None and cr.template_id is None
        n_usage = s.scalar(
            select(func.count()).select_from(Usage).where(Usage.document_id == doc_id)
        )
        assert n_usage == 0


async def test_on_nada_casou_ia_casa_segue_caminho(
    schema_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ON + nada casou + IA casa → NÃO quarentena; segue casamento; Usage; called_ai."""
    _set_fallback(monkeypatch, enabled=True)
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        with get_session(schema_engine) as s:
            # template cujos sinais NÃO estão no doc (matcher não casa)
            tpl = _template(
                s,
                name="Recibo",
                doc_type="recibo",
                signals=["recibo de pagamento"],
                fields=[("numero", "texto", False)],  # opcional → sem 2ª chamada de IA
            )
            tpl_id = tpl.id
            doc = _seed_doc(
                s,
                content_hash="2" * 64,
                fields_json=_pairs_json([("numero", "1")]),
                full_text="texto sem o sinal do template",
            )
            doc_id = doc.id

        structured = {
            "matched_template_id": tpl_id,
            "confidence": 0.93,
            "reason": "A IA reconheceu o documento como recibo.",
        }
        route = router.post("/responses").mock(
            return_value=HxResponse(200, json=_envelope(structured, "resp_fb_match"))
        )

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="2" * 64)

        assert result.matched is True
        assert result.template_id == tpl_id
        assert result.called_ai is True
        assert route.call_count == 1  # 1 chamada de fallback (campo opcional → sem 2ª)

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        assert reloaded.state != DocState.QUARENTENA
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is not None and cr.template_id == tpl_id
        n_usage = s.scalar(
            select(func.count())
            .select_from(Usage)
            .where(Usage.document_id == doc_id, Usage.step == USAGE_STEP)
        )
        assert n_usage == 1


async def test_on_nada_casou_ia_nao_casa_persiste_usage(
    schema_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ON + nada casou + IA NÃO casa → QUARENTENA, MAS Usage persistido (Pitfall 5)."""
    _set_fallback(monkeypatch, enabled=True)
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        with get_session(schema_engine) as s:
            _template(
                s,
                name="Boleto",
                doc_type="boleto",
                signals=["linha digitavel"],
                fields=[("valor", "moeda", True)],
            )
            doc = _seed_doc(
                s,
                content_hash="3" * 64,
                fields_json=_pairs_json([("algo", "x")]),
                full_text="documento desconhecido sem sinais",
            )
            doc_id = doc.id

        structured = {
            "matched_template_id": None,
            "confidence": 0.0,
            "reason": "Nenhum template corresponde ao documento.",
        }
        route = router.post("/responses").mock(
            return_value=HxResponse(200, json=_envelope(structured, "resp_fb_nomatch"))
        )

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="3" * 64)

        assert result.matched is False
        assert result.template_id is None
        assert result.called_ai is True
        assert route.call_count == 1  # a tentativa de fallback ocorreu (paga)

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.QUARENTENA
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is not None and cr.template_id is None
        # Pitfall 5: a chamada foi paga → Usage(step="classify") DEVE estar persistido
        n_usage = s.scalar(
            select(func.count())
            .select_from(Usage)
            .where(Usage.document_id == doc_id, Usage.step == USAGE_STEP)
        )
        assert n_usage == 1


async def test_on_forced_template_nao_dispara_fallback(
    schema_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ON + forced_template_id → ramo de fallback NÃO dispara (gate forced is None)."""
    _set_fallback(monkeypatch, enabled=True)
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            tpl = _template(
                s,
                name="Nota Fiscal",
                doc_type="nota_fiscal",
                signals=["nota fiscal"],
                fields=[("numero_nota", "texto", False)],
            )
            tpl_id = tpl.id
            doc = _seed_doc(
                s,
                content_hash="4" * 64,
                fields_json=_pairs_json([("numero_nota", "555")]),
                full_text="conteudo qualquer",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(
                s, content_hash="4" * 64, forced_template_id=tpl_id
            )

        assert result.matched is True
        assert result.template_id == tpl_id
        # caminho forçado pula matcher/desempate/fallback → 0 chamadas
        assert route.call_count == 0

    with get_session(schema_engine) as s:
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is not None and cr.template_id == tpl_id


async def test_on_ambiguo_ia_recusa_nao_paga_duas_vezes(
    schema_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WR-01: 2 templates AMBÍGUOS + IA de desempate recusa (null) → paga 1x, não 2x.

    Os 2 templates casam AMBOS o mesmo full_text (confiança 1.0/1.0 → decide
    'ambiguous'). O desempate (D-01) é PAGO 1x e a IA devolve matched_template_id=None
    (recusa). Sem a guarda `not called_ai` no gate do fallback, o doc não-casado
    re-dispararia a IA (call_count==2). COM a guarda: o fallback NÃO re-dispara após
    um desempate ambíguo recusado → call_count==1; o doc vai para QUARENTENA.
    """
    _set_fallback(monkeypatch, enabled=True)
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        with get_session(schema_engine) as s:
            _template(
                s,
                name="Boleto A",
                doc_type="boleto",
                signals=["documento comum"],
                fields=[("valor", "moeda", True)],
            )
            _template(
                s,
                name="Boleto B",
                doc_type="boleto",
                signals=["documento comum"],
                fields=[("valor", "moeda", True)],
            )
            doc = _seed_doc(
                s,
                content_hash="6" * 64,
                fields_json=_pairs_json([("algo", "x")]),
                full_text="este e um documento comum para ambos os templates",
            )
            doc_id = doc.id

        structured = {
            "matched_template_id": None,
            "confidence": 0.0,
            "reason": "A IA não conseguiu desempatar entre os candidatos.",
        }
        route = router.post("/responses").mock(
            return_value=HxResponse(200, json=_envelope(structured, "resp_ambig_null"))
        )

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="6" * 64)

        assert result.matched is False
        assert result.template_id is None
        assert result.called_ai is True
        # desempate pago 1x; o fallback NÃO re-dispara após recusa ambígua (WR-01)
        assert route.call_count == 1

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.QUARENTENA
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is not None and cr.template_id is None
        # exatamente 1 Usage (o desempate pago), nunca 2
        n_usage = s.scalar(
            select(func.count())
            .select_from(Usage)
            .where(Usage.document_id == doc_id, Usage.step == USAGE_STEP)
        )
        assert n_usage == 1


async def test_on_sem_templates_nao_paga_ia(
    schema_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WR-03: nenhum template cadastrado + fallback ON → 0 chamadas pagas; quarentena.

    Sem templates não há nada que a IA possa casar — chamar `disambiguate` contra uma
    lista vazia só queima token e retorna null. A guarda `templates` (lista vazia =
    falsy) impede a chamada: call_count==0, doc em QUARENTENA, sem Usage.
    """
    _set_fallback(monkeypatch, enabled=True)
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            doc = _seed_doc(
                s,
                content_hash="7" * 64,
                fields_json=_pairs_json([("algo", "x")]),
                full_text="documento qualquer sem nenhum template cadastrado",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="7" * 64)

        assert result.matched is False
        assert result.template_id is None
        assert result.called_ai is False
        assert route.call_count == 0  # sem templates → nada paga (WR-03)

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.QUARENTENA
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is not None and cr.template_id is None
        n_usage = s.scalar(
            select(func.count()).select_from(Usage).where(Usage.document_id == doc_id)
        )
        assert n_usage == 0


async def test_on_matcher_casou_comportamento_inalterado(
    schema_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ON mas matcher CASOU → fallback NÃO dispara (só quando nada casou)."""
    _set_fallback(monkeypatch, enabled=True)
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            tpl = _template(
                s,
                name="Nota Fiscal",
                doc_type="nota_fiscal",
                signals=["nota fiscal"],
                fields=[("numero_nota", "texto", False)],
            )
            tpl_id = tpl.id
            doc = _seed_doc(
                s,
                content_hash="5" * 64,
                fields_json=_pairs_json([("numero_nota", "999")]),
                full_text="NOTA FISCAL numero_nota 999",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="5" * 64)

        assert result.matched is True
        assert result.template_id == tpl_id
        assert result.called_ai is False
        assert route.call_count == 0  # matcher resolveu — fallback não dispara

    with get_session(schema_engine) as s:
        n_usage = s.scalar(
            select(func.count()).select_from(Usage).where(Usage.document_id == doc_id)
        )
        assert n_usage == 0

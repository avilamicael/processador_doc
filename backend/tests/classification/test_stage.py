"""classify_stage — idempotente, atômico, quarentena via transition (Plan 05, Task 1).

Prova o `<behavior>` do plano (espelha tests/extraction/test_idempotency.py +
test_persistence.py em forma/garantias):

- casa (sinais fortes): matcher resolve → ClassificationResult(template_id setado),
  FilledFields preenchidos/validados, state PROCESSANDO + last_completed_step=
  "classificado"; SEM tocar a IA (called_ai=False, call_count==0).
- quarentena: nenhum template casa → transition(QUARENTENA) DEPOIS de adicionar o
  ClassificationResult(template_id=None) à sessão → o registro está PERSISTIDO no
  banco (comitado junto pelo transition); nenhum FilledField criado.
- idempotência: 2ª execução com ClassificationResult existente → no-op,
  called_ai=False, ZERO novas chamadas respx (call_count inalterado).
- desempate: zona cinzenta → disambiguate() (respx) decide; 1 Usage(step="classify").
- faltantes: obrigatório sem par → fill_missing_fields() (respx) só p/ faltantes;
  1 Usage; o campo devolvido aparece em FilledField com o field_name CORRETO do
  template (prova do merge D-06 por nome de campo).
- usage: cada chamada paga grava exatamente 1 Usage(step="classify"); custo-zero → 0.
- campo inválido (DV CNPJ falho): FilledField.valid=False + invalid_reason; o
  documento SEGUE (D-10) — NÃO vai para quarentena.

LACUNA CONSCIENTE DE IDEMPOTÊNCIA (v1, RESEARCH Open Question 1): se o stage
falhar ENTRE a chamada paga de desempate e a de faltantes, o retry re-executa
ambas e RE-COBRA o desempate. Isso é ACEITO no v1 (cenário raro) — a rede dura é
a checagem de ClassificationResult ANTES de QUALQUER chamada paga, que cobre o
caso comum (stage já completou). NÃO "corrigir" essa janela como bug: a
atomicidade fim-a-fim entre duas chamadas pagas separadas exigiria persistência
intermediária que complicaria o commit único — decisão de design v1.

A OpenAI é mockada via respx (conftest local) — 0 token. O `confidence` é incluído
em cada par do payload de faltantes (ExtractedField exige — contrato do Plan 03).
"""

import json
from pathlib import Path

import pytest
import respx
from httpx import Response as HxResponse
from sqlalchemy import Engine, func, select

from app import config
from app.classification.stage import (
    CLASSIFIED_STEP,
    USAGE_STEP,
    classify_stage,
)
from app.models import (
    ClassificationResult,
    DocState,
    Document,
    Extraction,
    FilledField,
    Template,
    TemplateField,
    Usage,
)
from app.storage.db import get_session


@pytest.fixture(autouse=True)
def _openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chave OpenAI fictícia no env (respx mocka o transporte — 0 token)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-classify")
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


async def test_casa_sem_ia_preenche_e_valida(schema_engine: Engine) -> None:
    """Sinais fortes p/ 1 template → casa sem IA; FilledFields; PROCESSANDO+classificado."""
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            tpl = _template(
                s,
                name="Nota Fiscal",
                doc_type="nota_fiscal",
                signals=["nota fiscal", "numero_nota"],
                fields=[("numero_nota", "texto", True), ("valor_total", "moeda", True)],
            )
            tpl_id = tpl.id
            doc = _seed_doc(
                s,
                content_hash="a" * 64,
                fields_json=_pairs_json(
                    [("numero_nota", "12345"), ("valor_total", "1.234,56")]
                ),
                full_text="NOTA FISCAL numero_nota 12345",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="a" * 64)

        assert result.matched is True
        assert result.template_id == tpl_id
        assert result.called_ai is False
        assert route.call_count == 0  # matcher resolveu — sem chamada paga

    with get_session(schema_engine) as s:
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is not None and cr.template_id == tpl_id
        ffs = s.scalars(
            select(FilledField).where(
                FilledField.classification_result_id == cr.id
            )
        ).all()
        by_name = {f.field_name: f for f in ffs}
        assert by_name["numero_nota"].raw_value == "12345"
        assert by_name["valor_total"].normalized_value == "1234.56"
        assert all(f.valid for f in ffs)
        # estado terminal correto: PROCESSANDO + marcador "classificado"; nunca CONCLUIDO
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.PROCESSANDO
        assert reloaded.last_completed_step == CLASSIFIED_STEP
        # custo-zero → 0 Usage
        n_usage = s.scalar(
            select(func.count()).select_from(Usage).where(Usage.document_id == doc_id)
        )
        assert n_usage == 0


async def test_quarentena_persiste_classification_result_sem_filled(
    schema_engine: Engine,
) -> None:
    """Nenhum template casa → QUARENTENA via transition; CR(template_id=None) persistido."""
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            # template existe mas seus sinais NÃO estão no documento → quarentena
            _template(
                s,
                name="Boleto",
                doc_type="boleto",
                signals=["linha digitavel", "beneficiario"],
                fields=[("valor", "moeda", True)],
            )
            doc = _seed_doc(
                s,
                content_hash="b" * 64,
                fields_json=_pairs_json([("algo", "irrelevante")]),
                full_text="documento sem nenhum sinal conhecido",
                doc_type_guess="desconhecido",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="b" * 64)

        assert result.matched is False
        assert result.template_id is None
        assert route.call_count == 0  # nenhum sinal → quarentena sem IA

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        # (a) doc em QUARENTENA via transition
        assert reloaded.state == DocState.QUARENTENA
        # marcador NÃO avança para "classificado" (não foi classificado)
        assert reloaded.last_completed_step != CLASSIFIED_STEP
        # (b) ClassificationResult(template_id=None) PERSISTIDO (add ANTES do transition)
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is not None
        assert cr.template_id is None
        # (c) nenhum FilledField no caso quarentena
        ffs = s.scalars(
            select(FilledField).where(
                FilledField.classification_result_id == cr.id
            )
        ).all()
        assert ffs == []


async def test_idempotencia_nao_re_chama_ia(schema_engine: Engine) -> None:
    """2ª execução com ClassificationResult existente → no-op, called_ai=False, 0 nova IA."""
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/responses")
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
                content_hash="c" * 64,
                fields_json=_pairs_json([("numero_nota", "999")]),
                full_text="NOTA FISCAL numero_nota 999",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            r1 = await classify_stage(s, content_hash="c" * 64)
        assert r1.matched is True and r1.template_id == tpl_id

        calls_after_first = route.call_count

        with get_session(schema_engine) as s:
            r2 = await classify_stage(s, content_hash="c" * 64)
        assert r2.called_ai is False
        assert r2.matched is True
        assert r2.template_id == tpl_id
        # 2ª execução NÃO incrementa call_count (não re-cobra) — Pitfall 2 / T-04-13
        assert route.call_count == calls_after_first

    with get_session(schema_engine) as s:
        n_cr = s.scalar(
            select(func.count())
            .select_from(ClassificationResult)
            .where(ClassificationResult.document_id == doc_id)
        )
        assert n_cr == 1  # sem duplicação


async def test_desempate_chama_ia_e_grava_usage(schema_engine: Engine) -> None:
    """Zona cinzenta (2 templates empatados) → disambiguate (respx); 1 Usage(classify)."""
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        # A IA desempata escolhendo o template 1 (matched_template_id apontará p/ ele).
        with get_session(schema_engine) as s:
            tpl_a = _template(
                s,
                name="Nota A",
                doc_type="nota_fiscal",
                signals=["documento fiscal"],
                fields=[("numero", "texto", False)],
            )
            tpl_b = _template(
                s,
                name="Nota B",
                doc_type="nota_fiscal",
                signals=["documento fiscal"],
                fields=[("numero", "texto", False)],
            )
            tpl_a_id = tpl_a.id
            doc = _seed_doc(
                s,
                content_hash="d" * 64,
                fields_json=_pairs_json([("numero", "1")]),
                full_text="documento fiscal generico numero 1",
            )
            doc_id = doc.id

        # respx: disambiguate devolve matched_template_id = tpl_a_id
        structured = {
            "matched_template_id": tpl_a_id,
            "confidence": 0.95,
            "reason": "Sinal do template A predomina.",
        }
        route = router.post("/responses").mock(
            return_value=HxResponse(
                200, json=_envelope(structured, "resp_disambig")
            )
        )

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="d" * 64)

        assert result.matched is True
        assert result.template_id == tpl_a_id
        assert result.called_ai is True
        assert route.call_count == 1  # desempate pago ocorreu
        # tpl_b existe mas não foi o escolhido
        assert result.template_id != tpl_b.id

    with get_session(schema_engine) as s:
        n_usage = s.scalar(
            select(func.count())
            .select_from(Usage)
            .where(Usage.document_id == doc_id, Usage.step == USAGE_STEP)
        )
        assert n_usage == 1  # exatamente 1 Usage(step="classify") por chamada paga


async def test_faltantes_chama_ia_e_merge_por_nome(schema_engine: Engine) -> None:
    """Obrigatório sem par → fill_missing_fields (respx); merge pelo field_name do template."""
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        with get_session(schema_engine) as s:
            tpl = _template(
                s,
                name="Nota Fiscal",
                doc_type="nota_fiscal",
                signals=["nota fiscal"],
                fields=[
                    ("numero_nota", "texto", True),
                    ("valor_total", "moeda", True),  # ESTE faltará → IA preenche
                ],
            )
            tpl_id = tpl.id
            doc = _seed_doc(
                s,
                content_hash="e" * 64,
                # só numero_nota presente; valor_total ausente (obrigatório)
                fields_json=_pairs_json([("numero_nota", "777")]),
                full_text="NOTA FISCAL numero_nota 777",
            )
            doc_id = doc.id

        # A IA devolve o campo faltante usando EXATAMENTE o field_name do template.
        structured = {
            "fields": [
                {"key": "valor_total", "value": "2.000,00", "confidence": 0.88},
            ]
        }
        route = router.post("/responses").mock(
            return_value=HxResponse(200, json=_envelope(structured, "resp_fields"))
        )

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="e" * 64)

        assert result.matched is True
        assert result.template_id == tpl_id
        assert result.called_ai is True
        assert route.call_count == 1  # fill_missing_fields pago ocorreu

    with get_session(schema_engine) as s:
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        ffs = s.scalars(
            select(FilledField).where(
                FilledField.classification_result_id == cr.id
            )
        ).all()
        by_name = {f.field_name: f for f in ffs}
        # prova do merge D-06 por NOME: o valor da IA aparece sob o field_name correto
        assert "valor_total" in by_name
        assert by_name["valor_total"].raw_value == "2.000,00"
        assert by_name["valor_total"].normalized_value == "2000.00"
        # 1 Usage(step="classify")
        n_usage = s.scalar(
            select(func.count())
            .select_from(Usage)
            .where(Usage.document_id == doc_id, Usage.step == USAGE_STEP)
        )
        assert n_usage == 1


async def test_campo_invalido_marca_sem_quarentena(schema_engine: Engine) -> None:
    """DV de CNPJ falho → FilledField.valid=False; documento SEGUE (D-10), não quarentena."""
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            tpl = _template(
                s,
                name="Nota Fiscal",
                doc_type="nota_fiscal",
                signals=["nota fiscal"],
                fields=[("cnpj_emitente", "cpf_cnpj", True)],
            )
            tpl_id = tpl.id
            doc = _seed_doc(
                s,
                content_hash="f" * 64,
                # CNPJ com DV inválido → validate_field marca valid=False
                fields_json=_pairs_json([("cnpj_emitente", "11.111.111/1111-11")]),
                full_text="NOTA FISCAL cnpj_emitente 11.111.111/1111-11",
            )
            doc_id = doc.id

        with get_session(schema_engine) as s:
            result = await classify_stage(s, content_hash="f" * 64)

        assert result.matched is True
        assert result.template_id == tpl_id
        assert route.call_count == 0  # campo presente — sem chamada de faltantes

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        # documento NÃO foi para quarentena (D-10: marca, não bloqueia)
        assert reloaded.state == DocState.PROCESSANDO
        assert reloaded.last_completed_step == CLASSIFIED_STEP
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        ff = s.scalar(
            select(FilledField).where(
                FilledField.classification_result_id == cr.id,
                FilledField.field_name == "cnpj_emitente",
            )
        )
        assert ff.valid is False
        assert ff.invalid_reason is not None


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

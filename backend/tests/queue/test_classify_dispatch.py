"""Fiação na fila do step="classify" + sweep de legados (Plan 05, Task 2).

Prova o `<behavior>` (espelha tests/queue/test_dispatch.py + tests/extraction/
test_enqueue_sweep.py):

- step="classify" → o worker despacha chamando `classify_stage` como COROUTINE
  (await direto, NÃO to_thread); persiste o ClassificationResult e marca o job done.
- _fail_for_step roteia "classify" por content_hash (igual a extract).
- enqueue_pending_classifications: Documents PROCESSANDO + last_completed_step=
  "extraido" SEM ClassificationResult → enfileira classify; idempotente (rodar 2x
  não duplica); cobre legados; Document já classificado NÃO é re-enfileirado.

A OpenAI é mockada via respx — 0 token. O cenário "casa sem IA" usa um template
cujos sinais batem com o documento (matcher resolve, called_ai=False).
"""

import asyncio
import json

import pytest
import respx
from httpx import Response as HxResponse
from sqlalchemy import Engine, select

from app import config
from app.models import (
    ClassificationResult,
    DocState,
    Document,
    Extraction,
    Job,
    JobStatus,
)
from app.queue import repo, worker
from app.storage.db import get_session

HASH_A = "a" * 64
HASH_B = "b" * 64


@pytest.fixture(autouse=True)
def _openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-classify-worker")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _seed_extracted_block(
    session, *, content_hash: str, with_template: bool
) -> Document:
    """Cria um bloco PROCESSANDO+'extraido' com Extraction; opcionalmente um template
    cujos sinais batem (matcher casa sem IA)."""
    from app.models import Template, TemplateField

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
            fields_json=json.dumps(
                [{"key": "numero_nota", "value": "123", "confidence": 0.9}]
            ),
            full_text="NOTA FISCAL numero_nota 123",
            doc_type_guess="nota_fiscal",
            doc_type_confidence=0.8,
            route="native_text",
        )
    )
    if with_template:
        tpl = Template(
            name="Nota Fiscal",
            doc_type="nota_fiscal",
            signals_json=json.dumps(["nota fiscal", "numero_nota"]),
        )
        session.add(tpl)
        session.commit()
        session.add(
            TemplateField(
                template_id=tpl.id, name="numero_nota", field_type="texto", required=True
            )
        )
    session.commit()
    return doc


def test_dispatch_classify_chama_stage_e_marca_done(schema_engine: Engine) -> None:
    """step='classify' → await classify_stage no loop; ClassificationResult; job done."""
    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        route = router.post("/responses")
        with get_session(schema_engine) as s:
            doc = _seed_extracted_block(s, content_hash=HASH_A, with_template=True)
            doc_id = doc.id

        with get_session(schema_engine) as s:
            repo.enqueue(
                s,
                original_hash=HASH_A,
                step="classify",
                payload=json.dumps({"content_hash": HASH_A}),
            )

        processed = asyncio.run(worker._run_once(schema_engine))
        assert processed is True
        # matcher resolveu (sinais fortes) → nenhuma chamada paga
        assert route.call_count == 0

    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == HASH_A))
        assert job.status == JobStatus.DONE
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr is not None and cr.template_id is not None
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.PROCESSANDO
        assert reloaded.last_completed_step == "classificado"


def test_dispatch_classify_esgota_retries_leva_documento_a_falha(
    schema_engine: Engine, monkeypatch
) -> None:
    """classify falhando com retries esgotados → Document (por content_hash) a FALHA."""
    with get_session(schema_engine) as s:
        doc = _seed_extracted_block(s, content_hash=HASH_A, with_template=False)
        doc_id = doc.id

    async def _boom(session, *, content_hash):  # noqa: ANN001
        raise RuntimeError("falha simulada de classificação")

    monkeypatch.setattr(worker, "classify_stage", _boom)

    with get_session(schema_engine) as s:
        repo.enqueue(
            s,
            original_hash=HASH_A,
            step="classify",
            payload=json.dumps({"content_hash": HASH_A}),
            max_attempts=1,
        )

    asyncio.run(worker._run_once(schema_engine))

    with get_session(schema_engine) as s:
        job = s.scalar(select(Job).where(Job.original_hash == HASH_A))
        assert job.status == JobStatus.FAILED
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.FALHA


def test_sweep_classify_enfileira_pendentes(schema_engine: Engine) -> None:
    """Cada Document 'extraido' sem ClassificationResult → job (content_hash, 'classify')."""
    with get_session(schema_engine) as s:
        _seed_extracted_block(s, content_hash=HASH_A, with_template=False)
        _seed_extracted_block(s, content_hash=HASH_B, with_template=False)

    with get_session(schema_engine) as s:
        n = worker.enqueue_pending_classifications(s)
    assert n == 2

    with get_session(schema_engine) as s:
        jobs = s.scalars(select(Job).where(Job.step == "classify")).all()
        hashes = {j.original_hash for j in jobs}
        assert hashes == {HASH_A, HASH_B}
        for j in jobs:
            assert json.loads(j.payload)["content_hash"] == j.original_hash


def test_sweep_classify_idempotente(schema_engine: Engine) -> None:
    """Rodar 2x não duplica jobs (UNIQUE uq_jobs_hash_step + enqueue no-op)."""
    with get_session(schema_engine) as s:
        _seed_extracted_block(s, content_hash=HASH_A, with_template=False)

    with get_session(schema_engine) as s:
        first = worker.enqueue_pending_classifications(s)
    with get_session(schema_engine) as s:
        second = worker.enqueue_pending_classifications(s)

    assert first == 1
    assert second == 0

    with get_session(schema_engine) as s:
        jobs = s.scalars(
            select(Job).where(Job.original_hash == HASH_A, Job.step == "classify")
        ).all()
        assert len(jobs) == 1


def test_sweep_classify_ignora_ja_classificado(schema_engine: Engine) -> None:
    """Document que já tem ClassificationResult NÃO é re-enfileirado (não re-cobra)."""
    with get_session(schema_engine) as s:
        doc = _seed_extracted_block(s, content_hash=HASH_A, with_template=False)
        s.add(
            ClassificationResult(
                document_id=doc.id, template_id=None, confidence=None
            )
        )
        s.commit()

    with get_session(schema_engine) as s:
        n = worker.enqueue_pending_classifications(s)
    assert n == 0

    with get_session(schema_engine) as s:
        assert s.scalars(select(Job).where(Job.step == "classify")).all() == []


def test_sweep_classify_ignora_estado_errado(schema_engine: Engine) -> None:
    """Document que NÃO está 'extraido' (ainda aguardando_extracao) não é enfileirado."""
    with get_session(schema_engine) as s:
        doc = Document(
            content_hash=HASH_A,
            original_filename="x.pdf",
            state=DocState.PROCESSANDO,
            last_completed_step="aguardando_extracao",
        )
        s.add(doc)
        s.commit()

    with get_session(schema_engine) as s:
        n = worker.enqueue_pending_classifications(s)
    assert n == 0


def test_fail_for_step_classify_por_content_hash(schema_engine: Engine) -> None:
    """_fail_for_step roteia CLASSIFY_STEP por content_hash (igual a extract)."""
    with get_session(schema_engine) as s:
        doc = _seed_extracted_block(s, content_hash=HASH_A, with_template=False)
        doc_id = doc.id

    worker._fail_for_step(schema_engine, step=worker.CLASSIFY_STEP, original_hash=HASH_A)

    with get_session(schema_engine) as s:
        reloaded = s.get(Document, doc_id)
        assert reloaded.state == DocState.FALHA


def test_classify_disambiguate_via_respx(schema_engine: Engine) -> None:
    """Cenário com IA: zona cinzenta despachada pelo worker → disambiguate via respx."""
    from app.models import Template, TemplateField

    with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
        with get_session(schema_engine) as s:
            # dois templates empatados (mesmo sinal) → ambiguous → IA desempata
            ids = []
            for name in ("Nota A", "Nota B"):
                tpl = Template(
                    name=name,
                    doc_type="nota_fiscal",
                    signals_json=json.dumps(["documento fiscal"]),
                )
                s.add(tpl)
                s.commit()
                s.add(
                    TemplateField(
                        template_id=tpl.id, name="numero", field_type="texto", required=False
                    )
                )
                s.commit()
                ids.append(tpl.id)
            doc = Document(
                content_hash=HASH_A,
                original_filename="x.pdf",
                state=DocState.PROCESSANDO,
                last_completed_step="extraido",
            )
            s.add(doc)
            s.commit()
            s.add(
                Extraction(
                    document_id=doc.id,
                    fields_json=json.dumps(
                        [{"key": "numero", "value": "1", "confidence": 0.9}]
                    ),
                    full_text="documento fiscal generico",
                    doc_type_guess="nota_fiscal",
                    doc_type_confidence=0.8,
                    route="native_text",
                )
            )
            s.commit()
            doc_id = doc.id
            chosen = ids[0]

        structured = {
            "matched_template_id": chosen,
            "confidence": 0.95,
            "reason": "Sinal do A predomina.",
        }
        route = router.post("/responses").mock(
            return_value=HxResponse(200, json=_envelope(structured))
        )

        with get_session(schema_engine) as s:
            repo.enqueue(
                s,
                original_hash=HASH_A,
                step="classify",
                payload=json.dumps({"content_hash": HASH_A}),
            )

        asyncio.run(worker._run_once(schema_engine))
        assert route.call_count == 1

    with get_session(schema_engine) as s:
        cr = s.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == doc_id
            )
        )
        assert cr.template_id == chosen


def _envelope(structured: dict) -> dict:
    return {
        "id": "resp_worker",
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

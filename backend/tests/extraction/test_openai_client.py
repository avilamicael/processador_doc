"""Testes do `openai_client` (Fase 3) — Responses API + _unwrap + tokens.

OpenAI mockado via respx (fixture `mock_openai` do conftest) — NENHUM token gasto.
Cobre o `<behavior>` do Task 3:
- extract_from_text / extract_from_image_pages → (ExtractionResult, usage)
- recusa (`output_parsed is None`) → `ExtractionRefused` (não AttributeError, não loop)
- mapeamento de tokens: input_tokens→prompt, output_tokens→completion
- a chave OpenAI NUNCA aparece em log/mensagem de erro (T-03-03)
"""

import logging

import pytest
import respx
from httpx import Response as HxResponse

from app.extraction import openai_client
from app.extraction.openai_client import ExtractionRefused
from app.extraction.schema import ExtractionResult

# Chave fictícia usada pelos testes; o respx mocka o transporte, nada é gasto.
_FAKE_KEY = "sk-test-CHAVE-SECRETA-NAO-DEVE-VAZAR-1234567890"


@pytest.fixture(autouse=True)
def _patch_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garante uma chave conhecida em Settings p/ asserir que ela nunca vaza."""
    from app.config import Settings, get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)
    # força recomputo do Settings com a chave de teste
    monkeypatch.setattr("app.config.get_settings", lambda: Settings())
    yield
    get_settings.cache_clear()


# --- caminho de sucesso: texto ---


async def test_extract_from_text_devolve_resultado_e_usage(
    mock_openai: respx.MockRouter,
) -> None:
    result, usage = await openai_client.extract_from_text("Nota Fiscal 12345")
    assert isinstance(result, ExtractionResult)
    assert result.doc_type_guess == "nota_fiscal"
    assert any(f.key == "cnpj_emitente" for f in result.fields)
    # mapeamento de tokens: input→prompt, output→completion
    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 64


# --- caminho de sucesso: visão ---


async def test_extract_from_image_pages_devolve_resultado_e_usage(
    mock_openai: respx.MockRouter,
    png_bytes: bytes,
) -> None:
    result, usage = await openai_client.extract_from_image_pages([png_bytes, png_bytes])
    assert isinstance(result, ExtractionResult)
    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 64
    # a requisição enviou as duas páginas como input_image
    request = mock_openai.calls.last.request
    body = request.content.decode()
    assert body.count("input_image") == 2
    assert "data:image/png;base64," in body


# --- recusa ---


async def test_recusa_levanta_extraction_refused(
    mock_openai: respx.MockRouter,
    openai_refusal_payload: dict,
) -> None:
    mock_openai.post("/responses").mock(
        return_value=HxResponse(200, json=openai_refusal_payload)
    )
    with pytest.raises(ExtractionRefused):
        await openai_client.extract_from_text("conteudo qualquer")


async def test_recusa_loga_motivo_mas_nao_a_chave(
    mock_openai: respx.MockRouter,
    openai_refusal_payload: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_openai.post("/responses").mock(
        return_value=HxResponse(200, json=openai_refusal_payload)
    )
    with caplog.at_level(logging.INFO), pytest.raises(ExtractionRefused) as exc:
        await openai_client.extract_from_text("conteudo qualquer")
    # o motivo do refusal pode ser logado/exposto...
    combined = caplog.text + str(exc.value)
    # ...mas a CHAVE OpenAI NUNCA (T-03-03).
    assert _FAKE_KEY not in combined


# --- segredo nunca vaza, mesmo no caminho de sucesso ---


async def test_chave_nunca_aparece_em_logs_no_sucesso(
    mock_openai: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        await openai_client.extract_from_text("Nota Fiscal 12345")
    assert _FAKE_KEY not in caplog.text

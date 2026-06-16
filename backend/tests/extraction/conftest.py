"""Fixtures de extração (Fase 3, Wave 0) — base reusável dos Plans 02-04.

Fornece:
- `openai_success_payload` / `openai_refusal_payload`: JSON da Responses API que
  o respx devolve, produzindo respectivamente um `output_parsed` válido
  (`ExtractionResult`) e um `output_parsed is None` (recusa do modelo, Pitfall 2).
- `mock_openai`: fixture respx que intercepta `POST /v1/responses` e devolve o
  payload de sucesso por padrão; reconfigurável para a variante de recusa.
- `text_pdf_bytes` / `scanned_pdf_bytes`: bytes de PDF sintético COM texto nativo
  (caminho barato) e SEM texto (escaneado → força o caminho visão), gerados com
  `fitz` (PyMuPDF).
- `png_bytes` / `jpeg_bytes`: bytes de imagem mínima — caminho magic-bytes do
  Plan 02/03 (imagem ingerida como bloco cru, sem extensão no CAS).

A chave passada ao `AsyncOpenAI` nestes testes é fictícia ("sk-test") — nenhum
token é gasto; o respx mocka o transporte HTTP.
"""

import json
from collections.abc import Iterator

import fitz  # PyMuPDF
import pytest
import respx
from httpx import Response as HxResponse

# --- Payloads da Responses API (formato que o SDK pós-processa em output_parsed) ---

@pytest.fixture
def openai_success_payload() -> dict:
    """JSON de uma resposta bem-sucedida com Structured Output válido.

    Quando devolvido pelo respx, `client.responses.parse(text_format=ExtractionResult)`
    popula `response.output_parsed` com uma instância de `ExtractionResult`.
    """
    structured = {
        "fields": [
            {"key": "cnpj_emitente", "value": "12.345.678/0001-90", "confidence": 0.92},
            {"key": "valor_total", "value": "1.234,56", "confidence": 0.88},
        ],
        "full_text": "Documento sintético de teste — nota fiscal exemplo.",
        "doc_type_guess": "nota_fiscal",
        "doc_type_confidence": 0.8,
    }
    return {
        "id": "resp_success",
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
        "usage": {"input_tokens": 120, "output_tokens": 64, "total_tokens": 184},
        "metadata": {},
    }


@pytest.fixture
def openai_refusal_payload() -> dict:
    """JSON de uma RECUSA do modelo → `output_parsed is None` (Pitfall 2).

    O Plan 03/04 trata isso como falha de extração (fila faz backoff → FALHA, D-08).
    """
    return {
        "id": "resp_refusal",
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
                        "type": "refusal",
                        "refusal": "Não posso ajudar com esse conteúdo.",
                    }
                ],
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "usage": {"input_tokens": 12, "output_tokens": 6, "total_tokens": 18},
        "metadata": {},
    }


@pytest.fixture
def mock_openai(openai_success_payload: dict) -> Iterator[respx.MockRouter]:
    """Intercepta `POST /v1/responses` e devolve o payload de sucesso por padrão.

    Para exercitar a variante de recusa, reconfigurar a rota dentro do teste:

        mock_openai.post("/responses").mock(
            return_value=HxResponse(200, json=openai_refusal_payload)
        )
    """
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/responses").mock(
            return_value=HxResponse(200, json=openai_success_payload)
        )
        yield router


# --- PDFs / imagem sintéticos (fitz) ---

@pytest.fixture
def text_pdf_bytes() -> bytes:
    """PDF de uma página COM texto nativo extraível (caminho barato native_text)."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Nota Fiscal numero 12345 - CNPJ 12.345.678/0001-90 - Valor 1.234,56",
    )
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def scanned_pdf_bytes() -> bytes:
    """PDF de uma página SEM texto (só imagem) — força o caminho visão."""
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 64, 64))
    pix.clear_with(255)
    page.insert_image(fitz.Rect(0, 0, 64, 64), pixmap=pix)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def png_bytes() -> bytes:
    """Bytes de um PNG mínimo (magic \\x89PNG) — caminho imagem direto (visão)."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 32))
    pix.clear_with(200)
    return pix.tobytes("png")


@pytest.fixture
def jpeg_bytes() -> bytes:
    """Bytes de um JPEG mínimo (magic \\xFF\\xD8) — caminho imagem direto (visão)."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 32))
    pix.clear_with(200)
    return pix.tobytes("jpeg")

"""Fixtures locais dos testes de fila que exercitam o caminho de extração.

O `mock_openai` (e os payloads) vivem em `tests/extraction/conftest.py`, fora do
escopo de `tests/queue/`. Aqui reexpomos um router respx mínimo que intercepta
`POST /v1/responses` com uma resposta de sucesso da Responses API, para o dispatch
de `step="extract"` rodar sem gastar token.
"""

import json
from collections.abc import Iterator

import pytest
import respx
from httpx import Response as HxResponse


def _success_payload() -> dict:
    """JSON de resposta bem-sucedida (output_parsed → ExtractionResult válido)."""
    structured = {
        "fields": [
            {"key": "cnpj_emitente", "value": "12.345.678/0001-90", "confidence": 0.9}
        ],
        "full_text": "Documento sintético para o teste de dispatch da fila.",
        "doc_type_guess": "nota_fiscal",
        "doc_type_confidence": 0.8,
    }
    return {
        "id": "resp_queue",
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
        "usage": {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
        "metadata": {},
    }


@pytest.fixture
def mock_openai() -> Iterator[respx.MockRouter]:
    """Intercepta `POST /v1/responses` devolvendo o payload de sucesso por padrão."""
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/responses").mock(
            return_value=HxResponse(200, json=_success_payload())
        )
        yield router

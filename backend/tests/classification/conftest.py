"""Fixtures de classificação (Fase 4, Wave 0) — base reusável dos Plans seguintes.

Espelha tests/extraction/conftest.py, mas para o **desempate por IA** da
classificação (Responses API, `POST /v1/responses`). Fornece:
- `openai_classify_match_payload`: JSON da Responses API que produz um
  `output_parsed` válido apontando o template casado (matched_template_id /
  confidence / reason) — caminho "a IA desempatou e casou".
- `openai_classify_no_match_payload`: variante em que a IA NÃO casa nenhum
  template (matched_template_id null) → quarentena (template_id null, D-03).
- `openai_classify_fields_payload`: variante com a lista de campos preenchidos
  (list-of-pairs raw/normalized — strict-safe como na extração).
- `mock_openai_classify`: fixture respx que intercepta `POST /v1/responses` e
  devolve o payload de "casou" por padrão; reconfigurável para as variantes.

A chave passada ao `AsyncOpenAI` nestes testes é fictícia ("sk-test") — nenhum
token é gasto; o respx mocka o transporte HTTP. Os helpers de PDF/imagem vivem em
tests/extraction/conftest.py; importar de lá quando necessário (sem duplicar).
"""

import json
from collections.abc import Iterator

import pytest
import respx
from httpx import Response as HxResponse


def _responses_envelope(structured: dict, *, resp_id: str) -> dict:
    """Monta o envelope JSON da Responses API que o SDK pós-processa em
    `output_parsed` (mesma forma usada em tests/extraction/conftest.py)."""
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


@pytest.fixture
def openai_classify_match_payload() -> dict:
    """Desempate por IA que CASA um template (matched_template_id + confiança)."""
    structured = {
        "matched_template_id": 1,
        "confidence": 0.91,
        "reason": "Cabeçalho 'NOTA FISCAL' e chave de 44 dígitos batem com o template.",
    }
    return _responses_envelope(structured, resp_id="resp_classify_match")


@pytest.fixture
def openai_classify_no_match_payload() -> dict:
    """Desempate por IA que NÃO casa nenhum template → quarentena (D-03)."""
    structured = {
        "matched_template_id": None,
        "confidence": 0.0,
        "reason": "Nenhum sinal identificador dos templates cadastrados foi encontrado.",
    }
    return _responses_envelope(structured, resp_id="resp_classify_no_match")


@pytest.fixture
def openai_classify_fields_payload() -> dict:
    """Campos preenchidos pela IA (list-of-pairs strict-safe — raw/normalized)."""
    structured = {
        "fields": [
            {"key": "numero_nota", "value": "12345"},
            {"key": "valor_total", "value": "1.234,56"},
        ]
    }
    return _responses_envelope(structured, resp_id="resp_classify_fields")


@pytest.fixture
def mock_openai_classify(
    openai_classify_match_payload: dict,
) -> Iterator[respx.MockRouter]:
    """Intercepta `POST /v1/responses` e devolve o payload de "casou" por padrão.

    Para exercitar variantes, reconfigurar a rota dentro do teste:

        mock_openai_classify.post("/responses").mock(
            return_value=HxResponse(200, json=openai_classify_no_match_payload)
        )
    """
    with respx.mock(base_url="https://api.openai.com/v1") as router:
        router.post("/responses").mock(
            return_value=HxResponse(200, json=openai_classify_match_payload)
        )
        yield router

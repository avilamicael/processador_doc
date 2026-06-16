"""Cliente OpenAI da extração (Fase 3) — Responses API + Structured Outputs.

Wrapper `AsyncOpenAI` sobre a **Responses API** (`client.responses.parse`) com o
schema Pydantic `ExtractionResult` como `text_format` (Structured Outputs). Isola a
única integração externa da fase atrás de funções de módulo (estilo `cas.py`, sem
classe), prontas para o `extract_stage` (Plan 03) orquestrar.

Garantias materializadas (Critical Failure Modes da AI-SPEC §1):
- **Segredo nunca logado (CFM 5 / T-03-03):** a `openai_api_key` é `SecretStr`;
  `.get_secret_value()` é chamado SÓ no ponto de criação do `AsyncOpenAI`. Nem a
  chave nem o conteúdo do documento aparecem em log ou exceção.
- **Recusa tratada (CFM / Pitfall 2 / D-08):** `response.output_parsed is None` é
  RECUSA do modelo → `_unwrap` levanta `ExtractionRefused` logando só o motivo do
  bloco `refusal` (metadado), nunca a chave nem o conteúdo. NÃO há retry aqui — o
  backoff é da fila (Plan 04); a recusa apenas levanta para cair no caminho de FALHA.
- **Tokens para cobrança (D-10):** o `usage` da Responses API expõe
  `input_tokens`/`output_tokens`; o modelo `Usage` usa `prompt_tokens`/
  `completion_tokens` — mapeamos **input→prompt, output→completion** num
  `ExtractionUsage` tipado, devolvido ao caller para gravar.

Disciplina de prompt (AI-SPEC §4b): `instructions=` é o system prompt FIXO
("extraia TODOS os pares dado→valor, o texto integral e um palpite de tipo com
confiança; não invente campos"). SEM few-shot inline — anti-padrão p/ motor
genérico (enviesaria para os tipos do exemplo).
"""

import base64
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import get_settings
from app.extraction.schema import ExtractionResult

logger = logging.getLogger(__name__)

# System prompt FIXO (= instructions da Responses API). Genérico por desenho
# (D-01/D-02): sem citar tipos específicos nem exemplos (few-shot enviesaria).
SYSTEM_INSTRUCTIONS = (
    "Você extrai dados de documentos. Devolva TODOS os pares dado->valor que "
    "encontrar, o texto integral lido e um palpite do tipo de documento com "
    "confiança. Não invente campos: só o que está literalmente no documento."
)


class ExtractionRefused(Exception):
    """O modelo RECUSOU a extração (`output_parsed is None`, Pitfall 2 / D-08).

    Tratada como falha de extração: a fila (Plan 04) faz retry/backoff e, ao
    esgotar, leva o documento a FALHA. A mensagem traz só o MOTIVO da recusa
    (metadado) — nunca a chave nem o conteúdo do documento.
    """


@dataclass(frozen=True)
class ExtractionUsage:
    """Tokens da chamada, já mapeados para o vocabulário do modelo `Usage` (D-10).

    A Responses API usa `input_tokens`/`output_tokens`; o modelo `Usage` (Fase 1)
    usa `prompt_tokens`/`completion_tokens`. Mapeamento: input→prompt, output→completion.
    """

    prompt_tokens: int
    completion_tokens: int


def _client() -> AsyncOpenAI:
    """Cria o cliente async. `.get_secret_value()` SÓ aqui (CFM 5 / T-03-03)."""
    settings = get_settings()
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    return AsyncOpenAI(api_key=api_key)


def _map_usage(response) -> ExtractionUsage:
    """Mapeia o usage da Responses API → ExtractionUsage (input→prompt, output→completion)."""
    usage = response.usage
    return ExtractionUsage(
        prompt_tokens=usage.input_tokens,
        completion_tokens=usage.output_tokens,
    )


def _unwrap(response) -> ExtractionResult:
    """Devolve o `ExtractionResult` tipado ou levanta `ExtractionRefused` na recusa.

    `response.output_parsed` é `None` quando o modelo recusou (Pitfall 2). Recupera
    o motivo do bloco `refusal` (se houver) para o log/exceção — SÓ o motivo,
    NUNCA a chave nem o conteúdo do documento (CFM 5).
    """
    parsed = response.output_parsed
    if parsed is None:
        reason = _refusal_reason(response)
        logger.info("Extração recusada pelo modelo: %s", reason)
        raise ExtractionRefused(reason)
    return parsed


def _refusal_reason(response) -> str:
    """Extrai o texto do bloco `refusal` da resposta, se houver (metadado seguro)."""
    for item in getattr(response, "output", None) or []:
        for block in getattr(item, "content", None) or []:
            refusal = getattr(block, "refusal", None)
            if refusal:
                return str(refusal)
    return "recusa sem motivo declarado"


async def extract_from_text(native_text: str) -> tuple[ExtractionResult, ExtractionUsage]:
    """Caminho TEXTO NATIVO (barato): 1 bloco `input_text` → (resultado, usage)."""
    settings = get_settings()
    client = _client()
    response = await client.responses.parse(
        model=settings.openai_extract_model,
        instructions=SYSTEM_INSTRUCTIONS,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": native_text}],
            }
        ],
        text_format=ExtractionResult,
        temperature=settings.openai_extract_temperature,
        max_output_tokens=settings.openai_extract_max_output_tokens,
    )
    return _unwrap(response), _map_usage(response)


async def extract_from_image_pages(
    png_bytes_per_page: list[bytes],
) -> tuple[ExtractionResult, ExtractionUsage]:
    """Caminho VISÃO (caro): 1 `input_text` + N `input_image` (data URL base64).

    Envia TODAS as páginas do bloco numa só chamada (AI-SPEC §3/§4). `detail` vem do
    tunável `openai_extract_image_detail` (Pitfall 4 / D-04: "high" lê dígitos finos
    de scans ruins; "low" reduz custo).
    """
    settings = get_settings()
    content: list[dict] = [
        {"type": "input_text", "text": "Extraia os dados deste documento."}
    ]
    for png in png_bytes_per_page:
        data_url = "data:image/png;base64," + base64.b64encode(png).decode()
        content.append(
            {
                "type": "input_image",
                "image_url": data_url,
                "detail": settings.openai_extract_image_detail,
            }
        )
    client = _client()
    response = await client.responses.parse(
        model=settings.openai_extract_model,
        instructions=SYSTEM_INSTRUCTIONS,
        input=[{"role": "user", "content": content}],
        text_format=ExtractionResult,
        temperature=settings.openai_extract_temperature,
        max_output_tokens=settings.openai_extract_max_output_tokens,
    )
    return _unwrap(response), _map_usage(response)

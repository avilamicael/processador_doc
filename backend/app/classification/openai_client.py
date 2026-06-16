"""Cliente OpenAI da CLASSIFICAÇÃO (Fase 4) — Responses API + Structured Outputs.

Espelha `extraction/openai_client.py`: wrapper `AsyncOpenAI` sobre a **Responses
API** (`client.responses.parse`) com schemas Pydantic como `text_format`. Isola
as duas chamadas PAGAS da fase atrás de funções de módulo (sem classe), prontas
para o `classify_stage` (Plan seguinte) orquestrar:

- `disambiguate(...)`  → `(DisambiguationResult, ClassifyUsage)` — desempate D-01;
- `fill_missing_fields(...)` → `(MissingFieldsResult, ClassifyUsage)` — campos D-06.

Garantias materializadas (mesmas da Fase 3):
- **Segredo nunca logado (CFM 5 / V7-V8 / T-04-07):** `openai_api_key` é
  `SecretStr`; `.get_secret_value()` SÓ no ponto de criação do `AsyncOpenAI`.
- **Recusa tratada (T-04-06):** `response.output_parsed is None` → `_unwrap`
  levanta `ClassificationRefused` logando só o motivo (metadado). SEM retry aqui
  — o backoff é da fila; a recusa apenas levanta para cair no caminho de FALHA.
- **Tokens para cobrança:** a Responses API expõe `input_tokens`/`output_tokens`;
  mapeamos **input→prompt, output→completion** num `ClassifyUsage` tipado.
- **Tampering via conteúdo (T-04-06):** Structured Outputs limita a saída ao
  schema; `instructions=` são FIXAS, sem few-shot do conteúdo do documento.

Logamos SÓ metadados (template_id/confidence) — NUNCA full_text/fields/chave.
"""

import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.classification.schema import DisambiguationResult, MissingFieldsResult
from app.config import get_settings

logger = logging.getLogger(__name__)

# System prompts FIXOS (= instructions da Responses API). Sem few-shot do conteúdo
# do documento (anti-padrão / T-04-06): o que o modelo recebe vem só no `input`.
DISAMBIGUATION_INSTRUCTIONS = (
    "Você classifica um documento contra uma lista de templates candidatos. "
    "Receberá um resumo de cada template candidato (id e sinais identificadores) "
    "e um trecho de contexto do documento. Escolha o id do template que casa, ou "
    "null se NENHUM corresponder. Não invente ids fora da lista; justifique de "
    "forma curta sem repetir o conteúdo do documento."
)
FILL_FIELDS_INSTRUCTIONS = (
    "Você extrai do documento APENAS os campos solicitados. Receberá a "
    "especificação dos campos faltantes e o texto do documento. Devolva os pares "
    "dado->valor pedidos que encontrar; omita os que não estiverem no documento. "
    "Não invente valores: só o que está literalmente no documento."
)


class ClassificationRefused(Exception):
    """O modelo RECUSOU a classificação (`output_parsed is None`, T-04-06).

    Análoga a `ExtractionRefused`: tratada como falha; a fila faz retry/backoff e,
    ao esgotar, leva o documento a FALHA. A mensagem traz só o MOTIVO da recusa
    (metadado) — nunca a chave nem o conteúdo do documento.
    """


@dataclass(frozen=True)
class ClassifyUsage:
    """Tokens da chamada, já mapeados para o vocabulário do modelo `Usage`.

    A Responses API usa `input_tokens`/`output_tokens`; o modelo `Usage` usa
    `prompt_tokens`/`completion_tokens`. Mapeamento: input→prompt, output→completion.
    """

    prompt_tokens: int
    completion_tokens: int


def _client() -> AsyncOpenAI:
    """Cria o cliente async. `.get_secret_value()` SÓ aqui (CFM 5 / T-04-07)."""
    settings = get_settings()
    api_key = (
        settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    )
    return AsyncOpenAI(api_key=api_key)


def _map_usage(response) -> ClassifyUsage:
    """Mapeia o usage da Responses API → ClassifyUsage (input→prompt, output→completion)."""
    usage = response.usage
    return ClassifyUsage(
        prompt_tokens=usage.input_tokens,
        completion_tokens=usage.output_tokens,
    )


def _refusal_reason(response) -> str:
    """Extrai o texto do bloco `refusal` da resposta, se houver (metadado seguro)."""
    for item in getattr(response, "output", None) or []:
        for block in getattr(item, "content", None) or []:
            refusal = getattr(block, "refusal", None)
            if refusal:
                return str(refusal)
    return "recusa sem motivo declarado"


def _unwrap(response):
    """Devolve `output_parsed` ou levanta `ClassificationRefused` na recusa.

    `response.output_parsed` é `None` quando o modelo recusou. Recupera o motivo
    do bloco `refusal` (se houver) para log/exceção — SÓ o motivo, NUNCA a chave
    nem o conteúdo do documento (CFM 5 / T-04-07).
    """
    parsed = response.output_parsed
    if parsed is None:
        reason = _refusal_reason(response)
        logger.info("Classificação recusada pelo modelo: %s", reason)
        raise ClassificationRefused(reason)
    return parsed


async def disambiguate(
    candidates_summary: str, doc_context: str
) -> tuple[DisambiguationResult, ClassifyUsage]:
    """Desempate D-01: a IA escolhe o template (ou null) entre os candidatos.

    `candidates_summary` é o resumo (id + sinais) dos templates em zona cinzenta;
    `doc_context` é o trecho do documento usado para decidir. Devolve a decisão
    tipada + o usage para cobrança.
    """
    settings = get_settings()
    client = _client()
    response = await client.responses.parse(
        model=settings.openai_classify_model,
        instructions=DISAMBIGUATION_INSTRUCTIONS,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"Templates candidatos:\n{candidates_summary}\n\n"
                            f"Contexto do documento:\n{doc_context}"
                        ),
                    }
                ],
            }
        ],
        text_format=DisambiguationResult,
        temperature=settings.openai_classify_temperature,
        max_output_tokens=settings.openai_classify_max_output_tokens,
    )
    return _unwrap(response), _map_usage(response)


async def fill_missing_fields(
    missing_field_specs: str, doc_text: str
) -> tuple[MissingFieldsResult, ClassifyUsage]:
    """Campos faltantes D-06: a IA lê SÓ os campos obrigatórios não preenchidos.

    `missing_field_specs` descreve os campos pedidos (nome/tipo/hint); `doc_text`
    é o texto do documento. Devolve os pares encontrados + o usage para cobrança.
    """
    settings = get_settings()
    client = _client()
    response = await client.responses.parse(
        model=settings.openai_classify_model,
        instructions=FILL_FIELDS_INSTRUCTIONS,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"Campos a extrair:\n{missing_field_specs}\n\n"
                            f"Documento:\n{doc_text}"
                        ),
                    }
                ],
            }
        ],
        text_format=MissingFieldsResult,
        temperature=settings.openai_classify_temperature,
        max_output_tokens=settings.openai_classify_max_output_tokens,
    )
    return _unwrap(response), _map_usage(response)

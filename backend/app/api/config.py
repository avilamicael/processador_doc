"""API de configuração global — limiar de confiança para revisão (REV-02 / D-03).

Router fino (`/config`) que a UI (S6, Plano 04) usa para ler e ajustar o **limiar
global de qualidade de extração** abaixo do qual um documento vai para revisão
humana (EM_REVISAO). É config GLOBAL (D-03), não por-template.

- `GET /config/review-threshold` → o valor efetivo atual (`get_settings()`).
- `PUT /config/review-threshold` → persiste o novo valor no `.env` (mesmo arquivo
  que `SettingsConfigDict(env_file=".env")` lê) de forma atômica e LIMPA o cache de
  `get_settings` (lru_cache), para que o roteamento do `classify_stage` releia o
  novo limiar SEM reiniciar o processo.

VALIDAÇÃO (T-05-15): o body é validado pelo Pydantic (`ge=0.0, le=1.0`) — fora da
faixa → 422 antes de qualquer escrita. O valor já validado é gravado como
`REVIEW_CONFIDENCE_THRESHOLD=<valor>` no `.env`; nunca interpolamos input cru em
SQL/shell (não há DB nem subprocess aqui).
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import get_settings, persist_env_setting

router = APIRouter(prefix="/config", tags=["config"])

# Chave do `.env` que mapeia para `Settings.review_confidence_threshold`
# (validation_alias "REVIEW_CONFIDENCE_THRESHOLD"). Constante do código.
_THRESHOLD_ENV_KEY = "REVIEW_CONFIDENCE_THRESHOLD"


class ReviewThresholdOut(BaseModel):
    """Valor efetivo atual do limiar global de confiança (0.0–1.0)."""

    threshold: float


class ReviewThresholdIn(BaseModel):
    """Novo limiar global — validado na faixa [0.0, 1.0] (T-05-15 → 422 fora dela)."""

    threshold: float = Field(ge=0.0, le=1.0)


@router.get("/review-threshold", response_model=ReviewThresholdOut)
def get_review_threshold() -> ReviewThresholdOut:
    """Lê o limiar global efetivo de `get_settings()` (REV-02 / D-03)."""
    return ReviewThresholdOut(threshold=get_settings().review_confidence_threshold)


@router.put("/review-threshold", response_model=ReviewThresholdOut)
def put_review_threshold(body: ReviewThresholdIn) -> ReviewThresholdOut:
    """Persiste o limiar no `.env` e invalida o cache de settings (sem reiniciar).

    O Pydantic já garantiu a faixa [0.0, 1.0] (fora dela → 422). Grava no `.env`
    atomicamente, limpa o `lru_cache` de `get_settings` para o stage reler o novo
    valor, e retorna o valor efetivo relido.
    """
    persist_env_setting(_THRESHOLD_ENV_KEY, str(body.threshold))
    get_settings.cache_clear()
    return ReviewThresholdOut(threshold=get_settings().review_confidence_threshold)

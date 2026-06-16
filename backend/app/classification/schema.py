"""Schemas Structured Outputs da CLASSIFICAÇÃO (Fase 4) — contratos `text_format`.

Duas chamadas PAGAS à IA existem nesta fase, cada uma com seu schema:

1. **Desempate** (D-01): quando o matcher local fica na zona cinzenta, a IA decide
   qual template casa → `DisambiguationResult`. `matched_template_id` é
   `int | None`: `None` = a IA não casou nenhum template → quarentena (D-03).

2. **Campos faltantes** (D-06): quando o filler local não preencheu todos os
   campos obrigatórios, a IA lê só os faltantes → `MissingFieldsResult`, uma
   `list[ExtractedField]`.

PONTO TÉCNICO (Pitfall 1, herdado da Fase 3): em Structured Outputs strict mode
NÃO existe dict aberto de chaves variáveis (`additionalProperties:true` é
rejeitado). Por isso `MissingFieldsResult` REUSA `ExtractedField` (list-of-pairs)
da extração — NÃO redeclaramos o tipo nem modelamos `campo→valor` como dict. As
`description` de cada Field guiam o modelo (disciplina de prompt).
"""

from pydantic import BaseModel, Field

from app.extraction.schema import ExtractedField


class DisambiguationResult(BaseModel):
    """Decisão de desempate da IA entre os templates candidatos (D-01).

    `matched_template_id` nullable é o ponto-chave: `None` significa que a IA não
    reconheceu nenhum dos templates candidatos → o documento vai para QUARENTENA
    (template_id null, D-03), em vez de forçar um casamento ruim.
    """

    matched_template_id: int | None = Field(
        description=(
            "ID do template que casa com o documento, ou null quando NENHUM dos "
            "templates candidatos corresponde (vai para quarentena)."
        )
    )
    confidence: float = Field(
        description="0.0-1.0: confiança na decisão de casamento/não-casamento"
    )
    reason: str = Field(
        description=(
            "Justificativa curta da decisão (metadado não sensível). Não repetir "
            "o conteúdo do documento — só o sinal que levou à escolha."
        )
    )


class MissingFieldsResult(BaseModel):
    """Campos preenchidos pela IA para o documento (D-06).

    `fields` REUSA `ExtractedField` (list-of-pairs strict-safe) da Fase 3 — NUNCA
    um dict de chaves dinâmicas. O stage (Plan seguinte) casa cada par de volta
    aos `TemplateField` que estavam faltando.
    """

    fields: list[ExtractedField] = Field(
        description=(
            "Os campos solicitados encontrados no documento, como pares "
            "dado->valor (list-of-pairs), NUNCA um dict aberto. Só os campos "
            "pedidos; omitir o que não estiver no documento."
        )
    )

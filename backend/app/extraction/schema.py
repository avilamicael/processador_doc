"""Schema GENÉRICO de extração (Fase 3) — contrato `text_format` da Responses API.

PONTO TÉCNICO Nº 1 DA FASE: em Structured Outputs strict mode, todo campo é
`required` e todo objeto tem `additionalProperties:false` — logo NÃO existe
`dict[str, str]` de chaves arbitrárias (o instinto óbvio para `dado→valor`). A
API rejeita o dict aberto. Modelamos `dado→valor` como uma **list-of-pairs**
(`list[ExtractedField]`), onde as chaves variáveis viram DADOS (`value`), não
forma do schema.

Schema é GENÉRICO (D-01/D-02): não derivado de template, sem tipagem por campo
nem validações de domínio (DV de CNPJ, datas plausíveis) — isso é Fase 4
(EXT-04 re-escopado). As `description` de cada Field são embutidas no JSON Schema
e guiam o modelo (disciplina de prompt, AI-SPEC §4b).
"""

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    """Um par dado→valor encontrado no documento.

    As chaves variáveis (`cnpj_emitente`, `valor_total`, ...) viram DADOS no
    `key`/`value`, não forma do schema — é o que mantém o motor genérico e
    compatível com strict mode.
    """

    key: str = Field(
        description="Nome do dado, ex.: 'cnpj_emitente', 'valor_total', 'beneficiario'"
    )
    value: str = Field(
        description="Valor lido, como aparece no documento (sem normalizar)"
    )
    confidence: float = Field(description="0.0-1.0: confiança na leitura deste campo")


class ExtractionResult(BaseModel):
    """Resultado genérico da extração de um bloco de documento.

    É o `text_format` passado a `client.responses.parse(...)`: o SDK gera o JSON
    Schema (strict), a OpenAI garante conformidade, e `response.output_parsed`
    devolve uma instância já validada. A conformidade ao schema é a única
    validação da Fase 3 (D-09: sem gate de qualidade aqui).
    """

    fields: list[ExtractedField] = Field(
        description=(
            "TODOS os pares dado->valor encontrados no documento. "
            "Lista de pares (list-of-pairs), NUNCA um dict aberto."
        )
    )
    full_text: str = Field(description="Texto integral lido do documento")
    doc_type_guess: str = Field(
        description=(
            "Palpite do tipo de documento, ex.: 'boleto', 'nota_fiscal', "
            "'holerite', 'desconhecido' quando incerto"
        )
    )
    doc_type_confidence: float = Field(
        description="0.0-1.0: confiança no palpite de tipo"
    )

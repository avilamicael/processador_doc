"""Pacote de classificação (Fase 4) — peças puras + cliente OpenAI.

Materializa o motor custo-zero de TPL-03 (matcher local resolve a maioria sem
IA) e a base de EXT-04 (mapeamento local de pares→campos + chamada dirigida só
aos faltantes). O `classify_stage` (Plan seguinte) compõe estas peças:

- `schema`   — schemas Structured Outputs (desempate D-01 + faltantes D-06),
               strict-safe (nullable / list-of-pairs, reusa `ExtractedField`);
- `matcher`  — matcher local por sinais (D-02), função pura, custo 0;
- `filler`   — mapeia pares já extraídos → campos do template (D-05), sem IA;
- `openai_client` — chamadas PAGAS de desempate/faltantes (Responses API),
               espelhando `extraction/openai_client`.
"""

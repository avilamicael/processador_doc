---
phase: 03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens
verified: 2026-06-16T00:00:00Z
status: passed
human_resolution: "CR-01 aceito para v1 (decisão humana 2026-06-16, Opção A) — limitação documentada em openai_client.py:_unwrap; follow-up registrado em 03-HUMAN-UAT.md"
score: 4/4 must-haves verificados
overrides_applied: 0
human_verification:
  - test: "Validar que documentos longos (com full_text grande) não terminam em FALHA por truncamento"
    expected: "CR-01: quando max_output_tokens é atingido, output_parsed devolve None, e o stage trata isso como ExtractionRefused → retry → FALHA. Verificar manualmente se o comportamento observado é aceitável para a Fase 3 ou se a distinção truncamento vs recusa deve ser implementada agora."
    why_human: "Não é possível verificar com grep se a Responses API devolve status=incomplete em vez de refusal — requer chamada real ou fixture que simule o campo status='incomplete'. A fixture respx existente só simula output_parsed=None sem status, não diferencia os dois casos."
---

# Fase 3: Extração Genérica via IA e Medição de Tokens — Relatório de Verificação

**Meta da Fase:** O sistema extrai, para qualquer tipo de documento (incluindo imagens e PDFs escaneados), os dados que encontrar via IA da OpenAI de forma genérica (não dirigida por template), aproveitando texto nativo local quando disponível, e mede o consumo de tokens por documento para a cobrança.
**Verificado:** 2026-06-16
**Status:** human_needed
**Re-verificação:** Não — verificação inicial

## Conquista da Meta

### Verdades Observáveis

| #  | Verdade                                                                                                                            | Status      | Evidência                                                                                                                     |
|----|------------------------------------------------------------------------------------------------------------------------------------|-------------|-------------------------------------------------------------------------------------------------------------------------------|
| SC1 | O sistema extrai dados de qualquer tipo de documento (imagens, PDFs escaneados) via IA, devolvendo pares dado→valor, texto integral e palpite de tipo | ✓ VERIFICADO | `extract_stage` → `router.choose` → `openai_client.extract_from_text/extract_from_image_pages(text_format=ExtractionResult)` → persiste `Extraction`. `test_stage.py`: 5 testes (texto/visão/imagem) todos passam. Schema `ExtractionResult` contém `fields: list[ExtractedField]`, `full_text`, `doc_type_guess`, `doc_type_confidence`. |
| SC2 | A IA retorna dados em formato estruturado (Structured Outputs, schema genérico), persistido com texto nativo como base para templates da Fase 4 | ✓ VERIFICADO | `responses.parse(text_format=ExtractionResult)` nas linhas 113/152 do `openai_client.py`. Schema sem `additionalProperties:true` (verificado programaticamente — PASS). `fields_json` + `full_text` persistidos em `Extraction`. 170 testes passam. |
| SC3 | Quando o PDF tem texto nativo, o sistema extrai localmente sem custo de IA                                                         | ✓ VERIFICADO | `pdf_io.extract_text_and_decide()` usa `fitz.get_text()` localmente. `router.choose` retorna `"native_text"` para PDFs com texto suficiente. `stage.py`: caminho `native_text` chama `openai_client.extract_from_text` com o texto já extraído (texto local → IA recebe texto, não imagem). Teste `test_extract_text_and_decide_native_text` verde. |
| SC4 | Cada chamada à IA registra os tokens consumidos (prompt + completion) ligados ao documento                                         | ✓ VERIFICADO | `ExtractionUsage(prompt_tokens=usage.input_tokens, completion_tokens=usage.output_tokens)` em `openai_client.py:78-81`. `stage.py:163-169` persiste `Usage(document_id, step="extract", prompt_tokens, completion_tokens)` no mesmo commit atômico. `test_usage.py`: 2 testes verificam 1 Usage por extração com tokens mapeados. |

**Pontuação:** 4/4 verdades verificadas

### Artefatos Obrigatórios

| Artefato                                           | Esperado                                           | Status      | Detalhes                                                             |
|----------------------------------------------------|----------------------------------------------------|-------------|----------------------------------------------------------------------|
| `backend/app/extraction/schema.py`                 | ExtractionResult / ExtractedField (Pydantic strict-safe) | ✓ VERIFICADO | `class ExtractionResult` e `class ExtractedField` existem. `fields: list[ExtractedField]`. Schema sem `additionalProperties:true`. |
| `backend/app/extraction/pdf_io.py`                 | PyMuPDF: get_text + heurística + render + magic bytes | ✓ VERIFICADO | `import fitz`. `detect_blob_type`, `extract_text_and_decide`, `render_pages_png`. 11 testes passam. |
| `backend/app/extraction/router.py`                 | Seam D-03 — `choose` retorna "native_text"\|"vision"  | ✓ VERIFICADO | `def choose(blob)` presente. Docstring documenta seam D-03 (Fases 4/7 estendem). 6 testes passam. |
| `backend/app/extraction/openai_client.py`          | AsyncOpenAI wrapper + responses.parse + _unwrap + tokens | ✓ VERIFICADO | `AsyncOpenAI` importado. `responses.parse(text_format=ExtractionResult)` em linha 113 e 156. `_unwrap` e `_map_usage` presentes. `ExtractionRefused` definida. |
| `backend/app/extraction/stage.py`                  | extract_stage async, idempotente, commit atômico   | ✓ VERIFICADO | `async def extract_stage`. Checagem de `Extraction` existente antes da chamada paga. Commit único após persistir `Extraction + Usage + marcador`. 5 testes passam. |
| `backend/app/models/extraction.py`                 | Modelo SQLAlchemy Extraction                       | ✓ VERIFICADO | `class Extraction(Base)`, `__tablename__="extractions"`, `document_id` FK UNIQUE, `fields_json`, `full_text`, `doc_type_guess`, `doc_type_confidence`, `route`. |
| `backend/alembic/versions/0003_extractions.py`     | Migração que cria tabela extractions               | ✓ VERIFICADO | `op.create_table('extractions', ...)` + `batch_alter_table` para índice UNIQUE em `document_id`. `downgrade` faz `op.drop_table`. |
| `backend/app/queue/worker.py`                      | Dispatch bifurcado por step + sweep de enqueue     | ✓ VERIFICADO | `_dispatch` bifurca: `extract` → `await extract_stage(...)` (coroutine no loop); `ingest` → `asyncio.to_thread`. `enqueue_pending_extractions` chamado no startup. |

### Verificação de Vínculos-Chave

| De                               | Para                             | Via                                      | Status      | Detalhes                                                                   |
|----------------------------------|----------------------------------|------------------------------------------|-------------|----------------------------------------------------------------------------|
| `openai_client.py`               | `ExtractionResult` (text_format) | `responses.parse(text_format=ExtractionResult)` | ✓ WIRED | Linhas 122 e 156 de `openai_client.py`.                                    |
| `openai_client.py`               | `openai_api_key`                 | `.get_secret_value()` só na criação      | ✓ WIRED | `_client()` linha 71: `settings.openai_api_key.get_secret_value()` — único ponto. Teste `test_chave_nunca_aparece_em_logs_no_sucesso` verde. |
| `stage.py`                       | `Extraction + Usage` (mesmo commit) | `session.add` + `session.commit()` único | ✓ WIRED | `stage.py:151-176`: ambos os `session.add()` + `doc.last_completed_step` em memória antes do único `session.commit()`. |
| `stage.py`                       | `mark_step('extraido')` via set em memória | `doc.last_completed_step = EXTRACTED_STEP` | ✓ WIRED | `stage.py:174`. `test_state.py::test_nao_chama_transition_com_auto_laco` verde (espião prova que `transition` não foi chamado). |
| `worker.py`                      | `extract_stage` (coroutine no loop) | `await extract_stage(...)` no `_dispatch` | ✓ WIRED | `worker.py:149-152`: `if step == EXTRACT_STEP: ... await extract_stage(...)`. NUNCA `to_thread`. |
| `models/__init__.py`             | `Extraction`                     | import + `__all__`                        | ✓ WIRED | Linha 11: `from app.models.extraction import Extraction`. `"Extraction"` em `__all__`. |

### Rastreamento de Dados (Nível 4)

| Artefato           | Variável de dados        | Fonte                              | Produz dados reais | Status      |
|--------------------|--------------------------|------------------------------------|--------------------|-------------|
| `stage.py`         | `result: ExtractionResult` | `openai_client.extract_from_text/extract_from_image_pages` | Sim — via Responses API (mockada em testes) | ✓ FLOWING |
| `stage.py`         | `usage: ExtractionUsage` | `openai_client._map_usage(response)` | Sim — `response.usage.input_tokens/output_tokens` | ✓ FLOWING |
| `stage.py`         | `full_text: str`         | `pdf_io.extract_text_and_decide` ou `""` para imagem crua | Sim — texto nativo local | ✓ FLOWING |
| `Extraction` model | `fields_json`            | `_fields_to_json(result)` em `stage.py` | Sim — serializa `result.fields` | ✓ FLOWING |
| `Usage` model      | `prompt_tokens/completion_tokens` | `usage.prompt_tokens/completion_tokens` (já mapeados) | Sim | ✓ FLOWING |

### Verificações Comportamentais

| Comportamento                                 | Comando                                                      | Resultado                 | Status  |
|-----------------------------------------------|--------------------------------------------------------------|---------------------------|---------|
| Suíte completa (170 testes)                   | `uv run pytest -q --tb=no`                                   | 170 passed, 15 warnings   | ✓ PASS  |
| Testes de extração (44 testes)               | `uv run pytest tests/extraction tests/queue/test_dispatch.py -q` | 57 passed                 | ✓ PASS  |
| Imports de produção funcionam                 | `uv run python -c "import fitz; from app.extraction.stage import extract_stage"` | OK | ✓ PASS  |
| Schema sem additionalProperties:true          | Verificação programática no schema JSON                       | PASS                      | ✓ PASS  |
| Tunables OPENAI_EXTRACT_* com defaults        | `Settings()` imprime 5 valores                               | gpt-4o-2024-08-06 / 0.0 / 4096 / high / 16 | ✓ PASS  |

### Verificação de Probes

Nenhuma probe declarada nos PLANs desta fase.

### Cobertura de Requisitos

| Requisito | Plano(s) de origem  | Descrição                                                                 | Status       | Evidência                                                                           |
|-----------|---------------------|---------------------------------------------------------------------------|--------------|--------------------------------------------------------------------------------------|
| EXT-01    | 03-02, 03-03        | Sistema extrai texto nativo de PDFs localmente, sem custo de IA           | ✓ SATISFEITO | `pdf_io.extract_text_and_decide` usa `fitz.get_text()` local. Router retorna `"native_text"` para PDFs com texto. Stage não chama visão nesse caminho. |
| EXT-02    | 03-01, 03-02, 03-03, 03-04 | Sistema extrai dados de qualquer tipo de documento via IA (OpenAI), incluindo imagens e PDFs escaneados | ✓ SATISFEITO | `openai_client.extract_from_image_pages` envia PNG base64. `extract_from_text` envia texto. `ExtractionResult` é genérico (qualquer tipo). 170 testes verdes. |
| USE-02    | 03-01, 03-03, 03-04 | Sistema mede e registra uso de tokens/chamadas por documento              | ✓ SATISFEITO | `Usage(step="extract", prompt_tokens, completion_tokens)` gravado no mesmo commit atômico. `test_usage.py` prova 1 Usage por extração com tokens mapeados corretamente. |

### Anti-Padrões Encontrados

| Arquivo                              | Linha | Padrão            | Severidade    | Impacto                                                                          |
|--------------------------------------|-------|-------------------|---------------|----------------------------------------------------------------------------------|
| Nenhum arquivo modificado            | —     | TBD/FIXME/XXX     | —             | Nenhum marcador de dívida não-referenciado encontrado nos arquivos da Fase 3.    |

**Marcadores de dívida bloqueantes:** nenhum encontrado.

Ocorrências da string "TODO" nos arquivos verificados são todas em documentações de campos de formulário (`"TODOS os pares dado→valor"`) — não são marcadores de dívida de código.

### Avaliação do CR-01 (achado crítico do code review)

O code review (03-REVIEW.md) identificou CR-01 como o único achado crítico:

**CR-01: `_unwrap` não distingue truncamento por `max_output_tokens` de recusa real**

Confirmado via leitura direta de `openai_client.py:84-96`: `_unwrap` verifica apenas `response.output_parsed is None` e sempre levanta `ExtractionRefused`, sem inspecionar `response.status` ou `response.incomplete_details.reason`. Isso significa que um documento cujo output seja truncado pelo teto de 4096 tokens recebe o mesmo tratamento que uma recusa: 5 retries → FALHA, sem persistir nada.

**Avaliação quanto ao bloqueio da meta da fase:** A meta da Fase 3 é a extração genérica funcionar e medir tokens. O CR-01 não impede que documentos comuns (dentro do teto de tokens) sejam extraídos e medidos corretamente — a lógica de extração, persistência e medição de tokens está completa e verificada por testes. O CR-01 é um **risco de correctness** em documentos longos (full_text extenso + muitos campos) que atinge o teto de 4096 tokens, mas não invalida o mecanismo central da fase.

**Decisão de impacto na verificação:** CR-01 não é BLOCKER para a meta da fase (extração genérica funciona para a esmagadora maioria dos documentos), mas é um **risco de correctness real** que deve ser avaliado pelo desenvolvedor antes de ativar o sistema em produção com documentos longos. Registrado como item de verificação humana.

### Verificação Humana Necessária

#### 1. CR-01 — Truncamento classificado como recusa

**Teste:** Criar uma fixture respx que simule uma resposta com `output_parsed=None` E `status="incomplete"` (em vez de `status="completed"`) e executar `_unwrap`. Alternativamente, testar com um documento real longo que ultrapasse 4096 tokens.
**Esperado:** Comportamento observado: `ExtractionRefused` é levantado igualmente para truncamento e recusa. O desenvolvedor deve decidir: (a) aceitar isso para v1 e documentar que documentos muito longos podem ir a FALHA (tratável aumentando `OPENAI_EXTRACT_MAX_OUTPUT_TOKENS`), ou (b) implementar a distinção `status="incomplete"` → `ExtractionIncomplete` antes de ir para produção.
**Por que humano:** Requer decisão de produto sobre a aceitabilidade do comportamento, e/ou fixture adicional que simule o campo `status` da Responses API com `output_parsed=None` — não verificável apenas com grep.

---

## Resumo de Lacunas

Nenhuma lacuna bloqueante foi identificada. A meta da fase está tecnicamente alcançada:

- EXT-01 (texto nativo local), EXT-02 (extração genérica via IA) e USE-02 (medição de tokens) foram entregues e verificados por 170 testes que passam.
- Todos os artefatos obrigatórios existem, são substantivos e estão conectados.
- O fluxo de dados foi rastreado do blob do CAS até a Extraction e Usage persistidas.
- O schema genérico `ExtractionResult` (list-of-pairs, strict-safe) está definido e testado.
- A idempotência (não cobrar duas vezes) é garantida por UNIQUE no banco + checagem prévia + commit atômico — provada por `test_idempotency`.
- O segredo nunca é logado — testado por `test_chave_nunca_aparece_em_logs_no_sucesso`.

O status `human_needed` reflete exclusivamente o CR-01 (truncamento vs recusa indistinguíveis), que requer uma decisão explícita do desenvolvedor sobre aceitabilidade antes de produção com documentos longos.

---

_Verificado: 2026-06-16_
_Verificador: Claude (gsd-verifier)_

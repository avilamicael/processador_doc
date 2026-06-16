---
phase: 03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens
reviewed: 2026-06-16T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - backend/app/extraction/schema.py
  - backend/app/extraction/pdf_io.py
  - backend/app/extraction/router.py
  - backend/app/extraction/openai_client.py
  - backend/app/extraction/stage.py
  - backend/app/extraction/__init__.py
  - backend/app/models/extraction.py
  - backend/app/models/document.py
  - backend/app/models/__init__.py
  - backend/alembic/versions/0003_extractions.py
  - backend/app/config.py
  - backend/app/queue/worker.py
findings:
  critical: 1
  warning: 7
  info: 4
  total: 12
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-06-16
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Revisei o motor de extração genérica via IA da Fase 3: schema strict-safe, primitivas PyMuPDF, seam D-03, cliente AsyncOpenAI sobre a Responses API, o `extract_stage` idempotente e o wiring no worker. A arquitetura de idempotência (UNIQUE por bloco + checagem prévia de `Extraction` antes da chamada paga + commit único antes do `mark_done`) está bem construída e a garantia central de "não cobrar duas vezes" se sustenta sob crash/resume. A máquina de estados foi corretamente operada via marcador `"extraido"` (sem o auto-laço inválido `PROCESSANDO→PROCESSANDO`), e o segredo (`SecretStr`) está isolado no ponto de criação do cliente.

Os defeitos encontrados concentram-se em **classificação de falha** e **robustez de borda**, não na espinha dorsal de idempotência. O mais grave: o tratamento de "não-retryável" (chave OpenAI inválida) tem um furo que faz o caminho mais comum de configuração errada (chave AUSENTE) cair no retry caro, e a detecção de recusa via `output_parsed is None` engole silenciosamente truncamento por `max_output_tokens` — gerando FALHA por motivo errado e perda de dados extraídos. Há também leitura dupla do PDF (router + stage) que pode, em PDFs no limiar, divergir de rota, e tunables de env (`image_detail`, `model`, `temperature`) entram sem validação na chamada paga.

## Critical Issues

### CR-01: Truncamento por `max_output_tokens` é classificado como recusa e descartado

**File:** `backend/app/extraction/openai_client.py:84-96` (e `stage.py:128,146`)
**Issue:** `_unwrap` trata `response.output_parsed is None` como **recusa do modelo** (`ExtractionRefused`). Mas a Responses API também devolve `output_parsed is None` quando a resposta é **truncada** (`status="incomplete"`, `incomplete_details.reason == "max_output_tokens"`). O schema inclui `full_text` (o documento inteiro), então documentos longos atingem o teto de 4096 tokens com facilidade (o próprio `config.py:107-115` adverte para isso, Pitfall 6). Resultado: uma extração truncada — que pode conter dezenas de campos válidos já extraídos — é tratada como recusa, propaga como `ExtractionRefused`, é re-tentada 5× (sempre truncando de novo, pois o documento não encolhe) e termina em `FALHA`. O documento vai a dead-letter por um motivo que o operador não consegue diagnosticar (o log diz "recusa", não "truncamento"), e nenhum dado extraído é persistido. Isto é incorreto: trunca ≠ recusa, e a Fase 3 não tem gate de qualidade (D-09), logo extração parcial DEVERIA persistir.
**Fix:** Distinguir os dois casos antes de levantar `ExtractionRefused`. Inspecionar `response.status`/`incomplete_details` e levantar uma exceção dedicada (ex.: `ExtractionTruncated`) ou logar o motivo real; idealmente persistir o que houver. Mínimo:
```python
def _unwrap(response) -> ExtractionResult:
    parsed = response.output_parsed
    if parsed is None:
        status = getattr(response, "status", None)
        details = getattr(response, "incomplete_details", None)
        if status == "incomplete":
            reason = getattr(details, "reason", "incomplete")
            logger.warning("Extração incompleta (status=%s reason=%s)", status, reason)
            raise ExtractionIncomplete(reason)  # log distingue de recusa
        reason = _refusal_reason(response)
        logger.info("Extração recusada pelo modelo: %s", reason)
        raise ExtractionRefused(reason)
    return parsed
```
Acrescentar a checagem de truncamento sugerida na própria pesquisa (`usage.output_tokens ≈ max_output_tokens`, RESEARCH Pitfall 6 dim 6) e considerar não re-tentar truncamento (retry sem mudar o teto é determinístico — sempre falha).

## Warnings

### WR-01: Chave OpenAI AUSENTE não é tratada como não-retryável — furo no T-03-14

**File:** `backend/app/extraction/openai_client.py:68-72` + `backend/app/queue/worker.py:197-210`
**Issue:** O worker captura `openai.AuthenticationError` (chave INVÁLIDA) como não-retryável → dead-letter imediato. Mas o caso mais comum de má-configuração — chave **ausente** (`openai_api_key is None`) — constrói `AsyncOpenAI(api_key=None)`, que levanta `openai.OpenAIError("The api_key client option must be set...")`, e NÃO `AuthenticationError`. Essa exceção cai no `except Exception` genérico (`worker.py:211`) → `schedule_retry` → backoff exponencial 5×, e só então `FALHA`. O SUMMARY do Plan 03 (Auto-fixed #2) confirma que o ambiente de teste teve de injetar uma chave fictícia justamente porque esse caminho dispara antes do respx — ou seja, o comportamento foi observado e contornado no teste, mas não tratado no runtime. Não custa tokens (a chamada nunca sai), mas atrasa o diagnóstico do erro de config mais provável numa instalação nova (Windows, primeira execução sem `.env`).
**Fix:** Capturar `openai.OpenAIError` (ou checar `settings.openai_api_key is None` no início de `extract_stage`/`_client`) e tratá-lo como não-retryável, junto de `AuthenticationError`:
```python
except (AuthenticationError, openai.OpenAIError):  # chave inválida OU ausente
    ...dead-letter imediato + FALHA...
```
Cuidado: `OpenAIError` é a base de várias exceções transitórias (rede, rate limit) — não capturá-la de forma ampla. Preferir uma checagem explícita de chave ausente antes da chamada.

### WR-02: PDF é lido/decodificado duas vezes e as decisões de rota podem divergir

**File:** `backend/app/extraction/stage.py:116,123-127,134-141` (com `router.py:40-42`)
**Issue:** No caminho `native_text`, `router.choose` (linha 116) já chama `pdf_io.extract_text_and_decide`, abrindo o PDF e extraindo todo o texto — e **descarta o texto**, devolvendo só a rota. Em seguida o stage (linha 123) chama `extract_text_and_decide` DE NOVO para obter o texto, reabrindo o mesmo PDF. No caminho `vision` com `blob_type=="pdf"`, há ainda uma 3ª abertura (`extract_text_and_decide` em 136) + uma 4ª (`render_pages_png` em 141), além de `detect_blob_type` reabrir os magic bytes. Além do desperdício de CPU (fora do escopo v1), há um risco de **correção**: as duas avaliações da heurística usam `get_settings().openai_extract_min_chars_per_page` lido em momentos diferentes; se a heurística estiver no limiar e o resultado de `get_text()` não for perfeitamente determinístico (ou se um cache de settings for limpo entre as chamadas), a rota decidida por `router.choose` pode não bater com o que o stage assume. O stage confia cegamente na rota do router mas re-extrai o texto por conta própria — duas fontes de verdade para a mesma decisão.
**Fix:** Fazer `router.choose` (ou um novo helper) devolver `(route, full_text)` numa única passada e o stage consumir ambos, eliminando a re-extração e a divergência:
```python
# pdf_io: já devolve (texto, rota). Propagar o texto pelo router.
route, native_text = router.choose_with_text(blob)  # uma só abertura do PDF
```

### WR-03: Tunables de env injetados na chamada paga sem validação

**File:** `backend/app/config.py:95-132` + `backend/app/extraction/openai_client.py:113-159`
**Issue:** `openai_extract_image_detail`, `openai_extract_model` e `openai_extract_temperature` são `str`/`float` livres lidos de env e passados direto à Responses API. Três foot-guns:
1. `image_detail` aceita qualquer string; só `"low"`/`"high"`/`"auto"` são válidos. Um typo (`"hihg"`) gera `BadRequestError` em TODA chamada de visão → 5× retry → FALHA, sem mensagem clara.
2. Trocar `openai_extract_model` para um modelo da série de raciocínio (o1/o3) faz a API **rejeitar `temperature`** → `BadRequestError` em toda chamada. O default `gpt-4o-2024-08-06` é seguro, mas o campo é anunciado como tunável sem deploy (config.py:92-94) e nada valida a combinação.
3. `temperature` é sempre enviado mesmo quando o modelo não o aceita.
**Fix:** Validar `image_detail` com um `Literal["low","high","auto"]` (Pydantic rejeita no boot, não na 5ª retry). Documentar/validar que o modelo deve aceitar `temperature` + visão + Structured Outputs, ou tornar `temperature` opcional/condicional ao modelo.

### WR-04: `enqueue_pending_extractions` perde blocos cujo `content_hash` coincide com um já-extraído

**File:** `backend/app/queue/worker.py:257-264`
**Issue:** A subquery de exclusão usa `~Document.content_hash.in_(select(Document.content_hash).join(Extraction))`, isto é, "exclua documentos cujo `content_hash` esteja entre os hashes que TÊM extração". Como `content_hash` é UNIQUE em `documents`, hoje isso é equivalente a "exclua quem já tem Extraction" e funciona. Porém é um acoplamento frágil: a correção depende inteiramente da unicidade global de `content_hash`. O critério natural e robusto é `Document.id NOT IN (select Extraction.document_id)` — que expressa diretamente a intenção ("blocos sem Extraction") e não depende de unicidade de hash. Além disso, comparar por hash força um join+subquery sobre uma coluna `String(64)` em vez do `id` inteiro indexado.
**Fix:**
```python
~Document.id.in_(select(Extraction.document_id))
```
Expressa a intenção real (1 Extraction por `document_id`, que é a UNIQUE de fato), sem depender da unicidade de `content_hash`.

### WR-05: `last_completed_step` como string mágica não-tipada espalhada por 3 módulos

**File:** `backend/app/extraction/stage.py:56` / `backend/app/pipeline/ingest_stage.py:53` / `backend/app/queue/worker.py:261`
**Issue:** O contrato de estado do pipeline depende de strings literais (`"extraido"`, `"aguardando_extracao"`) comparadas entre módulos. `enqueue_pending_extractions` filtra por `Document.last_completed_step == AWAITING_EXTRACTION_STEP` (importado de `ingest_stage`), mas `EXTRACTED_STEP` é definido independentemente em `stage.py`. Não há um enum/fonte única para esses marcadores; um erro de digitação em qualquer literal (ou uma divergência de capitalização) falha **silenciosamente** — o sweep simplesmente não enfileira o bloco, e o documento fica preso em `aguardando_extracao` para sempre, sem erro. Isso é um risco de "documento perdido" (a constraint nº 1 da CLAUDE.md: "nunca pode causar perda"), ainda que por inação.
**Fix:** Centralizar os marcadores de etapa num único enum/módulo (`pipeline/steps.py`) e referenciá-lo em todos os pontos, para que o type-checker e os testes peguem divergências.

### WR-06: Recusa real consome tokens, mas nenhum `Usage` é gravado

**File:** `backend/app/extraction/openai_client.py:84-96` + `backend/app/extraction/stage.py:128-170`
**Issue:** Quando o modelo recusa (`output_parsed is None`), `_unwrap` levanta `ExtractionRefused` ANTES de `_map_usage` ser chamado, e a exceção propaga do `extract_stage` antes do bloco de persistência. Mas a recusa **consumiu tokens** (o fixture de recusa em conftest mostra `input_tokens:12, output_tokens:6`, e uma recusa de visão com `detail:"high"` consome muito mais input). USE-02/SC4 exige medir o consumo por documento — o consumo de chamadas recusadas/falhas é invisível. Para o objetivo de cobrança por consumo (uma chave por cliente), tokens gastos em recusas/retries são custo real não-contabilizado. Decisão consciente é aceitável, mas hoje é silenciosa.
**Fix:** Decidir explicitamente: ou (a) gravar `Usage(step="extract")` mesmo no caminho de recusa (commit do Usage antes de propagar a exceção — exige um commit separado para não conflitar com o rollback do stage), ou (b) documentar que o consumo de recusas/retries não é medido em v1. Hoje não há decisão registrada no código.

### WR-07: Imagem crua é enviada à OpenAI sem validação de tamanho/decodificabilidade

**File:** `backend/app/extraction/stage.py:142-146` + `backend/app/extraction/openai_client.py:142-150`
**Issue:** No caminho de imagem, `pngs = [blob]` (linha 145) envia os bytes crus do CAS direto como `input_image` base64. Diferente do caminho PDF (onde PyMuPDF re-renderiza e normaliza), a imagem crua não passa por nenhuma validação: um JPEG/PNG corrompido (magic bytes válidos, payload quebrado), gigante, ou com dimensões absurdas é base64-encodado e enviado. A OpenAI rejeita com `BadRequestError` (tamanho/formato) → 5× retry → FALHA, ou aceita e cobra por uma imADO enorme. Como o blob veio da ingestão (Fase 2) ele é "confiável" na origem, mas não há teto de tamanho antes de gastar tokens.
**Fix:** Validar/normalizar a imagem antes do envio (abrir com PyMuPDF/Pillow e re-encodar, ou ao menos checar `len(blob)` contra um teto configurável). Re-renderizar pela mesma via do PDF (`fitz.open(stream=blob)` → pixmap) uniformizaria o tratamento e descartaria payloads quebrados localmente, antes da chamada paga.

## Info

### IN-01: `extract_from_image_pages` usa prompt diferente de `extract_from_text`

**File:** `backend/app/extraction/openai_client.py:140-141`
**Issue:** O caminho de texto envia apenas o `native_text` como `input_text` (sem instrução no turno do usuário, confiando no `instructions=` fixo), enquanto o caminho de visão acrescenta um `input_text` "Extraia os dados deste documento." Essa assimetria pode enviesar levemente as duas rotas a resultados diferentes para o mesmo documento, prejudicando a base estável que as Fases 4/7 vão construir (D-06). Padronizar o turno do usuário entre as rotas.
**Fix:** Usar o mesmo prefixo de instrução (ou nenhum) em ambas as rotas.

### IN-02: `_map_usage`/`_unwrap`/`_refusal_reason` recebem `response` sem type hint

**File:** `backend/app/extraction/openai_client.py:75,84,99`
**Issue:** As três funções helper aceitam `response` sem anotação de tipo, perdendo verificação estática sobre o uso de `.usage`/`.output_parsed`/`.output`. Anotar com o tipo de retorno de `responses.parse` (`ParsedResponse[ExtractionResult]`) daria checagem do mapeamento de tokens.
**Fix:** Adicionar o type hint do tipo de resposta da SDK.

### IN-03: `min_chars_per_page` zera o limiar para PDF de 0 páginas

**File:** `backend/app/extraction/pdf_io.py:60-65`
**Issue:** Para um PDF válido mas com 0 páginas, `page_count == 0` → `min_chars_per_page * 0 == 0` → `total >= 0` é sempre verdadeiro → rota `native_text` com `full_text=""`. O documento seria enviado à IA como texto vazio. Borda improvável (PDFs reais têm ≥1 página), mas a heurística não trata `page_count == 0` explicitamente.
**Fix:** Tratar `page_count == 0` como rota `vision` ou levantar erro controlado (FALHA), em vez de mandar texto vazio à IA.

### IN-04: Comentário do modelo `Document.content_hash` referencia "Plan 04" do CAS incorretamente

**File:** `backend/app/models/document.py:6-7`
**Issue:** O docstring diz "a implementação do CAS é o Plan 04, aqui só a coluna" — mas o CAS já existe e é usado por esta fase (`cas.read_bytes` em stage.py). Comentário desatualizado (provavelmente herdado da Fase 1). Sem impacto funcional.
**Fix:** Atualizar o docstring para refletir que o CAS já está implementado.

---

_Reviewed: 2026-06-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

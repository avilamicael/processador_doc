# Phase 10: Classificação robusta e reprocessamento - Pattern Map

**Mapped:** 2026-06-25
**Files analyzed:** 12 (5 backend src, 1 frontend api lib, 3 frontend pages/hooks, 3 test files)
**Analogs found:** 12 / 12 (todos têm análogo direto no código existente — fase quase 100% aditiva)

Esta fase é **composição de código existente**, não descoberta. Cada arquivo novo/alterado tem um análogo exato no repositório. O valor está em copiar os padrões corretos **preservando invariantes** (ReDoS/timeout, falha-fechada, idempotência, seam `decide` puro, LGPD/não-logar).

---

## File Classification

| Arquivo novo/alterado | Role | Data Flow | Análogo mais próximo | Qualidade |
|-----------------------|------|-----------|----------------------|-----------|
| `backend/app/classification/matcher.py` (alterar `_condition_matches`, `match_templates`; novo `_normalize_text` + helper público `evaluate_groups`) | service / motor puro | transform | o próprio arquivo (`_strip_accents` de `naming.py:146`) | exact (self) |
| `backend/app/classification/stage.py` (alterar `classify_stage`: ramo IA-fallback) | service | request-response (async) | o próprio bloco de desempate `stage.py:221-247` | exact (self) |
| `backend/app/api/templates.py` (novo `POST /templates/preview-signals`) | controller/route | file-I/O (upload) + transform | endpoints CRUD do mesmo arquivo + `pdf_io.extract_text_and_decide` | role-match |
| `backend/app/api/documents.py` (novo `POST /documents/{id}/reprocess` + batch) | controller/route | event-driven (requeue) | `reclassify_document` `documents.py:600-653` | exact |
| `backend/app/config.py` (novo setting `classify_ai_fallback_enabled`) | config | — | `review_confidence_threshold` `config.py:156` + `persist_env_setting` | exact |
| `backend/app/api/config.py` (novo `GET/PUT /config/ai-fallback`) | controller/route | CRUD (1 setting) | `review-threshold` endpoints `api/config.py:43-59` | exact |
| `frontend/src/pages/TemplatesPage.tsx` (painel testar sinais) | component | file-I/O (upload) + request-response | actions/inputs do mesmo arquivo | role-match |
| `frontend/src/pages/AttentionPage.tsx` / `DocumentsPage.tsx` (botões reprocessar) | component | request-response | botão "Reclassificar" `AttentionPage.tsx:270` | exact |
| `frontend/src/lib/api.ts` (funções `postReprocess*`, `previewSignals`, `get/putAiFallback`) | service/client | request-response | `postReclassify` `api.ts:108` + `getReviewThreshold` `api.ts:134` | exact |
| `frontend/src/hooks/useAttention.ts` (hooks reprocess) e `useTemplates.ts` (hook preview) | hook | request-response | `useReclassifyDocument` `useAttention.ts:55` + `useSaveReviewThreshold` `useAttention.ts:99` | exact |
| `backend/tests/classification/test_matcher_norm.py` (novo) | test | unit | `tests/classification/test_matcher_groups.py` | role-match |
| `backend/tests/classification/test_stage_ai_fallback.py` (novo) | test | unit (respx) | `test_stage.py::test_desempate_chama_ia_e_grava_usage` `test_stage.py:286` | exact |
| `backend/tests/test_api_documents.py` / `test_api_templates.py` (estender) | test | api (TestClient) | testes existentes nos mesmos arquivos | exact |

---

## Pattern Assignments

### `backend/app/classification/matcher.py` (service / motor puro, transform)

**Análogo:** o próprio `matcher.py` + `naming._strip_accents`.

**Padrão de remoção de acentos a COPIAR** (`naming.py:146-154` — NÃO importar; copiar o corpo, Pitfall 8 do RESEARCH):
```python
# naming.py:146-154 — stdlib pura, sem tabela própria
def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
```

**Nova função pura `_normalize_text`** (RESEARCH Pattern 1 / Code Examples — usar `re` stdlib só para a regex de normalização, NÃO a lib `regex` que é para ReDoS):
```python
import re as _re
import unicodedata
_PUNCT_RE = _re.compile(r"[^\w\s]", _re.UNICODE)   # não-palavra/espaço → espaço
_WS_RE = _re.compile(r"\s+")                        # runs de espaço E \n → 1 espaço

def _normalize_text(s: str) -> str:
    """Normaliza p/ casamento tolerante de `texto` (D-02). PURA. Não loga (V7)."""
    decomposed = unicodedata.normalize("NFKD", s or "")
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    no_punct = _PUNCT_RE.sub(" ", no_accents.lower())
    return _WS_RE.sub(" ", no_punct).strip()
```

**Bifurcação por modo — INVARIANTE A PRESERVAR** (atual `_condition_matches` `matcher.py:118-149`). O ramo `regex` fica **byte-a-byte intacto** (tetos `_MAX_SIGNAL_REGEX_LEN`/`_MAX_HAYSTACK_LEN` + `timeout=_REGEX_TIMEOUT_S` + `except (regex.error, TimeoutError)`). Só o ramo `texto` muda para usar `_normalize_text` simetricamente (Pitfall 1 e 2):
```python
# refactor de matcher._condition_matches — assinatura recebe AMBOS os haystacks
def _condition_matches(cond, haystack_norm: str, haystack_lower: str) -> bool:
    value = str(cond.get("value", ""))
    mode = cond.get("mode", "texto")
    if mode == "regex":
        # INALTERADO — copiar exatamente matcher.py:130-143 (tetos + timeout + except)
        ...  # usa haystack_lower
    needle = _normalize_text(value)          # SIMETRIA D-02: value também normalizado
    if not needle:
        return False
    return needle in haystack_norm
```

**Preparação dos dois haystacks UMA vez** (atual `match_templates` `matcher.py:181` faz `haystack = (full_text or "").lower()`). Passa a preparar os dois e repassá-los aos grupos:
```python
haystack_lower = (full_text or "").lower()      # p/ regex (comportamento atual)
haystack_norm = _normalize_text(full_text or "") # p/ texto (novo)
```

**Helper público novo `evaluate_groups`** (RESEARCH Open Question 3 — consumido por `match_templates` E pelo preview, garante D-09). Recomendação: `@dataclass(frozen=True)` para `ConditionReport(mode, value, matched)` e `GroupReport(matched, conditions)`, espelhando o estilo de `TemplateMatch`/`MatchDecision` (`matcher.py:69-88`).

**Reusar `_parse_groups`** (`matcher.py:91-115`) sem alteração — a forma canônica de `signals_json` não muda.

---

### `backend/app/classification/stage.py` (service, request-response async)

**Análogo:** o bloco de desempate existente no MESMO arquivo (`stage.py:221-247`).

**Onde o ramo de IA-fallback entra:** após `decide`→quarantine e ANTES do bloco de quarentena (`stage.py:256`), reusando exatamente o padrão do desempate. Copiar a estrutura de `disambiguate` + `Usage` de `stage.py:229-247`:
```python
# stage.py:229-241 — padrão de chamada paga + persistência de Usage a REPLICAR
result, usage = await openai_client.disambiguate(
    _candidates_summary(candidates), extraction.full_text,
)
called_ai = True
usages.append(Usage(
    document_id=doc.id, step=USAGE_STEP,
    prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
))
```

**Diferença no fallback (D-05):** chamar `disambiguate` com `_candidates_summary(templates)` — TODOS os templates, não só os `>= threshold` (contraste com `stage.py:223-228`). Gate por `settings.classify_ai_fallback_enabled and forced_template_id is None`. `Usage` persistido mesmo quando a IA não casa (Pitfall 5 — a tentativa foi paga).

**Invariantes a preservar:** seam `decide` puro (a decisão de chamar IA é do stage, NUNCA do matcher — D-06); idempotência prévia (`stage.py:163-174`); leitura de `get_settings()` (`stage.py:184`) já no fluxo; quarentena via state machine com add ANTES de `transition` (`stage.py:256-266`). `classify_stage` já recarrega templates do DB a cada run (`stage.py:205`) — o reprocess pega edições sem trabalho extra.

**Reusar `_candidates_summary`** (`stage.py:103-113`) — já passa só metadados de config do operador (id/nome/sinais), sem conteúdo do documento (V7/V8).

---

### `backend/app/api/documents.py` (controller/route, event-driven requeue)

**Análogo direto:** `reclassify_document` (`documents.py:600-653`).

**Reprocess (single) = reclassify MENOS o template forçado** (RESEARCH Pattern 3). Copiar `documents.py:600-653` com 3 diferenças: (a) aceita `QUARENTENA` **e** `EM_REVISAO`; (b) sem `body.template_id`; (c) payload SEM `forced_template_id`.

**Guard semântico de estado** (Pitfall 4 — a allowlist sozinha não basta; espelha `documents.py:625-629` e `documents.py:580-584`):
```python
if doc.state not in (DocState.QUARENTENA, DocState.EM_REVISAO):
    raise HTTPException(status.HTTP_409_CONFLICT,
        "reprocessar só é permitido para QUARENTENA ou EM_REVISAO")
```

**Apagar o CR ANTES de requeue** (Pitfall 3 — CRÍTICO; senão a idempotência de `stage.py:163-174` faz no-op). Copiar exatamente `documents.py:631-637`:
```python
cr = session.scalar(
    select(ClassificationResult).where(ClassificationResult.document_id == document_id)
)
if cr is not None:
    session.delete(cr)   # cascade delete-orphan limpa os FilledFields
```

**Transição + requeue** (`documents.py:639-652`, mas payload SEM forced):
```python
try:
    transition(session, doc, DocState.PROCESSANDO)
except InvalidTransition as exc:
    raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
_requeue(session, content_hash=doc.content_hash, step=CLASSIFY_STEP,
         payload={"content_hash": doc.content_hash})   # SEM forced_template_id
return _build_detail(session, doc, _folder_path_for(session, doc))
```

**Reusar:** `_requeue` (`documents.py:549-559`, UNIQUE-safe), `_build_detail` (`documents.py:206-244`), `_folder_path_for` (`documents.py:247-255`), constantes `CLASSIFY_STEP` (`documents.py:57`).

**Batch (D-12):** novo `POST /documents/reprocess` recebendo `{"bucket": "quarentena"|"em_revisao"}` (resolve ids no backend a partir do mesmo filtro de `get_attention` `documents.py:391-403`/`406-415`) OU `{"ids":[...]}`. Espelhar o loop de uma só sessão de `delete_documents` (`documents.py:475-510`) e retornar `{reprocessed: N}` (espelha `DeleteDocumentsOut` `documents.py:188-191`), ignorando ids fora dos estados elegíveis (idempotente).

---

### `backend/app/config.py` + `backend/app/api/config.py` (config + controller CRUD)

**Análogo:** `review_confidence_threshold` em `config.py:156-159` e os endpoints `review-threshold` em `api/config.py`.

**Novo setting** (espelha `config.py:156-159`, mas `bool` default `False` — preserva comportamento atual):
```python
classify_ai_fallback_enabled: bool = Field(
    default=False,
    validation_alias=AliasChoices(
        "CLASSIFY_AI_FALLBACK_ENABLED", "classify_ai_fallback_enabled"),
)
```

**Endpoints** — copiar `api/config.py:43-59` (GET lê de `get_settings()`; PUT chama `persist_env_setting` + `get_settings.cache_clear()`). Reusar `persist_env_setting` (`config.py:256-290`, escrita atômica) e o padrão da chave-constante `_THRESHOLD_ENV_KEY` (`api/config.py:28`). Validação por Pydantic no body (bool não precisa de faixa; espelha `ReviewThresholdIn` `api/config.py:37-40`).

---

### `backend/app/api/templates.py` (controller/route, file-I/O upload + transform)

**Análogo:** endpoints CRUD do mesmo arquivo (`templates.py`) + `pdf_io.extract_text_and_decide`.

**Padrão de router/sessão a copiar** (`templates.py:261-281`): `request.app.state.engine` + `with get_session(engine)`, schemas `In`/`Out` Pydantic, 404 em ausente, `Literal` para dispatch por etiqueta.

**Extração de texto nativo (D-08)** — reusar `pdf_io.extract_text_and_decide` (`pdf_io.py:48`, assinatura `(pdf_bytes, min_chars_per_page) -> tuple[texto, route]`) com `settings.openai_extract_min_chars_per_page` (`config.py:127`). `route == "vision"` → devolver `scanned=true` e NÃO chamar IA (Pitfall 7). Validar magic bytes com `pdf_io.detect_blob_type` (`pdf_io.py:29`) → 422 amigável (V5).

**Reuso do motor (D-09):** ler os sinais do template via `_loads_signals_groups` (`templates.py:52-81`, réplica sincronizada de `_parse_groups`) e rodar o **helper público `evaluate_groups`** novo do matcher — NUNCA reimplementar o casamento (anti-pattern). Resultado por-grupo/por-sinal.

**Upload:** `UploadFile`/`File()` (multipart, requer `python-multipart` — gate `checkpoint:human-verify` antes de `uv add`, RESEARCH Package Audit) OU base64 no body JSON (sem dependência; o cliente `api.ts:42` é JSON-only hoje). Decisão de planning.

**LGPD:** NÃO logar o conteúdo do PDF de teste nem `full_text` (V7 — vale igual ao matcher e ao stage).

---

### Frontend — `api.ts`, hooks, pages

**Cliente API** (`api.ts`) — copiar o padrão de `postReclassify` (`api.ts:108-113`) para os endpoints de reprocess e o de `getReviewThreshold`/`putReviewThreshold` (`api.ts:134-143`) para o toggle ai-fallback:
```ts
export function postReprocess(id: number): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}/reprocess`, { method: 'POST' })
}
```
Para o preview com upload, usar `FormData` (multipart) — NOTA: o `request` helper (`api.ts:42-60`) força `Content-Type: application/json`; o preview precisa de um caminho que NÃO defina esse header (deixar o browser pôr o boundary do multipart) OU enviar base64 via o `request` atual.

**Hooks** (`useAttention.ts`) — copiar `useReclassifyDocument` (`useAttention.ts:55-62`): `useMutation` + `useInvalidateAttention` (`useAttention.ts:37-43`, invalida `['attention']` + `['documents']`). Para o toggle, copiar `useReviewThreshold`/`useSaveReviewThreshold` (`useAttention.ts:92-107`). Para o preview, mutation simples no padrão de `useTemplates.ts:25-31`.

**Botões reprocessar** — copiar o botão "Reclassificar" (`AttentionPage.tsx:270-278`): `disabled={mut.isPending}`, label condicional (`isPending ? 'Reprocessando…' : 'Reprocessar'`). Botão de lote: um único `onClick` que chama a mutation de batch por balde.

**Painel testar sinais (`TemplatesPage.tsx`)** — copiar os padrões de `<input>`/`<button onClick>`/`isPending` já no arquivo (`TemplatesPage.tsx:275,337,535`); adicionar `<input type="file">` para o upload e renderizar o relatório por-grupo/sinal. Nomes/valores vindos do backend são renderizados como texto puro pelo React (T-02-11 — `api.ts:9-10`).

---

### Testes

**`test_matcher_norm.py` (novo)** — análogo `tests/classification/test_matcher_groups.py`. Funções puras, sem DB/IA. Cobrir D-02 (acento/quebra/pontuação/espaço; simetria value↔haystack) e D-04 (palavra trocada NÃO casa). **Verde obrigatório:** `test_matcher_groups.py::test_regex_*`/`test_redos*` continuam passando (Pitfall 1).

**`test_stage_ai_fallback.py` (novo)** — análogo EXATO `test_stage.py::test_desempate_chama_ia_e_grava_usage` (`test_stage.py:286-343`). Copiar o padrão respx:
```python
with respx.mock(base_url="https://api.openai.com/v1", assert_all_called=False) as router:
    route = router.post("/responses").mock(return_value=HxResponse(200, json=_envelope(structured, "resp_x")))
    ...
    result = await classify_stage(s, content_hash="d" * 64)
    assert route.call_count == 1
```
Reusar o fixture `_openai_key` (`test_stage.py:61-63`), helpers `_template`/`_seed_doc`/`_pairs_json`. Cobrir: toggle OFF → quarentena direta, `route.call_count == 0`; toggle ON + nada casou → IA chamada; `Usage(step="classify")` persistido mesmo sem casar.

**Estender `test_api_documents.py`** — análogo `test_detail_*`/`reclassify` no mesmo arquivo. Fixture `client` (`test_api_documents.py:37-43`, TestClient com `schema_engine`). Cobrir reprocess single (QUARENTENA→PROCESSANDO, requeue SEM forced, CR apagado), batch por balde, e guards 409 (doc CONCLUIDO → 409, não 500 — Pitfall 4).

**Estender `test_api_templates.py`** — endpoint preview: texto nativo (relatório por-sinal idêntico ao real), escaneado→flag `scanned`, não-PDF→422. Fixture `client` (`test_api_templates.py`).

---

## Shared Patterns

### Normalização de texto (acentos)
**Fonte:** `backend/app/automation/naming.py:146-154` (`_strip_accents`, NFKD + drop combining).
**Aplicar a:** `matcher._normalize_text` (COPIAR o corpo, não importar — Pitfall 8 mantém o matcher autossuficiente, sem acoplamento `classification → automation`).

### Requeue UNIQUE-safe + apagar CR antes
**Fonte:** `backend/app/api/documents.py:549-559` (`_requeue`) + `documents.py:631-637` (apagar CR).
**Aplicar a:** todos os endpoints de reprocess. SEMPRE apagar `ClassificationResult` antes do requeue (idempotência do stage faz no-op senão — Pitfall 3).

### Guard semântico de estado antes de transition
**Fonte:** `documents.py:580-584` (retry) e `documents.py:625-629` (reclassify).
**Aplicar a:** reprocess. A allowlist permite PROCESSANDO de vários estados; checar a origem explicitamente → 409.

### Setting global + persistência atômica de .env
**Fonte:** `config.py:256-290` (`persist_env_setting`) + `api/config.py:49-59` (PUT + `cache_clear`).
**Aplicar a:** `classify_ai_fallback_enabled` e seu endpoint. Default que preserva comportamento atual (OFF); sem migração Alembic (é env, não coluna).

### Chamada paga de IA + persistência de Usage
**Fonte:** `stage.py:229-241` (`disambiguate` + `Usage(step="classify")`).
**Aplicar a:** ramo de IA-fallback. Persistir `Usage` MESMO quando a IA não casa (a tentativa foi cobrada — Pitfall 5).

### Mutation TanStack + invalidação
**Fonte:** `useAttention.ts:37-62` (`useInvalidateAttention` + `useReclassifyDocument`).
**Aplicar a:** todos os hooks de reprocess. Invalidar `['attention']` + `['documents']` em `onSuccess`.

### Seam puro `decide` / motor reusado (D-06/D-09)
**Fonte:** `matcher.decide` (`matcher.py:193-223`) — puro, sem IA.
**Aplicar a:** stage (IA fora do matcher) e preview (reusa `evaluate_groups`, não reimplementa). NUNCA embutir IA no matcher.

### LGPD/V7 — não logar conteúdo
**Fonte:** docstrings de `matcher.py:41`, `stage.py:34`, `documents.py:25`.
**Aplicar a:** preview (PDF de teste), reprocess e ai-fallback. Logar só metadados (document_id/template_id/route); NUNCA `full_text`/valores de sinal.

---

## No Analog Found

Nenhum. Todos os arquivos têm análogo direto. Únicos pontos sem precedente exato no repo (mas com padrão adjacente claro):

| Item | Role | Data Flow | Observação |
|------|------|-----------|------------|
| Upload `UploadFile`/multipart no preview | controller | file-I/O | NÃO há endpoint multipart existente — o app só recebe arquivos via watcher de pasta. `python-multipart` ausente. Fallback: base64 via `request` JSON atual. Decidir no planning (RESEARCH Open Q1). |
| Relatório por-sinal/grupo (`evaluate_groups`) | service (helper) | transform | O matcher só expõe booleano agregado hoje; o helper público é novo, mas modelado no estilo dos dataclasses `TemplateMatch`/`MatchDecision` (`matcher.py:69-88`). |

---

## Metadata

**Análogos lidos (read-only):**
`matcher.py`, `stage.py`, `api/documents.py`, `api/templates.py`, `config.py`, `api/config.py`, `naming.py` (excerpt), `pdf_io.py` (grep), `openai_client.py` (excerpt), `lib/api.ts`, `hooks/useDocuments.ts`, `hooks/useTemplates.ts`, `hooks/useAttention.ts`, `pages/TemplatesPage.tsx` (grep), `pages/AttentionPage.tsx` (grep), `tests/classification/test_stage.py` (excerpt), `tests/test_api_documents.py` (grep), `tests/test_api_templates.py` (head).

**Escopo de busca:** `backend/app/classification`, `backend/app/api`, `backend/app/automation`, `backend/app/extraction`, `backend/app/config.py`, `backend/tests`, `frontend/src/{pages,hooks,lib}`.
**Data:** 2026-06-25

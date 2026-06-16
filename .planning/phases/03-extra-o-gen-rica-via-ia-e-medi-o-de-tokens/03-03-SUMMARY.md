---
phase: 03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens
plan: 03
subsystem: extraction
tags: [extract-stage, idempotencia, commit-atomico, tokens, state-machine, mark-step, asyncio-to-thread, respx, tdd]

# Dependency graph
requires:
  - phase: 03
    plan: 01
    provides: "ExtractionResult/ExtractedField, modelo Extraction (UNIQUE document_id), modelo Usage, fixtures respx (sucesso+recusa) e PDFs/imagem sintéticos"
  - phase: 03
    plan: 02
    provides: "router.choose (seam D-03), pdf_io (extract_text_and_decide/render_pages_png/detect_blob_type), openai_client (extract_from_text/extract_from_image_pages, ExtractionRefused, ExtractionUsage mapeado)"
  - phase: 01
    provides: "state_machine (transition/mark_step), states (allowlist TRANSITIONS), Document, get_session, cas.read_bytes/store"
provides:
  - "extract_stage: estágio async isolável (sem HTTP), idempotente, com commit atômico (Extraction + Usage + marcador 'extraido' num único commit)"
  - "ExtractStageResult(route, called_ai): called_ai=False sinaliza no-op idempotente (base do call_count==1)"
  - "EXTRACTED_STEP='extraido' (marcador terminal de sucesso da extração; state permanece PROCESSANDO, D-07)"
  - "Suíte de comportamento da fase: test_stage/test_usage/test_state/test_idempotency (OpenAI mockada, 0 token)"
affects: [03-04 worker-wiring, phase-04-templates, phase-05-validacao, phase-07-deterministic]

# Tech tracking
tech-stack:
  added: []
  patterns: ["estágio async espelhando ingest_stage (docstring rica + @dataclass frozen resultado + commit único)", "set-em-memória do marcador + commit único (NÃO mark_step) para atomicidade Extraction+Usage+marcador", "checagem de Extraction existente ANTES da chamada paga (idempotência pré-IA)", "só PyMuPDF em asyncio.to_thread; chamada OpenAI await direto", "respx call_count para provar não-cobrança-dupla"]

key-files:
  created:
    - backend/app/extraction/stage.py
    - backend/tests/extraction/test_stage.py
    - backend/tests/extraction/test_usage.py
    - backend/tests/extraction/test_state.py
    - backend/tests/extraction/test_idempotency.py
  modified: []

key-decisions:
  - "Avanço do marcador via set-em-memória (doc.last_completed_step='extraido') + commit ÚNICO ao final — NÃO mark_step (que comitaria sozinho e quebraria a atomicidade Extraction+Usage+marcador, CR-02)"
  - "Idempotência checada ANTES de ler o blob/chamar a IA: Extraction existente → return no-op (called_ai=False), evitando a chamada PAGA; a UNIQUE(document_id) é a rede no banco"
  - "router.choose (CPU-bound: get_text na heurística de PDF) também vai em asyncio.to_thread; só a chamada OpenAI é await direto (nunca to_thread, nunca asyncio.run)"
  - "full_text persiste o texto nativo disponível mesmo no caminho visão (D-06): PDF escaneado guarda o que houver; imagem crua guarda string vazia (sem texto nativo local)"
  - "Document inexistente para o content_hash levanta ValueError (erro de orquestração) — propaga ao worker; o stage não inventa documento"

patterns-established:
  - "Estágio de pipeline async: localiza entidade → checa idempotência → trabalho CPU-bound em to_thread → I/O externo await → persistência atômica em commit único; recusa/erro propagam ANTES do commit (nada parcial)"
  - "Seed de teste: gravar blob no CAS (via data_dir temporário) + Document PROCESSANDO/'aguardando_extracao' com commit explícito (get_session só auto-commita com pendências no exit)"
  - "Espionar transition no namespace do módulo de stage (monkeypatch raising=False) para provar que o sucesso NÃO usa transition(PROCESSANDO→PROCESSANDO)"

requirements-completed: [EXT-01, EXT-02, USE-02]

# Metrics
duration: 14min
completed: 2026-06-16
---

# Phase 3 Plan 03: extract_stage — Orquestração da Extração (idempotente + atômica) Summary

**Implementou o coração funcional da Fase 3: `extract_stage`, o estágio async isolável (sem HTTP) que liga CAS → router (D-03) → pdf_io → openai_client → persistência, gravando `Extraction` + `Usage(step="extract")` + o marcador `"extraido"` num ÚNICO commit (atomicidade CR-02), com idempotência que checa a `Extraction` existente ANTES de qualquer chamada paga (não cobra duas vezes) e estado correto via marcador (`state` permanece PROCESSANDO, NUNCA `transition(PROCESSANDO→PROCESSANDO)` nem CONCLUIDO). EXT-01 + EXT-02 + USE-02 unidos num fluxo atômico, provados por 10 testes de comportamento com OpenAI mockada (0 token).**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-06-16
- **Completed:** 2026-06-16
- **Tasks:** 2 completed (ambas TDD)
- **Files created:** 5 (1 módulo + 4 testes)

## Accomplishments

- **`extract_stage` — orquestração async idempotente + commit atômico (Task 1):** `async def extract_stage(session, *, content_hash)` espelha `ingest_stage.process_ingest` em forma e garantias (docstring rica, `@dataclass(frozen=True)` para o resultado, commit ÚNICO ao final). Fluxo: localiza o `Document` por `content_hash` → checa `Extraction` existente (no-op idempotente, NÃO chama a IA) → lê o blob do CAS → `router.choose` (seam D-03) → parte PyMuPDF em `asyncio.to_thread` → chamada OpenAI `await` direto → persiste `Extraction` + `Usage(step="extract")` + marcador `"extraido"` em memória, com um único `session.commit()`. Recusa (`ExtractionRefused`) e PDF malformado (`fitz.FileDataError`) PROPAGAM ao worker sem corromper estado (a exceção ocorre antes do commit). Loga só `document_id`/route/`doc_type_guess` (nunca chave/`full_text`/`fields`, V7/V8).
- **Estado correto via marcador (D-07 / correção crítica da fase):** o sucesso avança SÓ `doc.last_completed_step="extraido"` em memória + commit único; `state` permanece `PROCESSANDO`. NÃO usa `mark_step` (que comitaria sozinho, quebrando a atomicidade) nem `transition(PROCESSANDO→PROCESSANDO)` (auto-laço fora da allowlist de `states.py`). Provado por `test_state` (incluindo um espião que falha se `transition` for chamado).
- **Idempotência = não cobrar duas vezes (T-03-07 / Failure Mode 3):** a checagem de `Extraction` existente acontece ANTES de ler o blob e ANTES da chamada paga; `ExtractStageResult.called_ai=False` sinaliza o no-op. `test_idempotency` prova via respx que 2 execuções tocam o endpoint `/responses` UMA única vez (`call_count==1`) e que não há `Extraction`/`Usage` duplicados.
- **Medição de tokens (USE-02 / SC4):** cada extração grava exatamente 1 `Usage(step="extract")` com o mapeamento `input_tokens→prompt_tokens` / `output_tokens→completion_tokens` (já mapeado pelo `openai_client`, gravado direto no mesmo commit atômico). Provado por `test_usage` (120→prompt, 64→completion da fixture sintética).

## Task Commits

Cada task seguiu o ciclo TDD RED → GREEN (Task 1) ou foi escrita como suíte de comportamento contra o stage já implementado (Task 2), commitada atomicamente:

1. **Task 1: extract_stage** — `22258c8` (test, RED) → `0f96281` (feat, GREEN)
2. **Task 2: testes de tokens/estado/idempotência** — `40414a4` (test)

## Files Created

- `backend/app/extraction/stage.py` — `extract_stage` (orquestração async idempotente + commit atômico), `ExtractStageResult`, `EXTRACTED_STEP`
- `backend/tests/extraction/test_stage.py` — 5 testes (texto/visão/imagem, recusa propaga sem corromper, PDF malformado propaga)
- `backend/tests/extraction/test_usage.py` — 2 testes (1 Usage(step=extract) por extração, tokens mapeados; sem duplicação)
- `backend/tests/extraction/test_state.py` — 2 testes (PROCESSANDO + "extraido", nunca CONCLUIDO; transition não chamado)
- `backend/tests/extraction/test_idempotency.py` — 1 teste (2ª execução não re-chama a IA, call_count==1, sem duplicação)

## Verification Evidence

- `uv run pytest tests/extraction/test_stage.py -x -q` → 5 passed
- `uv run pytest tests/extraction/test_usage.py tests/extraction/test_state.py tests/extraction/test_idempotency.py -q` → 5 passed
- `uv run pytest tests/extraction -q` → 40 passed (schema/persistence do Plan 01 + pdf_io/router/openai_client do Plan 02 + stage/usage/state/idempotency deste plan)
- `uv run pytest -q` (suite completa do backend) → 163 passed, sem regressões (+10 testes vs. Plan 02)
- `uv run ruff check app/extraction/stage.py tests/extraction/` → All checks passed
- Nenhum teste gasta token (respx mocka `POST /v1/responses`); nenhum teste usa `transition(PROCESSANDO→PROCESSANDO)` — sucesso via marcador "extraido"

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Seed de teste exigia commit explícito**
- **Found during:** Task 1
- **Issue:** O helper de seed criava o `Document`, fazia `session.flush()` e dependia do auto-commit de `get_session` no exit. Como `get_session` só comita se `session.new/dirty/deleted` estiver populado e o `flush` esvazia `session.new`, o seed era descartado no `close()` — o stage não encontrava o documento (`ValueError`).
- **Fix:** Trocar o `flush` por `session.commit()` explícito no helper de seed, com comentário explicando o comportamento de auto-commit.
- **Files modified:** `backend/tests/extraction/test_stage.py` (e o mesmo padrão nos seeds de test_usage/test_state/test_idempotency)
- **Commit:** `0f96281`, `40414a4`

**2. [Rule 3 - Blocking] Chave OpenAI ausente no env de teste**
- **Found during:** Task 1
- **Issue:** `_client()` constrói `AsyncOpenAI(api_key=None)` quando `OPENAI_API_KEY` não está no env, e a SDK levanta `OpenAIError("Missing credentials")` antes de o respx interceptar.
- **Fix:** Fixture autouse `_openai_key` que depende de `data_dir` (para `DATA_DIR` e `OPENAI_API_KEY` coexistirem no env) e seta a chave fictícia + `get_settings.cache_clear()` (sem monkeypatchar `get_settings`, pois o stage lê dele tanto `data_dir` quanto o tunável de extração).
- **Files modified:** `backend/tests/extraction/test_stage.py`, `test_usage.py`, `test_state.py`, `test_idempotency.py`
- **Commit:** `0f96281`, `40414a4`

**3. [Rule 1 - Bug] `mock_openai.assert_all_called` no teste de PDF malformado / re-registro de rota na idempotência**
- **Found during:** Task 1 (malformado) e Task 2 (idempotência)
- **Issue:** (a) O teste de PDF malformado não chega à IA (fitz levanta antes), mas `mock_openai` exige todas as rotas chamadas no exit; (b) `mock_openai.post("/responses")` re-registra a rota com um mock vazio (retorna `''`), quebrando o parse da SDK.
- **Fix:** (a) Remover `mock_openai` do teste de PDF malformado (a IA não deve ser tocada num PDF corrompido — vira asserção positiva); (b) usar `mock_openai.calls.call_count` em vez de re-registrar a rota para contar chamadas.
- **Files modified:** `backend/tests/extraction/test_stage.py`, `test_idempotency.py`
- **Commit:** `0f96281`, `40414a4`

_Ajustes menores de lint (f-string sem placeholder, import sort, `B017` blind-exception trocado por `fitz.FileDataError` concreto, quebra de linha >100) aplicados antes dos commits._

## Known Stubs

Nenhum. Este plan entrega o estágio de extração completo e atômico. O que falta é o WIRING no worker (Plan 04): registrar o handler de extração na fila para que o job `extract` chame `extract_stage`, capture `ExtractionRefused`/erros e roteie para retry/FALHA via `transition(...FALHA)`, e marque o job done APÓS o commit atômico do stage. Isso é por desenho da fase (Wave 4), não stub.

## Threat Flags

Nenhuma surface nova além do `<threat_model>` do plano. T-03-07 (cobrança dupla) e T-03-08 (medição perdida/dupla) mitigados e PROVADOS por test_idempotency/test_usage; T-03-09 (PDF malformado) propaga como `fitz.FileDataError` controlada (worker tratará); T-03-10 (vazamento) — log só com metadados. T-03-11 (alucinação de campo) permanece `accept` (sem gate de qualidade na Fase 3 — D-09).

## Notas para o Plan 04 (worker wiring)

- **Handler de extração:** o worker deve, para um job `extract`, abrir sessão própria → `await extract_stage(session, content_hash=...)` → em sucesso, marcar o job done APÓS o retorno (o commit atômico já ocorreu dentro do stage). NÃO chamar `mark_done` antes de `extract_stage` retornar.
- **Recusa/erro:** capturar `ExtractionRefused`, `fitz.FileDataError` e erros transitórios; aplicar `schedule_retry` com backoff e, ao esgotar, `transition(doc, DocState.FALHA)` (a allowlist PROCESSANDO→FALHA existe). O stage NÃO faz retry — é responsabilidade da fila (D-08).
- **Idempotência de resume:** re-despachar o mesmo job é seguro — `extract_stage` é no-op se a `Extraction` já existe (`called_ai=False`); a IA não é re-chamada.
- **CPU-bound já isolado:** o stage já envolve a parte PyMuPDF em `asyncio.to_thread`; o worker só precisa garantir 1 sessão por coroutine (padrão já estabelecido na Fase 2).

## Self-Check: PASSED

Os 5 artefatos-chave existem em disco e os 3 commits de tarefa (`22258c8`, `0f96281`, `40414a4`) estão presentes no histórico git.

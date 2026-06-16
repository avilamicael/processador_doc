---
phase: 03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens
plan: 02
subsystem: extraction
tags: [openai, responses-api, structured-outputs, pymupdf, magic-bytes, seam-d03, tokens, respx, tdd]

# Dependency graph
requires:
  - phase: 03
    plan: 01
    provides: "ExtractionResult/ExtractedField (text_format), tunables OPENAI_EXTRACT_*, fixtures respx (sucesso+recusa) e PDFs/imagem sintéticos"
provides:
  - "pdf_io: detect_blob_type (magic bytes) + extract_text_and_decide (heurística texto-vs-visão EXT-01/D-04) + render_pages_png"
  - "router.choose: seam de extração D-03 plugável (Fases 4/7 estendem) — nunca crava 'sempre IA'"
  - "openai_client: AsyncOpenAI sobre Responses API + Structured Outputs; _unwrap de recusa; ExtractionUsage (input→prompt/output→completion)"
  - "ExtractionRefused: exceção de recusa (output_parsed is None → fila faz backoff → FALHA, D-08)"
affects: [03-03 extract_stage, 03-04 worker-wiring, phase-04-templates, phase-07-deterministic]

# Tech tracking
tech-stack:
  added: []
  patterns: ["funções de módulo atrás de interface (sem classe)", "magic-byte detection p/ blob sem extensão no CAS", "seam D-03 mínimo (só pdf_io, sem OpenAI/DB)", "segredo via get_secret_value só no ponto de criação", "mapeamento de tokens input→prompt/output→completion", "TDD RED/GREEN por task"]

key-files:
  created:
    - backend/app/extraction/pdf_io.py
    - backend/app/extraction/router.py
    - backend/app/extraction/openai_client.py
    - backend/tests/extraction/test_pdf_io.py
    - backend/tests/extraction/test_router.py
    - backend/tests/extraction/test_openai_client.py
  modified: []

key-decisions:
  - "render_pages_png() sem parâmetro dpi explícito (usa o padrão do fitz) — o AI-SPEC mostrava dpi=... como placeholder; mantido mínimo, DPI vira tunável só quando observação exigir"
  - "ExtractionRefused definido no próprio openai_client.py (não em errors.py separado) — uma exceção, módulo único é mais simples; pode migrar p/ errors.py se a Fase crescer"
  - "ExtractionUsage como @dataclass(frozen=True) com prompt_tokens/completion_tokens já mapeados — o caller (extract_stage, Plan 03) grava direto no modelo Usage sem reconverter"
  - "PNG magic bytes completo (\\x89PNG\\r\\n\\x1a\\n) em vez de só \\x89PNG — mais robusto contra falso-positivo"

patterns-established:
  - "Seam D-03 (router.choose): imagem→vision direto; PDF→delega heurística de pdf_io; docstring documenta que Fases 4/7 plugam atalho local custo-zero aqui"
  - "Segredo: _client() chama get_secret_value() só na criação do AsyncOpenAI; teste assere ausência do valor da chave em logs/erros (sucesso E recusa)"
  - "Recusa: _unwrap levanta ExtractionRefused logando só o motivo do bloco refusal (metadado), nunca chave/conteúdo (D-08/CFM5)"

requirements-completed: [EXT-01, EXT-02, USE-02]

# Metrics
duration: 9min
completed: 2026-06-16
---

# Phase 3 Plan 02: Primitivas de Extração (pdf_io + router + openai_client) Summary

**Implementou as três primitivas puras e testáveis da extração atrás de interface: `pdf_io` (PyMuPDF — texto nativo, heurística texto-vs-visão, render PNG, detecção PDF-vs-imagem por magic bytes), `router.choose` (o seam arquitetural D-03 que Fases 4/7 estendem) e `openai_client` (AsyncOpenAI sobre a Responses API + Structured Outputs, com recusa tratada via `ExtractionRefused` e tokens mapeados) — tudo com OpenAI mockado por respx, sem gastar token.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-16
- **Completed:** 2026-06-16
- **Tasks:** 3 completed (todas TDD)
- **Files created:** 6 (3 módulos + 3 testes)

## Accomplishments

- **`pdf_io.py` — leitura local sem custo de IA (EXT-01/D-04):** `detect_blob_type` distingue PDF/JPEG/PNG por magic bytes (o CAS guarda só o hash, sem extensão — Pitfall 5); `extract_text_and_decide` soma o texto nativo de TODAS as páginas e decide `native_text`/`vision` contra `min_chars_per_page * page_count`; `render_pages_png` renderiza 1 PNG por página para o caminho visão. Imagem nunca é aberta como PDF. PDF malformado levanta `fitz.FileDataError` controlado (T-03-06).
- **`router.choose` — seam D-03 plugável (Critical Failure Mode 4 evitado):** mínimo e sem lógica de OpenAI/DB — imagem→`vision` direto, PDF→delega a `pdf_io`. Docstring documenta que Fases 4 (template casado) e 7 (determinístico→nativo→IA) plugam o atalho local de custo zero AQUI, sem reescrever o motor. Blob desconhecido levanta `ValueError` (não chuta rota).
- **`openai_client.py` — Responses API + Structured Outputs isolado:** `extract_from_text` (1 bloco `input_text`) e `extract_from_image_pages` (1 `input_text` + N `input_image` base64 com `detail` do tunável) chamam `responses.parse(text_format=ExtractionResult)`; `_unwrap` trata recusa (`output_parsed is None` → `ExtractionRefused`); `ExtractionUsage` mapeia `input_tokens→prompt`, `output_tokens→completion` (D-10). `max_output_tokens` sempre explícito (Pitfall 3); SYSTEM_INSTRUCTIONS fixo sem few-shot; sem retry (é da fila, Plan 04).
- **Segredo nunca vaza (CFM 5 / T-03-03):** `.get_secret_value()` só no ponto de criação do `AsyncOpenAI`; testes asseram que o valor da chave não aparece em logs/erros nos caminhos de sucesso E de recusa.

## Task Commits

Cada task seguiu o ciclo TDD RED → GREEN, commitado atomicamente:

1. **Task 1: pdf_io** — `7274dc4` (test, RED) → `120f69c` (feat, GREEN)
2. **Task 2: router.choose (seam D-03)** — `3c821cb` (test, RED) → `ea85485` (feat, GREEN)
3. **Task 3: openai_client** — `62f3368` (test, RED) → `e255464` (feat, GREEN)

## Files Created

- `backend/app/extraction/pdf_io.py` — PyMuPDF: magic bytes + heurística texto-vs-visão + render PNG
- `backend/app/extraction/router.py` — seam de extração D-03 (`choose`)
- `backend/app/extraction/openai_client.py` — AsyncOpenAI/Responses API + `_unwrap` + `ExtractionUsage` + `ExtractionRefused`
- `backend/tests/extraction/test_pdf_io.py` — 11 testes (magic bytes, heurística, render, malformed)
- `backend/tests/extraction/test_router.py` — 6 testes (rotas + ValueError + docstring D-03)
- `backend/tests/extraction/test_openai_client.py` — 5 testes (sucesso texto/visão, recusa, chave não vaza)

## Verification Evidence

- `uv run pytest tests/extraction/test_pdf_io.py -x -q` → 11 passed
- `uv run pytest tests/extraction/test_router.py -x -q` → 6 passed
- `uv run pytest tests/extraction/test_openai_client.py -x -q` → 5 passed
- `uv run pytest tests/extraction -q` → 30 passed (schema/persistence do Plan 01 + pdf_io/router/openai_client deste plan)
- `uv run pytest -q` (suite completa do backend) → 153 passed, sem regressões
- `uv run ruff check app/extraction/ tests/extraction/` → All checks passed
- Nenhum teste gasta token (respx mocka `POST /v1/responses`)

## Deviations from Plan

None — plano executado exatamente como escrito. As três primitivas foram criadas como funções de módulo (sem classe), o seam D-03 ficou mínimo, a recusa levanta `ExtractionRefused`, os tokens são mapeados input→prompt/output→completion, e a chave nunca aparece em logs (testado). Pequenas decisões de discrição (DPI implícito no render, `ExtractionRefused` no próprio módulo) estão em key-decisions.

## Known Stubs

Nenhum. Este plan entrega primitivas puras e completas (leitura de PDF, roteamento, cliente OpenAID). O que ainda falta é a ORQUESTRAÇÃO: o `extract_stage` (Plan 03) que liga `router.choose` → `pdf_io` → `openai_client` → persistência (Extraction + Usage) com commit atômico, e o wiring no worker (Plan 04). Isso é por desenho da fase (Wave 3/4), não stub.

## Threat Flags

Nenhuma surface de segurança nova além do já mapeado no `<threat_model>` do plano (T-03-03/04 mitigados via segredo nunca logado e teste de ausência da chave; T-03-06 — PDF malformado vira `fitz.FileDataError` controlado, capturado pelo stage no Plan 03).

## Notas para os próximos plans (03 / 04)

- **`extract_stage` (Plan 03)** consome: `cas.read_bytes(content_hash)` → `router.choose(blob)` → se `native_text`: `pdf_io.extract_text_and_decide` + `openai_client.extract_from_text`; se `vision`: `pdf_io.render_pages_png` + `openai_client.extract_from_image_pages`. Persistir SEMPRE o `full_text` (D-06) mesmo no caminho visão.
- **Token → Usage**: `ExtractionUsage(prompt_tokens, completion_tokens)` já vem mapeado; gravar direto em `Usage(step="extract")` no MESMO commit atômico que persiste `Extraction` (evita cobrança dupla, Pitfall 3).
- **Recusa/erro**: `extract_stage` apenas deixa `ExtractionRefused` (e erros transitórios) PROPAGAREM — o worker (Plan 04) captura, faz backoff e, ao esgotar, `transition(... FALHA)`. NÃO implementar retry no stage.
- **Modelo**: `openai_extract_model` default `gpt-4o-2024-08-06` é placeholder — confirmar o vigente na conta antes de qualquer chamada real (precisa de visão + Structured Outputs).

## Self-Check: PASSED

Os 6 artefatos-chave existem em disco e os 6 commits de tarefa (`7274dc4`, `120f69c`, `3c821cb`, `ea85485`, `62f3368`, `e255464`) estão presentes no histórico git.

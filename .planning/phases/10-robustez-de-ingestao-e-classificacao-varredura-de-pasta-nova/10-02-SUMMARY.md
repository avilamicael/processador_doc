---
phase: 10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova
plan: 02
subsystem: api/classification
tags: [preview, sinais, matcher, templates, lgpd, dos]
requires:
  - "matcher.evaluate_groups + _prepare_haystacks (Plano 01, D-09)"
  - "pdf_io.detect_blob_type + extract_text_and_decide (Fase 3)"
  - "templates.py CRUD + _loads_signals_groups (Fase 06.1-02)"
provides:
  - "POST /templates/preview-signals (base64 → texto nativo → evaluate_groups → relatório por-grupo/condição + flag scanned)"
  - "PreviewSignalsOut: scanned/matched_any/groups[conditions] — contrato p/ o frontend (Plano 05)"
affects:
  - "backend/app/api/templates.py"
  - "backend/tests/test_api_templates.py"
tech-stack:
  added: []
  patterns:
    - "base64 stdlib no body JSON (NÃO multipart): evita python-multipart, mantém api.ts JSON-only"
    - "preview custo-zero reusa o motor real do matcher (fonte-única, D-09): nunca reimplementa casamento"
    - "validação de upload em camadas: base64 → teto de bytes → magic bytes → leitura (falha fechada 422/413)"
key-files:
  created: []
  modified:
    - "backend/app/api/templates.py"
    - "backend/tests/test_api_templates.py"
decisions:
  - "Open Q1: base64 no body JSON, não multipart/UploadFile — zero dependência nova, sem gate de slopcheck"
  - "Escaneado (route=vision) retorna scanned=true/groups=[] SEM chamar matcher nem IA (D-08/Pitfall 7) — custo zero garantido"
  - "Relatório do endpoint é byte-idêntico ao de matcher.evaluate_groups sobre o mesmo texto (D-09), provado por teste"
metrics:
  duration: ~8 min
  completed: 2026-06-25
  tasks: 2
  files: 2
---

# Phase 10 Plan 02: Preview de Sinais (testar sinais) Summary

Endpoint `POST /templates/preview-signals` (ferramenta "testar sinais", D-07): recebe um PDF de teste em base64, extrai o texto NATIVO via PyMuPDF (custo zero, D-08), roda os sinais do template pelo MESMO motor da classificação real (`matcher.evaluate_groups`, D-09) e devolve o detalhamento por-grupo/por-condição (casa/falha). PDF escaneado → `scanned=true` sem tocar a IA; não-PDF / base64 inválido / acima do teto → 422/413; template ausente → 404.

## What Was Built

### Task 1 — Endpoint `POST /templates/preview-signals` (`7cfd597`)
- Schemas `PreviewSignalsIn` (`template_id`, `pdf_base64`), `PreviewConditionOut`, `PreviewGroupOut`, `PreviewSignalsOut` (`scanned`/`matched_any`/`groups`).
- Pipeline de validação de upload em camadas (todas falha-fechada): carrega template (404 se ausente) → `base64.b64decode(validate=True)` (422 se inválido) → teto `_MAX_PREVIEW_BYTES=20MB` (413, V5/T-10-04) → `pdf_io.detect_blob_type` magic bytes (422 para não-PDF, V5/T-10-04T) → `extract_text_and_decide` (422 para PDF malformado).
- `route == "vision"` → `PreviewSignalsOut(scanned=True, matched_any=False, groups=[])` **sem chamar IA nem o matcher** (D-08/Pitfall 7, custo zero).
- Texto nativo → `_loads_signals_groups(signals_json)` + `matcher.evaluate_groups(grupos, texto)`, mapeando cada `GroupReport`/`ConditionReport` para os schemas Out; `matched_any = any(g.matched)`.
- Blob NUNCA persistido (memória só). Nada logado (LGPD/V7): nem texto, nem blob, nem valores de sinal.

### Task 2 — Cobertura de API do preview (`650fb68`)
- Helper `_native_pdf_b64` constrói um PDF de texto nativo em memória via `fitz` e codifica em base64.
- Casos: texto nativo casa (relatório por-grupo: grupo 1 casa, grupo 2 falha), texto nativo não casa, não-PDF → 422, base64 inválido → 422, template inexistente → 404.
- Escaneado: `route="vision"` mockado via `monkeypatch` + sentinela que faz `evaluate_groups` lançar se for chamado → prova `scanned=true`, `groups=[]`, motor não executado (D-08).
- Identidade D-09: roda `matcher.evaluate_groups` diretamente sobre o mesmo texto e compara `matched_any`, número de grupos, e por-condição (`matched`/`mode`/`value`) com o retorno do endpoint.

## Deviations from Plan

None — plano executado exatamente como escrito. Sem dependência nova (só `base64`/`binascii` da stdlib). Sem checkpoints. Sem auth gates.

## Verification

- `uv run python -c "import app.api.templates"` — importa sem erro (sem multipart).
- `uv run pytest tests/test_api_templates.py -x -q` — **23 passed** (16 pré-existentes + 7 novos do preview).
- `uv run pytest tests/classification -q` — **57 passed** (não-regressão do motor reusado, D-09).
- `uv run pytest -q` (suíte completa) — **480 passed**.

## Notas

- Deprecation warning do Starlette (`HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT`) aparece nos testes de 422. É convenção pré-existente do repo (usada em `watched_folders.py`/`templates.py` inteiro); o constante ainda resolve para 422. Mudança seria repo-wide e fora do escopo deste plano — não alterado (SCOPE BOUNDARY).

## Self-Check: PASSED

- FOUND: backend/app/api/templates.py (endpoint `preview_signals` + 4 schemas)
- FOUND: backend/tests/test_api_templates.py (7 testes de preview)
- FOUND commit 7cfd597 (Task 1)
- FOUND commit 650fb68 (Task 2)

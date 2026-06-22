---
phase: quick-260622-ebo
plan: 01
subsystem: empacotamento/distribuição (Windows) + serviço single-origin
tags: [windows, install, powershell, fastapi, staticfiles, spa, uv]
requires:
  - backend/app/main.py (FastAPI app + routers + /health já existentes)
  - frontend (build Vite -> frontend/dist)
provides:
  - "Serviço single-origin: FastAPI serve frontend/dist com fallback SPA sem quebrar API/health"
  - "instalar.ps1 / atualizar.ps1 (Windows, PT-BR) — instalação e atualização preservando dados"
  - "INSTALL-WINDOWS.md — guia do operador"
affects:
  - backend/app/main.py
tech-stack:
  added: []
  patterns:
    - "Catch-all GET /{full_path:path} registrado por ÚLTIMO (após routers + /health) para fallback SPA"
    - "FRONTEND_DIST resolvido via Path(__file__).resolve().parents[2] (independe do CWD)"
    - "Confinamento anti path-traversal via is_relative_to antes de servir arquivo real"
    - "uvicorn --workers 1 obrigatório (watcher+worker como asyncio.Task por processo)"
key-files:
  created:
    - backend/tests/test_static_spa.py
    - instalar.ps1
    - atualizar.ps1
    - INSTALL-WINDOWS.md
  modified:
    - backend/app/main.py
decisions:
  - "Catch-all dinâmico (resolve FRONTEND_DIST por requisição) em vez de StaticFiles(html=True) montado em '/' — html=True quebra deep-links de SPA (404 em subcaminhos); o catch-all serve index.html para qualquer rota não-API."
  - "FRONTEND_DIST resolvido por requisição a partir do atributo de módulo (não capturado em closure) — permite testar com dist temporário via monkeypatch e degradar quando ausente."
metrics:
  duration: ~5 min
  completed: 2026-06-22
  tasks: 3
  files: 5
---

# Quick 260622-ebo: Criar instalação Windows (Python+uv) servindo backend+frontend single-origin — Summary

FastAPI passa a servir o frontend buildado (frontend/dist) num único processo em http://localhost:8000 com fallback de SPA, sem quebrar a API nem o /health, e degradando sem crash quando o dist está ausente; acompanha instalador/atualizador PowerShell (PT-BR) e guia de instalação Windows.

## O que foi feito

- **Task 1 (TDD) — Serviço single-origin em `main.py`:** adicionado `FRONTEND_DIST` (resolvido via `Path(__file__).resolve().parents[2]/"frontend"/"dist"`, independente do CWD) e um handler catch-all `GET /{full_path:path}` registrado **por último** (após todos os `include_router` e o `/health`). O handler serve arquivos reais confinados ao dist (assets, favicon, vite.svg) e cai em `index.html` para qualquer outro caminho (fallback SPA). Quando o dist está ausente, emite aviso PT-BR via `logging` no import e retorna 404 nas rotas de frontend — sem crashar o boot. `backend/tests/test_static_spa.py` cobre todos os casos do `<behavior>`.
- **Task 2 — `instalar.ps1` e `atualizar.ps1` (PT-BR, idempotentes):** `instalar.ps1` garante Python 3.12 (winget) + uv (instalador oficial) → `uv sync` → cria `backend\.env` de `.env.example` (avisando para preencher a chave) → builda o frontend se Node disponível → `alembic upgrade head` → sobe `uvicorn --workers 1`. `atualizar.ps1` faz `git pull` + `uv sync` + rebuild + `alembic upgrade head` + restart, com banner explícito de que os dados em `%ProgramData%\ProcessadorDocumentos` são preservados.
- **Task 3 — `INSTALL-WINDOWS.md`:** guia passo a passo em PT-BR — pré-requisitos, execução do instalador, ajuste de `ExecutionPolicy` por sessão, configuração da `OPENAI_API_KEY` no `.env`, acesso em localhost:8000, atualização preservando dados e seção de troubleshooting (porta 8000, ExecutionPolicy, chave ausente/inválida, dist faltando, onde ficam dados/logs).

## Decisões

- **Catch-all dinâmico vs `StaticFiles(html=True)`:** o plano sugeria `app.mount("/assets", StaticFiles(...))` + catch-all. Optei por um **único** catch-all que resolve `FRONTEND_DIST` em tempo de requisição (lendo o atributo do módulo). Motivo: (1) serve assets e fallback no mesmo handler; (2) `is_dir()` por requisição degrada limpo quando o dist some/aparece; (3) permite testar de forma determinística com um dist temporário via `monkeypatch`, sem depender do build (que é git-ignored e ausente em CI). `StaticFiles(html=True)` montado em "/" foi descartado porque dá 404 em deep-links de SPA.

## Deviations from Plan

### Auto-fixed / Ajustes

**1. [Rule 3 - Abordagem] Catch-all único em vez de mount estático + skipif**
- **Found during:** Task 1
- **Issue:** O plano previa `app.mount("/assets", StaticFiles(...))` decidido no import e testes com `pytest.mark.skipif(not FRONTEND_DIST.is_dir())`. Como `frontend/dist` é git-ignored e ausente no worktree/CI, os testes de frontend ficariam sempre pulados — não provariam o comportamento.
- **Fix:** Resolver `FRONTEND_DIST` por requisição num único catch-all e testar com um `dist` temporário injetado via `monkeypatch.setattr(app_main, "FRONTEND_DIST", ...)`. Mantém o comportamento exigido pelo `<behavior>` (assets reais, deep-link SPA, degradação 404 sem dist) e prova tudo de forma determinística. Também build real do frontend foi executado e validado ao vivo.
- **Files modified:** backend/app/main.py, backend/tests/test_static_spa.py
- **Commits:** 73b8edf, ffbc8b4

## Verificação

- `uv run pytest tests/test_static_spa.py tests/test_api_documents.py -x -q` → 19 passed.
- `uv run pytest -q` (suíte inteira) → **409 passed**, zero regressão; nenhuma rota de API capturada pelo catch-all.
- Boot manual (`uvicorn app.main:app --host 127.0.0.1 --workers 1`) após `alembic upgrade head` e `npm run build`:
  - `/health` → 200 `{"status":"ok","db":"ok","version":"0.1.0"}`
  - `/documents`, `/templates`, `/watched-folders`, `/config/review-threshold` → 200 `application/json` (não index.html)
  - `/` → index.html do frontend
  - `/documentos` (deep-link) → index.html (não 404)
  - `/assets/index-*.js` → asset real `text/javascript` (não index.html)
- Sem dist (DATA_DIR temporário, sem build): `/health` 200, `/` e `/documentos` 404 (degradação), boot sem crash.
- `npm ci && npm run build` → gera `frontend/dist/index.html` + `dist/assets/` com sucesso (Node 24).
- Segredo: `grep` confirma que nenhum script lê/exibe/loga o valor de `OPENAI_API_KEY`.
- `frontend/dist` permanece git-ignored — não foi commitado.

## Known Stubs

Nenhum.

## Self-Check: PASSED

Arquivos criados/modificados (existência confirmada):
- FOUND: backend/app/main.py
- FOUND: backend/tests/test_static_spa.py
- FOUND: instalar.ps1
- FOUND: atualizar.ps1
- FOUND: INSTALL-WINDOWS.md

Commits (confirmados em git log):
- FOUND: ffbc8b4 (test — RED)
- FOUND: 73b8edf (feat — GREEN main.py)
- FOUND: 04cd242 (feat — scripts PowerShell)
- FOUND: 2c16a67 (docs — INSTALL-WINDOWS.md)

## TDD Gate Compliance

Task 1 seguiu RED/GREEN: commit `test(...)` ffbc8b4 (falhou por `AttributeError: FRONTEND_DIST`) precede o commit `feat(...)` 73b8edf (suíte verde). REFACTOR não foi necessário (implementação já enxuta).

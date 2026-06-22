---
phase: quick-260622-f4b
plan: 01
subsystem: distribuicao-windows
tags: [windows, powershell, release, packaging, github-releases, install]
requires: []
provides:
  - "empacotar.ps1 — gera ZIP de release auto-contido (frontend/dist incluído)"
  - "atualizar.ps1 — atualizador sem Git (GitHub Releases ou -LocalZip)"
  - "instalar.ps1 — pula build quando frontend/dist já existe"
  - "INSTALL-WINDOWS.md — dois fluxos (cliente / dev)"
affects:
  - empacotar.ps1
  - atualizar.ps1
  - instalar.ps1
  - INSTALL-WINDOWS.md
tech-stack:
  added: []
  patterns:
    - "Distribuição via ZIP de release auto-contido (sem Git/Node no cliente)"
    - "Inclusão explícita de itens no staging (allowlist) para não vazar segredos"
    - "Atualização preservando backend/.env e %ProgramData%"
key-files:
  created:
    - empacotar.ps1
  modified:
    - atualizar.ps1
    - instalar.ps1
    - INSTALL-WINDOWS.md
decisions:
  - "empacotar.ps1 monta o staging por inclusão EXPLÍCITA (item a item), nunca por exclusão recursiva — garante que .env/.git/node_modules/frontend/src/tests/*.db*/data nunca entram no pacote (T-f4b-01)."
  - "atualizar.ps1 não apaga backend/ antes de copiar; o ZIP só traz .env.example, então o backend/.env existente é preservado por desenho (T-f4b-02)."
  - "Download de asset da release via HTTPS sem verificação de assinatura no piloto (T-f4b-04, accept); -LocalZip cobre entrega offline controlada."
metrics:
  duration: ~8 min
  completed: 2026-06-22
---

# Quick 260622-f4b: Entrega Windows via ZIP (sem Git) Summary

Habilitada a entrega e atualização do sistema no Windows via **ZIP de release auto-contido** publicado em GitHub Releases: o cliente piloto instala e atualiza **sem Git e sem Node** (o `frontend/dist` já vem buildado dentro do pacote), enquanto o dev gera o pacote com `empacotar.ps1`. O artefato de build permanece git-ignored — só existe dentro do ZIP de release.

## What Was Built

- **`empacotar.ps1`** (NOVO, raiz) — rodado pelo DEV em Windows com Node. Exige npm (build obrigatório), builda o frontend (`npm ci` + `npm run build`), lê a versão de `backend/pyproject.toml` via regex, monta staging por inclusão explícita e gera `processador-doc-<versao>.zip`. Imprime (sem executar) o `gh release create`.
- **`atualizar.ps1`** (REESCRITO) — removido `git pull`. `param([string]$LocalZip)` no topo. Modo ONLINE consulta `api.github.com/repos/avilamicael/processador_doc/releases/latest`, seleciona o asset `.zip` e baixa; modo OFFLINE usa `-LocalZip`. Extrai e sobrescreve só o código, preservando `backend/.env` e `%ProgramData%`. Mantém `uv sync` + `alembic upgrade head` + `uvicorn --workers 1`. Limpeza de temporários em `finally`.
- **`instalar.ps1`** (AJUSTE) — quando `frontend/dist` existe, mensagem clara `frontend\dist já presente (pacote de release ou build anterior) — build pulado`. Ordem dist→npm→aviso e idempotência mantidas; restante do script intocado.
- **`INSTALL-WINDOWS.md`** (REESCRITO) — dois fluxos: Fluxo A (Cliente, ZIP de release, sem Git/Node) e Fluxo B (Dev, clone + `empacotar.ps1` + `gh release create`). Troubleshooting acrescido de "Release não encontrada / sem internet" (`-LocalZip`) e esclarecimento de que o `dist` já vem no pacote. Removida toda menção a `git pull` para atualização.

## Task Commits

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Criar empacotar.ps1 | d203923 | empacotar.ps1 |
| 2 | Reescrever atualizar.ps1 | 5735e81 | atualizar.ps1 |
| 3 | Ajustar instalar.ps1 + INSTALL-WINDOWS.md | c81dcfe | instalar.ps1, INSTALL-WINDOWS.md |

## Verification

Ambiente sem `pwsh` (host Linux) — verificação por **análise estática** (grep dos tokens-chave + revisão manual da lógica):

- **Task 1:** `test -f empacotar.ps1` + presença de `Compress-Archive`, `version =`, `npm run build`, `processador-doc-`; ausência de `gh release create.*Invoke` (o comando só é impresso via `Write-Host`). Revisado: cópia item a item (allowlist), nenhum `.env`/`.git`/`node_modules`/`frontend\src` no staging, OPENAI_API_KEY nunca lida. → OK
- **Task 2:** presença de `param(`, `LocalZip`, `releases/latest`, `Expand-Archive`, `alembic upgrade head`, `--workers 1`; ausência de `git pull`. Revisado: `param` é o primeiro statement (só comentários antes — válido em PowerShell); `backend/` não é apagado antes da cópia (preserva `.env`); nenhuma cópia mira `%ProgramData%`; `finally` limpa temporários. → OK
- **Task 3:** `instalar.ps1` contém `build pulado` e mantém `if (Test-Path $DistDir)`; `INSTALL-WINDOWS.md` contém `LocalZip`, `releases/latest`, `empacotar.ps1` e **não** contém `git pull`. (Nota: o check `grep 'Test-Path $DistDir'` falhou inicialmente por expansão de variável do bash no argumento não-aspado; confirmado presente com `grep -F` na linha 86.) → OK

`git status --short` vazio após os commits: nenhum `frontend/dist` nem `.zip` versionado (dist segue git-ignored).

## Deviations from Plan

None - plano executado exatamente como escrito.

## Self-Check: PASSED

- FOUND: empacotar.ps1
- FOUND: atualizar.ps1
- FOUND: instalar.ps1
- FOUND: INSTALL-WINDOWS.md
- FOUND commit: d203923
- FOUND commit: 5735e81
- FOUND commit: c81dcfe

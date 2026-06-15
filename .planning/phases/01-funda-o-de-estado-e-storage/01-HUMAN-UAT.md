---
status: partial
phase: 01-funda-o-de-estado-e-storage
source: [01-VERIFICATION.md]
started: 2026-06-15T22:00:00Z
updated: 2026-06-15T22:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Subida e operação em Windows real (modo padrão)
expected: Em uma máquina Windows, com a pasta de dados padrão `%ProgramData%\ProcessadorDocumentos`, o backend sobe (`uv run uvicorn app.main:app`), cria a pasta de dados, abre o engine SQLite com WAL ativo e `GET /health` retorna `{status: "ok", db: "ok"}`. A URL do SQLite é montada a partir de um `Path` Windows (com backslashes) sem `.as_posix()` — confirmar que o SQLAlchemy abre o banco corretamente e o WAL fica ativo. Se falhar, o fix é trivial (usar `URL.create` / `as_posix()` em `config.effective_database_url`).
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

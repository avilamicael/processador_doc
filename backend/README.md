# Processador de Documentos — Backend

Backend FastAPI single-tenant (Windows-first) com banco SQLite em modo WAL.

## Requisitos

- Python 3.12 (gerenciado via [uv](https://docs.astral.sh/uv/))

## Setup

```bash
cd backend
uv sync
```

## Rodar testes

```bash
uv run pytest -x
```

## Configuração

Copie `.env.example` para `.env` e ajuste as chaves (`DATA_DIR`, `DATABASE_URL`,
`OPENAI_API_KEY`). O arquivo `.env` nunca é versionado.

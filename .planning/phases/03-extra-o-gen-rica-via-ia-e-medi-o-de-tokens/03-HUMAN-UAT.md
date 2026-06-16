---
status: resolved
phase: 03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens
source: [03-VERIFICATION.md, 03-REVIEW.md]
started: 2026-06-16T16:39:04Z
updated: 2026-06-16T16:39:04Z
---

## Current Test

[aguardando decisão humana]

## Tests

### 1. CR-01 — Truncamento por max_output_tokens indistinguível de recusa
expected: Decisão explícita do desenvolvedor sobre o comportamento quando a Responses API retorna `output_parsed=None` com `status="incomplete"` (teto `OPENAI_EXTRACT_MAX_OUTPUT_TOKENS` atingido em documentos com `full_text` longo). Hoje `_unwrap` (`backend/app/extraction/openai_client.py:84-96`) trata isso identicamente a uma recusa real → 5 retries determinísticos → FALHA, sem persistir nenhum dado já extraído.

Decisão a tomar:
- **Opção A (aceitar para v1):** documentar que documentos muito longos podem ir a FALHA; operador aumenta `OPENAI_EXTRACT_MAX_OUTPUT_TOKENS` via env; registrar a decisão no código.
- **Opção B (corrigir antes de produção):** distinguir `status="incomplete"` → `ExtractionIncomplete` em `_unwrap` (gap closure, conforme 03-REVIEW.md CR-01).
result: ACEITO PARA v1 (decisão humana 2026-06-16, Opção A) — limitação documentada em código (`openai_client.py:_unwrap`); operador aumenta `OPENAI_EXTRACT_MAX_OUTPUT_TOKENS` via env. Distinção `status="incomplete"` fica como follow-up.

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

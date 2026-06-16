---
phase: 03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens
plan: 01
subsystem: extraction
tags: [openai, responses-api, structured-outputs, pydantic, pymupdf, alembic, sqlalchemy, respx]

# Dependency graph
requires:
  - phase: 01
    provides: "Base/get_session/create_db_engine (storage.db), modelo Document, Usage, Alembic versionado (0001)"
  - phase: 02
    provides: "Alembic 0002 (jobs/dedup/folders), padrão de migração com batch_alter_table, fixtures de engine/session em tests/conftest"
provides:
  - "Schema genérico Pydantic ExtractionResult/ExtractedField (contrato text_format strict-safe, list-of-pairs)"
  - "Modelo SQLAlchemy Extraction + tabela extractions via Alembic 0003 (UNIQUE document_id = 1 extração por bloco)"
  - "Tunables OPENAI_EXTRACT_* em config.py (model, temperature, max_output_tokens, image_detail, min_chars_per_page)"
  - "Deps openai/PyMuPDF/respx instaladas e pinadas"
  - "Scaffold tests/extraction/ com fixture respx de AsyncOpenAI (sucesso + recusa) e PDFs/imagem sintéticos"
affects: [03-02 openai_client/pdf_io/router, 03-03 extract_stage, 03-04 worker-wiring, phase-04-templates, phase-07-deterministic]

# Tech tracking
tech-stack:
  added: [openai==2.41.*, PyMuPDF==1.27.*, respx (dev)]
  patterns: ["Structured Outputs list-of-pairs (não dict aberto)", "tunables via Field+AliasChoices", "migração só-cria-tabela sem trigger recreate", "fixture respx mockando POST /v1/responses"]

key-files:
  created:
    - backend/app/extraction/__init__.py
    - backend/app/extraction/schema.py
    - backend/app/models/extraction.py
    - backend/alembic/versions/0003_extractions.py
    - backend/tests/extraction/__init__.py
    - backend/tests/extraction/conftest.py
    - backend/tests/extraction/test_schema.py
    - backend/tests/extraction/test_persistence.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/app/config.py
    - backend/app/models/__init__.py
    - backend/app/models/document.py
    - backend/tests/test_migrations.py

key-decisions:
  - "fields modelado como list[ExtractedField] (list-of-pairs), nunca dict[str,str] aberto — strict mode rejeita additionalProperties:true"
  - "UNIQUE(document_id) em extractions = 1 extração por bloco = idempotência (não re-chamar/re-cobrar a IA)"
  - "Migração 0003 só cria extractions, não toca documents → não recria o trigger trg_documents_updated_at"
  - "openai_extract_min_chars_per_page default=16 como ponto de partida da heurística texto-vs-visão"
  - "Fixture respx mocka POST /v1/responses com JSON real da Responses API → output_parsed e usage reais (sucesso + recusa)"

patterns-established:
  - "Schema-de-IA Pydantic: descriptions embutidas no JSON Schema guiam o modelo; sem validação de domínio (Fase 4)"
  - "respx scaffold: payload Responses API (output_text válido vs refusal) reusável pelos Plans 02-04 sem gastar token"
  - "PDFs sintéticos via fitz (com/sem texto nativo) + PNG/JPEG por magic-bytes para exercitar o roteador texto-vs-visão"

requirements-completed: [EXT-02, USE-02]

# Metrics
duration: 18min
completed: 2026-06-16
---

# Phase 3 Plan 01: Fundação da Extração (contratos + schema + tabela + scaffold) Summary

**Estabeleceu o blueprint da extração genérica via IA: schema Pydantic strict-safe (ExtractionResult list-of-pairs), modelo Extraction com tabela extractions (Alembic 0003, UNIQUE por bloco), tunables OPENAI_EXTRACT_*, e o scaffold de testes com OpenAI mockado por respx — tudo que os Plans 02-04 consomem diretamente.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-16
- **Completed:** 2026-06-16
- **Tasks:** 3 completed
- **Files modified/created:** 14

## Accomplishments

- **Schema genérico strict-safe**: `ExtractionResult`/`ExtractedField` com `fields` como list-of-pairs (não dict aberto) — o ponto técnico nº 1 da fase, validado por teste que rejeita dict bruto e checa ausência de `additionalProperties:true` no JSON Schema gerado.
- **Tabela `extractions` + modelo registrado**: `Extraction` espelha `usage.py` (FK→documents CASCADE, created_at server_default), com **UNIQUE(document_id)** = 1 extração por bloco = idempotência (não re-chamar/re-cobrar a IA). Migração Alembic 0003 com upgrade/downgrade testados.
- **Tunables de extração em `config.py`**: 5 parâmetros `OPENAI_EXTRACT_*` lidos de env no mesmo padrão `Field(default, validation_alias=AliasChoices(...))` dos `queue_*`; `openai_api_key` permanece `SecretStr` intacto.
- **Scaffold respx**: fixture de `AsyncOpenAI` mockando `POST /v1/responses` com JSON real da Responses API — devolve `output_parsed` válido (sucesso) e `output_parsed is None` (recusa, Pitfall 2), mais PDFs sintéticos com/sem texto nativo e PNG/JPEG para o roteador texto-vs-visão.

## Task Commits

Each task was committed atomically:

1. **Task 1: Dependências + tunables de extração** - `3270944` (chore)
2. **Task 2 (TDD): Schema genérico ExtractionResult** - `3e0e2bc` (test, RED) → `73fc9c9` (feat, GREEN)
3. **Task 3 (TDD): Modelo Extraction + migração 0003 + scaffold respx** - `fccb114` (feat)

_Task 3 reuniu modelo+migração+testes num commit por serem o mesmo contrato co-dependente (o autogenerate do Alembic exige o modelo registrado)._

## Files Created/Modified

**Criados:**
- `backend/app/extraction/__init__.py` - pacote de extração da Fase 3
- `backend/app/extraction/schema.py` - `ExtractionResult`/`ExtractedField` (contrato `text_format`)
- `backend/app/models/extraction.py` - modelo SQLAlchemy `Extraction`
- `backend/alembic/versions/0003_extractions.py` - cria a tabela `extractions` (UNIQUE document_id)
- `backend/tests/extraction/conftest.py` - fixture respx (sucesso/recusa) + PDFs/imagem sintéticos
- `backend/tests/extraction/test_schema.py` - testes do schema strict-safe
- `backend/tests/extraction/test_persistence.py` - round-trip + UNIQUE + respx + fixtures
- `backend/tests/extraction/__init__.py` - pacote de testes

**Modificados:**
- `backend/pyproject.toml` / `backend/uv.lock` - deps openai/PyMuPDF/respx
- `backend/app/config.py` - tunables `OPENAI_EXTRACT_*`
- `backend/app/models/__init__.py` - registra `Extraction` (import + `__all__`)
- `backend/app/models/document.py` - relationship recíproca 1:1 `extraction`
- `backend/tests/test_migrations.py` - casos 0003 (cria extractions + UNIQUE; downgrade -1/-2)

## Verification Evidence

- `uv run pytest tests/extraction tests/test_migrations.py -q` → 18 passed
- `uv run pytest -q` (suite completa do backend) → 131 passed, sem regressões
- `uv run python -c "import fitz, openai; from app.models import Extraction; from app.extraction.schema import ExtractionResult"` → ok
- `uv run python -c "from app.config import Settings; s=Settings(); print(...)"` → `gpt-4o-2024-08-06 0.0 4096 high 16`
- `uv run ruff check app/ tests/extraction/ tests/test_migrations.py` → All checks passed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Assertion do índice UNIQUE no test_migrations**
- **Found during:** Task 3
- **Issue:** O inspector do SQLAlchemy sobre SQLite retorna `unique` como `1` (int), não `True` (bool); a asserção `is True` falhava embora o índice fosse de fato UNIQUE.
- **Fix:** Trocar `assert idx["unique"] is True` por `assert idx["unique"]` (truthy), com comentário explicando o int 1/0 do SQLite.
- **Files modified:** `backend/tests/test_migrations.py`
- **Commit:** `fccb114`

**2. [Rule 3 - Blocking] Ajuste do teste de downgrade existente para o novo head**
- **Found during:** Task 3
- **Issue:** `test_downgrade_um_passo_remove_so_a_fase_2` assumia head=0002; com head=0003, `downgrade -1` passa a remover a Fase 3, não a Fase 2 — o teste quebraria.
- **Fix:** Reescrito para `test_downgrade_um_passo_remove_so_a_fase_3` (downgrade -1 remove só extractions) + adicionado `test_downgrade_dois_passos_remove_fase_2` (downgrade -2 remove Fases 3+2, preserva Fase 1) e `test_0003_cria_extractions_com_unique_em_document_id`.
- **Files modified:** `backend/tests/test_migrations.py`
- **Commit:** `fccb114`

**3. [Rule 2 - Missing functionality] Relationship recíproca em Document**
- **Found during:** Task 3
- **Issue:** O modelo `Extraction` usa `back_populates="extraction"`, exigindo a contraparte em `Document` (caso contrário SQLAlchemy levanta erro de mapeamento).
- **Fix:** Adicionada relationship 1:1 `extraction` em `Document` (`uselist=False`, `cascade="all, delete-orphan"`), espelhando `usages`/`pages`.
- **Files modified:** `backend/app/models/document.py`
- **Commit:** `fccb114`

## Known Stubs

Nenhum. Este plan é fundação de contratos (schema/modelo/migração/scaffold) — sem dados de UI stub. As implementações que consomem estes contratos (cliente OpenAI, pdf_io, router, extract_stage, worker wiring) são os Plans 02-04 desta fase, por desenho.

## Notas para os próximos plans (02-04)

- **`openai_extract_model`**: confirmar o modelo vigente na conta no momento da implementação (precisa de visão + Structured Outputs); o default `gpt-4o-2024-08-06` é placeholder tunável.
- **Mapeamento de tokens**: a Responses API expõe `usage.input_tokens`/`output_tokens`; o modelo `Usage` usa `prompt_tokens`/`completion_tokens` — mapear `input→prompt`, `output→completion`.
- **Segredo**: `.get_secret_value()` só no ponto de criação do `AsyncOpenAI` (Plan 02); nunca logar a chave nem o conteúdo do documento.
- **Idempotência**: checar `Extraction` existente por `document_id` antes de chamar a IA (a UNIQUE já garante no banco; a checagem prévia evita a chamada paga).

## Self-Check: PASSED

Todos os 7 artefatos-chave existem em disco e os 4 commits de tarefa (`3270944`, `3e0e2bc`, `73fc9c9`, `fccb114`) estão presentes no histórico git.

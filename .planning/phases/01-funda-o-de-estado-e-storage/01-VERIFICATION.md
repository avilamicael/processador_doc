---
phase: 01-funda-o-de-estado-e-storage
verified: 2026-06-15T23:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Rodar a aplicação num host Windows real (ou VM) sem modificações e verificar que o padrão de data_dir resolve para %ProgramData%\\ProcessadorDocumentos"
    expected: "A pasta é criada em C:\\ProgramData\\ProcessadorDocumentos (ou equivalente); /health retorna 200"
    why_human: "Os testes de config mockam PROGRAMDATA em Linux; a lógica de derivação funciona via variável de ambiente, mas o comportamento real em Windows com backslashes na URL SQLite (WR-01) precisa de validação no SO-alvo"
  - test: "Verificar que a URL SQLite construída com backslashes (WR-01) funciona no Windows"
    expected: "Engine SQLAlchemy abre o banco corretamente; WAL ativo; /health retorna 200 sem erro"
    why_human: "f'sqlite:///{data_dir / app.db}' produz backslashes no Windows; SQLAlchemy geralmente tolera mas não há teste no SO primário. Fix recomendado: usar .as_posix() ou URL.create()"
---

# Phase 1: Fundacao de Estado e Storage — Verification Report

**Phase Goal:** Existe uma fundacao que garante que nenhum dado se perde — modelos de dominio, maquina de estados explicita, armazenamento imutavel por hash e migracoes seguras — rodando confiavelmente em Windows.
**Verified:** 2026-06-15T23:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                                         | Status     | Evidence                                                                                                                                |
|----|---------------------------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| 1  | Cada documento tem um estado persistido e so transita por transicoes explicitas validas (transicao invalida falha, nao corrompe dado) | VERIFIED   | `TRANSITIONS` allowlist em `pipeline/states.py`; `transition()` valida antes de atribuir e faz rollback em falha; 10 testes; spot-check comportamental confirmado: RECEBIDO->CONCLUIDO levanta `InvalidTransition` e estado no banco permanece RECEBIDO |
| 2  | Um arquivo ingerido e armazenado de forma imutavel endereçado por hash (CAS) e pode ser recuperado mesmo apos qualquer automacao posterior | VERIFIED   | `storage/cas.py` implementa SHA-256 + sharding + os.replace atomico; 11 testes; spot-check: store -> remove source -> read_bytes(hash) retorna bytes originais |
| 3  | O sistema sobe e opera em Windows no modo padrao sem broker externo e sem dependencias de infraestrutura adicionais | VERIFIED*  | Sem redis/arq/celery nas dependencias (pyproject.toml); SQLite WAL in-process; spot-check: journal_mode=wal, busy_timeout=5000, foreign_keys=ON; *ver Human Verification para validacao real em Windows |
| 4  | A chave OpenAI por instancia e configuravel e lida da configuracao da aplicacao (sem proxy central)           | VERIFIED   | `openai_api_key: SecretStr` em `config.py`; spot-check: valor nao aparece em repr/str; acessivel via `.get_secret_value()`; /health nao expoe a chave |
| 5  | O schema do banco evolui via migracao versionada (Alembic) sem recriar o banco                               | VERIFIED   | `alembic/versions/0001_initial.py` cria 4 tabelas; `env.py` wired a `Base.metadata` e `get_settings()`; `render_as_batch=True`; spot-check: `upgrade head` / `downgrade base` ambos bem-sucedidos; `create_all` ausente do codigo de aplicacao |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact                                    | Expected                                                | Status    | Details                                                                 |
|---------------------------------------------|---------------------------------------------------------|-----------|-------------------------------------------------------------------------|
| `backend/app/config.py`                     | Settings com data_dir, database_url, openai_api_key     | VERIFIED  | `class Settings(BaseSettings)` com `computed_field` para data_dir e effective_database_url; `SecretStr` para chave |
| `backend/app/storage/db.py`                 | Engine SQLAlchemy 2.0 WAL, Base, get_session            | VERIFIED  | `DeclarativeBase`, `create_db_engine` com PRAGMAs gated em dialect.name == "sqlite", `get_session` como context manager |
| `backend/app/storage/cas.py`                | store(src)->hash, path_for, exists, read_bytes, open_blob | VERIFIED | Implementacao completa: SHA-256 streaming, sharding, os.replace atomico, sem delete/update |
| `backend/app/main.py`                       | FastAPI app, lifespan, GET /health                      | VERIFIED  | Lifespan garante data_dir + engine; /health executa SELECT 1 e retorna {status, db, version} sem expor chave |
| `backend/app/models/enums.py`               | DocState com 6 estados                                  | VERIFIED  | RECEBIDO/PROCESSANDO/EM_REVISAO/CONCLUIDO/QUARENTENA/FALHA como (str, Enum) |
| `backend/app/models/document.py`            | Document com state, last_completed_step, content_hash   | VERIFIED  | Todos os campos presentes; default RECEBIDO na instancia; SAEnum native_enum=False |
| `backend/alembic/versions/0001_initial.py`  | Migracao inicial criando 4 tabelas                      | VERIFIED  | Cria documents/pages/audit_log/usage; downgrade reverte; `down_revision=None` |
| `backend/app/pipeline/states.py`            | TRANSITIONS + InvalidTransition + is_valid_transition   | VERIFIED  | Todos 6 estados como chaves; CONCLUIDO terminal; InvalidTransition carrega from/to state |
| `backend/app/pipeline/state_machine.py`     | transition() que valida/persiste/falha sem corromper    | VERIFIED  | Valida antes de atribuir; rollback defensivo; mark_step() para marcador interno |

### Key Link Verification

| From                                | To                           | Via                                   | Status   | Details                                           |
|-------------------------------------|------------------------------|---------------------------------------|----------|---------------------------------------------------|
| `backend/app/storage/db.py`         | `backend/app/config.py`      | `get_settings().effective_database_url` | WIRED  | `create_db_engine` recebe URL derivada de Settings via caller (main.py); env.py usa `get_settings()` diretamente |
| `backend/app/main.py`               | `backend/app/storage/db.py`  | lifespan cria engine com PRAGMAs WAL  | WIRED    | `create_db_engine(settings.effective_database_url)` no lifespan; confirma WAL com PRAGMA journal_mode |
| `backend/alembic/env.py`            | `backend/app/storage/db.py`  | `target_metadata = Base.metadata`     | WIRED    | `from app.storage.db import Base`; `target_metadata = Base.metadata`; `import app.models` registra todos os modelos |
| `backend/app/models/document.py`    | `backend/app/models/enums.py` | coluna state tipada por DocState      | WIRED    | `from app.models.enums import DocState`; `SAEnum(DocState, ...)` na coluna state |
| `backend/app/pipeline/state_machine.py` | `backend/app/models/document.py` | le/escreve Document.state e last_completed_step | WIRED | `from app.models.document import Document`; atribuicao direta de `.state` e `.last_completed_step` |
| `backend/app/pipeline/states.py`    | `backend/app/models/enums.py` | TRANSITIONS chaveado por DocState     | WIRED    | `from app.models.enums import DocState`; todos os membros de DocState sao chaves de TRANSITIONS |
| `backend/app/storage/cas.py`        | `backend/app/config.py`      | raiz do CAS derivada de data_dir      | WIRED    | `from app.config import get_settings`; `cas_root() = get_settings().data_dir / "cas"` |

### Data-Flow Trace (Level 4)

Nao aplicavel nesta fase: nenhum artefato renderiza dados dinamicos via UI ou API de dados. Os endpoints (/health) retornam status estatico. A fase e de fundacao de storage/estado — os dados vem do CAS e banco, verificados via testes e spot-checks comportamentais.

### Behavioral Spot-Checks

| Behavior                                                     | Command                                                         | Result                                                   | Status |
|--------------------------------------------------------------|-----------------------------------------------------------------|----------------------------------------------------------|--------|
| SC-1: Transicao invalida falha sem corromper estado          | `transition(session, doc, DocState.CONCLUIDO)` de RECEBIDO     | `InvalidTransition` levantada; estado relido = RECEBIDO  | PASS   |
| SC-2: CAS armazena por hash, recuperavel apos remocao do fonte | `store(src)` + `src.unlink()` + `read_bytes(hash)`           | Conteudo recuperado integralmente por hash               | PASS   |
| SC-3: SQLite WAL ativo sem broker externo                    | `PRAGMA journal_mode` / `busy_timeout` / `foreign_keys`        | wal / 5000 / 1 — sem redis/arq nas deps                 | PASS   |
| SC-4: Chave OpenAI mascarada em repr/str                     | `repr(Settings(OPENAI_API_KEY=...))` nao contem o valor        | `SecretStr('**********')` em repr; valor via `.get_secret_value()` | PASS |
| SC-5: Alembic upgrade/downgrade round-trip                   | `upgrade head` / `downgrade base` em SQLite temporario         | Tabelas criadas incluindo state + last_completed_step; revertidas | PASS |
| Suite de testes completa                                     | `cd backend && uv run pytest -q`                               | 50 passed, 1 warning (httpx deprecation em TestClient)   | PASS   |

### Probe Execution

Nenhuma probe declarada no PLAN ou no SUMMARY desta fase. N/A.

### Requirements Coverage

| Requirement | Source Plan | Description                                                             | Status    | Evidence                                                                                |
|-------------|-------------|-------------------------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------|
| PROC-01     | 01-02, 01-04 | Cada documento percorre maquina de estados explicita persistida         | SATISFIED | `DocState` com 6 estados; `TRANSITIONS` allowlist; `transition()` valida/persiste/falha sem corromper; testes de nao-corrupcao passam |
| USE-01      | 01-01       | Cada instancia usa chave OpenAI por cliente lida da configuracao         | SATISFIED | `openai_api_key: SecretStr` em Settings; lida de `OPENAI_API_KEY` env; nunca exposta em repr/logs/health; `get_secret_value()` para acesso |
| DIST-01     | 01-01, 01-03 | Sistema roda em Windows (plataforma primaria)                           | PARTIAL   | Codigo usa `pathlib`/`os.replace` portaveis; PROGRAMDATA-branch implementado; sem broker; POREM: URL SQLite com f-string pode produzir backslashes no Windows (WR-01) — validacao real em Windows pendente para humano |
| DIST-02     | 01-01       | Modo padrao sem broker externo (fila in-process)                        | PARTIAL   | Fundacao estabelecida (SQLite WAL, sem redis/arq nas deps, sem broker); fila in-process propriamente dita e DIST-02 marcados como Pending — a implementacao da fila e escopo da Fase 2 (confirmado pelo REQUIREMENTS.md: Phase 1 = Pending para DIST-02) |

**Nota sobre DIST-02:** REQUIREMENTS.md lista DIST-02 como Pending para Fase 1 e a traceability confirma que o requisito completo sera entregue na Fase 2 (in-process queue). A Fase 1 apenas garante que nao bloqueia esse desenho (sem broker externo, SQLite como base). Este status e esperado e justificado.

**Nota sobre DIST-01:** Marcado como Complete no REQUIREMENTS.md. A fundacao esta correta (pathlib, os.replace, sem infra adicional), mas ha uma fragilidade documentada na URL SQLite com backslashes em Windows (WR-01) que nao foi testada no SO primario. A verificacao humana e necessaria para confirmar Complete com confianca.

### Anti-Patterns Found

| File                          | Line   | Pattern                                                          | Severity | Impact                                                             |
|-------------------------------|--------|------------------------------------------------------------------|----------|--------------------------------------------------------------------|
| `app/storage/cas.py`          | 98-109 | Cleanup `finally` depende de `.endswith(".tmp")` para nao tocar o blob final (CR-01) | WARNING  | Nao e um bug ativo: final_path nao tem sufixo `.tmp`, entao o guard nunca afeta o blob. E uma fragilidade de construcao: se houver refatoracao futura que alias `tmp_path` ao `final_path`, haveria data loss silencioso. Recomendado: fixar com `tmp_path = None` apos consume (per review) |
| `app/config.py`               | 75     | `f"sqlite:///{self.data_dir / 'app.db'}"` pode produzir backslashes no Windows (WR-01) | WARNING  | Funciona em Linux/CI; no Windows o path stringifica com backslashes. SQLAlchemy geralmente tolera, mas e exatamente o tipo de bug que so aparece no OS primario |
| `app/storage/db.py`           | 65-81  | `make_session_factory(engine)` chamado dentro de `get_session` a cada invocacao (WR-03) | WARNING  | Ineficiencia (sessionmaker recriada por request); contrato "FastAPI dependency" nao foi wired no main.py ainda (engine em app.state mas sem dependency injection formal) |
| `app/storage/db.py`           | 48-55  | Duas deteccoes de SQLite: `url.startswith("sqlite")` para connect_args e `engine.dialect.name` para PRAGMAs (WR-02) | INFO     | Concorda em URLs normais; pode divergir com esquemas incomuns |
| `app/main.py`                 | 29     | `assert str(mode).lower() == "wal"` — assert pode ser stripado com Python -O (IN-04) | INFO     | O PyInstaller/sidecar futuro pode rodar com -O; WAL seria confirmado sem verificacao. Fix: usar `raise RuntimeError(...)` |
| `app/models/document.py`      | 70-75  | `onupdate=func.now()` e ORM-side; sem trigger/server_onupdate (WR-05) | INFO     | Escrita por SQL direto ou data migration deixa updated_at obsoleto; aceito para v1 single-writer |
| `app/alembic/versions/0001_initial.py` | 28 | SAEnum sem `create_constraint=True` — sem CHECK constraint no banco (WR-06) | INFO   | Estado invalido pode ser gravado por SQL direto; validacao apenas em Python via TRANSITIONS; aceito para v1 dado que todo acesso passa pelo ORM e state_machine |

**Resultado debt-marker scan:** Zero marcadores TBD/FIXME/XXX encontrados em `app/` e `tests/`. Nenhum bloqueador de auditoria.

### Human Verification Required

#### 1. Validacao em Windows real

**Test:** Num host Windows (ou VM Windows 10/11), clonar o repositorio, instalar com `uv sync`, executar `uv run uvicorn app.main:app` e chamar `GET /health`.
**Expected:** Pasta `%ProgramData%\ProcessadorDocumentos` criada automaticamente; WAL ativo; /health retorna `{"status":"ok","db":"ok","version":"0.1.0"}` sem erro de path.
**Why human:** Todos os testes rodam em Linux. A URL SQLite e construida com f-string e path do OS (WR-01) — em Windows isso produz backslashes (`sqlite:///C:\ProgramData\...\app.db`). SQLAlchemy geralmente tolera mas nao ha evidencia empirica no OS primario. Se falhar, o fix e trivial (`.as_posix()` na linha 75 de config.py).

#### 2. Validacao da URL SQLite com backslashes no Windows

**Test:** No host Windows, confirmar que o banco e criado corretamente em `%ProgramData%\ProcessadorDocumentos\app.db` e que `PRAGMA journal_mode` retorna `wal`.
**Expected:** Banco criado; WAL ativo; sem `OperationalError: unable to open database file`.
**Why human:** WR-01: path.as_posix() nao e usado na URL; comportamento de backslashes varia conforme versao do SQLAlchemy e driver sqlite3.

### Gaps Summary

Nenhum gap bloqueia o objetivo da fase. Todos os 5 success criteria sao verificavelmente verdadeiros no codebase:

1. Estado persistido com maquina de estados explicita e sem corrupcao em transicao invalida — COMPROVADO por 10 testes e spot-check comportamental.
2. CAS imutavel por SHA-256, recuperavel apos automacao posterior — COMPROVADO por 11 testes e spot-check.
3. Sem broker externo; SQLite WAL ativo — COMPROVADO por inspecao de dependencias e PRAGMAs.
4. Chave OpenAI mascarada e configuravel — COMPROVADO por SecretStr e spot-check.
5. Schema via Alembic (upgrade/downgrade) sem create_all em app — COMPROVADO por testes e CLI.

O status `human_needed` reflete exclusivamente a necessidade de validar o comportamento no Windows real (plataforma primaria), conforme WR-01 do code review. A fragilidade CR-01 (cas.store cleanup) nao e um bug ativo — o final_path nunca tem sufixo `.tmp` na implementacao atual, entao a guarda de string nunca afeta o blob final. E uma code smell a corrigir antes da Fase 2 (proxima a adicionar ingestao real), nao um bloqueador do objetivo atual.

**DIST-01 status em REQUIREMENTS.md:** Marcado como Complete pelos executores. A verificacao confirma que o codigo e portavel e correto conceitualmente, mas requer confirmacao manual em Windows para ratificar o status Complete de forma auditavel.

**DIST-02 status em REQUIREMENTS.md:** Marcado como Pending, justificadamente — a fila in-process e escopo da Fase 2. A Fase 1 estabelece a fundacao necessaria (SQLite WAL sem broker) sem bloquear esse desenho.

---

_Verified: 2026-06-15T23:00:00Z_
_Verifier: Claude (gsd-verifier)_

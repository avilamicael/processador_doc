---
phase: 02-ingest-o-e-fila-ass-ncrona
reviewed: 2026-06-16T04:03:24Z
depth: standard
files_reviewed: 41
files_reviewed_list:
  - backend/alembic/versions/0002_ingestion.py
  - backend/app/api/__init__.py
  - backend/app/api/documents.py
  - backend/app/api/watched_folders.py
  - backend/app/config.py
  - backend/app/ingest/__init__.py
  - backend/app/ingest/hashing.py
  - backend/app/ingest/splitter.py
  - backend/app/ingest/stabilizer.py
  - backend/app/ingest/watcher.py
  - backend/app/main.py
  - backend/app/models/__init__.py
  - backend/app/models/document.py
  - backend/app/models/enums.py
  - backend/app/models/ingested_original.py
  - backend/app/models/job.py
  - backend/app/models/watched_folder.py
  - backend/app/pipeline/ingest_stage.py
  - backend/app/queue/__init__.py
  - backend/app/queue/repo.py
  - backend/app/queue/worker.py
  - backend/pyproject.toml
  - frontend/package.json
  - frontend/src/App.tsx
  - frontend/src/components/StatusPill.tsx
  - frontend/src/hooks/useDocuments.ts
  - frontend/src/hooks/useWatchedFolders.ts
  - frontend/src/lib/api.ts
  - frontend/src/main.tsx
  - frontend/src/pages/ConfigPage.tsx
  - frontend/src/pages/DocumentsPage.tsx
  - frontend/src/types.ts
  - backend/tests/conftest.py
  - backend/tests/test_api_documents.py
  - backend/tests/test_api_watched_folders.py
  - backend/tests/test_config.py
  - backend/tests/test_dedup_gate.py
  - backend/tests/test_ingest_stage.py
  - backend/tests/test_migrations.py
  - backend/tests/test_models.py
  - backend/tests/test_queue.py
  - backend/tests/test_splitter.py
  - backend/tests/test_stabilizer.py
  - backend/tests/test_watcher.py
findings:
  critical: 0
  warning: 7
  info: 4
  total: 13
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-06-16T04:03:24Z
**Depth:** standard
**Files Reviewed:** 41
**Status:** issues_found

## Summary

Revisei a fase de ingestão e fila assíncrona com foco adversarial nos pontos de risco apontados: claim atômico da fila SQLite, idempotência por hash+etapa, gate de dedup pré-split, validação de path de pasta monitorada (path traversal), shutdown limpo do watcher/worker e vazamento de dados sensíveis.

A arquitetura é sólida e bem documentada, e a maioria dos invariantes (single-writer, gate de dedup, estado terminal) está coberta por testes. Porém encontrei dois defeitos de correção que comprometem garantias centrais da fase: (1) o claim atômico **perde jobs presos em `running`** após um crash quando o `step` não é `ingest`, e mais grave, há um caminho onde um job pode ser **reprocessado com criação de blocos órfãos** porque o gate de dedup e o registro do `IngestedOriginal` não são commitados atomicamente com os `Document`s no caminho de retry; e (2) a validação de path da pasta monitorada **não impede path traversal real** — apenas normaliza — permitindo cadastrar qualquer diretório do host (incluindo raízes de sistema), o que é uma exposição de leitura de arquivos arbitrários do sistema operacional.

Há ainda warnings relevantes sobre o supervisor de reconfiguração (poll fixo de 5s que duplica leitura de DB), o uso de `Path.resolve()` que toca o filesystem e segue symlinks, e inconsistências de timezone na comparação de `next_run_at`.

## Critical Issues

### CR-01: Path traversal / leitura arbitrária — validação de pasta só normaliza, não confina

**Status:** resolved (commit `0889614`) — docstring (módulo + `_normalize_path`) reescrito para não alegar que `resolve()` "barra path traversal": deixa explícito que só canoniza o formato e que não há confinamento de raiz no v1 single-tenant local (decisão de produto: cadastro por caminho absoluto mantido; allowlist/seletor fora de escopo, ficam para um eventual modo servidor). Endurecimento básico adicionado: path que já existe e não é diretório → 422; symlink → 422 (não seguimos link como pasta monitorada). Path inexistente continua aceito. Testes novos cobrem arquivo/symlink/diretório/inexistente.

**File:** `backend/app/api/watched_folders.py:35-54`
**Issue:** O docstring e os comentários afirmam que `_normalize_path` "barra path traversal" (V5/V12 — T-02-10). Isso é falso. `Path(raw).resolve()` apenas **resolve** `..` para um caminho absoluto canônico — não restringe a nenhuma raiz permitida. O teste `test_relative_path_is_normalized` confirma que `/tmp/foo/../bar` vira `/tmp/bar`, mas isso não é proteção: um operador (ou uma requisição maliciosa à API, que não tem autenticação nesta fase) pode cadastrar `C:\Windows\System32`, `/etc`, `/`, ou qualquer diretório do host. O watcher então fará `rglob("*")` recursivo, calculará hash e **copiará para o CAS** (via `cas.store`) o conteúdo de arquivos sensíveis do sistema operacional inteiro — e a fase explicitamente envia conteúdo para a OpenAI em fases seguintes. A própria CLAUDE.md exige "minimizar e tornar explícito o que sai da máquina". Resolver `..` sem confinar a uma allowlist de raízes **não é** uma defesa contra traversal; é só normalização de formato.

Adicionalmente, `Path(raw).strip()` com `resolve(strict=False)` em paths relativos resolve **contra o CWD do processo do servidor**, tornando o destino dependente de onde o serviço foi iniciado — comportamento silencioso e perigoso.

**Fix:** Introduzir uma allowlist de raízes configurável (env, ex.: `WATCH_ALLOWED_ROOTS`) e rejeitar (HTTP 422) qualquer path que não seja descendente de uma raiz permitida. Rejeitar paths relativos explicitamente em vez de resolvê-los contra o CWD. Exemplo:
```python
def _normalize_path(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        raise HTTPException(422, "path da pasta não pode ser vazio")
    p = Path(s)
    if not p.is_absolute():
        raise HTTPException(422, "path deve ser absoluto")
    resolved = p.resolve()
    allowed = get_settings().watch_allowed_roots  # list[Path] resolvidos
    if allowed and not any(
        resolved == root or root in resolved.parents for root in allowed
    ):
        raise HTTPException(422, f"path fora das raízes permitidas: {resolved}")
    return str(resolved)
```
Se a decisão de produto for não ter allowlist no v1 single-tenant, então o docstring/comentários devem PARAR de afirmar que isto "barra path traversal" — a afirmação de segurança é a parte que torna isto um defeito de revisão, pois mascara a ausência de controle.

### CR-02: Resume após crash perde/duplica trabalho — gate de dedup não cobre o caminho de retry com `IngestedOriginal` já commitado

**Status:** resolved (commit `ed990ac`) — adotada a opção (a): `process_ingest` virou UMA transação. O loop de blocos não chama mais `transition()` (que commitava por bloco); valida a aresta RECEBIDO→PROCESSANDO uma vez e seta o estado em memória, com um único `session.commit()` no final. Crash antes do commit = rollback total → o gate de dedup jamais enxerga um `IngestedOriginal` meio-criado, então o resume recria todos os blocos (sem perda) e o `content_hash` único evita duplicata. Teste novo simula crash após o 1º bloco e prova rollback total + reprocesso recriando os 4 blocos exatamente uma vez; outro teste prova que o reprocesso sem crash continua no-op (duplicate).

**File:** `backend/app/pipeline/ingest_stage.py:108-164` e `backend/app/queue/worker.py:114-141`
**Issue:** `process_ingest` faz `session.commit()` apenas no final (linha 164), e o gate de dedup depende de `IngestedOriginal` já existir. Isso protege o caso em que um job inteiro re-roda. Porém há uma janela real de inconsistência no caminho de **retry parcial**:

Considere um PDF grande, `pages_per_block=1`, gerando 50 blocos. Em `process_ingest`, o `IngestedOriginal` é criado e `flush`-ado (linha 119-120), e cada bloco é `cas.store`-ado e seu `Document` criado/transicionado com `transition(...)` que faz `session.commit()` **por bloco** (state_machine.py:61). Ou seja, **os `Document`s e o `IngestedOriginal` JÁ são parcialmente commitados** antes do `commit` final, porque `transition` commita a sessão inteira a cada chamada. Se o processo crashar (ou o worker for cancelado no shutdown via `task.cancel()` em main.py:66) no meio do loop — digamos após 20 blocos — o `IngestedOriginal` está persistido com `block_count=0` (só atualizado na linha 163) e 20 `Document`s existem.

No resume, `requeue_running` devolve o job a `pending`, o worker re-claima e chama `process_ingest` de novo. O gate (linha 98-106) encontra o `IngestedOriginal` existente e retorna `"duplicate"` **sem criar os 30 blocos restantes**. Resultado: **perda permanente de 30 documentos do cliente** — exatamente o que a constraint "nunca pode causar perda" da CLAUDE.md proíbe. Além disso `block_count` fica `0` para sempre (a UI reportará 0 blocos para um original que tem 20).

A afirmação no docstring (linha 13-14) de que "o `content_hash` único dos blocos torna re-criar um Document um no-op (checagem prévia)" só vale se o gate de dedup **não** interceptar antes — mas ele intercepta, justamente impedindo o reprocesso de completar os blocos faltantes.

**Fix:** Não permitir que `transition` commite por bloco dentro do loop de ingestão, ou tornar a criação dos blocos resiliente a `IngestedOriginal` parcial. Duas opções concretas:
1. Tornar todo `process_ingest` uma única transação (não commitar dentro do loop; usar `flush` + atualizar estado sem `transition` commitando), commitando só no final — assim crash = rollback total e o gate nunca vê um original "meio-criado".
2. Tornar o gate condicional a "original completo": só tratar como duplicata quando `block_count > 0 AND count(documents)==block_count`; caso contrário, retomar a criação dos blocos faltantes (idempotente via `content_hash` único). Exemplo do gate corrigido:
```python
if existing is not None and existing.block_count > 0:
    n_docs = session.scalar(
        select(func.count(Document.id)).where(
            Document.origin_original_id == existing.id
        )
    )
    if n_docs == existing.block_count:
        existing.duplicate_hits += 1
        session.commit()
        return IngestResult(status="duplicate", block_count=existing.block_count)
    # original incompleto (crash no meio): cair no caminho de criação/retomada
```

## Warnings

### WR-01: `transition` commita a sessão a cada bloco — ingestão não é atômica

**File:** `backend/app/pipeline/ingest_stage.py:154-164`, `backend/app/pipeline/state_machine.py:57-63`
**Issue:** Mesmo desconsiderando o cenário de crash do CR-02, chamar `transition` (que faz `session.commit()`) dentro do loop por bloco significa que `process_ingest` emite N commits para N blocos. Isso (a) expõe estados intermediários a leitores concorrentes (a UI faz polling), (b) multiplica a contenção de escrita no SQLite single-writer (contrário ao objetivo WR-04 de minimizar COMMITs), e (c) é a raiz mecânica do CR-02. O `original.block_count = len(blocks)` na linha 163 só é visível após o último commit, deixando uma janela em que `block_count=0` coexiste com Documents já persistidos.
**Fix:** Separar "mutação de estado em memória" de "persistência". Para a criação inicial em PROCESSANDO, setar `doc.state`/`doc.last_completed_step` diretamente (a validação de transição RECEBIDO→PROCESSANDO pode ser feita uma vez) e fazer um único `session.commit()` ao final de `process_ingest`. Reservar `transition` (com commit) para mudanças de estado pontuais fora de loops.

### WR-02: `claim_next` só re-enfileira `running` na resume, mas `requeue_running` ignora `next_run_at`/backoff

**File:** `backend/app/queue/repo.py:185-200`
**Issue:** `requeue_running` faz `status='pending'` para todos os `running`, mas **não reseta `next_run_at`**. Se um job estava em `running` com `next_run_at` no passado, ok; porém combinado com `schedule_retry`, um job que crashou logo após um retry pode ter `next_run_at` no futuro distante e ainda assim ser revertido a `pending` — o que está correto — mas o `attempts` **não é decrementado**, então um crash de infraestrutura (não culpa do job) consome uma tentativa. Com `queue_max_attempts=5`, 5 crashes do processo durante o mesmo job o mandam a dead-letter/FALHA permanentemente, mesmo que o job nunca tenha falhado por mérito próprio. Isso pode levar documentos válidos a FALHA por instabilidade do host (Windows reinicia, etc.).
**Fix:** Em `requeue_running`, considerar decrementar `attempts` (o claim vai incrementá-lo de novo) ou não contar reverts de resume como tentativas. No mínimo, resetar `next_run_at = now` para que o resume não fique preso atrás de um backoff antigo:
```python
"UPDATE jobs SET status='pending', attempts = MAX(attempts - 1, 0), "
"next_run_at = :now, updated_at=CURRENT_TIMESTAMP WHERE status='running'"
```

### WR-03: `_handle_changes` resolve symlinks e pode vazar fora da pasta monitorada

**File:** `backend/app/ingest/watcher.py:284`, `backend/app/api/watched_folders.py:49`
**Issue:** `_folder_for_path(file_path.resolve(), folders)` e `active_folder_paths` usam `Path.resolve()`, que **segue symlinks**. Um arquivo dentro da pasta monitorada que seja um symlink para fora dela (ex.: `hot/link -> /etc/shadow`) será resolvido para o alvo real, e o `relative_to` no `_folder_for_path` falhará (corretamente descartando), MAS `_stabilize_hash_gate_enqueue` recebe o `file_path` **não-resolvido** (linha 288 passa o `file_path` original do change), então o hash e o `cas.store` operam sobre o alvo do symlink. Combinado com CR-01, isso amplia a superfície de leitura arbitrária: arquivos fora da pasta monitorada podem entrar no CAS via symlink.
**Fix:** Após resolver, verificar que o caminho real ainda está contido na pasta monitorada antes de processar; rejeitar symlinks que apontem para fora. Usar `os.path.realpath` e confirmar `realpath.is_relative_to(folder_path)`.

### WR-04: Comparação de `next_run_at` mistura formatos de datetime entre claim e mark/retry

**File:** `backend/app/queue/repo.py:98-117` vs `120-126`, `154-167`
**Issue:** `claim_next` corretamente bind-a `:now` em Python para comparar com `next_run_at`. Porém `mark_done`/`mark_failed`/`schedule_retry` gravam `updated_at=CURRENT_TIMESTAMP` (SQL puro, segundos sem offset) enquanto `next_run_at` é escrito via bind Python tz-aware (`YYYY-MM-DD HH:MM:SS.ffffff+00:00`). O modelo declara `updated_at`/`created_at` como `DateTime(timezone=True)` com `server_default=func.now()`. Há, portanto, **dois formatos de timestamp coexistindo na mesma tabela** (`next_run_at` tz-aware com offset; `updated_at`/`created_at` via `CURRENT_TIMESTAMP` sem offset). Isso é frágil: qualquer query futura que ordene/compare `updated_at` contra um datetime Python tz-aware sofrerá o mesmo bug lexicográfico que o próprio comentário do claim descreve. Hoje não quebra porque nada compara `updated_at`, mas é uma armadilha latente.
**Fix:** Padronizar: ou bind-ar `_utcnow()` para `updated_at` também (não usar `CURRENT_TIMESTAMP` no SQL), ou usar `CURRENT_TIMESTAMP` para `next_run_at` também. Consistência elimina a classe inteira de bugs.

### WR-05: `_supervisor_interval_seconds` fixo de 5s e dois loops lendo o DB em paralelo

**File:** `backend/app/ingest/watcher.py:212-269`
**Issue:** Tanto `run_watcher` (linha 213) quanto `_watch_for_reconfig` (linha 264) leem `active_folder_paths` a cada 5s, em paralelo, enquanto o `awatch` roda. São duas tarefas consultando o DB independentemente para o mesmo propósito (detectar mudança de conjunto). Além de duplicar I/O de banco no único-writer, há uma janela de corrida: `run_watcher` lê `folders` para passar a `_handle_changes`, mas `_watch_for_reconfig` é quem decide reiniciar — se uma pasta é removida, o `_handle_changes` em voo ainda usa o `folders` antigo. Não corrompe estado (o gate protege), mas pode enfileirar com `folder_id` de uma pasta já removida.
**Fix:** Unificar a detecção de reconfiguração num único ponto, ou recarregar `folders` dentro de `_handle_changes` em vez de capturá-lo no escopo externo. Tornar o intervalo configurável via Settings em vez de constante de módulo.

### WR-06: `split_pdf` só captura `pikepdf.PdfError`, deixando outras exceções escaparem sem contexto

**File:** `backend/app/ingest/splitter.py:57-73`
**Issue:** O `try/except` captura apenas `pikepdf.PdfError`. Mas `pikepdf.Pdf.open` pode levantar `FileNotFoundError` (arquivo removido entre estabilização e split — janela real, pois são etapas separadas no tempo), `PermissionError` (lock no Windows), ou `OSError`. Essas escapam como exceções cruas. No worker isso ainda vira retry/FALHA (o `except Exception` genérico pega), então não há crash — mas a mensagem de erro perde o contexto controlado ("PDF inválido ou corrompido: nome") e um arquivo simplesmente removido será tratado como falha permanente após esgotar tentativas, em vez de ser descartado silenciosamente. O docstring promete "exceção controlada com contexto do arquivo" que não cobre esses casos.
**Fix:** Ampliar o except para `(pikepdf.PdfError, OSError)` e diferenciar `FileNotFoundError` (descartar/no-op) de corrupção real (FALHA).

### WR-07: `_store_block` carrega o bloco inteiro em memória; imagem lê arquivo inteiro

**File:** `backend/app/pipeline/ingest_stage.py:128,133-134,169-189`
**Issue:** `blocks = [source_path.read_bytes()]` (linha 128) e o loop que recebe `block_bytes: bytes` materializam o conteúdo completo de cada bloco/imagem em memória, e `split_pdf` (splitter.py:69) acumula **todos** os blocos como `list[bytes]` simultaneamente. Para um PDF de centenas de MB com `pages_per_block=1`, isso mantém o documento inteiro fatiado na RAM de uma vez. O CAS já é streaming-friendly (recebe um `Path`), então essa materialização é um retrocesso. (Performance pura está fora de escopo v1, mas isto é também um risco de **estabilidade**: OOM no processo único derruba watcher+worker+API juntos no Windows.)
**Fix:** Fazer `split_pdf` escrever cada bloco direto num arquivo temporário (`yield` de paths em vez de `list[bytes]`), e `_store_block` receber um path. Para imagem, passar `source_path` direto ao `cas.store` (já é um arquivo) em vez de `read_bytes()`.

## Info

### IN-01: `formatSize`/coluna "Tamanho" renderiza sempre "—" — campo `size` nunca é populado

**File:** `frontend/src/pages/DocumentsPage.tsx:35-40,236`, `backend/app/api/documents.py:34-43`
**Issue:** `DocumentOut` no backend não expõe `size`; `Doc.size` no frontend é opcional e nunca chega preenchido. A coluna "Tamanho" sempre mostra "—". Código morto efetivo (`formatSize` nunca recebe número) até a API expor o tamanho.
**Fix:** Ou remover a coluna/`formatSize` até a API suportar, ou adicionar `size` ao `DocumentOut` (derivado do blob no CAS).

### IN-02: Watcher global na UI (`watcher`/`onToggleWatcher`) é puramente cosmético

**File:** `frontend/src/App.tsx:32,83`, `frontend/src/pages/ConfigPage.tsx:206`
**Issue:** O toggle "Watcher global" controla apenas `useState(true)` local; não há endpoint que pause/retome o watcher real (que sobe no lifespan). Um operador que "desligar" o watcher na UI continuará tendo arquivos ingeridos — falsa sensação de controle.
**Fix:** Documentar como mock até existir o controle real, ou desabilitar/ocultar o toggle nesta fase.

### IN-03: `claim_next` faz `session.commit()` após `UPDATE ... RETURNING`, mas o comentário sobre 2 workers é aspiracional

**File:** `backend/app/queue/repo.py:80-117`
**Issue:** O docstring afirma que o claim é seguro "mesmo com 2 workers no futuro". Com `check_same_thread=False` e `busy_timeout`, dois writers SQLite podem colidir e um receberá `SQLITE_BUSY`/erro em vez de simplesmente "não ganhar a linha". A afirmação de segurança multi-worker não está provada por teste (todos os testes são sequenciais) e o design declarado é single-writer. Não é bug hoje, mas o comentário promete mais do que o código garante.
**Fix:** Restringir a afirmação ao caso single-writer real (D-11), ou cobrir com teste de concorrência se a garantia multi-worker for desejada.

### IN-04: Migração 0002 usa `server_default='ingest'`/strings literais que podem divergir do modelo

**File:** `backend/alembic/versions/0002_ingestion.py:77,80-82`
**Issue:** A migração declara `server_default='ingest'`, `'0'`, `'5'`, `'pending'` como literais, espelhando o modelo manualmente. Não há teste que compare o schema gerado pela migração com `Base.metadata` (autogenerate diff). Divergências futuras entre modelo e migração passariam despercebidas — risco para upgrades no cliente (criticidade reconhecida na própria CLAUDE.md: "Crítico para upgrades sem perda de dados").
**Fix:** Adicionar um teste que rode `alembic upgrade head` e compare o schema resultante com `Base.metadata` (ex.: `alembic check` ou comparação de `inspect`), garantindo que migração e modelos não divirjam.

---

_Reviewed: 2026-06-16T04:03:24Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

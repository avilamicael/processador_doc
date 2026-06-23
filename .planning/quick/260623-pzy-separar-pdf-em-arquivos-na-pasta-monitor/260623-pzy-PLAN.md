---
phase: quick-260623-pzy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/models/watched_folder.py
  - backend/alembic/versions/0009_split_to_files.py
  - backend/app/api/watched_folders.py
  - backend/app/pipeline/ingest_stage.py
  - backend/app/queue/worker.py
  - backend/app/ingest/watcher.py
  - backend/app/automation/fileops.py
  - frontend/src/types.ts
  - frontend/src/pages/ConfigPage.tsx
  - backend/tests/test_split_to_files.py
autonomous: true
requirements: [QUICK-SPLIT-TO-FILES]
user_setup: []

must_haves:
  truths:
    - "Com opt-in LIGADO, um PDF de 5 páginas com pages_per_block=2 vira 3 arquivos na própria pasta (2+2+1) e o original some do disco"
    - "O original é sempre recuperável do CAS após a substituição (nunca há perda)"
    - "O watcher NÃO re-ingere os arquivos de bloco gravados na pasta monitorada (sem loop)"
    - "Com opt-in DESLIGADO (default), o comportamento atual é idêntico — nada é gravado na pasta nem removido"
    - "Cada gravação de bloco e a remoção do original ficam registradas em AuditLog write-ahead (intent→done), reversíveis pelo undo"
    - "Os arquivos de bloco têm nomes genéricos derivados do original + faixa de páginas, sanitizados para Windows"
  artifacts:
    - path: "backend/alembic/versions/0009_split_to_files.py"
      provides: "Coluna split_to_files (Boolean, default 0) em watched_folders — forward-only, sem tocar documents"
      contains: "add_column"
    - path: "backend/app/pipeline/ingest_stage.py"
      provides: "Materialização opt-in dos blocos na pasta + anti-loop + audit + remoção do original"
      contains: "split_to_files"
    - path: "backend/tests/test_split_to_files.py"
      provides: "Cobertura: N arquivos gravados, original removido+recuperável, watcher no-op, opt-in off intacto"
      contains: "def test_"
  key_links:
    - from: "backend/app/pipeline/ingest_stage.py"
      to: "ingested_originals.original_hash"
      via: "registro do content_hash de cada bloco no gate ANTES de gravar o arquivo (anti-loop)"
      pattern: "IngestedOriginal\\("
    - from: "backend/app/pipeline/ingest_stage.py"
      to: "backend/app/automation/fileops.py"
      via: "materialize_to_dest (escreve do CAS, verifica hash) + remove_original"
      pattern: "materialize_to_dest|remove_original"
    - from: "backend/app/pipeline/ingest_stage.py"
      to: "audit_log"
      via: "AuditLog write-ahead intent→done por bloco e pela remoção do original"
      pattern: "AuditLog\\("
---

<objective>
Quando um PDF multipágina entra numa pasta monitorada marcada com opt-in, o sistema
SEPARA o PDF em arquivos físicos na própria pasta, SUBSTITUINDO o original pelos
blocos, ANTES da IA. Ex.: PDF de 5 páginas + `pages_per_block=2` → a pasta passa a
ter `<stem>_p1-2.pdf`, `<stem>_p3-4.pdf`, `<stem>_p5.pdf` e o original some. Cada
bloco segue o pipeline normal depois (extract→classify→apply, INALTERADO).

O sistema JÁ cria um Document por bloco em `process_ingest`, e cada bloco já está no
CAS por `content_hash`. O que falta é MATERIALIZAR esses blocos como arquivos na
pasta e REMOVER o original — de forma segura, reversível e sem loop do watcher.

Purpose: Entregar a separação física opt-in pedida pelo usuário sem violar a
constraint sagrada da CLAUDE.md (nunca perder arquivo do cliente) e sem reinventar a
máquina de arquivo (reusa fileops/audit/CAS/dedup existentes).

Output: campo opt-in `split_to_files` (modelo+migração 0009+API+UI), lógica de
materialização-na-pasta no `ingest_stage`, anti-loop via gate de dedup, audit
write-ahead, e testes pytest.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

<!-- CONSTRAINT SAGRADA (CLAUDE.md): operações que movem/renomeiam arquivos do
     cliente devem ser reversíveis e NUNCA podem causar perda. O original já vai ao
     CAS em process_ingest ANTES do split (rede de segurança); a remoção do disco só
     ocorre DEPOIS dos blocos gravados e verificados por hash. -->

@backend/app/pipeline/ingest_stage.py
@backend/app/automation/fileops.py
@backend/app/models/watched_folder.py
@backend/app/models/ingested_original.py
@backend/app/models/audit_log.py
@backend/app/api/watched_folders.py
@backend/app/ingest/watcher.py
@backend/app/queue/worker.py
@backend/app/automation/naming.py
@frontend/src/types.ts
@frontend/src/pages/ConfigPage.tsx

<interfaces>
<!-- Contratos REAIS extraídos do código. O executor usa estes diretamente. -->

fileops.py (app/automation/fileops.py):
- materialize_to_dest(content_hash: str, dst: Path) -> Path
    Lê o blob do CAS, escreve em dst com verificação de hash (tmp+fsync+os.replace).
    Hash divergente → IntegrityError, dst NÃO criado/corrompido. NÃO toca a origem.
- remove_original(source_path: Path) -> None
    unlink(missing_ok=True). Chamar SOMENTE após o(s) destino(s) verificado(s).
- resolve_collision(dst: Path, src: Path) -> Path | None   (anti-colisão D-09/D-10)
- class IntegrityError(Exception)

ingest_stage.py (já existente):
- process_ingest(session, *, source_path: Path, folder_id: int|None,
    pages_per_block: int|None, original_hash: str) -> IngestResult   (assinatura ATUAL)
- _store_block(block_bytes, data_dir) -> str   (retorna content_hash do bloco)
- split_pdf(src_path, pages_per_block) -> list[bytes]  (de app.ingest.splitter)

watcher.py — onde o payload do job ingest é montado:
- _stabilize_hash_gate_enqueue(engine, file_path, folder_id, pages_per_block) -> bool
    monta `payload = json.dumps({"source_path","folder_id","pages_per_block"})` e chama
    repo.enqueue(step="ingest"). Os DOIS call sites (scan_and_enqueue ~L184,
    _handle_changes ~L287) passam folder.id e folder.pages_per_block.
worker.py — _process_job_blocking lê data["source_path"], data.get("folder_id"),
    data.get("pages_per_block") e chama process_ingest.

IngestedOriginal (gate de dedup, app/models/ingested_original.py):
- original_hash: str  (UNIQUE, index) — o watcher faz sha256_file(arquivo) e compara
  AQUI. sha256_file usa o MESMO SHA-256 do CAS → para um arquivo de bloco,
  sha256_file(bloco) == content_hash do bloco.
- original_filename, source_folder_id (FK SET NULL), block_count, duplicate_hits

AuditLog (write-ahead, app/models/audit_log.py):
- action: str, status: str ("intent"/"done"/"undone"), source_path, dest_path,
  run_id, content_hash, document_id (nullable), details
  (undo.py reverte por action: "apply"=move restaura origem/CAS; "copy"=apaga dest)

naming.py:
- sanitize_component(value: str, max_len: int|None=None) -> str  (seguro p/ Windows)
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Coluna opt-in split_to_files (modelo + migração 0009 + API)</name>
  <files>backend/app/models/watched_folder.py, backend/alembic/versions/0009_split_to_files.py, backend/app/api/watched_folders.py</files>
  <action>
Adicionar o campo opt-in `split_to_files` (default DESLIGADO) à pasta monitorada,
espelhando EXATAMENTE o padrão de `active`/`pages_per_block` já presentes.

1. WatchedFolder (modelo): adicionar `split_to_files: Mapped[bool]` via
`mapped_column(Boolean, default=False, server_default=text("0"), nullable=False)`.
No `__init__`, `kwargs.setdefault("split_to_files", False)` (mesmo padrão dos
defaults existentes). Atualizar o docstring do módulo mencionando o opt-in.

2. Migração `0009_split_to_files.py` (forward-only, `down_revision = "0008"`):
`upgrade()` usa `op.batch_alter_table('watched_folders')` + `batch_op.add_column(
sa.Column('split_to_files', sa.Boolean(), nullable=False, server_default='0'))`.
`downgrade()` faz `drop_column('split_to_files')`. NO docstring, registrar o CAVEAT
padrão: esta migração SÓ toca `watched_folders` — NÃO faz batch em `documents`, logo
o trigger `trg_documents_updated_at` (0002) permanece intacto. Espelhar o estilo da
0005 (header de revisão + comentários PT-BR).

3. API (watched_folders.py): adicionar `split_to_files: bool = False` ao
`WatchedFolderIn`; `split_to_files: bool | None = None` ao `WatchedFolderPatch`;
`split_to_files: bool` ao `WatchedFolderOut`. No `create_folder` passar
`split_to_files=body.split_to_files` ao construir `WatchedFolder`. No `update_folder`
adicionar `if body.split_to_files is not None: folder.split_to_files = body.split_to_files`
(mesmo padrão de `active`).

NÃO tocar `documents` nem o trigger. NÃO alterar a lógica de dedup/path existente.
  </action>
  <verify>
    <automated>cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run python -c "from app.models.watched_folder import WatchedFolder; f=WatchedFolder(path='/x'); assert f.split_to_files is False"</automated>
  </verify>
  <done>Migração 0009 sobe e desce sem erro; WatchedFolder tem split_to_files default False; API aceita/retorna o campo; documents/trigger intactos.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Materialização opt-in dos blocos na pasta + anti-loop + audit + remoção do original</name>
  <files>backend/app/pipeline/ingest_stage.py, backend/app/queue/worker.py, backend/app/ingest/watcher.py, backend/app/automation/fileops.py, backend/tests/test_split_to_files.py</files>
  <behavior>
Foco da segurança/corretude. Testes em test_split_to_files.py (RED primeiro):

- test_opt_in_grava_n_arquivos_e_remove_original: pasta monitorada com
  split_to_files=True, pages_per_block=2, PDF de 5 páginas em <pasta>/doc.pdf →
  após process_ingest a pasta contém 3 arquivos de bloco (ex.: doc_p1-2.pdf,
  doc_p3-4.pdf, doc_p5.pdf) e doc.pdf NÃO existe mais. block_count==3.
- test_original_recuperavel_do_cas: após a substituição, o original (pelo
  original_hash) ainda é lido via cas.read_bytes(original_hash) e bate byte-a-byte
  com o PDF original — invariante "nunca perde".
- test_anti_loop_gate_reconhece_blocos: cada arquivo de bloco gravado tem seu
  content_hash registrado como IngestedOriginal ANTES de o arquivo existir no disco;
  re-rodar o caminho do gate (sha256_file do arquivo de bloco → consulta
  IngestedOriginal) encontra a linha → no-op (não enfileira/re-separa). Verificar
  que existe um IngestedOriginal com original_hash == content_hash de cada bloco.
- test_audit_write_ahead_intent_done: para cada bloco gravado e para a remoção do
  original há AuditLog; ao final ficam status="done" com source_path/dest_path/
  content_hash preenchidos (reversível pelo undo).
- test_opt_in_off_comportamento_atual: split_to_files=False → NENHUM arquivo novo na
  pasta, o original PERMANECE intacto, e os Documents/blocos são criados como hoje
  (regressão do fluxo atual).
- test_idempotencia_crash_safety: rodar process_ingest 2x para o mesmo original
  (segundo via gate de duplicata) NÃO duplica arquivos na pasta nem perde o original;
  e se alguns blocos já estão na pasta, re-materializar é no-op (resolve_collision
  D-10 pula idêntico). Garantir que a remoção do original é idempotente.
  </behavior>
  <action>
Implementar a materialização-na-pasta DENTRO de `process_ingest`, executada SOMENTE
quando a pasta tem `split_to_files` ligado. Ordem OBRIGATÓRIA (a sequência É a
garantia de segurança e anti-loop):

PRÉ-REQUISITO de assinatura (threading do opt-in pasta→fila→worker→stage):
- `process_ingest`: adicionar o parâmetro keyword-only `split_to_files: bool = False`
  (default False preserva TODOS os callers/testes atuais).
- worker.py `_process_job_blocking`: ler `split_to_files = data.get("split_to_files", False)`
  e repassar a `process_ingest(...)`.
- watcher.py: adicionar o parâmetro `split_to_files: bool` à assinatura de
  `_stabilize_hash_gate_enqueue` e incluir `"split_to_files": split_to_files` no
  dict de `json.dumps` do payload do job ingest. Atualizar os DOIS call sites:
  `scan_and_enqueue` (passar `folder.split_to_files`) e `_handle_changes` (calcular
  `split_to_files = folder.split_to_files if folder is not None else False` e passar).

Dentro de `process_ingest`, manter os passos atuais (1–7) INALTERADOS. No passo 6,
guardar a lista `block_hashes` (na ordem dos blocos) — já temos cada hash. Após o
commit único do passo 7 (blocos+IngestedOriginal já persistidos), adicionar um passo
NOVO "split-to-files", executado só se `split_to_files and is_pdf and folder_id and len(blocks) > 0`:

(A) ANTI-LOOP PRIMEIRO — registrar o gate de cada bloco ANTES de qualquer arquivo
existir na pasta. Para cada `block_hash` em `block_hashes`, inserir um
`IngestedOriginal` com `original_hash = block_hash` (o gate é keyed por hash;
sha256_file de um arquivo de bloco == content_hash do bloco), `original_filename =
<nome do arquivo de bloco>`, `source_folder_id = folder_id`, `block_count = 0`. Usar
try/except (rollback parcial) por linha para o caso de a UNIQUE já existir (re-run
idempotente → pula). `session.commit()` ESTE registro do gate ANTES de escrever
qualquer arquivo de bloco no disco — fechar a corrida (o watcher pode detectar o
arquivo no instante em que ele aparece; o gate já tem que estar lá). Documentar no
docstring/comentário o uso justificado de `ingested_originals` como mecanismo de
ignore (mesma tabela, mesma semântica de "hash já visto") — é mais limpo que um
mecanismo dedicado e reusa o gate que JÁ roda no watcher e no passo 2.

(B) Derivar o nome de cada arquivo de bloco do nome do original + faixa de páginas.
Calcular as faixas a partir de `pages_per_block` e do nº total de páginas do PDF
(reproduzir o range do `split_pdf`: blocos de até N páginas; rótulo `_p{a}` para 1
página, `_p{a}-{b}` para faixa). Stem = `Path(source_path.name).stem`; nome =
`sanitize_component(f"{stem}_p{a}-{b}.pdf")` (sanitize p/ Windows). dest = pasta do
original (`source_path.parent`) / nome. A anti-colisão de nome repetido é coberta por
`materialize_to_dest`+`resolve_collision` do fileops — NÃO reimplementar.

(C) Para cada bloco (mesma ordem de block_hashes): write-ahead AuditLog
`status="intent"`, `action="apply"`, `source_path = <caminho do arquivo de bloco a
gravar>`, `dest_path = <mesmo caminho>` (o "destino" é a própria pasta),
`content_hash = block_hash`, `document_id` = id do Document do bloco. commit do
intent. Então `fileops.materialize_to_dest(block_hash, dest_path)` (escreve do CAS,
verifica hash). Em sucesso, marcar o AuditLog `status="done"`. Em IntegrityError,
propagar (worker roteia a FALHA; original NÃO é removido — preservação).

Por que `action="apply"`: o undo de "apply" restaura via destino ou via CAS — exatamente
a reversão desejada (apagar o bloco e restaurar o original do CAS). Se o executor
julgar que a semântica de undo precisa apagar TODOS os blocos + restaurar o original,
documentar a escolha de `action` no SUMMARY; a propriedade obrigatória é só:
reversível e nunca perde (o original está no CAS por original_hash).

(D) SÓ DEPOIS de TODOS os blocos gravados e verificados (todos os AuditLog="done"),
remover o original do disco: write-ahead AuditLog `status="intent"`,
`action="apply"`, `source_path = str(source_path)`, `content_hash = original_hash`,
`dest_path = None`; commit; `fileops.remove_original(source_path)`; marcar
`status="done"`. Se qualquer bloco falhou em (C), NÃO chegar aqui — o original
permanece (rede de segurança). `remove_original` é idempotente (missing_ok).

Crash-safety: reusar os padrões existentes — UNIQUE(content_hash) dos blocos, gate
UNIQUE(original_hash), e o AuditLog intent/done já tem `reconcile_orphans` no startup
do worker. Re-rodar process_ingest para o mesmo original cai no gate de duplicata
(passo 2) e é no-op; re-materializar um bloco já gravado é no-op via resolve_collision
(D-10 pula idêntico); remover um original já removido é no-op.

NÃO place fenced code in this action. NÃO mudar o pipeline downstream
(extract/classify/apply). NÃO logar conteúdo (só metadados/paths — LGPD V7/V9).
fileops: só adicionar fachada fina se faltar algo; preferir reusar materialize_to_dest
/remove_original/resolve_collision sem reescrever a máquina segura.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_split_to_files.py -x -q && uv run pytest tests/test_ingest_stage.py tests/test_watcher.py -q</automated>
  </verify>
  <done>Todos os testes de test_split_to_files.py passam (N arquivos gravados, original removido E recuperável do CAS, gate anti-loop registrado pré-gravação, audit intent→done, opt-in off = regressão intacta, idempotência); test_ingest_stage.py e test_watcher.py continuam verdes (sem regressão).</done>
</task>

<task type="auto">
  <name>Task 3: UI — toggle split_to_files na ConfigPage</name>
  <files>frontend/src/types.ts, frontend/src/pages/ConfigPage.tsx</files>
  <action>
Expor o opt-in na aba "Pastas monitoradas", espelhando o padrão de `pages_per_block`
no formulário e de `active` na linha.

1. types.ts: adicionar `split_to_files: boolean` a `Folder`; `split_to_files: boolean`
a `FolderCreate`; `split_to_files?: boolean` a `FolderPatch` (mesma estrutura dos
campos vizinhos já presentes).

2. ConfigPage.tsx (PastasTab):
- `FormState`: adicionar `splitToFiles: boolean`.
- `openAdd`: incluir `splitToFiles: false`. `openEdit`: `splitToFiles: f.split_to_files`.
- No formulário inline, abaixo do campo "Separar a cada N páginas", adicionar um
  `<label>` com o componente `Switch` (já importado) controlando `form.splitToFiles`
  (onToggle → `setForm({ ...form, splitToFiles: !form.splitToFiles })`), com título
  "Separar fisicamente o PDF em arquivos na pasta" e um texto de ajuda PT-BR curto:
  explicar que, quando ligado, o PDF é separado em arquivos na própria pasta
  (substituindo o original) ANTES do processamento, e que o original continua
  recuperável (não há perda). Mencionar que depende de "Separar a cada N páginas"
  estar configurado.
- `submitForm`: incluir `split_to_files: form.splitToFiles` no body de create e no
  body de update (PATCH).
- Na `folder-row` (lista), no `folder-meta`, adicionar um indicador quando
  `f.split_to_files` for true (ex.: span "· Separa em arquivos") para o usuário ver o
  estado sem abrir o editor.

Manter o estilo inline existente (sem CSS novo). Textos voltados ao usuário em PT-BR.
  </action>
  <verify>
    <automated>cd frontend && npx tsc --noEmit && npm run build</automated>
  </verify>
  <done>tsc sem erros e build passa; o formulário de pasta tem o toggle "split_to_files"; a linha indica quando está ligado; create e update enviam o campo.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| pasta monitorada → disco do cliente | gravação de N arquivos + remoção do original; risco de PERDA (constraint sagrada) |
| arquivo de bloco gravado → watcher | o arquivo aparece na pasta observada; risco de LOOP de reprocessamento |
| nome derivado (stem do original) → caminho de arquivo Windows | stem do original é entrada do usuário; risco de path/nome inválido |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-pzy-01 | Denial of Service (perda) | remoção do original após split | mitigate | original já no CAS (passo 3 do ingest) ANTES do split; remove_original SÓ após todos os blocos gravados+verificados por hash (materialize_to_dest); AuditLog intent→done torna reversível |
| T-pzy-02 | Tampering (loop) | arquivos de bloco na pasta monitorada | mitigate | registrar content_hash de cada bloco em ingested_originals (gate) e COMMIT ANTES de gravar o arquivo; watcher/passo-2 reconhecem como duplicata → no-op |
| T-pzy-03 | Tampering (path) | nome do arquivo de bloco (stem do original) | mitigate | sanitize_component (Windows) + anti-colisão resolve_collision do fileops |
| T-pzy-04 | Repudiation | gravação/remoção sem trilha | mitigate | AuditLog write-ahead (intent→done) por bloco e pela remoção do original; reconcile_orphans no startup adjudica intents pendurados |
| T-pzy-05 | Tampering | migração 0009 tocar documents/trigger | mitigate | batch_alter_table SÓ em watched_folders; CAVEAT documentado; trigger trg_documents_updated_at intacto |
| T-pzy-SC | Tampering | npm/pip installs | accept | nenhum pacote novo é instalado neste plano (reusa stack existente) — sem superfície de supply-chain |
</threat_model>

<verification>
Checks de fase (a máquina piloto WSL valida AO VIVO além dos pytest):
- `cd backend && uv run pytest tests/test_split_to_files.py tests/test_ingest_stage.py tests/test_watcher.py -q` → verde.
- `cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` → sem erro.
- `cd frontend && npx tsc --noEmit && npm run build` → sem erro.
- AO VIVO (orquestrador, WSL): pasta com split_to_files=True + pages_per_block=2;
  dropar um PDF de 5 páginas → a pasta passa a ter 3 arquivos de bloco, o original
  some, e NÃO há novo job/loop (logs do watcher: "Duplicata ignorada (gate)" para os
  blocos). Chave OpenAI vazia NÃO bloqueia (split-to-files é antes da IA).
</verification>

<success_criteria>
- Opt-in `split_to_files` por pasta (default OFF) em modelo+migração 0009+API+UI.
- Com opt-in ON: PDF multipágina vira N arquivos na pasta (faixas de páginas no nome,
  sanitizados p/ Windows) e o original é removido do disco.
- Original SEMPRE recuperável do CAS (invariante de não-perda da CLAUDE.md).
- Watcher NUNCA re-ingere os arquivos de bloco gravados (gate registrado antes da
  gravação).
- Com opt-in OFF: comportamento atual idêntico (regressão coberta por teste).
- Cada gravação e a remoção do original em AuditLog write-ahead (reversível pelo undo).
- migração 0009 forward-only; documents/trigger intactos.
- Nenhum pacote novo; nenhum nssm.exe/.zip/.vbs commitado.
</success_criteria>

<output>
Create `.planning/quick/260623-pzy-separar-pdf-em-arquivos-na-pasta-monitor/260623-pzy-SUMMARY.md` when done
</output>

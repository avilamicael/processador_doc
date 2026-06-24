---
phase: quick-260624-far
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/api/documents.py
  - backend/app/api/watcher_status.py
  - backend/app/main.py
  - backend/app/ingest/watcher.py
  - backend/tests/test_api_documents.py
  - backend/tests/test_api_watcher_status.py
  - frontend/src/lib/api.ts
  - frontend/src/types.ts
  - frontend/src/hooks/useDocuments.ts
  - frontend/src/hooks/useWatcherStatus.ts
  - frontend/src/pages/DocumentsPage.tsx
  - frontend/src/pages/ConfigPage.tsx
  - frontend/src/components/Sidebar.tsx
  - frontend/src/components/Header.tsx
  - frontend/src/App.tsx
autonomous: true
requirements: [UI-AJUSTES-260624]

must_haves:
  truths:
    - "Usuário pode remover um ou vários documentos da lista; some apenas o registro do app, o arquivo físico permanece intocado"
    - "Remover um documento NUNCA apaga nem move o arquivo de origem do cliente"
    - "Abas 'Regras de separação' e 'Integrações' aparecem desabilitadas com aviso 'em breve / versão 2'"
    - "Na aba 'Leitura de dados', os controles mock ficam desabilitados mas o Limiar de confiança continua funcional (salva na API)"
    - "A Sidebar mostra o status real do watcher: ativo/inativo, número de pastas ativas e quando foi a última varredura"
    - "Busca e sino do Header ficam desabilitados (esmaecidos), sem o ponto vermelho de notificação"
  artifacts:
    - path: "backend/app/api/documents.py"
      provides: "Endpoint POST /documents/delete (remoção em lote, só registro)"
      contains: "documents/delete"
    - path: "backend/app/api/watcher_status.py"
      provides: "Endpoint GET /watcher/status"
      contains: "watcher/status"
    - path: "frontend/src/components/Sidebar.tsx"
      provides: "Status do watcher dinâmico (sem hardcode '4 pastas')"
  key_links:
    - from: "frontend/src/pages/DocumentsPage.tsx"
      to: "/documents/delete"
      via: "useDeleteDocuments → postDeleteDocuments"
      pattern: "documents/delete"
    - from: "frontend/src/components/Sidebar.tsx"
      to: "/watcher/status"
      via: "useWatcherStatus (polling)"
      pattern: "watcher/status"
    - from: "backend/app/ingest/watcher.py"
      to: "app.state.last_scan_at"
      via: "scan_and_enqueue atualiza timestamp da última varredura"
      pattern: "last_scan_at"
---

<objective>
Quatro ajustes de UI/UX no Processador de Documentos, com suporte de backend onde necessário:

1. **Remover documento(s)** na aba Documentos — apaga SÓ o registro do app (Document + linhas relacionadas órfãs), NUNCA toca no arquivo físico do cliente.
2. **Desabilitar subabas não funcionais** em Configurações (Regras de separação e Integrações 100% mock; na Leitura de dados desabilitar só os controles mock, mantendo o Limiar de confiança funcional).
3. **Status real do watcher** na Sidebar (hoje hardcoded "4 pastas · varredura há 2 min").
4. **Desabilitar busca e sino** no Header (esmaecidos, "em breve").

Purpose: Tirar elementos mock/falsos da interface (que confundem e parecem bugs) e dar ao usuário o controle de limpar entradas que falharam ou que ele já tratou manualmente — sem risco de perda de arquivos.
Output: 2 endpoints novos (DELETE em lote + status do watcher), rastreamento de última varredura no watcher, e ajustes em 5 arquivos de frontend.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

<interfaces>
<!-- Contratos já existentes no código — usar diretamente, sem explorar a base. -->

backend/app/api/documents.py — router já montado em main.py via app.include_router(documents_api.router); usa `request.app.state.engine` + `get_session(engine)`. Já tem rotas /documents, /documents/{id} (path int), /documents/{id}/retry|reclassify|approve, /rescan. CRÍTICO: registrar a rota de delete em lote como POST /documents/delete (NÃO como variação de /documents/{document_id}) — o conversor de path `{document_id}: int` rejeita "delete" com 422, então /documents/delete deve ser registrado ANTES de /documents/{document_id}, igual /documents/attention já é (ver comentário em documents.py:345).

Document (backend/app/models/document.py): content_hash UNIQUE, origin_original_id FK→ingested_originals (ON DELETE SET NULL), e relationships com cascade="all, delete-orphan" para pages/usages/audit_logs/extraction/classification → session.delete(doc) já apaga em cascata extraction/classification/filled_fields/usages/audit_logs. NÃO há cascade para Jobs nem para IngestedOriginal (são por hash, não FK direta a Document).

IngestedOriginal (backend/app/models/ingested_original.py): original_hash UNIQUE = gate de dedup do watcher. block_count = quantos blocos o original gerou.

Job (backend/app/models/job.py): UNIQUE(original_hash, step). repo já existe (app.queue.repo) com enqueue/requeue_step.

watcher.py: `_stabilize_hash_gate_enqueue` consulta IngestedOriginal por original_hash; se existe → trata como duplicata e NÃO re-enfileira. `scan_and_enqueue(engine, paths)` é o ponto único de varredura (startup, /rescan, watcher). `run_watcher` roda como asyncio.Task no lifespan (main.py:71); app.state.engine e app.state.stop_event já existem.

watched_folders.py: WatchedFolder tem coluna `active` (bool). Contagem de pastas ativas = select(func.count).where(WatchedFolder.active.is_(True)).

Padrão de teste (backend/tests/test_api_documents.py): fixture `client` sobrescreve app.state.engine com `schema_engine`; helper `_seed` cria Documents/IngestedOriginal; usa get_session(schema_engine) para asserts diretos no banco.

Frontend api.ts: helper `request<T>(path, init)` checa res.ok, trata 204. Padrão de mutation+invalidate em useDocuments.ts (useRescan invalida ['documents'] e ['duplicates-count']). App.tsx mantém `selected: number[]` + toggleSel/toggleAll; passa para DocumentsPage. Header recebe props mas search/sino são locais ao componente.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Backend — DELETE em lote de documentos (só registro) + GET /watcher/status</name>
  <files>backend/app/api/documents.py, backend/app/api/watcher_status.py, backend/app/main.py, backend/app/ingest/watcher.py, backend/tests/test_api_documents.py, backend/tests/test_api_watcher_status.py</files>
  <behavior>
    DELETE em lote (POST /documents/delete com {ids:[...]}):
    - Test: remover ids existentes → 200, retorna {deleted: N}; os Documents somem do banco; o ARQUIVO FÍSICO de origem NÃO é tocado (o endpoint nunca chama os.remove/shutil/Path.unlink — o teste verifica que nenhuma operação de FS é referenciada; o CAS e a pasta monitorada permanecem intactos).
    - Test: ids inexistentes são ignorados silenciosamente (não derruba o lote); lista vazia → 200 {deleted: 0}.
    - Test (anti-órfão de dedup): ao remover o ÚLTIMO Document de um IngestedOriginal (nenhum outro Document com aquele origin_original_id), o IngestedOriginal é removido também → o gate de dedup é liberado e, se o arquivo ainda estiver na pasta, o watcher pode re-ingerir (comportamento esperado). Se AINDA houver outros Documents apontando para o mesmo IngestedOriginal (caso split), o IngestedOriginal é PRESERVADO.
    - Test (anti-órfão de fila): Jobs com original_hash == doc.content_hash são removidos junto (senão um Job 'done' com a UNIQUE (hash,step) bloquearia uma futura re-ingestão). Idem para o original_hash do IngestedOriginal removido.
    - Test: cascade já apaga extraction/classification/filled_fields/usages/audit_logs do Document (não deixa órfãos).

    GET /watcher/status:
    - Test: retorna {active: bool, active_folder_count: int, last_scan_at: str|null}. active_folder_count = nº de WatchedFolder com active=True. last_scan_at reflete o timestamp gravado em app.state após uma varredura (null se nunca varreu).
  </behavior>
  <action>
    Criar POST /documents/delete em backend/app/api/documents.py, REGISTRADO ANTES de GET /documents/{document_id} (mesma razão de /documents/attention — senão "delete" cairia no conversor int e daria 422). Body Pydantic `DeleteDocumentsIn(ids: list[int])`; resposta `DeleteDocumentsOut(deleted: int)`. Implementação numa única sessão get_session(engine):
    (1) Para cada id em ids: session.get(Document, id); se None, pula (ignora silenciosamente).
    (2) ANTES de deletar, capturar doc.content_hash e doc.origin_original_id.
    (3) session.delete(doc) — o cascade all,delete-orphan já remove extraction/classification/filled_fields/usages/audit_logs.
    (4) Limpar Jobs órfãos: delete em jobs where original_hash == doc.content_hash (o bloco). 
    (5) Anti-órfão de dedup: após o flush dos deletes de Document, para cada origin_original_id distinto que foi tocado, checar se AINDA existe algum Document com aquele origin_original_id; se NÃO existir mais nenhum, buscar o IngestedOriginal, capturar seu original_hash, deletar o IngestedOriginal e deletar os Jobs where original_hash == (hash do original). Se ainda existir outro Document apontando, preservar o IngestedOriginal.
    (6) commit; retornar {deleted: <quantos Documents foram realmente apagados>}.
    NUNCA importar/chamar os/shutil/Path.unlink/remover arquivo — a remoção é PURAMENTE de banco (constraint forte do projeto: nunca causar perda de arquivos do cliente). Acrescentar docstring explicando: "Remove SÓ o registro do app; o arquivo físico permanece. Se o arquivo ainda estiver na pasta monitorada e o original ficar sem blocos, o watcher pode re-ingeri-lo numa próxima varredura — comportamento esperado."

    Rastreamento da última varredura: em backend/app/ingest/watcher.py, ao final de `scan_and_enqueue` (após o loop), gravar o timestamp atual. Como scan_and_enqueue recebe `engine` (não o app), expor o timestamp via uma referência acessível: gravar em `app.state.last_scan_at` a partir de main.py NÃO é direto daqui — em vez disso, definir um módulo-level `LAST_SCAN_AT: datetime | None = None` em watcher.py, atualizado dentro de scan_and_enqueue com datetime.now(timezone.utc) ao final, e uma função pública `get_last_scan_at() -> datetime | None`. (Mantém o watcher desacoplado do FastAPI app, consistente com o design atual.)

    Criar backend/app/api/watcher_status.py: APIRouter(tags=["watcher"]) com GET /watcher/status. Resposta `WatcherStatusOut(active: bool, active_folder_count: int, last_scan_at: datetime | None)`. `active` = True se app.state.stop_event existe e NÃO está setado (watcher task viva) — ler de request.app.state.stop_event (definido em main.py:70); fallback True se ausente em testes. active_folder_count via select(func.count()).select_from(WatchedFolder).where(WatchedFolder.active.is_(True)). last_scan_at via watcher.get_last_scan_at(). Registrar o router em main.py (app.include_router(watcher_status_api.router)) ANTES do catch-all _serve_frontend (que é o último).

    Testes: estender backend/tests/test_api_documents.py com casos do <behavior> do delete (reusar fixture `client`/`_seed`, asserts via get_session). Criar backend/tests/test_api_watcher_status.py espelhando o padrão de client/schema_engine para o GET /watcher/status (active_folder_count com pasta ativa/inativa; last_scan_at null inicialmente).
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/test_api_documents.py tests/test_api_watcher_status.py -x -q</automated>
  </verify>
  <done>POST /documents/delete remove só registros (Document+cascade+Jobs órfãos+IngestedOriginal sem blocos restantes), sem tocar em arquivo físico; GET /watcher/status retorna active/active_folder_count/last_scan_at; testes verdes.</done>
</task>

<task type="auto">
  <name>Task 2: Frontend — botão Remover, status do watcher, desabilitar subabas e Header</name>
  <files>frontend/src/types.ts, frontend/src/lib/api.ts, frontend/src/hooks/useDocuments.ts, frontend/src/hooks/useWatcherStatus.ts, frontend/src/pages/DocumentsPage.tsx, frontend/src/pages/ConfigPage.tsx, frontend/src/components/Sidebar.tsx, frontend/src/components/Header.tsx, frontend/src/App.tsx</files>
  <action>
    **types.ts:** adicionar `interface WatcherStatus { active: boolean; active_folder_count: number; last_scan_at: string | null }`.

    **api.ts:** adicionar `postDeleteDocuments(ids: number[]): Promise<{ deleted: number }>` chamando POST /documents/delete com body {ids} (padrão do `request` existente, ver postRescan ~76); e `getWatcherStatus(): Promise<WatcherStatus>` em GET /watcher/status.

    **useDocuments.ts:** adicionar hook `useDeleteDocuments()` (useMutation sobre postDeleteDocuments) que, no onSuccess, invalida ['documents'] e ['duplicates-count'] (mesmo padrão de useRescan).

    **useWatcherStatus.ts (novo):** hook `useWatcherStatus()` com useQuery queryKey ['watcher-status'], queryFn getWatcherStatus, refetchInterval 8000, refetchIntervalInBackground false, placeholderData keepPreviousData (espelha useDocuments.ts).

    **DocumentsPage.tsx:** importar useDeleteDocuments. Adicionar botão "Remover" na table-toolbar (ao lado de "Forçar varredura"), VISÍVEL só quando `selected.length > 0`, com estilo de ação destrutiva (background var(--st-erro), igual ao confirmar-remoção da PastasTab). Ao clicar, abrir um modal de confirmação (reusar o padrão de confirmação destrutiva já presente em ConfigPage.tsx PastasTab ~304-344: overlay fixed + card) com texto: "Remover N documento(s) da lista? Isto remove apenas o registro no aplicativo — os arquivos originais NÃO são apagados nem movidos. Se um arquivo ainda estiver numa pasta monitorada, ele pode ser reprocessado numa próxima varredura." Botões: "Manter" (ghost) e "Remover" (destrutivo). Confirmar → deleteDocs.mutate(selected, { onSuccess: limpar seleção }). Após sucesso, limpar a seleção: como `selected`/setSelected vivem em App.tsx, adicionar uma prop `onClearSel: () => void` em DocumentsPageProps e chamá-la no onSuccess. Desabilitar o botão Remover enquanto deleteDocs.isPending ("Removendo…").

    **App.tsx:** adicionar `const clearSel = () => setSelected([])` e passar `onClearSel={clearSel}` ao DocumentsPage.

    **Sidebar.tsx:** importar e usar useWatcherStatus. Substituir o título hardcoded "Watcher ativo" e o sub "4 pastas · varredura há 2 min" por valores dinâmicos: título "Watcher ativo"/"Watcher inativo" conforme status.active; sub = `${N} pasta(s) · varredura ${rel}` onde N = active_folder_count e `rel` é derivado de last_scan_at por um helper relativo em pt-BR ("há Xs"/"há X min"/"há X h"; "—" se null). O dot (.watcher-dot) reflete ativo/inativo via inline style background (var(--st-tratado) ativo / var(--text-3) inativo, espelhando o dot da PastasTab ~229). Tratar loading/erro: enquanto isLoading sem data → sub "verificando…"; isError → sub "—". Manter o markup/classes existentes.

    **Header.tsx:** desabilitar o input de busca (prop `disabled` no input, opacidade reduzida via style esmaecido, title "em breve") — a filtragem local em DocumentsPage fica inativa por hora (ok). Desabilitar o botão do sino (disabled + title "em breve") e REMOVER o `<span className="notif-dot" />` (não renderizar o ponto vermelho).

    **ConfigPage.tsx:**
    - RegrasTab (~349-380): desabilitar a aba inteira — adicionar no topo do conteúdo um aviso destacado "Em breve — disponível na versão 2"; desabilitar o botão "Nova regra" (disabled) e todos os Switch das RULES (passar `disabled`/não-interativo ao Switch; se o componente Switch não aceitar disabled, envolver num container com pointer-events:none + opacity 0.5 e remover o onToggle). Visualmente esmaecido.
    - IntegracoesTab (~530-551): idem — aviso "Em breve — disponível na versão 2" no topo, cards esmaecidos (opacity reduzida), sem interação.
    - LeituraTab (~382-441): desabilitar APENAS os controles mock — o select "Motor de OCR" (~392), o select "Idioma principal" (~403), o slider "Confiança mínima" (~414, esmaecer pois é estático), o Switch "Corrigir inclinação (deskew)" (~427) e o Switch "Remoção de ruído" (~434): adicionar `disabled` aos selects, esmaecer o bloco do slider e desabilitar/esmaecer os Switches, cada um com uma marca "em breve" discreta (ex.: pequena tag ao lado do read-label). MANTER 100% funcional o `<ReviewThresholdField />` (~438-440) — NÃO tocar nele.
    - TABS (~27-32): nos labels das abas 'regras' e 'integracoes', adicionar uma badge "em breve" discreta (ex.: `<span className="badge badge-off">em breve</span>` ou um sufixo estilizado) se simples e consistente com o visual; as abas continuam clicáveis (mostram o conteúdo desabilitado com o aviso).

    Não introduzir libs novas (code-and-config). Reusar tokens CSS existentes (--st-erro, --st-tratado, --text-3, badge/badge-off, card, btn-ghost/btn-primary).
  </action>
  <verify>
    <automated>cd frontend && npm run build</automated>
  </verify>
  <done>Botão Remover aparece com seleção e confirma antes de remover (limpando a seleção no sucesso); Sidebar mostra status real do watcher (pastas ativas + última varredura, dot dinâmico, loading/erro tratados); busca e sino do Header desabilitados sem ponto vermelho; Regras e Integrações desabilitadas com aviso v2, Leitura mantém só o Limiar funcional; `npm run build` verde (sem erro de tipos).</done>
</task>

</tasks>

<verification>
- `cd backend && uv run pytest -q` — suíte inteira verde (sem regressão nos testes existentes de documents/watcher).
- `cd frontend && npm run build` — TypeScript + Vite sem erros.
- Conferir manualmente que documents.py NÃO importa os/shutil e que a rota /documents/delete não chama unlink/remove (grep): `grep -nE "unlink|shutil|os\.remove" backend/app/api/documents.py | grep -v '^#'` deve retornar VAZIO.
</verification>

<success_criteria>
- POST /documents/delete remove só o registro (Document + cascata + Jobs/IngestedOriginal órfãos), nunca o arquivo físico; ids inexistentes ignorados; resposta {deleted: N}.
- GET /watcher/status responde com active, active_folder_count (pastas ativas) e last_scan_at (timestamp da última varredura, atualizado em scan_and_enqueue).
- Frontend: botão Remover com confirmação que reforça "arquivos NÃO são apagados"; Sidebar com status real; Header com busca/sino desabilitados sem notif-dot; ConfigPage com Regras/Integrações desabilitadas (aviso v2) e Leitura mantendo só o Limiar funcional.
- Nenhuma lib npm/pip nova. Build do frontend e suíte do backend verdes.
</success_criteria>

<output>
Create `.planning/quick/260624-far-ajustes-ui-remover-documentos-desabilita/260624-far-SUMMARY.md` when done
</output>

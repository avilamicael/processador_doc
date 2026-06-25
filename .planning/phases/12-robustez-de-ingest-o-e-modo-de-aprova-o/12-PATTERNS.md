# Phase 12: Robustez de ingestão e modo de aprovação - Pattern Map

**Mapped:** 2026-06-25
**Files analyzed:** 11 (modify) + 0 (create) — todos os pontos são EXTENSÃO de código existente
**Analogs found:** 11 / 11 (item 12 tem o molde EXATO do par `ai-fallback`)

> Achado-chave: **nenhum arquivo novo é necessário.** Os três itens são alterações
> cirúrgicas em arquivos existentes, e o item 12 (modo de aprovação) replica 1:1 o
> par de endpoints/hook/field do `ai-fallback` (Fase 10). Ver "Discrepâncias de path
> do CONTEXT" no fim — duas referências do CONTEXT apontam para o arquivo errado.

---

## File Classification

| Arquivo a modificar | Role | Data Flow | Analog mais próximo | Match |
|---------------------|------|-----------|---------------------|-------|
| `backend/app/ingest/watcher.py` (item 2) | service/watcher | event-driven | o próprio `scan_and_enqueue` + scan de startup (mesmo arquivo) | self / exact |
| `backend/app/api/documents.py` `delete_documents` (item 7) | route | CRUD/cleanup | bloco anti-órfão já existente (mesma função) | self / exact |
| `backend/app/config.py` Settings (item 12) | config | — | campo `classify_ai_fallback_enabled` (linhas 160-174) | exact |
| `backend/app/api/config.py` (item 12) | route/config | request-response | par `GET/PUT /config/ai-fallback` (linhas 70-100) | exact |
| `backend/app/queue/worker.py` `enqueue_pending_applications` (item 12) | service/worker | batch | a própria função (linhas 364-408) — gate novo | self / exact |
| `frontend/src/types.ts` (item 12) | type | — | `interface AiFallback` (linhas 407-409) | exact |
| `frontend/src/lib/api.ts` (item 12) | api-client | request-response | `get/putAiFallback` (linhas 177-186) | exact |
| `frontend/src/hooks/useAttention.ts` (item 12) | hook | request-response | `useAiFallback`/`useSaveAiFallback` (linhas 134-148) | exact |
| `frontend/src/pages/ConfigPage.tsx` (item 12) | component | request-response | `AiFallbackField` (linhas 523-589) | exact |
| `frontend/src/pages/DryRunPage.tsx` (item 12) | component | request-response | a própria página (vira fila de aprovação) | self / role-match |
| `backend/app/api/watched_folders.py` `update_folder` (item 2, opcional) | route | CRUD | PATCH existente (linhas 174-202) | self |

---

## Pattern Assignments

### Item 2 — `backend/app/ingest/watcher.py` (watcher, event-driven)

**Analog:** `scan_and_enqueue` (mesmo arquivo) — já é o caminho idempotente de varredura
de existentes; só falta DISPARÁ-LO quando uma pasta nova aparece em runtime.

**Onde a lacuna mora — supervisor de reconfig** (linhas 309-334). `_watch_for_reconfig`
APENAS detecta `current != observed` e sinaliza `local_stop` para reiniciar o `awatch`;
**não varre os existentes** das pastas recém-adicionadas:
```python
        with get_session(engine) as session:
            current = set(active_folder_paths(session).keys())
        if current != observed:
            logger.info("Conjunto de pastas mudou — reiniciando observação")
            local_stop.set()
            return
```

**O loop externo** `run_watcher` relê as pastas no topo de cada ciclo MAS **não retém o
conjunto anterior** entre iterações, então não sabe quais são NOVAS (linhas 277-280):
```python
    while not stop.is_set():
        with get_session(engine) as session:
            folders = active_folder_paths(session)
        current_paths = set(folders.keys())
```

**Padrão a copiar — assinatura do scan** (D-01 idempotente por dedup, seguro):
```python
async def scan_and_enqueue(engine: Engine, paths: list[Path]) -> ScanResult:
    ...  # rglob → estabiliza → hash → gate → enqueue; ScanResult(enqueued, skipped_duplicates)
```

**Padrão a copiar — scan de startup** (linhas 266-275), o template exato de "varrer
existentes sem derrubar o watcher" que o item 2 deve replicar para o diff:
```python
    with get_session(engine) as session:
        initial_paths = list(active_folder_paths(session).keys())
    if initial_paths:
        try:
            result = await scan_and_enqueue(engine, initial_paths)
            if result.enqueued:
                logger.info("Scan inicial enfileirou %s candidato(s)", result.enqueued)
        except Exception:  # noqa: BLE001 — scan inicial nunca derruba o watcher
            logger.exception("Falha no scan inicial do watcher")
```

**Nota de implementação para o planner (D-01):** o diff `current - observed` precisa ser
PLUMBADO. `_watch_for_reconfig` conhece `observed` e calcula `current`, mas hoje só
sinaliza. Duas opções limpas:
1. Dentro de `_watch_for_reconfig`, ao detectar `current != observed`, varrer
   `current - observed` com o try/except do startup ANTES de `local_stop.set()`; ou
2. Fazer `run_watcher` reter `current_paths` da iteração anterior e, no topo do loop,
   varrer `new = current_paths - previous` (mais alinhado a "diff" da D-01).
Em ambos: chamar `scan_and_enqueue(engine, sorted(new_paths))` envolto no mesmo
try/except `BLE001` do startup. Idempotente por dedup → re-varrer é seguro.

**Item 2 opcional (D-01) — varrer ao (re)ativar via PATCH:** `update_folder`
(`watched_folders.py:189-190`) seta `folder.active = body.active`. Para varrer na
hora ao reativar, dispararia `scan_and_enqueue` para o path da pasta após o commit.
Cuidado: o endpoint é `def` síncrono e `scan_and_enqueue` é async — exigiria
`asyncio`/task ou tornar a rota async. O supervisor (opção principal) já cobre o caso
em ≤5s sem esse acoplamento; tratar o PATCH como reforço opcional.

---

### Item 7 — `backend/app/api/documents.py` `delete_documents` (route, CRUD/cleanup)

**Analog:** o próprio bloco anti-órfão de dedup da função (linhas 555-571) — é onde a
limpeza vive; falta cobrir o hash de BLOCO.

**A associação bloco↔documento (resposta à Discrição do CONTEXT):** é TRIVIAL —
o hash de bloco registrado no gate é IGUAL ao `content_hash` do Document. Em
`pipeline/ingest_stage.py` `_materialize_blocks_to_folder` (linhas 298-309) cada bloco
vira uma entrada SEPARADA no gate keyed pelo próprio hash do bloco:
```python
    for block_hash, (start, end) in zip(block_hashes, ranges, strict=True):
        ...
        session.add(
            IngestedOriginal(
                original_hash=block_hash,          # ← chave do gate == content_hash do Document
                original_filename=block_name,
                source_folder_id=folder_id,
                block_count=0,
            )
        )
        session.commit()
```
E o `block_hash` é exatamente o `content_hash` do Document do bloco (mesmo
`_store_block` → `select(Document).where(Document.content_hash == block_hash)`,
ingest_stage.py:174). Logo: `IngestedOriginal.original_hash == doc.content_hash` para
todo doc vindo de split.

**O gap exato** — a limpeza atual só apaga Jobs por `content_hash` e o `IngestedOriginal`
do ORIGINAL (via `origin_original_id`), NUNCA o `IngestedOriginal` do BLOCO:
```python
        # (4) Jobs órfãos do(s) bloco(s) removido(s).
        for content_hash in block_hashes:
            session.execute(delete(Job).where(Job.original_hash == content_hash))

        # (5) Anti-órfão de dedup: IngestedOriginal sem blocos restantes.
        for origin_id in touched_origin_ids:
            remaining = session.scalar(
                select(func.count(Document.id)).where(Document.origin_original_id == origin_id)
            )
            if remaining:
                continue  # Outro bloco ainda aponta (split) → preserva o original.
            original = session.get(IngestedOriginal, origin_id)
            ...
            session.delete(original)
            session.execute(delete(Job).where(Job.original_hash == original_hash))
```
`block_hashes` já é coletado (linha 543: `block_hashes.append(doc.content_hash)`) — o
material está à mão. A correção (D-02) é, no passo (4) ou um passo (4b), **também apagar
o `IngestedOriginal` cuja `original_hash == content_hash`** (a entrada de gate do bloco),
liberando a re-ingestão:
```python
        for content_hash in block_hashes:
            session.execute(delete(Job).where(Job.original_hash == content_hash))
            # D-02 (item 7): limpa também a entrada de gate do BLOCO (split anti-loop),
            # senão a re-varredura dedupa o arquivo de bloco e não re-ingere.
            session.execute(
                delete(IngestedOriginal).where(IngestedOriginal.original_hash == content_hash)
            )
```
`delete` de `sqlalchemy` já está importado (documents.py:36). Modelo: `IngestedOriginal`
já importado (usado no passo 5). **Cautela:** para docs SEM split o `content_hash` do
bloco normalmente NÃO tem entrada própria no gate (o gate é o `original_hash`), então o
`delete` extra é no-op inofensivo — seguro em ambos os caminhos. Confirmar no
planejamento que o `original_hash` (não-split) não colide com nenhum `content_hash` de
bloco (não colide: hashes distintos por conteúdo).

**Modelo de referência:** `backend/app/models/ingested_original.py` — `original_hash`
`unique=True` é o gate; `duplicate_hits` é o contador exibido na UI.

---

### Item 12 — Setting global novo (config, persistido no .env + cache_clear)

#### `backend/app/config.py` — campo do Settings

**Analog EXATO:** `classify_ai_fallback_enabled` (linhas 169-174). Copiar 1:1, trocando
nome/alias e mantendo `default=False` (D-03 default OFF):
```python
    classify_ai_fallback_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "CLASSIFY_AI_FALLBACK_ENABLED", "classify_ai_fallback_enabled"
        ),
    )
```
→ novo campo (ex.) `approval_mode_enabled: bool = Field(default=False,
validation_alias=AliasChoices("APPROVAL_MODE_ENABLED", "approval_mode_enabled"))`.
Nome exato fica à Discrição (CONTEXT).

#### `backend/app/api/config.py` — par GET/PUT

**Analog EXATO:** o par `ai-fallback` (linhas 70-100). É o MOLDE LITERAL do toggle —
copiar o bloco inteiro trocando o nome:
```python
_AI_FALLBACK_ENV_KEY = "CLASSIFY_AI_FALLBACK_ENABLED"

class AiFallbackOut(BaseModel):
    enabled: bool

class AiFallbackIn(BaseModel):
    enabled: bool

@router.get("/ai-fallback", response_model=AiFallbackOut)
def get_ai_fallback() -> AiFallbackOut:
    return AiFallbackOut(enabled=get_settings().classify_ai_fallback_enabled)

@router.put("/ai-fallback", response_model=AiFallbackOut)
def put_ai_fallback(body: AiFallbackIn) -> AiFallbackOut:
    persist_env_setting(_AI_FALLBACK_ENV_KEY, str(body.enabled))
    get_settings.cache_clear()
    return AiFallbackOut(enabled=get_settings().classify_ai_fallback_enabled)
```
→ replicar como `/config/approval-mode` (chave `_APPROVAL_MODE_ENV_KEY = "APPROVAL_MODE_ENABLED"`).
`persist_env_setting` + `get_settings.cache_clear()` é o padrão estabelecido (escrita
atômica no `.env`, sem reiniciar).

#### `backend/app/queue/worker.py` `enqueue_pending_applications` — o GATE do toggle

**ESTE é o ponto único de auto-apply de alta confiança (decisão 06-04).** A função
varre docs `PROCESSANDO` + `classificado` + `confidence_score >= threshold` e enfileira
`(content_hash, "apply")`. O gate da D-05 entra AQUI: com o toggle LIGADO, **não
enfileirar** — os docs ficam pendentes aguardando aprovação humana via DryRunPage.
```python
def enqueue_pending_applications(session: Session) -> int:
    threshold = get_settings().review_confidence_threshold
    docs = session.scalars(
        select(Document)
        .join(ClassificationResult, ClassificationResult.document_id == Document.id)
        .where(
            Document.state == DocState.PROCESSANDO,
            Document.last_completed_step == CLASSIFIED_STEP,
            ClassificationResult.confidence_score.is_not(None),
            ClassificationResult.confidence_score >= threshold,
            ~Document.id.in_(
                select(AuditLog.document_id).where(AuditLog.status == "done")
            ),
        )
    ).all()
    created = 0
    for doc in docs:
        job = repo.enqueue(session, original_hash=doc.content_hash, step=APPLY_STEP,
                           payload=json.dumps({"content_hash": doc.content_hash}))
        if job is not None:
            created += 1
    return created
```
**Gate a inserir (D-05):** no topo da função, `if get_settings().approval_mode_enabled:
return 0` (curto-circuito — não auto-aplica nada; a trava de confiança/limiar segue
intacta, D-04: docs de baixa confiança continuam indo a EM_REVISAO no `classify_stage`,
fora deste sweep). `get_settings()` já é importado (linha usada para `threshold`).

**Importante (D-04/D-05 — onde NÃO mexer):** o gate vai SÓ no sweep automático
(`enqueue_pending_applications`). `apply_stage` (`automation/stage.py`) NÃO deve ser
gateado — ele é o executor real chamado tanto pelo aprovar manual quanto pelo
auto-apply; gateá-lo quebraria a aprovação manual (D-06: aprovar = apply). O CONTEXT
cita `apply_stage` como contexto, mas o gate pertence ao enqueue.

---

### Item 12 — Frontend (TanStack Query, espelha o par ai-fallback ponta-a-ponta)

#### `frontend/src/types.ts`
**Analog:** `interface AiFallback` (linhas 407-409):
```typescript
export interface AiFallback {
  enabled: boolean
}
```
→ `export interface ApprovalMode { enabled: boolean }`.

#### `frontend/src/lib/api.ts`
**Analog:** `get/putAiFallback` (linhas 177-186):
```typescript
export function getAiFallback(): Promise<AiFallback> {
  return request<AiFallback>('/config/ai-fallback')
}
export function putAiFallback(enabled: boolean): Promise<AiFallback> {
  return request<AiFallback>('/config/ai-fallback', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  })
}
```

#### `frontend/src/hooks/useAttention.ts`
**Analog:** `useAiFallback`/`useSaveAiFallback` (linhas 134-148) + a chave
`AI_FALLBACK_KEY = ['ai-fallback']` (linha 27):
```typescript
export function useAiFallback() {
  return useQuery({ queryKey: AI_FALLBACK_KEY, queryFn: getAiFallback })
}
export function useSaveAiFallback() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => putAiFallback(enabled),
    onSuccess: () => { qc.invalidateQueries({ queryKey: AI_FALLBACK_KEY }) },
  })
}
```

#### `frontend/src/pages/ConfigPage.tsx`
**Analog:** componente `AiFallbackField` (linhas 523-589) — card com `<Switch>` que lê
o GET e salva ao alternar; renderizado dentro de `LeituraTab` ao lado do
`ReviewThresholdField` (linhas 512-515). O toggle de aprovação entra do mesmo jeito
(CONTEXT: "provável ConfigPage, junto de limiar/IA-fallback"). Estrutura a copiar
(card + título + descrição + `<Switch on={enabled} onToggle={toggle}>` + estados
loading/error/saveError).

#### `frontend/src/pages/DryRunPage.tsx` — vira a fila de aprovação (D-06)
**Analog:** a própria página. Já É uma lista origem→destino com seleção por linha
(`toggleSel`/`selected`), aplicar selecionados (`doApply(selected)`) e estados de badge
por situação (`SituationBadge`). D-06 reusa o dry-run/apply existentes:
- **Aprovar (por linha/lote)** = o `doApply` já existente (`useApply` → `apply_stage`).
- **Negar/pular** = NÃO aplicar aquele doc nesta rodada — basta NÃO incluí-lo na seleção
  enviada ao apply (o arquivo fica intocado; D-06: "o move só acontece no aprovar").
  Possível adicionar uma ação por-linha que remove o doc da lista local (`setRows`) sem
  chamar backend — semântica "negar = não aplica agora, doc segue pronto".
- O hook de apply/dry-run vive em `frontend/src/hooks/useAutomations.ts`
  (`useDryRun`/`useApply`/`useUndo`, importado na linha 4) — reusar, não recriar.
- Quando o toggle está LIGADO, esta página é a fila de aprovação (os docs de alta
  confiança NÃO foram auto-aplicados pelo worker, então aparecem aqui como "Prontos");
  com o toggle DESLIGADO, o worker já auto-aplicou e a lista mostra só o que sobra.

---

## Shared Patterns

### Setting global no .env (persist + cache_clear)
**Source:** `backend/app/config.py:271` `persist_env_setting` + `backend/app/api/config.py:88-100`
**Apply to:** item 12 (novo toggle de aprovação).
```python
    persist_env_setting(_AI_FALLBACK_ENV_KEY, str(body.enabled))
    get_settings.cache_clear()
```
Escrita atômica no `.env` + invalidação do `lru_cache` de `get_settings` → o
worker/stage releem sem reiniciar. Mesmo padrão de `review-threshold`.

### Idempotência por dedup torna re-varredura segura
**Source:** `backend/app/ingest/watcher.py:135-202` (`_stabilize_hash_gate_enqueue`)
**Apply to:** item 2 (varrer pasta nova é seguro — gate descarta duplicatas).

### "Nunca perder arquivos" (constraint sagrada)
**Source:** `backend/app/api/documents.py:506-514` (delete só apaga REGISTRO, nunca o arquivo)
**Apply to:** itens 7 e 12. Negar/remover na fila de aprovação NUNCA move nem apaga
arquivo (D-06: o move só no aprovar/aplicar). A limpeza de dedup do delete (item 7) só
libera o gate — o arquivo físico e o blob CAS permanecem.

### Frontend: TanStack Query, texto puro, zero npm novo
**Source:** `frontend/src/hooks/useAttention.ts` (par ai-fallback) + `ConfigPage` `AiFallbackField`
**Apply to:** todo o item 12 frontend.

---

## No Analog Found

Nenhum. Todos os pontos têm analog exato ou são extensão de código existente. Item 12
tem o molde literal do par `ai-fallback` (Fase 10) ponta-a-ponta (Settings → endpoint →
api → hook → field).

---

## Discrepâncias de path do CONTEXT (CONTEXT vs código vivo)

| O que o CONTEXT diz | Realidade no código | Impacto |
|---------------------|---------------------|---------|
| `GET/PUT /config/review-threshold` está em `backend/app/api/documents.py` (canonical_refs, linha 56) | Está em **`backend/app/api/config.py:51-67`** (junto do ai-fallback) | O planner deve apontar o item 12 backend para `api/config.py`, NÃO `api/documents.py`. |
| `enqueue_pending_applications` está em `backend/app/automation/stage.py` (decisions D-05 + canonical_refs linha 55) | Está em **`backend/app/queue/worker.py:364-408`**. `stage.py` só tem `apply_stage`/`dry_run`/`reconcile_orphans` | O gate da D-05 vai no worker, não no stage. `stage.py`/`apply_stage` NÃO deve ser gateado (quebraria a aprovação manual). |
| (implícito) API client do frontend | É **`frontend/src/lib/api.ts`** (não `frontend/src/api/client.ts`) | Caminho correto para as funções `get/putApprovalMode`. |
| `frontend/src/pages/DryRunPage.tsx`, `ConfigPage.tsx` | CONFIRMADOS corretos | — |
| `backend/app/ingest/watcher.py` (`scan_and_enqueue`, `_watch_for_reconfig`/`run_watcher`) | CONFIRMADOS corretos | A varredura do diff precisa de plumbing (o diff `current - observed` não é exposto hoje a quem chama `scan_and_enqueue`) — ver nota de implementação do item 2. |

---

## Metadata

**Analog search scope:** `backend/app/{ingest,api,automation,queue,pipeline,models,config}`,
`frontend/src/{pages,hooks,lib,types}`
**Files scanned:** ~16 (lidos em profundidade: watcher.py, api/config.py, automation/stage.py,
queue/worker.py, api/documents.py, pipeline/ingest_stage.py, models/ingested_original.py,
config.py, ConfigPage.tsx, DryRunPage.tsx, useAttention.ts, lib/api.ts, types.ts,
watched_folders.py)
**Pattern extraction date:** 2026-06-25

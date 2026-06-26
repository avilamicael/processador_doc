---
phase: 11-ux-e-visibilidade-reverter-movidos-dedup-visivel-rotulos-e-f
reviewed: 2026-06-26T14:29:54Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - backend/app/api/documents.py
  - backend/app/ingest/watcher.py
  - frontend/src/App.tsx
  - frontend/src/components/StatusPill.tsx
  - frontend/src/hooks/useDocuments.ts
  - frontend/src/lib/api.ts
  - frontend/src/pages/AutomationsPage.tsx
  - frontend/src/pages/DocumentsPage.tsx
  - frontend/src/types.ts
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-06-26T14:29:54Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 11 entrega visibilidade/UX: endpoint read-only `GET /documents/{id}/audit`, serialização UTC tz-aware (`_as_utc`), `skipped_duplicates` no `/rescan`, fluxo de "Reverter para a origem" por documento, dropdown estrito de campo nas automações e o rótulo derivado "Classificado — pronto".

Os focos de segurança e robustez pedidos estão sólidos:
- **T-11 (audit read-only):** verificado. O endpoint só faz `select(AuditLog)` parametrizado por `document_id: int` (sem string-building de SQL), não escreve, não dispara undo, não constrói paths a partir de input e devolve apenas colunas persistidas. Sem achado de segurança.
- **Serialização UTC (`_as_utc`):** correta — `replace(tzinfo=UTC)` em naive, passthrough em aware; o frontend (`new Date(iso)` + `toLocaleString`) parseia o offset sem regressão.
- **`skipped_duplicates`:** a agregação dos 3 estados (`enqueued`/`duplicate`/`skipped`) está correta; só "duplicate" alimenta o contador.
- **Undo por documento:** restaura do CAS com guard próprio + reabertura defensiva (`_reopen_if_concluded`), idempotente; a UI esconde a seção quando não há `done`, evitando duplo-undo. Sem risco de perda de arquivo.

O defeito central está no **CTA "Aprovar" da linha do documento**, que aciona um endpoint cujo guard de estado o rejeita (409) — a ação principal da nova UI não funciona no range revisado.

## Critical Issues

### CR-01: CTA "Aprovar" da linha chama `/approve`, mas o doc está em PROCESSANDO → 409 silencioso

**File:** `frontend/src/pages/DocumentsPage.tsx:355` (botão "Aprovar") + `frontend/src/hooks/useDocuments.ts` (`useApproveDocument` → `postApprove`) vs `backend/app/api/documents.py:980-983` (guard do `approve_document`)

**Issue:** O CTA "Aprovar" só aparece quando `isClassifiedReady(d.state, d.last_completed_step)` é verdadeiro, ou seja, `state === 'processando' && last_completed_step === 'classificado'`. Ao clicar, `approve.mutate(d.id)` chama `POST /documents/{id}/approve`. Mas o guard do `approve_document` é estrito:

```python
if doc.state != DocState.EM_REVISAO:
    raise HTTPException(status.HTTP_409_CONFLICT,
        "aprovar só é permitido para documentos em EM_REVISAO")
```

Um doc em `processando`+`classificado` **nunca** está em `EM_REVISAO`, então o clique sempre retorna **409**. Pior: a mutação não tem `onError` nem UI de erro, então o usuário não recebe nenhum feedback — o botão sai de "Aprovando…" e volta a "Aprovar" como se nada tivesse acontecido. A ação principal da nova tela está quebrada e falha em silêncio.

**Fix:** O caminho de conclusão para um doc "classificado pronto" é o `apply` (que conclui o doc via worker), não o `approve` (restrito a EM_REVISAO). Trocar a mutação por `useApply()` / `POST /automations/apply` por `document_id`, e adicionar `onError` com mensagem ao usuário:
```ts
onClick={() => apply.mutate(d.id, { onError: () => setRowError('Não foi possível aprovar.') })}
```
Nota: já corrigido fora do range revisado pelo commit `ccfece9` ("CTA 'Aprovar' do doc pronto chama apply, não approve (409)"). Registrado por estar presente em `f8c330677`. Verificar que o `onError`/feedback de falha também foi adicionado.

## Warnings

### WR-01: Mutação `approve`/`apply` compartilhada desabilita o CTA de TODAS as linhas e não mostra erro

**File:** `frontend/src/pages/DocumentsPage.tsx:357-362`

**Issue:** Há uma única instância da mutação (`const approve = useApproveDocument()`) reusada por todas as linhas. O botão usa `disabled={approve.isPending}` — então, enquanto uma linha está pendente, o CTA de **todas** as outras linhas "prontas" fica desabilitado, embora só uma mostre "Aprovando…" (`approve.variables === d.id`). Além disso, não há tratamento de `isError`/`onError`, então qualquer falha (o 409 do CR-01, timeout, etc.) é silenciosa.

**Fix:** Desabilitar só a linha em andamento (`disabled={mut.isPending && mut.variables === d.id}`) e adicionar feedback de erro por linha (estado local de erro ou toast), análogo ao `rescanToast` já existente.

### WR-02: Pílula verde "Classificado — pronto" (token `tratado`) reutiliza a cor de "Concluído" para um arquivo AINDA não movido

**File:** `frontend/src/components/StatusPill.tsx:38-41`

**Issue:** O ramo novo retorna `{ label: 'Classificado — pronto', token: 'tratado' }` — exatamente o mesmo token verde de `concluido: { label: 'Concluído', token: 'tratado' }`. Para o operador, verde sinaliza "tratado/organizado". Mas um doc em `processando`+`classificado` **ainda não teve a automação aplicada**: o arquivo continua na pasta de origem, não foi renomeado nem movido. Usar a mesma cor de "concluído" pode levar o usuário a crer que o arquivo já foi organizado, contrariando o core value do projeto ("não confiar cegamente / não perder arquivo"). É decisão de design documentada (D-10), mas o reuso exato do token verde de conclusão é ambíguo.

**Fix:** Diferenciar visualmente o "pronto, aguardando ação" do "concluído" — por exemplo um token distinto (ou variação de cor/contorno) para "Classificado — pronto", reservando o verde sólido `tratado` ao estado em que o arquivo de fato já foi movido/renomeado.

### WR-03: "Pré-visualizar" navega ao dry-run global sem escopar o documento clicado

**File:** `frontend/src/pages/DocumentsPage.tsx:347` (`onClick={() => onNavigate?.('dryrun')}`)

**Issue:** O CTA "Pré-visualizar" da linha apenas troca a página para `'dryrun'`, sem carregar/filtrar o documento específico (`d.id`). O usuário sai do contexto da linha e cai na tela de dry-run geral, tendo que reencontrar o documento manualmente — a expectativa do botão "Conferir origem → destino antes de aplicar" (title) é ver o destino daquele doc.

**Fix:** Passar o `document_id` na navegação (ex.: `onNavigate?.('dryrun', d.id)` com a página de dry-run lendo o id de querystring/estado) e pré-selecionar/filtrar o doc, ou abrir a pré-visualização do destino inline no detalhe.

## Info

### IN-01: Toast de varredura aparece mesmo com 0/0 ("0 novos enfileirados, 0 pulados por já existirem")

**File:** `frontend/src/pages/DocumentsPage.tsx:93-104`

**Issue:** `runRescan` sempre seta o toast no `onSuccess`, inclusive quando `enqueued === 0 && skipped_duplicates === 0`. A mensagem "0 novos enfileirados, 0 pulados por já existirem" é neutra mas pouco informativa. É intencional (provar que a varredura rodou), apenas registro.

**Fix:** Opcional — quando ambos forem 0, exibir algo como "Varredura concluída — nada novo encontrado".

### IN-02: `get_document_audit` expõe registros `intent`/`undone` à UI, que só consome `done`

**File:** `backend/app/api/documents.py:735-758` + `frontend/src/pages/DocumentsPage.tsx:470` (`doneOps = audit?.items.filter(... 'done')`)

**Issue:** O endpoint retorna todos os status (`intent`, `done`, `undone`, `undone_from_cas`), mas o frontend filtra apenas `done` para a seção "Operações aplicadas". Não é bug (read-only, paths persistidos), mas paga payload e expõe estados intermediários sem uso atual.

**Fix:** Opcional — se a UI nunca usará `intent`, filtrar no backend (`status in ('done','undone','undone_from_cas')`) para reduzir superfície e payload.

---

_Reviewed: 2026-06-26T14:29:54Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

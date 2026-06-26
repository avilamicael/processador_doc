---
phase: 12-robustez-de-ingest-o-e-modo-de-aprova-o
reviewed: 2026-06-26T14:31:29Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - backend/app/api/config.py
  - backend/app/api/documents.py
  - backend/app/config.py
  - backend/app/ingest/watcher.py
  - backend/app/queue/worker.py
  - frontend/src/hooks/useAttention.ts
  - frontend/src/lib/api.ts
  - frontend/src/pages/ConfigPage.tsx
  - frontend/src/pages/DryRunPage.tsx
  - frontend/src/types.ts
findings:
  critical: 0
  warning: 4
  info: 2
  total: 6
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-06-26T14:31:29Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Revisão adversarial das mudanças da Phase 12 (robustez de ingestão + modo de
aprovação). As quatro áreas-foco foram tracejadas até suas dependências:

- **Varredura de pasta recém-ativada (watcher D-01):** `_scan_new_active_folders`
  diffa `current - previous`, reusa `scan_and_enqueue` (idempotente por dedup de
  hash) e nunca propaga exceção. `previous_paths` avança em todos os ramos, sem
  vazamento nem re-varredura do conjunto inicial. Lógica de diff correta. Resta
  uma janela scan→awatch herdada do startup (WR-02).
- **Gate de dedup de bloco no delete (D-02):** confirmei pelo modelo de ingestão
  (`ingest_stage.py` passo A da materialização) que cada bloco materializado tem
  uma `IngestedOriginal(original_hash == block.content_hash)` própria. O delete
  extra remove exatamente esse gate; por content-addressing, colisão de hash
  implica conteúdo idêntico (re-ingestão equivalente é aceitável). Nenhum
  `Document` referencia o gate do próprio bloco via FK → remoção segura. Arquivo
  e blob CAS preservados. Constraint "nunca perder arquivos" mantida. Correto.
- **Gate do modo de aprovação no enqueue (D-05):** curto-circuito no topo de
  `enqueue_pending_applications` retorna 0; extract/classify seguem; a trava de
  confiança (`classify_stage`) intacta; gate ausente em `apply_stage` (D-06
  preservado). Correto. Ressalvas de timing/processo: WR-01 e WR-03.
- **DryRunPage negar/pular (D-06):** `denyDoc` é puramente local (`setRows`/
  `setSelected`), não chama backend, não toca arquivo. Correto.

Nenhum problema CRITICAL/BLOCKER. Quatro WARNINGs (3 de timing/ambiente, 1 de
mensagem enganosa) e dois INFO.

## Warnings

### WR-01: Toggle de modo de aprovação fica obsoleto no worker fora-de-processo (modo servidor/arq)

**File:** `backend/app/api/config.py:137` e `backend/app/queue/worker.py:391`
**Issue:** `put_approval_mode` persiste no `.env` e chama
`get_settings.cache_clear()` para invalidar o `lru_cache`. Isso só limpa o cache
do **processo que atende a API**. No modo padrão (fila in-process SQLite,
CLAUDE.md) API e worker compartilham o processo → funciona. Mas no modo servidor
documentado (arq + Redis em container separado), o sweep
`enqueue_pending_applications` roda em **outro processo**, cujo `lru_cache` de
`get_settings` não é invalidado pelo cache_clear da API. Resultado: ligar o
modo de aprovação NÃO surte efeito no worker até ele reiniciar — documentos de
alta confiança continuariam sendo auto-aplicados apesar do toggle ON, violando a
expectativa do "modo de teste". Mesma limitação já existe nos tunables vizinhos
(threshold, ai-fallback), mas para o modo de aprovação o efeito é mover/renomear
arquivos do cliente sem aprovação — impacto maior.
**Fix:** Ler o estado direto do banco/`.env` por ciclo de sweep em vez de confiar
no cache de processo, ou invalidar o cache no worker a cada ciclo ocioso. Ex.:

```python
# worker.py — reler env por ciclo, sem depender do cache_clear da API
def enqueue_pending_applications(session: Session) -> int:
    get_settings.cache_clear()  # garante leitura fresca neste processo
    if get_settings().approval_mode_enabled:
        return 0
    ...
```
Ou documentar explicitamente que, no modo servidor, alternar o toggle exige
reiniciar o worker.

### WR-02: Janela scan→awatch deixa arquivo de pasta recém-ativada não ingerido até reinício

**File:** `backend/app/ingest/watcher.py:289` (chamada) e `:319-340`
**Issue:** `_scan_new_active_folders` varre os arquivos JÁ presentes na pasta
nova, e só DEPOIS o `awatch(*current_paths)` começa a observar (linha 308). Um
arquivo escrito na pasta nova **entre** o fim do scan e o início do `awatch` não
é capturado por nenhum dos dois: o scan já passou e o `awatch` só reporta
mudanças posteriores ao seu start. Como a pasta deixa de ser "nova" no próximo
ciclo (`previous_paths = current_paths`), ela não é re-varrida — o arquivo fica
preso até um restart ou re-ativação manual. A janela é curta (ms) e o padrão é
herdado do scan de startup, mas, dado o constraint do projeto ("nunca perder /
confiável"), um arquivo silenciosamente não processado é relevante.
**Fix:** Inverter a ordem (iniciar o `awatch` e então varrer) ou re-varrer uma
vez logo após o `awatch` estabilizar; alternativamente, manter um sinal de
"varredura suja" que force um re-scan se o conjunto de pastas mudou durante o
ciclo. No mínimo, garantir que o botão "forçar varredura" (`/rescan`) cubra esse
caso para o usuário.

### WR-03: Jobs de apply já enfileirados antes de ligar o toggle escapam do gate

**File:** `backend/app/queue/worker.py:391`
**Issue:** O gate impede a CRIAÇÃO de novos jobs de apply, mas não cancela jobs
de apply já enfileirados (e ainda não consumidos) antes de o toggle ser ligado.
Como o gate vive só no enqueue e nunca em `apply_stage` (D-06), um doc de alta
confiança cujo job de apply foi enfileirado microssegundos antes do flip ON ainda
será auto-aplicado (move/renomeia) apesar de o modo de aprovação estar ligado.
Para o "modo de teste" isso significa que ligar o switch não garante que NADA
mais se mova — alguns docs no voo podem escapar.
**Fix:** Decisão de produto. Se o contrato é "ligou = nada se move sozinho",
remover os jobs de apply pendentes/não-iniciados ao persistir o toggle ON
(`DELETE FROM jobs WHERE step='apply' AND status IN ('pending', ...)`), ou
documentar explicitamente que jobs já no voo concluem. Hoje o comportamento é
silencioso.

### WR-04: Mensagem do estado vazio contradiz o modo de aprovação ligado

**File:** `frontend/src/pages/DryRunPage.tsx:351-354`
**Issue:** Com `approvalEnabled === true` e nenhuma linha pronta, o estado vazio
ainda exibe "Documentos de alta confiança são aplicados automaticamente; os
demais aguardam revisão." — exatamente o oposto do que o modo de aprovação faz
(no modo ON, alta confiança NÃO é auto-aplicada; tudo aguarda aprovação aqui).
Mensagem enganosa no estado em que mais importa orientar o usuário.
**Fix:** Condicionar o texto ao `approvalEnabled`:

```tsx
<p ...>
  {approvalEnabled
    ? 'Nenhum documento aguardando aprovação no momento.'
    : 'Documentos de alta confiança são aplicados automaticamente; os demais aguardam revisão.'}
</p>
```

## Info

### IN-01: Degradação silenciosa quando o GET /config/approval-mode falha na DryRunPage

**File:** `frontend/src/pages/DryRunPage.tsx:90-91`
**Issue:** `approvalEnabled = approvalMode.data?.enabled ?? false`. Se o GET
falhar enquanto o backend está com o modo ON, a página renderiza no modo normal
(sem coluna Aprovar/Negar) e o worker continua gateando o auto-apply. O usuário
ainda pode usar "Aplicar selecionados", então não há quebra funcional, mas a UI
some com as ações de aprovação sem nenhum aviso. Considerar um fallback visível
(ex.: manter as ações ou exibir um aviso de "estado do modo desconhecido").
**Fix:** Tratar `approvalMode.isError` mostrando um aviso discreto em vez de
assumir OFF silenciosamente.

### IN-02: Backlog acumulado é auto-aplicado em massa ao desligar o toggle

**File:** `backend/app/queue/worker.py:391`
**Issue:** Enquanto o modo de aprovação fica ON, docs de alta confiança se
acumulam em `PROCESSANDO`/`classificado`. Ao desligar o toggle, o próximo ciclo
ocioso do worker varre todos eles e enfileira apply em lote (auto-aplicação em
massa). É o comportamento de restauração esperado (D-04), mas pode surpreender:
desligar o switch dispara movimentação de muitos arquivos de uma vez.
**Fix:** Apenas documentar/avisar no toggle da ConfigPage ("ao desligar, os
documentos acumulados serão aplicados automaticamente").

---

_Reviewed: 2026-06-26T14:31:29Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

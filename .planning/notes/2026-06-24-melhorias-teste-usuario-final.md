# Melhorias — Teste como usuário final (rodada de 2026-06-24)

> **Propósito:** lista corrida de achados enquanto o Micael testa o sistema como
> usuário final. Cada item descreve o problema, o estado atual (com evidência no
> código), a melhoria proposta e uma estimativa de escopo. **No fim desta rodada,
> consolidar em um novo plano GSD** (`/gsd:quick` ou fase, conforme o tamanho).
>
> Status legenda: 🔴 aberto · 🟡 em discussão · 🟢 planejado (virou plano GSD)

---

## Item 1 — Recuperar/reverter documentos já movidos pela tela (lacuna de UX) 🔴

**Sintoma / pergunta do usuário:** depois que uma automação move/renomeia um
documento, o usuário **não consegue, pela tela, ver os documentos movidos (e para
onde foram) nem reverter para a origem** mais tarde.

**Estado atual (capacidade existe no backend, falta na UI):**

- ✅ **Motor de recuperação completo no backend:**
  - CAS imutável (`backend/app/storage/cas.py`): toda ingestão **copia** o original
    para `%ProgramData%\ProcessadorDocumentos\cas` por hash SHA-256; original nunca
    é tocado (D-07); blobs mantidos para sempre (D-08).
  - Audit write-ahead (`backend/app/models/audit_log.py`): grava intenção antes de
    tocar o disco (`status` intent→done→undone/undone_from_cas, `source_path`,
    `dest_path`, `run_id`, `content_hash`).
  - Undo (`backend/app/automation/undo.py` + `POST /automations/undo`): reverte por
    **`run_id` (lote)** OU por **`document_id` (um doc, a qualquer momento)**;
    restaura do CAS se o destino sumiu/mudou; reabre o doc (CONCLUIDO→PROCESSANDO).
- ❌ **Frontend só expõe o undo do lote recém-aplicado, na mesma sessão:**
  - `frontend/src/pages/DryRunPage.tsx`: o `undoRunId` é `useState` (linha ~93) →
    **perde no reload / ao sair da tela**. Não há como desfazer aquele lote depois.
  - `DocumentsPage.tsx`: **não mostra o destino** do arquivo nem tem botão de
    reverter (é só leitura de base + classificação).
  - `AutomationsPage.tsx`: **sem histórico** de aplicações e sem undo.
  - Não existe nenhuma tela persistente "documentos movidos → reverter para origem".

**Melhoria proposta:**
1. **Detalhe do documento concluído**: mostrar origem→destino (lendo do audit) e um
   botão **"Reverter para a origem"** → `POST /automations/undo` com `document_id`.
2. (Opcional) **Histórico de automações aplicadas** (por `run_id`) com reverter em lote.
3. **Backend novo**: um `GET` para listar o que foi aplicado a um documento
   (origem/destino/status/run_id do audit) para alimentar a tela — **ainda não existe**.

**Escopo estimado:** `/gsd:quick` (backend novo: endpoint de leitura do audit por doc;
frontend: detalhe + botão reverter; opcional: histórico). Capacidade já existe — é
sobretudo expor na UI.

**Relacionado:** constraint do projeto "operações reversíveis, nunca causar perda
(quarentena + dry-run + log/desfazer)". Ver decisões D-01/D-03/D-07/D-08, AUT-04/AUT-05.

---

## Item 2 — Pasta cadastrada antes de existir: arquivos pré-existentes não são varridos 🔴

**Sintoma (relato do usuário):** criou um apontamento (pasta monitorada) no sistema,
mas a pasta ainda não existia; depois criou a pasta manualmente e colocou documentos
dentro — e **não foi processado** (nada apareceu).

**Causa raiz (confirmada no código):**
1. O cadastro **aceita** uma pasta inexistente por design — `backend/app/api/watched_folders.py:60`
   (`_normalize_path`: "Um path AINDA inexistente é aceito").
2. Enquanto não existe, o watcher a ignora — `watcher.py:94` (`active_folder_paths` pula
   o que não é diretório).
3. Quando a pasta passa a existir, o supervisor detecta a mudança do conjunto (a cada 5s)
   e **reinicia o `awatch`** incluindo a nova pasta — `watcher.py:299`. **Mas o `awatch`
   só capta eventos FUTUROS:** os arquivos já presentes quando o watch ataca **não geram
   evento** → ficam de fora.
4. A varredura de arquivos JÁ EXISTENTES (`scan_and_enqueue` via `rglob`) só roda no
   **startup** (`watcher.py:234`) e no **`POST /rescan`** (`documents.py:759`). **NÃO** roda
   quando uma pasta nova aparece em runtime.

**Workaround atual:** aba Documentos → **"Forçar varredura"** (`/rescan`) recalcula as
pastas ativas e varre os arquivos já presentes. Reiniciar o servidor também resolve.

**Correção proposta:** no supervisor de reconfiguração (`_watch_for_reconfig` /
`run_watcher`), quando o conjunto de pastas ativas mudar, disparar `scan_and_enqueue`
sobre as pastas **recém-adicionadas** (diff `current - observed`) antes/depois de reatar
o `awatch` — fechando a lacuna e ficando consistente com o scan de startup. Idempotente
por dedup, então é seguro. (Considerar também: varrer ao (re)ativar uma pasta via PATCH.)

**Escopo estimado:** `/gsd:quick` (backend só; ~1 mudança no `watcher.py` + teste cobrindo
"pasta criada depois com arquivos pré-existentes é varrida sem /rescan manual").

---

<!-- PRÓXIMOS ACHADOS: adicionar como "## Item N — <título> <status>" abaixo, mesmo formato. -->

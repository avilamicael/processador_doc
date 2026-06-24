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

## Item 3 — Tornar o dedup (duplicata ignorada) explícito e rastreável na UI 🔴

**Sintoma (observado no teste):** colocar um arquivo de conteúdo IDÊNTICO a um já
ingerido numa pasta (ex.: o mesmo `exames_duda.pdf` numa pasta nova) e clicar em
"Forçar varredura" aparenta "não fazer nada" — o arquivo é corretamente pulado pelo
dedup (D-10), mas o usuário não tem feedback claro disso e acha que está quebrado.
(No teste: `duplicates-count` em 46; o `/rescan` viu o arquivo e o descartou por hash.)

**Comportamento correto, mas pouco visível.** O dedup por `content_hash` é intencional
(`watcher.py:155` — incrementa `IngestedOriginal.duplicate_hits` e NÃO enfileira; D-10).
O problema é só de VISIBILIDADE/UX.

**Estado atual (o que já existe):**
- Apenas um contador AGREGADO global: `GET /documents/duplicates-count` → chip
  "{N} duplicados ignorados" em `frontend/src/pages/DocumentsPage.tsx:302-308`.
- `DryRunPage.tsx:203` mostra "Duplicatas puladas" (também agregado, no contexto do dry-run).
- **Não há registro por-ocorrência:** não se sabe QUAL arquivo foi pulado, de QUAL pasta,
  QUANDO, nem com QUAL documento/original ele colide. O skip não gera linha/evento exposto.
- `POST /rescan` retorna só `enqueued` — não informa quantos foram pulados por duplicata.

**Melhoria proposta:**
1. **Win barato:** `/rescan` retornar também `skipped_duplicates` (e o frontend mostrar um
   toast pós-varredura: "X novos enfileirados, Y pulados por já existirem").
2. **Rastreável:** persistir/expor eventos de skip por duplicata (caminho, pasta, timestamp,
   hash e o documento/original correspondente) — hoje só existe o contador em
   `IngestedOriginal.duplicate_hits`, sem evento por-ocorrência (precisa de backend novo).
3. **UI:** uma visão/filtro "Duplicatas" listando os arquivos pulados com o motivo e link
   para o documento que já existe.

**Escopo estimado:** `/gsd:quick` (backend: enriquecer retorno do /rescan + opcional log
por-evento de dedup; frontend: toast + opcional lista/filtro de duplicatas).

**Relacionado:** Item 2 (varredura de pasta nova) — são coisas distintas: Item 2 é não
varrer; Item 3 é varrer, pular por duplicata e não deixar isso claro.

---

<!-- PRÓXIMOS ACHADOS: adicionar como "## Item N — <título> <status>" abaixo, mesmo formato. -->

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

## Item 4 — Condição "Valor de campo": trocar o nome do campo (texto livre) por seletor 🔴

**Sintoma (relato do usuário):** na automação, bloco "Quando rodar" → condição
**"Valor de campo"**, não fica claro como funciona — em parte porque o **nome do campo
é digitado à mão**.

**Como funciona hoje (correto, mas confuso):** a condição "Valor de campo" (`field`)
compara um **campo extraído do documento** (template + IA) com um valor, via operador
(`é`/`contém`/`>`/`<`). Avaliação em `backend/app/automation/rules.py:72` contra os
campos VÁLIDOS do doc (`automation/stage.py:204`); `é`/`contém` case-insensitive;
`>`/`<` numérico quando ambos os lados são número, senão texto.

**A aspereza de UX:** o nome do campo é um **`<input>` de texto livre** com placeholder
"nome do campo" — `frontend/src/pages/AutomationsPage.tsx:657-662`. O usuário precisa
**digitar o nome EXATO** do campo do template, de memória. Se errar (typo, nome que não
existe), a condição **nunca casa e não há aviso** (campo ausente → falso silencioso,
`rules.py:86-88`). Existe um painel "Campos do template" como referência na página
(`AutomationsPage.tsx:547`), mas o input não está ligado a ele.

**Melhoria proposta:**
1. Trocar o texto livre por um **`<select>`/autocomplete dos campos do template**
   referenciado (já dá pra saber o template via condição "Tipo de documento" ou o
   template selecionado; os campos já são buscados — ver painel "Campos do template").
2. Se nenhum template estiver fixado na automação, oferecer autocomplete com os campos
   conhecidos dos templates + permitir digitar (fallback), mas **validar/avisar** quando
   o nome não casar com nenhum campo conhecido.
3. (Opcional) no dry-run, sinalizar quando uma condição "Valor de campo" referencia um
   campo inexistente/ não extraído (hoje falha silenciosa).

**Escopo estimado:** `/gsd:quick` (frontend principalmente: select/autocomplete +
validação no form; reaproveita a busca de campos do template que já existe).

---

## Item 5 — Classificação por sinais é frágil (E exato) + faltam ferramentas no construtor 🔴

**Sintoma (teste real):** notas fiscais (DANFE) cadastradas foram TODAS para
**quarentena** — o template "Notas Fiscais" não casou, mesmo sendo claramente uma NF-e.

**Diagnóstico (confirmado extraindo o texto real do PDF e testando os 8 sinais):**
o matcher (`backend/app/classification/matcher.py:118-149`) faz **substring
case-insensitive** e exige que **TODAS as condições do grupo casem (E lógico)**. O
template tinha 8 sinais num único grupo; 5 casaram, mas **3 não existem literalmente**
no texto extraído (`extraction.full_text`), derrubando o grupo inteiro → quarentena:
- `DOCUMENTO AUXILIAR DE NOTA FISCAL ELETRÔNICA` → texto real é `DOCUMENTO AUXILIAR DA`
  + quebra de linha + `NOTA FISCAL ELETRÔNICA` ("DA" ≠ "DE" **e** quebra de linha no meio).
- `NATUREZA DA OPERAÇÃO` → texto real é `NATUREZA DE OPERAÇÃO` ("DE" ≠ "DA").
- `DATA EMISSÃO` → não existe; a nota traz `EMISSÃO:` (e "DATA DE RECEBIMENTO").
(Acento NÃO foi o problema — o matcher é case-insensitive e os acentos do template estão
corretos; o que falha é a literalidade exata + o E-de-tudo.)

**Observação de design:** o matcher é cheio-fechado por escolha (sinal local de custo 0;
IA só desempata "ambiguous", não classifica quando nenhum casa → vai pra quarentena).
Isso é intencional, mas combinado com "E exato de N sinais" vira uma armadilha de UX: o
usuário escreve sinais plausíveis e um único off-by-uma-palavra manda tudo pra quarentena.

**Melhorias propostas:**
1. **Testar sinais contra um documento de exemplo** no construtor de Templates: mostrar
   quais sinais casam/falham contra o texto extraído de um PDF de amostra (exatamente o
   diagnóstico feito à mão aqui). Mata 90% desse problema na origem.
2. **Casamento mais tolerante (opção):** permitir "casar N de M sinais" (limiar) em vez de
   exigir todos; e/ou modo de normalização (ignorar pontuação/quebras de linha, colapsar
   espaços; opcional ignorar acentos). Hoje é tudo-ou-nada por grupo.
3. (Avaliar) deixar a IA **classificar** quando o matcher local não casa nenhum template
   (antes de quarentena), não só desempatar ambíguos — alinhado à expectativa do usuário
   de "a IA lê e identifica". Decisão de custo/produto a discutir.

**Escopo estimado:** misto. (1) frontend + 1 endpoint backend de "preview de sinais";
(2) backend no matcher (limiar N-de-M + normalização) + UI; (3) mudança de política de
classificação (discutir antes). Provável fase pequena, não um quick só.

**Workaround imediato (não aplicado — usuário vai corrigir depois):** enxugar o template
"Notas Fiscais" para os sinais robustos que JÁ casaram e identificam DANFE com segurança:
`DANFE` + `CHAVE DE ACESSO` + regex 44 dígitos.

---

## Item 6 — Falta "reprocessar/reclassificar automático" após editar um template 🔴

**Sintoma (teste real):** usuário ajustou o template (sinais agora corretos — verificado:
o template "Notas Fiscais" com `DANFE` + `CHAVE DE ACESSO` + regex 44 díg. CASA com o
texto da nota), mas os documentos **continuam em `quarentena`**. Quarentena é terminal e
**editar o template não dispara reprocessamento**.

**Estado atual:** as únicas saídas da quarentena são (`backend/app/api/documents.py`):
- `POST /documents/{id}/reclassify` → **exige apontar um template na mão** (D-09); e
- `POST /documents/{id}/retry` → só para estado `FALHA`, não `QUARENTENA`.
Não existe ação "re-rodar a detecção automática" (matcher) num doc já classificado/
quarentenado. Para quem está AJUSTANDO templates, isso obriga a re-ingerir o arquivo só
pra testar — fluxo ruim.

**Melhoria proposta:** ação "Reprocessar/Reclassificar automaticamente" (por doc e em
lote) que re-roda matcher→(IA)→filler com os templates ATUAIS, sem forçar template.
Aplicável a `QUARENTENA` (e talvez `CONCLUIDO`/`EM_REVISAO` sob confirmação). Reaproveita
o `classify_stage` (já recarrega templates do DB). Botão na aba Documentos / "Precisam de
atenção".

**Escopo estimado:** `/gsd:quick` (backend: endpoint reprocess sem template + transição
QUARENTENA→PROCESSANDO + requeue classify; frontend: botão). Relacionado ao [[#item-5]]
(tuning de templates) e à tela de "testar sinais".

---

## Item 7 — "Remover + forçar varredura" NÃO re-ingere arquivos vindos de split 🔴

**Sintoma (confirmado ao vivo):** removi 2 docs em quarentena (`POST /documents/delete` →
`deleted:2`) e cliquei em forçar varredura → `enqueued: 0`. O `duplicates-count` subiu
(46 → 53): os arquivos foram **vistos e pulados como duplicata**, não re-ingeridos.

**Causa (split anti-loop):** os arquivos eram blocos de split (`<chave>_p1.pdf`, pasta com
`split_to_files=true`). A materialização do split registra o **hash do BLOCO** no gate de
dedup (anti-loop, `watcher.py`) — uma entrada separada da do original. A remoção
(`POST /documents/delete`, quick 260624-far) limpa o `IngestedOriginal` que o Document
aponta (o do original), **mas não a entrada de dedup do bloco** → a re-varredura dedupa o
bloco e não re-ingere. Resultado: para documentos com split, "remover + re-varrer" **não
faz nada, silenciosamente**.

**Melhorias propostas (a discutir qual):**
1. A limpeza de dedup da remoção deve cobrir também o(s) **hash(es) de bloco** associados
   ao documento removido (não só o `original_hash`), liberando a re-ingestão.
2. E/ou uma ação **"Reprocessar este arquivo"** que ignora o gate de dedup para um
   caminho específico (re-ingere mesmo sendo "conhecido").
3. Tornar visível que o arquivo foi pulado por dedup (liga com [[#item-3]]).

**Nota:** combina com o [[#item-6]] — se existisse "reprocessar automático" no doc, o
usuário nem precisaria deletar+re-ingerir pra testar template novo (evitaria cair neste
gap). Item 6 provavelmente resolve o caso de uso; Item 7 é a correção da mecânica de
dedup/remoção em si.

**Escopo estimado:** `/gsd:quick` (backend: ajuste na limpeza de dedup da remoção +/ou
flag de "force re-ingest"; testes cobrindo cenário split).

---

<!-- PRÓXIMOS ACHADOS: adicionar como "## Item N — <título> <status>" abaixo, mesmo formato. -->

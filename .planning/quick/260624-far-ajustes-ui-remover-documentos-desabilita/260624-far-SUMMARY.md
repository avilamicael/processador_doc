---
phase: quick-260624-far
plan: 01
subsystem: ui-ux + api-documentos + watcher
tags: [ui, remover-documento, watcher-status, config-em-breve, header]
requires:
  - "GET /documents, POST /rescan (api/documents.py)"
  - "scan_and_enqueue (ingest/watcher.py)"
  - "Sidebar/Header/DocumentsPage/ConfigPage (frontend)"
provides:
  - "POST /documents/delete (remoção em lote, só registro)"
  - "GET /watcher/status (active/active_folder_count/last_scan_at)"
  - "watcher.get_last_scan_at() + LAST_SCAN_AT (rastreio da última varredura)"
  - "useDeleteDocuments / useWatcherStatus (hooks frontend)"
  - "Sidebar com status real do watcher; Header com busca/sino desabilitados"
affects:
  - "api/documents.py, api/watcher_status.py, main.py, ingest/watcher.py"
  - "Sidebar.tsx, Header.tsx, DocumentsPage.tsx, ConfigPage.tsx, App.tsx, Icon.tsx"
tech-stack:
  added: []
  patterns:
    - "Remoção PURAMENTE de banco (nunca os/shutil/unlink) — constraint forte de não-perda"
    - "Anti-órfão: limpa Jobs do bloco + IngestedOriginal sem blocos restantes (libera gate de dedup)"
    - "Rota POST /documents/delete registrada ANTES de /documents/{id} (evita conversor int → 422)"
    - "LAST_SCAN_AT como estado de módulo (desacopla watcher do app FastAPI)"
    - "Switch sem prop disabled → wrapper pointer-events:none + opacity para desabilitar"
key-files:
  created:
    - backend/app/api/watcher_status.py
    - backend/tests/test_api_watcher_status.py
    - frontend/src/hooks/useWatcherStatus.ts
  modified:
    - backend/app/api/documents.py
    - backend/app/main.py
    - backend/app/ingest/watcher.py
    - backend/tests/test_api_documents.py
    - frontend/src/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/hooks/useDocuments.ts
    - frontend/src/pages/DocumentsPage.tsx
    - frontend/src/pages/ConfigPage.tsx
    - frontend/src/components/Sidebar.tsx
    - frontend/src/components/Header.tsx
    - frontend/src/components/Icon.tsx
    - frontend/src/App.tsx
decisions:
  - "Remover documento apaga SÓ o registro (Document + cascata + Jobs/IngestedOriginal órfãos); arquivo físico do cliente nunca é tocado (CLAUDE.md)"
  - "Ao remover o último bloco de um original, o IngestedOriginal e seus Jobs são apagados → gate de dedup liberado (re-ingestão possível, comportamento esperado)"
  - "Regras de separação e Integrações desabilitadas com aviso 'Em breve — versão 2'; Leitura desabilita só os mocks e mantém o Limiar de confiança funcional"
metrics:
  duration: ~14 min
  completed: 2026-06-24
---

# Quick 260624-far: Ajustes de UI (remover documentos, desabilitar mocks, status do watcher) Summary

Remoção em lote de documentos que apaga apenas o registro no app (nunca o arquivo físico), status real do watcher na Sidebar, e tirada de elementos mock/falsos da interface (busca/sino do Header, abas Regras/Integrações e controles de OCR) — mantendo funcional o Limiar de confiança.

## O que foi construído

### Task 1 — Backend (TDD: RED → GREEN)
- **POST /documents/delete** (`api/documents.py`): remove em lote SÓ o registro. Para cada id existente: captura `content_hash`/`origin_original_id`, `session.delete(doc)` (cascata limpa extraction/classification/filled_fields/usages/audit_logs/pages), limpa Jobs órfãos do bloco, e — após flush — apaga o `IngestedOriginal` (e seus Jobs) quando nenhum outro bloco aponta para ele. ids inexistentes são ignorados; lista vazia → `{deleted:0}`. NUNCA importa/chama `os`/`shutil`/`Path.unlink`. Registrada ANTES de `/documents/{document_id}` (evita o conversor int → 422).
- **GET /watcher/status** (`api/watcher_status.py`, novo): `{active, active_folder_count, last_scan_at}`. `active` deriva de `app.state.stop_event` (fallback True em testes); `active_folder_count` = `WatchedFolder` com `active=True`; `last_scan_at` via `watcher.get_last_scan_at()`.
- **Rastreio da última varredura** (`ingest/watcher.py`): `LAST_SCAN_AT` (módulo) + `get_last_scan_at()`; `scan_and_enqueue` grava `datetime.now(UTC)` ao final (inclusive com 0 candidatos). Mantém o watcher desacoplado do app FastAPI.
- Router registrado em `main.py` antes do catch-all do frontend.

### Task 2 — Frontend (build verde)
- `types.ts`: `WatcherStatus`. `api.ts`: `postDeleteDocuments`, `getWatcherStatus`. `useDocuments.ts`: `useDeleteDocuments` (invalida `['documents']`/`['duplicates-count']`). `useWatcherStatus.ts` (novo): polling 8s, sem flicker.
- **DocumentsPage**: botão "Remover (N)" destrutivo, visível só com seleção; modal de confirmação reforça "os arquivos originais NÃO são apagados nem movidos"; no sucesso chama `onClearSel` (App.tsx) e fecha. `App.tsx`: `clearSel` + prop `onClearSel`.
- **Sidebar**: status dinâmico (título ativo/inativo, dot por token, `N pasta(s) · varredura há …` via helper relativo pt-BR; `verificando…`/`—` em loading/erro).
- **Header**: busca e sino desabilitados (esmaecidos, `title="em breve"`), `notif-dot` removido.
- **ConfigPage**: Regras e Integrações com banner "Em breve — versão 2", badge "em breve" nas abas, conteúdo não-interativo (`pointer-events:none` + `opacity`); botão "Nova regra" disabled. Leitura desabilita só os mocks (selects/slider/2 switches com tag "em breve") e mantém o `ReviewThresholdField` 100% funcional.
- `Icon.tsx`: ícone `trash`.

## Deviations from Plan

Nenhuma. O plano foi executado exatamente como escrito (ajustes mínimos esperados: criação do ícone `trash`, ausente no conjunto, para o botão Remover; e troca de `timezone.utc` por `datetime.UTC`/`UTC` pela convenção do projeto via ruff — não altera comportamento).

## Resultados de testes

- **Backend** (`uv run pytest -q`): **431 passed** (24 warnings pré-existentes, não relacionados). Os 12 testes novos (8 de delete em `test_api_documents.py`, 4 em `test_api_watcher_status.py`) passam; nenhuma regressão na suíte existente.
- **Verificação anti-FS** (`grep -nE "unlink|shutil|os\.remove" backend/app/api/documents.py | grep -v '^#'`): só casa a linha de DOCSTRING (`não importa/chama os/shutil/Path.unlink`) — nenhuma chamada real de FS.
- **Frontend** (`npm run build`): **verde** (tsc -b + vite build; 83 módulos, sem erros de tipo).
- **ruff** nos arquivos tocados: All checks passed.

## TDD Gate Compliance

Plano com Task 1 `tdd="true"`. Gates no git log:
- RED: `532e971 test(quick-260624-far): falhando p/ DELETE em lote + GET /watcher/status` (12 testes falhando antes da implementação).
- GREEN: `ad8b534 feat(quick-260624-far): DELETE em lote (só registro) + GET /watcher/status`.
- REFACTOR: não necessário (implementação direta; ruff --fix aplicado dentro do GREEN).

## Known Stubs

Nenhum stub novo introduzido. Os controles de OCR/idioma/deskew/denoise da aba Leitura e as abas Regras/Integrações JÁ eram mock (dados de `data/mock`) e foram explicitamente DESABILITADOS com aviso "Em breve — versão 2" (objetivo do plano: remover elementos falsos que parecem bugs). Não bloqueiam o objetivo do plano.

## Commits

- `532e971` test(quick-260624-far): RED — DELETE em lote + GET /watcher/status
- `ad8b534` feat(quick-260624-far): GREEN — DELETE em lote (só registro) + GET /watcher/status
- `7081b0c` feat(quick-260624-far): botão Remover, status do watcher, abas em-breve, Header

## Self-Check: PASSED

Arquivos criados verificados em disco:
- backend/app/api/watcher_status.py — FOUND
- backend/tests/test_api_watcher_status.py — FOUND
- frontend/src/hooks/useWatcherStatus.ts — FOUND

Commits verificados no git log: 532e971, ad8b534, 7081b0c — todos FOUND.

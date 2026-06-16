---
phase: 04-templates-sub-templates-e-classificacao
plan: 06
subsystem: frontend
tags: [react, typescript, tanstack-query, templates, classification, ui-spec, schema-first, read-only]

# Dependency graph
requires:
  - phase: 04-templates-sub-templates-e-classificacao
    plan: 04
    provides: "API CRUD /templates (TemplateOut com fields aninhados + signals) e GET /documents/{id} (classification: template casado/campos bruto+normalizado/marca/quarentena)"
  - phase: 04-templates-sub-templates-e-classificacao
    plan: 05
    provides: "classify_stage escreve ClassificationResult/FilledField que o detalhe lê (incl. quarentena com template_id null)"
provides:
  - "Tipos reais de Template/TemplateField/TemplateCreate/TemplatePatch + FieldType (6 valores D-08) e Classification/ClassificationField/DocumentDetail (S4) em types.ts"
  - "Funções de API getTemplates/createTemplate/updateTemplate/deleteTemplate + getDocumentDetail em lib/api.ts (reusam request<T>/ApiError/204)"
  - "Hooks useTemplates/useCreateTemplate/useUpdateTemplate/useDeleteTemplate (TanStack Query, queryKey ['templates'], invalidate em onSuccess) espelhando useWatchedFolders"
  - "TemplatesPage real: grid S1 + construtor schema-first S2 (campos tipados/Switch/regex/dica/sinais) + modal de remoção S3 — substitui o mock"
  - "DocumentsPage S4: modal somente leitura de classificação (badge do template, tabela Campo/Valor/Normalizado com marca válido/inválido, pílula Quarentena, 'Aguardando classificação')"
affects: [frontend, revisao-fase5]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hooks de CRUD espelham useWatchedFolders 1-para-1 (TEMPLATES_KEY=['templates'], invalidate em onSuccess, fonte de verdade = API)"
    - "Construtor schema-first como form inline controlado (FormState) molde PastasTab; campos com chave local (FieldDraft.key) para reconciliação React sem usar índice"
    - "Detalhe de classificação carregado sob demanda via useQuery (['document-detail', id]) num modal — lista de polling permanece leve"
    - "Valores extraídos e nomes renderizados como TEXTO PURO (React), nunca dangerouslySetInnerHTML (T-04-12)"
    - "Cores semânticas só via tokens var(--st-*); pílula de quarentena reusa --st-leitura sem alterar o mapeamento do StatusPill"

key-files:
  created:
    - frontend/src/hooks/useTemplates.ts
  modified:
    - frontend/src/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/data/mock.ts
    - frontend/src/pages/TemplatesPage.tsx
    - frontend/src/pages/DocumentsPage.tsx

key-decisions:
  - "Detalhe de classificação (S4) aberto num modal disparado pelo clique no nome do arquivo — evita mudar App.tsx (estado local em DocumentsPage) e mantém a lista/polling intactos"
  - "FieldDraft com `key` local incremental para a lista de campos do construtor — reconciliação estável do React ao adicionar/remover campos, sem depender do índice"
  - "Sinais identificadores editados como texto separado por vírgula/quebra de linha → split/trim/filter no submit (UX simples, casa com signals: list[str] da API)"
  - "doc_type vazio enviado como null; regex/hint vazios enviados como null (coerentes com os opcionais do backend)"

patterns-established:
  - "Estados de tela (isInitialLoading/isError/isEmpty) derivados de query.data ausente — mesmo padrão de DocumentsPage; skeleton em .tpl-card, erro com 'Tentar novamente', empty state com copy exata do UI-SPEC"

requirements-completed: [TPL-01, TPL-03, TPL-04]

# Metrics
duration: 12min
completed: 2026-06-16
---

# Phase 4 Plan 06: Construtor de Templates real + Visibilidade de Classificação Summary

**TemplatesPage real (grid S1 + construtor schema-first S2 + modal de remoção S3) fiada à API de templates via TanStack Query — substituindo o mock — e DocumentsPage estendida com a visibilidade somente-leitura da classificação (S4: template casado, campos bruto+normalizado com marca válido/inválido, e estado de quarentena), honrando o design system TRAVADO do 04-UI-SPEC.md (classes/tokens/copy/pesos), sem XSS.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-06-16
- **Tasks:** 2 implementadas (auto) + 1 checkpoint de verificação visual (pendente)
- **Files modified:** 6 (1 criado, 5 modificados)

## Accomplishments
- `types.ts`: tipo `Template` mock substituído pela forma REAL da API (id/name/doc_type/signals/fields/created_at/updated_at); `TemplateField`, `TemplateCreate`, `TemplatePatch`, `FieldType` (os 6 valores do D-08); tipos do detalhe `ClassificationField`/`Classification`/`DocumentDetail` (S4)
- `lib/api.ts`: `getTemplates`/`createTemplate`/`updateTemplate`/`deleteTemplate` para `/templates` e `getDocumentDetail` para `/documents/{id}`, todos reusando `request<T>`/`ApiError`/tratamento 204 existentes
- `useTemplates.ts`: 4 hooks TanStack Query espelhando 1-para-1 `useWatchedFolders` (queryKey `['templates']`, invalidate em onSuccess)
- `TemplatesPage`: grid S1 com `.tpl-*`, estados loading (skeleton)/erro ("Tentar novamente")/vazio ("Nenhum template ainda"); construtor S2 inline (molde PastasTab) com Nome/Tipo/Sinais e lista de campos (Nome, Tipo via `select` dos 6 tipos, Obrigatório via `Switch`, regex opcional, dica), "Adicionar campo"/"Remover campo", CTAs contextuais "Salvar template"/"Salvar alterações"/"Descartar template"/"Descartar alterações"; modal S3 "Remover template" com botões "Manter template"/"Remover" (vermelho) e copy exata
- `DocumentsPage`: S4 somente leitura — clique no nome do arquivo abre modal "Classificação" com badge do template casado (ou pílula "Quarentena" + texto auxiliar quando não casou), tabela Campo / Valor (mono) / Normalizado com marca "válido"(`--st-tratado`)/"inválido"(`--st-erro`) por campo, e "Aguardando classificação" quando classification é null; StatusPill e mapeamento quarentena→leitura NÃO alterados
- `mock.ts`: array `TEMPLATES` removido (produção deixa de depender do mock)

## Task Commits

1. **Task 1: tipos + API client + hooks de templates** - `da96a30` (feat)
2. **Task 2: TemplatesPage real (S1/S2/S3) + DocumentsPage S4** - `dc4c41f` (feat)

## Files Created/Modified
- `frontend/src/hooks/useTemplates.ts` - 4 hooks TanStack Query (criado)
- `frontend/src/types.ts` - Template real + FieldType + tipos de classificação (S4)
- `frontend/src/lib/api.ts` - funções /templates + getDocumentDetail
- `frontend/src/data/mock.ts` - remove TEMPLATES mock
- `frontend/src/pages/TemplatesPage.tsx` - reescrita: S1 grid + S2 construtor + S3 modal, fiada à API
- `frontend/src/pages/DocumentsPage.tsx` - S4 modal de classificação somente leitura

## Decisões Made
- **S4 em modal disparado pelo nome do arquivo:** mantém o estado em `DocumentsPage` (sem tocar App.tsx) e preserva o polling/lista leve; o detalhe é carregado sob demanda via `useQuery(['document-detail', id])`.
- **FieldDraft.key local:** lista de campos do construtor reconcilia por chave estável (não por índice), evitando bugs ao remover campos do meio.
- **Sinais como texto separado por vírgula/quebra de linha:** UX simples que casa com `signals: list[str]` da API (split/trim/filter no submit).
- **Opcionais como null:** `doc_type`/`regex`/`hint` vazios viram `null` no body (coerente com o backend).

## Deviations from Plan

None - plano executado exatamente como escrito.

(Notas de detalhe, não desvios: a verificação `tsc --noEmit` da Task 1 passa trivialmente porque o `tsconfig.json` raiz usa project references com `files: []`; a checagem de tipos autoritativa é `tsc -b`/`npm run build`, ambos verdes ao final da Task 2. A abertura do detalhe S4 foi implementada via clique no nome do arquivo abrindo um modal — o plano não prescrevia o gesto exato de "abrir/selecionar um documento", apenas que o detalhe fosse mostrado somente-leitura.)

## Threat Surface
Mitigações do `<threat_model>` aplicadas:
- **T-04-12** (XSS): todos os nomes de template e valores extraídos renderizados como texto puro pelo React; nenhum `dangerouslySetInnerHTML` introduzido (grep em `src/pages/` confirma — único match é um comentário explicando a ausência).
- **T-04-18** (Information Disclosure): mensagens de erro genéricas pt-BR do UI-SPEC ("Não foi possível…", "Tentar novamente").
- **T-04-19** (DoS por regex do operador): o form só ENVIA a regex como string; o frontend nunca compila/executa a regex do operador.

Nenhuma superfície de segurança nova fora do `<threat_model>` foi introduzida.

## Known Stubs
None - TemplatesPage e o detalhe S4 estão wired à API real (sem mock, sem dados hardcoded). A resolução de quarentena / edição de campos / fila de revisão são explicitamente Fase 5 (fora de escopo desta fase, conforme UI-SPEC).

## Verificação Automatizada
- `npx tsc -b`: limpo (exit 0)
- `npm run build` (Vite): verde — `built in 232ms`, 77 módulos
- `grep "data/mock" src/pages/TemplatesPage.tsx`: vazio
- `grep "dangerouslySetInnerHTML" src/pages/`: só comentário (sem uso real)
- CTAs "Salvar template"/"Descartar template"/"Manter template" presentes; "Cancelar" ausente da TemplatesPage
- 6 tipos de campo (texto/numero/data/moeda/cpf_cnpj/booleano) presentes no select
- StatusPill.tsx NÃO modificado (fora do git diff)

## Checkpoint Pendente (Task 3 — human-verify, gate=blocking)
A Task 3 é a verificação visual humana do construtor (S1/S2/S3) e da visibilidade de classificação (S4) contra o 04-UI-SPEC.md. Plano `autonomous: false` e `auto_advance: false` → NÃO auto-aprovado. A implementação (Tasks 1-2) está completa e verde; aguarda-se a aprovação do usuário ("approved") ou a lista de divergências a corrigir.

## Next Phase Readiness
- Superfície de usuário de TPL-01 (criar/editar/remover templates) e a janela de leitura de TPL-03/TPL-04 (classificação/quarentena) estão entregues e fiadas à API real.
- Fase 5 (revisão humana) tem a base de UI: o detalhe S4 já lê bruto+normalizado+valid/invalid_reason por campo e o estado de quarentena — pronto para evoluir para edição/resolução.

## Self-Check: PASSED

Arquivo criado (`useTemplates.ts`) existe; os 2 commits de tarefa (`da96a30`, `dc4c41f`) estão no histórico; `tsc -b` e `npm run build` verdes; greps de aceitação confirmados.

---
*Phase: 04-templates-sub-templates-e-classifica-o*
*Completed: 2026-06-16*

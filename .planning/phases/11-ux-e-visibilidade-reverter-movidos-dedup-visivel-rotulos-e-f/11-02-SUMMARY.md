---
phase: 11-ux-e-visibilidade
plan: 02
subsystem: frontend
tags: [automacoes, ux, dropdown, validacao]
requires:
  - frontend/src/pages/AutomationsPage.tsx (activeTemplate, patchCond, validate, renderCond)
provides:
  - "<select> estrito dos campos do template na condição 'Valor de campo' (D-07)"
  - "guard D-08: bloqueio + aviso quando não há template determinável, sem fallback de texto livre"
affects:
  - construtor de automações (aba Automações)
tech-stack:
  added: []
  patterns:
    - "select estrito populado por activeTemplate.fields.map (mesmo molde do select de template)"
    - "aviso de bloqueio no estilo nochip-box (texto puro, sem dangerouslySetInnerHTML)"
key-files:
  created: []
  modified:
    - frontend/src/pages/AutomationsPage.tsx
decisions:
  - "D-07: nome do campo na condição 'Valor de campo' agora é dropdown estrito, não texto livre"
  - "D-08: sem template determinável a condição field é bloqueada com aviso; validate() impede salvar"
  - "D-09 (sinalizar campo não-extraído no dry-run): avaliado e NÃO incluído nesta fase — o select estrito elimina o off-by-nome na origem"
metrics:
  duration: ~10min
  completed: 2026-06-25
---

# Phase 11 Plan 02: Dropdown estrito de campo na condição "Valor de campo" Summary

Trocado o `<input>` de texto livre do nome do campo (condição "Valor de campo" do construtor de automações) por um `<select>` estrito dos campos do template referenciado, com guard que bloqueia a condição e o salvamento quando não há template determinável — eliminando na origem o off-by-nome silencioso (digitar o nome exato de memória).

## O que foi feito

### Task 1 — `<select>` estrito de campo + guard D-08 (commit `837e83f`)

- **D-07:** No ramo `isField` de `renderCond` (AutomationsPage.tsx), o `<input placeholder="nome do campo">` foi removido. Quando `activeTemplate` existe, renderiza um `<select className="select">` (mesmo estilo do select de template) com `<option value="">Escolha um campo…</option>` e `activeTemplate.fields.map((f) => <option key={f.id} value={f.name}>{f.name}</option>)`. `value={c.field_name}` e `onChange` → `patchCond(c.key, { field_name: e.target.value })` preservados.
- **D-08:** Quando `activeTemplate == null`, NÃO renderiza input algum — renderiza um aviso no estilo `nochip-box` (texto puro): "Escolha um template na condição «Tipo de documento» para comparar um campo." Sem fallback de texto livre nem autocomplete global.
- **Guard em `validate()`:** Acrescentado `draftTemplate` (resolvido a partir do próprio `d`, independente do closure de `selected`) e a regra: se há condição `field` e não há `draftTemplate`, retorna erro claro impedindo salvar. A exigência preexistente de `field_name` preenchido para `field==='field'` foi mantida.

## Decisão sobre D-09

D-09 (sinalizar, no dry-run, quando o campo escolhido não foi extraído do documento) foi **avaliado e NÃO incluído nesta fase**. Justificativa: o `<select>` estrito já elimina a causa-raiz do atrito do teste de usuário (o off-by-nome por digitação) na origem — não há mais como referenciar um campo que não existe no template. Sinalizar campo não-extraído no resultado do dry-run é um reforço de UX de naturezadiferente (depende de dados de extração reais), e fica como candidato a uma fase futura de dry-run (relacionado ao item 12 deferido), se o usuário pedir.

## Deviations from Plan

None - plano executado exatamente como escrito.

## Authentication Gates

Nenhum.

## Checkpoint visual — PENDENTE (deferido)

A Task 2 do plano é um `checkpoint:human-verify` (gate="blocking") de verificação visual ao vivo: confirmar no navegador que o nome do campo virou dropdown e que o aviso/bloqueio aparece sem template.

**Por decisão explícita do usuário, esta verificação visual está DEFERIDA para uma rodada de teste combinada de toda a fase.** O código está pronto, o `npm run build` passou (gate de drift de tipos verde) e os critérios de aceitação automáticos foram conferidos. A aprovação visual humana segue **PENDENTE** — não foi solicitada nem fabricada nesta execução.

Passos de verificação quando a rodada acontecer:
1. `cd frontend && npm run dev` → aba Automações.
2. Criar/editar automação → bloco "Quando rodar" → condição "Tipo de documento" + escolher template → adicionar condição "Valor de campo".
3. Confirmar que o nome do campo é um DROPDOWN dos campos daquele template.
4. Limpar a condição "Tipo de documento" → confirmar que a condição "Valor de campo" mostra o aviso e NÃO oferece texto livre, e que salvar é bloqueado.

## Build / Verificação automática

- `cd frontend && npm run build` → **verde** (tsc -b + vite build, 83 módulos, 0 erros).
- `grep -c "activeTemplate.fields.map"` = 2 (1 no ramo isField, 1 no renderTokenBar preexistente).
- `grep -c 'placeholder="nome do campo"'` = 0 (input free-text removido).
- `validate()` contém checagem de `draftTemplate` para bloquear condição field sem template.

## Known Stubs

Nenhum.

## Self-Check: PASSED

- FOUND: frontend/src/pages/AutomationsPage.tsx
- FOUND: 11-02-SUMMARY.md
- FOUND: commit 837e83f

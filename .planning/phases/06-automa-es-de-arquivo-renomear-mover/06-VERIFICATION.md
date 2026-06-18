---
phase: 06-automacoes-de-arquivo-renomear-mover
verified: 2026-06-18T00:00:00Z
status: human_needed
score: 6/6 success-criteria verified (test + build evidence)
overrides_applied: 0
re_verification: false
human_verification:
  - test: "Pela UI (Automações), criar uma automação Condições→Ações (ex.: condição template=X → ação Renomear {campo}_{data} + Mover Documentos/{cliente}/), rodar o Dry-run, Aplicar e depois Desfazer num documento real classificado"
    expected: "Dry-run mostra origem→destino com situação colorida; Aplicar move/renomeia o arquivo na pasta e marca o documento; Desfazer restaura o arquivo na origem. Nenhum arquivo some."
    why_human: "A suíte cobre cada peça (naming/fileops/undo/stage/executor/API) isoladamente e a integração via TestClient, mas o fluxo completo construtor→dry-run→aplicar→desfazer renderizado na UI com um documento real e arquivos no disco só é observável rodando o app ao vivo"
  - test: "Com o worker rodando, aprovar um documento em revisão e verificar que a automação dispara (apply_stage) automaticamente sem restart"
    expected: "Documento aprovado avança para CONCLUIDO com o arquivo aplicado dentro de poucos ciclos de poll"
    why_human: "O encadeamento approve→apply na fila depende do worker em runtime; latência real só é observável ao vivo (mesmo achado de encadeamento da Fase 4)"
gaps: []
deferred: []
---

# Phase 6: Automações de Arquivo (Renomear/Mover) — Verification Report

**Phase Goal:** O sistema renomeia e move arquivos do cliente com base nos campos extraídos de forma reversível e segura — dry-run obrigatório, log de auditoria antes de agir, proteção contra colisão e undo — de modo que nenhum arquivo jamais se perde. Inclui regras condicionais de tratativa (Condições→Ações) por tipo/cliente/valor.

**Verified:** 2026-06-18
**Status:** human_needed — código + testes entregam os 6 critérios; o fluxo end-to-end na UI (construtor→dry-run→aplicar→desfazer com arquivos reais) pede uma verificação ao vivo.
**Re-verification:** No — verificação inicial (a Fase 6 não tinha report; criado retroativamente após confirmar o estado real via git + testes).

---

## Nota de histórico (modelo evoluiu além dos planos)

O roadmap lista 8 planos (06-01..06-08) com 06-08 em aberto. O git mostra que **06-08 foi concluído** e o modelo de automações **evoluiu além do plano original**: 06-09 (refinamentos D-17/D-18/D-21/D-22) → 06-10 (construtor conforme mockup) → 06-11 (remodelagem para o **modelo final Condições→Ações**, D-23..D-26) → 06-12 (reescrita do frontend nesse modelo). A migração `0008` removeu o modelo de `pipeline`/`steps`/`filters` e criou `automations`/`conditions`/`actions`. O `- [ ]` do 06-08 no roadmap era apenas bookkeeping desatualizado.

---

## Goal Achievement

### Observable Truths (Success Criteria do Roadmap)

| # | Critério | Status | Evidência (testes passando) |
|---|----------|--------|------------------------------|
| 1 | Usuário define padrões de renomeação e pasta de destino usando os campos extraídos | VERIFIED | `automation/test_naming.py` (tokens→nome; `data_aaaa_mm`; sanitização Windows/reservados; pasta confinada; traversal bloqueado). `automation/test_executor.py` (rename só muda nome; move só muda pasta; rename→move compõem; ordem independente). `test_api_automations.py` (422 sem pattern em rename; 422 sem dest em move). Frontend: `AutomationsPage.tsx` com editor de token + pré-visualização (build limpo). |
| 2 | Antes de aplicar, dry-run/preview com pares origem→destino e colisões sinalizadas | VERIFIED | `automation/test_stage.py::test_dry_run_does_not_touch_disk`. `automation/test_fileops.py` (`test_no_overwrite`, `test_collision_suffix`, `test_collision_duplicate`). `test_api_automations.py::test_dry_run_endpoint_responds`. Frontend `DryRunPage.tsx` (build limpo). |
| 3 | Registra a intenção em log de auditoria ANTES de agir e nunca sobrescreve destino silenciosamente | VERIFIED | `automation/test_stage.py::test_intent_before_materialize`, `::test_reconcile_orphan_intent`, `::test_idempotencia_done_existente_no_op`. `automation/test_fileops.py::test_no_overwrite`. `test_migrations.py::test_0008_preserva_write_ahead_de_audit_log`. |
| 4 | Desfazer operações por documento e por lote/execução | VERIFIED | `automation/test_undo.py::test_undo_per_doc_restores_source`, `::test_undo_per_run_restores_all`, `::test_undo_cas_fallback`, `::test_undo_reopens_concluded_document`. |
| 5 | Mover entre discos diferentes é seguro (materializa do CAS → verifica hash → remove origem) | VERIFIED | `automation/test_fileops.py::test_cross_device`, `::test_integrity_divergent_hash_aborts` (hash divergente aborta), `::test_original_removed_after_apply` (só remove após verificar). |
| 6 | Regras condicionais de tratativa (condição sobre campos → qual automação aplicar) — TPL-02 | VERIFIED | `automation/test_rules.py` (operadores eq/contains/gt/lt; conjunção E/OU; precedência first-match). `automation/test_executor.py` (match por campo/extensão/pasta-origem/template/tamanho; combinados por E; first_matching_automation_wins; order_matters_position_decides; unknown_field fails-closed; inactive skipped). |

**Score: 6/6 critérios verificados por teste + build**

---

## Gates objetivos (2026-06-18)

- **Backend:** `pytest -q` → **378 passed** (24 warnings benignos: adaptador datetime do SQLite py3.12; alias 422 do Starlette). 0 falhas.
- **Frontend:** `npm run build` (`tsc -b && vite build`) → typecheck + build **limpos**; bundle 319 kB (gzip 91.5 kB).
- **Modelo de dados:** migração `0008` forward + downgrade reversível testados (`test_0008_*`, `test_downgrade_remove_toda_a_automacao`, `test_round_trip_up_down_up`).

---

## O que falta para "validado de verdade"

Os 6 critérios estão cobertos por testes unitários + de integração (TestClient) passando, e o frontend compila. O que **não** está registrado é uma execução **ao vivo** do fluxo completo na UI com arquivos reais (ver `human_verification` no frontmatter). Recomendado rodar antes de considerar a fase 100% fechada:

1. Construtor Condições→Ações → Dry-run → Aplicar → Desfazer num documento real.
2. Encadeamento approve→apply com o worker em runtime (latência real, mesmo achado de fila da Fase 4).

---

*Verification gerada retroativamente em 2026-06-18 após o usuário solicitar acerto do bookkeeping + verificação real da Fase 6.*

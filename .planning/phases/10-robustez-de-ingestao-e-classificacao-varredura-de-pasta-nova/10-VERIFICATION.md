---
phase: 10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova
verified: 2026-06-26T00:00:00Z
status: human_needed
score: 5/5 must-haves verificados (código); 1 item de verificação visual pendente
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
human_verification:
  - test: "Painel 'Testar sinais' no construtor de templates"
    expected: "Salvar um template, subir um PDF de teste de texto nativo, ver o relatório por-grupo/condição (casa/falha) com ✓/✗; subir um PDF escaneado e ver o aviso de documento escaneado (sem custo de IA)"
    why_human: "Renderização visual, upload de arquivo real e leitura do PDF — não verificável por grep"
  - test: "Reprocessar (por-doc) e 'Reprocessar todos' na visão Precisam de atenção"
    expected: "Documento em QUARENTENA/EM_REVISAO: editar o template, clicar Reprocessar → doc sai da quarentena e reclassifica com o template atual; 'Reprocessar todos' do balde re-enfileira todos com confirmação"
    why_human: "Fluxo de UI ao vivo com backend + fila + reclassificação real"
  - test: "Toggle IA-fallback na ConfigPage"
    expected: "Alternar o Switch salva imediatamente (sem botão); recarregar reflete o estado persistido; aviso de custo visível; default desligado"
    why_human: "Persistência via UI e comportamento de salvar-ao-alternar; verificação visual"
---

# Phase 10: Classificação robusta e reprocessamento — Verification Report

**Phase Goal (ROADMAP):** Classificação por sinais menos frágil (testar sinais, casamento tolerante, IA opcional antes da quarentena) + ação "reprocessar/reclassificar automático" (single + lote) sem forçar template.

**Phase Boundary (10-CONTEXT.md):** três capacidades — matcher tolerante por normalização (D-01: SÓ normalização, N-de-M deliberadamente NÃO adotado), ferramenta "testar sinais", reprocessar automático. Toggle IA-fallback (D-05).

**Verified:** 2026-06-26
**Status:** human_needed
**Re-verification:** No — verificação inicial

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Matcher tolerante via normalização simétrica (acento/quebra/pontuação/espaço) no ramo `texto`; ramo `regex` intacto (ReDoS/timeout/tetos) | ✓ VERIFIED | `matcher.py:116-129` `_normalize_text` (NFKD+drop combining+lower+pontuação→espaço+colapsa); `_condition_matches:159-195` bifurca cedo (regex→`haystack_lower`, texto→`haystack_norm` com needle normalizado); `_prepare_haystacks:239-244` fonte-única. Testes `test_matcher_norm.py` verdes. |
| 2 | `POST /templates/preview-signals` (base64→texto nativo→`evaluate_groups`, escaneado→flag, validações falha-fechada) | ✓ VERIFIED | `templates.py:389-476`: 404 template ausente, 422 base64 inválido, 413 acima de 20MB, 422 não-PDF, 422 corrompido, `route=="vision"`→`scanned=True groups=[]` sem IA, senão `matcher.evaluate_groups` (D-09). 7 testes de preview verdes. |
| 3 | Reprocess single + batch por bucket sem forçar template; QUARENTENA+EM_REVISAO; apaga CR antes; guards 409/422 | ✓ VERIFIED | `documents.py:592-614` `_reprocess_one` (apaga CR→PROCESSANDO→requeue classify SEM `forced_template_id`); single `:868-896` (409 fora de QUARENTENA/EM_REVISAO, 404 ausente); batch `:617-670` (XOR bucket/ids→422, ignora inelegíveis idempotente). 8 testes verdes. |
| 4 | Toggle global IA-fallback (default OFF) + `GET/PUT /config/ai-fallback` + ramo gated no `classify_stage` antes de quarentenar | ✓ VERIFIED | `config.py:169-173` `classify_ai_fallback_enabled=False`; `api/config.py:86-104` GET/PUT com `persist_env_setting`+`cache_clear`; `stage.py:264-289` ramo (5.5) gated `matched_template_id is None and settings.classify_ai_fallback_enabled and forced_template_id is None`, chama `disambiguate` antes do bloco de quarentena (6), Usage sempre persistido (Pitfall 5). Seam `matcher.decide` preservado. Testes `test_stage_ai_fallback.py` verdes. |
| 5 | UI: painel "Testar sinais" (TemplatesPage), botões Reprocessar/Reprocessar todos (AttentionPage), toggle IA-fallback (ConfigPage) | ✓ VERIFIED (código) / ⏳ visual pendente | `api.ts` (previewSignals base64, postReprocess, postReprocessBatch, get/putAiFallback); hooks `usePreviewSignals`/`useReprocessDocument`/`useReprocessBucket`/`useAiFallback`/`useSaveAiFallback`; `TestSignalsPanel`, `ReprocessBucketBar`, `AiFallbackField` montados e wired. Build verde. Verificação visual ao vivo (Task 3 do 10-05) explicitamente adiada. |

**Score:** 5/5 truths verificados no código. 1 item de verificação visual humana pendente (Task 3 do plano 10-05, checkpoint blocking adiado).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/classification/matcher.py` | `_normalize_text` + `evaluate_groups` + bifurcação por modo | ✓ VERIFIED | Funções presentes e substantivas; ramo regex intacto |
| `backend/app/classification/stage.py` | ramo IA-fallback gated antes da quarentena | ✓ VERIFIED | Bloco (5.5) `:264-289` |
| `backend/app/api/templates.py` | endpoint preview-signals | ✓ VERIFIED | `:389-476` |
| `backend/app/api/documents.py` | reprocess single + batch | ✓ VERIFIED | `:617-670`, `:868-896`, helper `:592` |
| `backend/app/api/config.py` | GET/PUT /config/ai-fallback | ✓ VERIFIED | `:86-104` |
| `backend/app/config.py` | setting classify_ai_fallback_enabled | ✓ VERIFIED | `:169-173`, default False |
| `frontend/src/pages/TemplatesPage.tsx` | TestSignalsPanel | ✓ VERIFIED | `:723` montado em `:373` |
| `frontend/src/pages/AttentionPage.tsx` | Reprocessar / Reprocessar todos | ✓ VERIFIED | `ReprocessBucketBar:199`, por-doc `:288` |
| `frontend/src/pages/ConfigPage.tsx` | toggle IA-fallback | ✓ VERIFIED | `AiFallbackField:603`, default OFF, aviso de custo |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| preview-signals endpoint | matcher engine | `matcher.evaluate_groups` (D-09 fonte-única) | ✓ WIRED |
| classify_stage fallback | OpenAI | `openai_client.disambiguate` gated por setting | ✓ WIRED |
| _reprocess_one | fila classify | `_requeue` com payload `{content_hash}` SEM forced | ✓ WIRED |
| frontend api.ts | backend endpoints | `request<T>` JSON-only (base64, sem multipart) | ✓ WIRED |
| AiFallbackField toggle | PUT /config/ai-fallback | `useSaveAiFallback` salva ao alternar | ✓ WIRED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Testes de preview/reprocess/fallback/matcher/norm | `pytest -k "preview or reprocess or fallback or matcher or norm"` | 64 passed, 451 deselected | ✓ PASS |

### Anti-Patterns Found

| File | Pattern | Severity |
|------|---------|----------|
| (nenhum) | Scan de TBD/FIXME/XXX/HACK/PLACEHOLDER nos 9 arquivos modificados | ℹ️ limpo |

### Accepted Deviation (informativo, não-gap)

O texto do goal no ROADMAP menciona "limiar **N-de-M** em vez de E-exato de todos + normalização opcional". O `10-CONTEXT.md` D-01 **narrou conscientemente o escopo**: "Tornar o casamento tolerante via NORMALIZAÇÃO apenas — NÃO adotar limiar N-de-M nesta fase". O Deferred Ideas registra N-de-M como deferido. A intenção do goal (classificação menos frágil) é atendida pela normalização + ferramenta de testar sinais + IA-fallback. Tradeoff D-04 (palavra trocada) coberto pela ferramenta de teste. Isso é uma decisão de fase documentada, não uma falha — registrado como deviation aceita.

### Human Verification Required

1. **Painel 'Testar sinais'** — salvar template, subir PDF nativo e ver relatório casa/falha por sinal; subir PDF escaneado e ver aviso (custo zero). Verificação visual.
2. **Reprocessar (por-doc e 'Reprocessar todos')** — editar template, reprocessar doc em QUARENTENA/EM_REVISAO e confirmar saída da quarentena; lote por balde com confirmação.
3. **Toggle IA-fallback** — alternar salva imediatamente, persiste no reload, default desligado, aviso de custo visível.

(Estes itens correspondem ao Task 3 do plano 10-05, checkpoint human-verify explicitamente adiado; alinhado às notas de MEMORY de "testar tudo junto no fim".)

### Gaps Summary

Nenhum gap de código. As três capacidades backend (normalização do matcher, preview de sinais, reprocess single+batch) e o toggle IA-fallback estão implementados, substantivos, wired e cobertos por testes (64 passed). A UI está montada e wired com build verde. O único pendente é a **verificação visual ao vivo** das três telas — adiada deliberadamente pelo checkpoint blocking do 10-05 e pelas decisões de teste consolidado do usuário. Por isso o status é `human_needed`, não `passed`.

---

_Verified: 2026-06-26_
_Verifier: Claude (gsd-verifier)_

---
phase: 10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova
reviewed: 2026-06-26T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - backend/app/api/config.py
  - backend/app/api/documents.py
  - backend/app/api/templates.py
  - backend/app/classification/matcher.py
  - backend/app/classification/stage.py
  - backend/app/config.py
  - frontend/src/hooks/useAttention.ts
  - frontend/src/hooks/useTemplates.ts
  - frontend/src/lib/api.ts
  - frontend/src/pages/AttentionPage.tsx
  - frontend/src/pages/ConfigPage.tsx
  - frontend/src/pages/TemplatesPage.tsx
  - frontend/src/types.ts
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-06-26
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Revisão adversarial das mudanças da Phase 10: normalização do matcher, endpoint
`preview-signals` (custo-zero), reprocess sem template forçado, toggle de IA-fallback
e edge cases de UI. O grosso da implementação está sólido: as transições
QUARENTENA/EM_REVISAO→PROCESSANDO são válidas na allowlist; o requeue é idempotente
(`requeue_step`→`enqueue`); `transition`, `enqueue` e `requeue_step` comitam
internamente, então o batch reprocess não deixa doc preso por rollback de iteração
vizinha (verificado); o gate de IA-fallback vive corretamente no `stage`, não no
`matcher.decide`; `preview-signals` valida magic-bytes + teto de bytes antes de tocar
o PyMuPDF, não persiste o blob e não chama IA. Não há perda de arquivo nem
vulnerabilidade de injeção/secret.

Os achados se concentram em **custo de IA não-intencional** (duas chamadas pagas num
caminho, chamada paga inútil com zero templates), **perda silenciosa de trabalho
humano** (reprocess apaga correções manuais de EM_REVISAO sem aviso/confirmação) e uma
**regressão sutil de correção** na normalização do matcher (needles curtos com
pontuação viram casamentos amplos demais). Não há findings classificados como CRITICAL.

Severidade usada: BLOCKER(critical)/WARNING. As tags HIGH/MEDIUM/LOW abaixo são o
mapeamento pedido no prompt — HIGH→WARNING forte, MEDIUM/LOW→WARNING/Info.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01 (HIGH): IA-fallback dispara uma SEGUNDA chamada paga em docs ambíguos que a IA recusou

**File:** `backend/app/classification/stage.py:264-289`
**Issue:** O gate do fallback é apenas
`matched_template_id is None and settings.classify_ai_fallback_enabled and forced_template_id is None`.
Essa condição também é verdadeira quando o documento passou pelo ramo **"ambiguous"**
(linhas 221-247), que **já chamou `disambiguate` (chamada PAGA)** e a IA devolveu
`matched_template_id = None`. Nesse caso o bloco (5.5) chama `disambiguate` **de novo**,
agora contra TODOS os templates — **dois faturamentos de IA para o mesmo documento**.
O comentário afirma que o bloco só roda "quando NADA casou (matcher local não
resolveu)", o que é impreciso: ele roda sempre que `matched_template_id is None`,
inclusive após um desempate pago que recusou. Viola a constraint do CLAUDE.md de
minimizar/tornar explícito o que vai para a OpenAI (o usuário paga 2x sem saber).
**Fix:** Rastrear se a IA já foi consultada neste fluxo e não repetir. Reusar a flag
`called_ai` já existente:
```python
if (
    matched_template_id is None
    and settings.classify_ai_fallback_enabled
    and forced_template_id is None
    and not called_ai  # NÃO repetir se o ramo ambíguo já consultou a IA
):
    ...
```

### WR-02 (HIGH): Reprocess apaga correções manuais de EM_REVISAO sem confirmação/aviso

**File:** `backend/app/api/documents.py:592-614`, `frontend/src/pages/AttentionPage.tsx:351-415`
**Issue:** `_reprocess_one` apaga o `ClassificationResult` (cascade → apaga os
`FilledField`) antes do requeue. Para docs em **EM_REVISAO**, esses `FilledField`
contêm as **correções manuais** feitas pelo operador via `PATCH .../fields/{name}`.
No frontend, o botão "Reprocessar" da `ReviewRow` chama `reprocess.mutate(item.id)`
**sem nenhum `window.confirm`** — um clique acidental descarta silenciosamente todo o
trabalho de revisão daquele documento. O batch "Reprocessar todos a revisão"
(`ReprocessBucketBar`) confirma, mas o texto do confirm não menciona que as correções
serão perdidas, e atinge o balde inteiro de uma vez. Isso colide com a constraint do
projeto "operações reversíveis e nunca podem causar perda" — aqui a perda é de trabalho
humano, irreversível (não há undo das correções apagadas).
**Fix:** (a) No frontend, exigir `window.confirm` no Reprocessar por-doc de EM_REVISAO
avisando que correções manuais serão descartadas, e enriquecer o texto do confirm do
batch ("As correções manuais feitas na revisão serão perdidas."). (b) Idealmente, no
backend, preservar/copiar os `FilledField` corrigidos manualmente (ex.: marca de
"editado pelo humano") ou pelo menos documentar/registrar em audit log a perda.

### WR-03 (MEDIUM): IA-fallback gera chamada paga inútil quando NÃO há templates cadastrados

**File:** `backend/app/classification/stage.py:264-272`
**Issue:** Com o toggle ON e nenhum template cadastrado, `templates == []`,
`matched_template_id is None`, e o bloco chama
`openai_client.disambiguate(_candidates_summary([]), ...)` — uma chamada PAGA contra
zero candidatos, que **nunca pode casar nada**. O ramo "ambiguous" tem o filtro
`candidates ≥ threshold` que naturalmente o protege; o fallback não tem guarda
equivalente. Custo garantido sem benefício possível; contraria "minimizar o que vai
para a OpenAI".
**Fix:** Curto-circuitar quando não há candidatos:
```python
if (
    matched_template_id is None
    and settings.classify_ai_fallback_enabled
    and forced_template_id is None
    and templates  # não pagar IA se não há nenhum template para escolher
    and not called_ai
):
```

### WR-04 (MEDIUM): Normalização agressiva do matcher transforma sinais curtos com pontuação em casamentos amplos demais

**File:** `backend/app/classification/matcher.py:75-83, 191-195`
**Issue:** No modo "texto", `_normalize_text` agora transforma toda pontuação em espaço
e colapsa, aplicando a MESMA normalização ao `value`. Sinais curtos dominados por
pontuação degeneram em needles minúsculos e amplos. Exemplos:
`"R$"` → needle `"r"` (casa praticamente qualquer texto);
`"Nº"` → NFKD/compat + strip → needle `"no"` (casa qualquer doc com "nota").
Comportamento anterior (substring lowercased cru) exigia o literal com a pontuação,
sendo bem mais específico. É uma **regressão silenciosa de correção** que pode causar
**misclassificação** (template errado casando) em configs existentes — algo central ao
core value "classificados corretamente, confiável". Needle vazio é guardado, mas needle
de 1-2 letras não.
**Fix:** Considerar um piso de tamanho para o needle normalizado no modo texto (ex.:
ignorar/avisar needles com < 2 caracteres alfanuméricos), ou manter a normalização mas
documentar/expor o efeito no construtor de templates. No mínimo, cobrir com teste os
casos `"R$"`/`"Nº"` para tornar a decisão explícita.

## Info

### IN-01 (LOW): Reprocessar por-doc em EM_REVISAO não tem confirmação na UI

**File:** `frontend/src/pages/AttentionPage.tsx:401-408`
**Issue:** Subitem de WR-02: o botão Reprocessar da `ReviewRow` aciona a mutação direto
no `onClick`, sem `window.confirm`, diferente do batch. Mesmo descartando correções,
não há barreira contra clique acidental.
**Fix:** Adicionar confirmação (ver WR-02).

### IN-02 (LOW): `preview-signals` mascara modos de falha distintos num `except Exception` genérico

**File:** `backend/app/api/templates.py:451-457`
**Issue:** `extract_text_and_decide` é envolto em `except Exception` → 422 "arquivo
corrompido?". Isso engole também eventuais erros de programação (ex.: bug interno do
caminho de extração) reportando-os como "PDF corrompido", dificultando diagnóstico.
**Fix:** Estreitar o catch para as exceções reais do fitz/pikepdf, ou logar o tipo da
exceção (sem o conteúdo do PDF, V7) antes de converter para 422.

### IN-03 (LOW): `templates` no bloco de IA-fallback depende da ordem de controle (risco de NameError em refactor)

**File:** `backend/app/classification/stage.py:270`
**Issue:** `templates` só é definido no ramo `else` (forced is None). O bloco de
fallback referencia `templates` e só é seguro porque o gate inclui
`forced_template_id is None`. Um refactor que mova/reordene o gate introduziria
`NameError` silencioso. O próprio comentário admite a fragilidade.
**Fix:** Inicializar `templates: list[Template] = []` no topo da função, ou retornar
cedo no caminho forçado, para remover a dependência implícita de ordem.

### IN-04 (LOW): Mensagens contraditórias no painel "Testar sinais" para template sem sinais

**File:** `frontend/src/pages/TemplatesPage.tsx` (TestSignalsPanel, ~785-805)
**Issue:** Para um template sem sinais (`groups == []`), `matched_any` é `false`, então
a UI mostra "✗ Nenhum grupo casou — o documento não casaria este template" E logo
abaixo "Este template não tem sinais definidos." A primeira frase sugere falha de
casamento; a real causa é ausência de sinais. Confunde o diagnóstico (embora seja
consistente com o comportamento real: template sem sinais nunca casa).
**Fix:** Quando `groups.length === 0`, suprimir o banner de "✗ não casaria" e mostrar
apenas o aviso de "sem sinais definidos".

---

_Reviewed: 2026-06-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

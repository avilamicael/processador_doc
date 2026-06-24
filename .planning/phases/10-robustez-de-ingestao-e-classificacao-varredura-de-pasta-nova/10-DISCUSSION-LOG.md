# Phase 10: Classificação robusta e reprocessamento - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova
**Areas discussed:** Tolerância do matcher, IA quando nada casa, Ferramenta "testar sinais", Escopo do reprocessar

---

## Tolerância do matcher (Item 5)

| Option | Description | Selected |
|--------|-------------|----------|
| Normalização + N-de-M | Os dois mecanismos: normalização (acento/pontuação/quebra) + limiar N-de-M por grupo; configurável por template | |
| Só normalização | Mantém "E de todas as condições" mas normaliza acento/pontuação/quebra de linha antes do match | ✓ |
| Só N-de-M | Limiar de sinais (casar N de M) sem normalização | |

**User's choice:** Só normalização
**Notes:** Aceito o tradeoff de que normalização sozinha não resolve sinal com palavra trocada (DE≠DA) — a ferramenta de testar sinais cobre esse caso (o usuário vê o sinal que falha e corrige). N-de-M fica deferido.

---

## IA quando nenhum template casa (Item 5)

| Option | Description | Selected |
|--------|-------------|----------|
| Não agora — quarentena-primeiro | Manter design custo-zero; nada casou → quarentena; confiar em normalização + ferramenta de teste | |
| Sim, com toggle (opt-in) | Toggle global (padrão off): quando ligado e nada casa, a IA tenta classificar antes da quarentena | ✓ |
| Sim, sempre | Sempre que nada casa, a IA classifica | |

**User's choice:** Sim, com toggle (opt-in)
**Notes:** Toggle global padrão DESLIGADO; custo (1 chamada de IA por doc não-casado) só ocorre quando ligado. Fallback vive no classify_stage, preservando o seam puro do matcher.

---

## Ferramenta "testar sinais" (Item 5)

| Option | Description | Selected |
|--------|-------------|----------|
| Doc já ingerido + colar | Escolher um doc já ingerido (full_text real) + opção de colar texto | |
| Só colar texto | O usuário cola o texto na ferramenta | |
| Upload de PDF novo | Subir um documento de teste que roda a extração na hora | ✓ |

**User's choice:** Upload de documento de teste (free-text / "Other")
**Notes:** Upload de um documento de teste; o backend extrai o texto e roda os sinais. Recomendação MVP: usar texto nativo (PyMuPDF, custo zero); avisar se for escaneado (precisaria de IA). Saída por-sinal e por-grupo (casa/falha), reusando o mesmo motor e a mesma normalização da classificação real.

---

## Escopo do reprocessar (Item 6)

| Option | Description | Selected |
|--------|-------------|----------|
| Só QUARENTENA, doc + lote | Re-rodar detecção automática para docs em QUARENTENA, por-doc e em lote | |
| QUARENTENA + EM_REVISAO | Inclui também docs em revisão humana (por-doc e lote) | ✓ |
| Também CONCLUIDO (sob confirmação) | Permite reprocessar docs concluídos (já movidos) sob confirmação | |

**User's choice:** QUARENTENA + EM_REVISAO (por-doc e lote)
**Notes:** Sem forçar template; re-roda matcher→(IA)→filler com os templates atuais. O usuário também apontou um achado relacionado fora de escopo: a pré-visualização só tem "Aplicar", falta "Negar/Pular" e "Remover" → registrado como Item 12 no backlog.

---

## Claude's Discretion

- Conjunto exato de normalização de pontuação e interação fina com o modo `regex` (D-03) → RESEARCH.
- Forma dos endpoints (preview de sinais multipart vs base64; reprocess single vs batch) → planning.
- Onde expor o toggle da IA-fallback na UI de configuração.

## Deferred Ideas

- Pré-visualização sem "Negar/Pular"/"Remover" → Item 12 do backlog.
- Limiar N-de-M / casamento parcial → fase futura se necessário.
- IA classificar sempre (sem toggle) → não escolhido.
- Itens 2 (varredura de pasta nova) e 7 (re-ingerir split) → fase futura de robustez de ingestão.

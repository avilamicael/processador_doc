# Phase 5: Confiança, Revisão Humana e Quarentena - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 5-Confiança, Revisão Humana e Quarentena
**Areas discussed:** Cálculo da confiança, Limiar e gatilho de revisão, Visualizador na fila, Resolver quarentena

---

## Cálculo da confiança (REV-01)

| Option | Description | Selected |
|--------|-------------|----------|
| % campos válidos (determinístico) | Fração de obrigatórios que passaram na validação determinística; não usa auto-relato da IA | ✓ |
| Combinar validação + confiança da IA/matcher | Mistura validação com confidence da IA — reintroduz auto-relato | |
| Categórico por regras | Sem score numérico, só regras alta/média/baixa | |

**User's choice:** % campos válidos (determinístico)
**Notes:** Alinhado ao roadmap e ao blocker de pesquisa (OpenAI não expõe score confiável por campo).

## Formato do indicador

| Option | Description | Selected |
|--------|-------------|----------|
| Score 0–100% + rótulo derivado | Guarda número (alimenta limiar) + mostra rótulo legível | ✓ |
| Só categoria | Simples, mas limiar fica grosseiro | |
| Só score numérico | Preciso, menos imediato | |

**User's choice:** Score 0–100% + rótulo derivado

## Limiar de confiança (REV-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Global, na configuração | Um limiar por instância, padrão dos tunables existentes | ✓ |
| Por template | Mais flexível, exige UI e modelagem — escopo maior | |

**User's choice:** Global, na configuração
**Notes:** Por-template deferido para evolução futura.

## Gatilho de revisão (REV-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Abaixo do limiar OU obrigatório inválido/faltante | Erros determinísticos sempre revisados | ✓ |
| Somente abaixo do limiar | Mais simples, mas obrigatório inválido poderia passar | |

**User's choice:** Abaixo do limiar OU obrigatório inválido/faltante

---

## Visualizador na fila (REV-03/04) — reframe de visão

| Option | Description | Selected |
|--------|-------------|----------|
| Render da página como imagem (PyMuPDF) | Endpoint serve PNG do CAS, fiel | |
| Servir arquivo original em embed | Zero render, depende do browser | |
| Só texto extraído | Trivial, mas revisor não confere contra o real | |

**User's choice:** (free-text) "não precisa mostrar os documentos na web, a ideia é o usuário não usar a web. Ele vai usar apenas para gestão... ele vai usar o explorer do windows, na web ele vai apenas gerenciar as configurações, templates e ver se der algum erro."
**Notes:** Visão reformulada — web = gestão/triagem, não manuseio de documento. Visualizador de documento CORTADO de escopo (D-06). Após eu detalhar os 3 baldes de erro (FALHA/QUARENTENA/EM_REVISAO) e o reframe "corrigir campo = corrigir o dado, não o arquivo", o usuário escolheu o modelo **"Web ativa, leve"** (mock aprovado: lista de "Precisam de atenção" com motivo + ações leves por balde).

## Ação de aprovar (REV-04)

| Option | Description | Selected |
|--------|-------------|----------|
| EM_REVISAO → CONCLUIDO | Aprovar marca concluído (automações são Phase 6) | ✓ |
| Fica EM_REVISAO até automação | Evita "concluído sem automação", mas estado ambíguo | |

**User's choice:** EM_REVISAO → CONCLUIDO

## Resolver quarentena (REV-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Atribuir template manualmente + reclassificar via fila | Reusa todo o motor (filler+validação) | ✓ |
| Reprocessar do zero | Só re-tenta matcher automático | |
| Editar campos direto e aprovar | Pula template e validação por tipo | |

**User's choice:** Atribuir template manualmente + reclassificar via fila

## Edição de campos

| Option | Description | Selected |
|--------|-------------|----------|
| Atualiza campo + marca "corrigido manualmente" | Revalida, auditável, sem re-cobrar IA | ✓ |
| Sobrescreve sem marca de origem | Mais simples, perde rastreabilidade | |

**User's choice:** Atualiza campo + marca "corrigido manualmente"

---

## Claude's Discretion

- Persistência do indicador de confiança (coluna em `documents` vs `classification_results`).
- Layout/UX fino da visão "Precisam de atenção" (norte = mock aprovado).
- Mecânica de "forçar template" no `classify_stage`.

## Deferred Ideas

- Visualizador de documento na web (usuário usa Windows Explorer).
- Limiar de confiança por template.
- Combinar auto-relato de confiança da IA no indicador.
- Ajustar a redação do REV-03/REV-04 no ROADMAP/REQUIREMENTS para refletir o corte do visualizador (tensão registrada).

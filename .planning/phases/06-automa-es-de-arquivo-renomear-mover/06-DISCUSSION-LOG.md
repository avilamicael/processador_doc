# Phase 6: Automações de Arquivo (Renomear/Mover) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-17
**Phase:** 6-Automações de Arquivo (Renomear/Mover)
**Areas discussed:** Disparo da automação, Regras condicionais (TPL-02), Padrões de nome/pasta, Política de colisão

---

## Disparo da automação

| Option | Description | Selected |
|--------|-------------|----------|
| Sempre manual | Sempre mostra dry-run; só aplica no clique. Máxima segurança | |
| Auto para alta confiança | Alta confiança aplica sozinho; resto espera revisão | ✓ |
| Auto para tudo aprovado | Aplica automaticamente assim que aprovado | |

**User's choice:** Auto para alta confiança
**Notes:** Garantias de segurança (log-antes-de-agir, undo) seguem valendo mesmo no auto-aplica.

| Option | Description | Selected |
|--------|-------------|----------|
| Por documento E por lote | Aplicar um a um ou em lote (espelha o undo AUT-05) | ✓ |
| Só por lote | Sempre em lote (uma execução) | |
| Só por documento | Um de cada vez | |

**User's choice:** Por documento E por lote

---

## Regras condicionais (TPL-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Condições campo/operador/valor | SE {campo} [=,>,<,contém] valor (E/OU) ENTÃO automação X | ✓ |
| Só mapeamento tipo+emissor | Sem operadores numéricos | |
| Mini-linguagem / expressão livre | Campo de expressão textual | |

**User's choice:** Condições campo/operador/valor

| Option | Description | Selected |
|--------|-------------|----------|
| Ordem de prioridade | Primeira regra que casar vence; usuário controla a ordem | ✓ |
| Mais específica vence | Mais condições satisfeitas ganha | |
| Você decide | Planejador escolhe | |

**User's choice:** Ordem de prioridade

---

## Padrões de nome/pasta

| Option | Description | Selected |
|--------|-------------|----------|
| Bloqueia → revisão | Não aplica nome incompleto; manda pra revisão (rebaixa até alta confiança) | ✓ |
| Usa placeholder fixo | Substitui por 'DESCONHECIDO' e aplica | |
| Pula a automação | Deixa o arquivo onde está, silenciosamente | |

**User's choice:** Bloqueia → revisão

| Option | Description | Selected |
|--------|-------------|----------|
| Sistema sanitiza + formata | Remove chars inválidos do Windows + formato de data {data:aaaa-mm} | ✓ |
| Mostra erro e usuário ajusta | Avisa e usuário corrige o padrão | |
| Você decide | Planejador define | |

**User's choice:** Sistema sanitiza + formata

---

## Política de colisão

| Option | Description | Selected |
|--------|-------------|----------|
| Sufixo automático _1, _2 | Renomeia o novo; não sobrescreve, não trava, registra colisão | ✓ |
| Pula → revisão | Não move; usuário resolve manualmente | |
| Pula e só sinaliza | Marca colisão no dry-run/log, sem mover | |

**User's choice:** Sufixo automático _1, _2 (conteúdo diferente)

| Option | Description | Selected |
|--------|-------------|----------|
| Detecta e pula como duplicata | Mesmo SHA-256 do CAS → já-feito, não cria _1 | ✓ |
| Trata como colisão normal | Gera sufixo _1 mesmo para conteúdo idêntico | |
| Você decide | Planejador escolhe | |

**User's choice:** Detecta e pula como duplicata (conteúdo idêntico)

---

## Claude's Discretion

- Comportamento do undo quando o arquivo de destino já foi movido/renomeado/apagado pelo usuário depois da automação.
- Formato/estrutura do audit log (extensão do modelo AuditLog para origem→destino + dados de undo).
- Onde a automação aparece na UI (nova aba de Automações + tela de dry-run/preview).
- Mecânica cross-device (copia→verifica→remove), reusando o hash do CAS.

## Deferred Ideas

- Automações além de renomear/mover (chamar API, e-mail/WhatsApp) — fora do v1.
- Separação dirigida por IA e roteamento determinístico de custo (boleto/NF-e) — Fase 7.

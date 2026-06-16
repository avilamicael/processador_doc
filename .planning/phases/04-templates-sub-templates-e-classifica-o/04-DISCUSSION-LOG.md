# Phase 4: Templates, Sub-templates e Classificação - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 4-Templates, Sub-templates e Classificação
**Areas discussed:** Mecânica de classificação, Fluxo extração↔template (EXT-04), Sub-templates (cliente/emissor), Campos + validações (EXT-04)

---

## Mecânica de classificação

| Option | Description | Selected |
|--------|-------------|----------|
| IA contextual | 2ª chamada manda campos+texto+lista de templates e pergunta qual casa | |
| Regras por presença de dados | Sinais obrigatórios casam localmente sem IA (custo 0) | |
| Híbrido (regras→IA) | Regras locais primeiro; IA desempata quando nada casa com confiança | ✓ |

**User's choice:** Híbrido (regras→IA)

| Option | Description | Selected |
|--------|-------------|----------|
| Sinais explícitos por template | Usuário declara sinais identificadores (presença de dados → tipo) | ✓ |
| Só nome + descrição do tipo | IA infere o casamento pelo contexto | |
| Você decide | — | |

**User's choice:** Sinais explícitos por template

| Option | Description | Selected |
|--------|-------------|----------|
| Maior confiança vence | Nenhum casa→quarentena; múltiplos→maior confiança | ✓ |
| Conservador: dúvida→quarentena | Qualquer incerteza→quarentena | |
| Você decide | — | |

**User's choice:** Maior confiança vence (nenhum casa → quarentena)

| Option | Description | Selected |
|--------|-------------|----------|
| Fica aguardando (Fases 5/6) | PROCESSANDO/'classificado', vinculado ao template, nunca CONCLUIDO | ✓ |
| Você decide | — | |

**User's choice:** Fica aguardando (Fases 5/6)
**Notes:** Classificação automática no pipeline (novo step="classify") fica como discretion.

---

## Fluxo extração↔template (EXT-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Mapear o que já foi extraído; IA só p/ faltantes | Mapeia fields_json da Fase 3; 1 chamada dirigida só p/ obrigatórios faltantes | ✓ |
| Re-extrair sempre com schema do template | 2ª chamada à IA com JSON Schema derivado do template em todo doc | |
| Só mapear, nunca re-chamar | Campo não encontrado fica vazio | |

**User's choice:** Mapear o que já foi extraído; IA só p/ faltantes

| Option | Description | Selected |
|--------|-------------|----------|
| Novo registro ligado a (documento, template) | Preserva a Extraction genérica bruta; cria registro de campos mapeados/validados | ✓ |
| Você decide | — | |

**User's choice:** Novo registro ligado a (documento, template)

---

## Sub-templates (cliente/emissor)

**Notes:** O usuário reformulou o conceito durante a discussão. Sub-template, na visão dele, é "ajustar a automação por condição": mesmo tipo de documento, tratativa diferente conforme os dados (cliente X → Desktop, cliente Y → Documentos; holerite > R$ 3.000 → análise, < R$ 3.000 → e-mail). Concluiu não ter certeza da real necessidade de uma entidade sub-template.

| Option | Description | Selected |
|--------|-------------|----------|
| Regras condicionais na automação (Fase 6) | Sem entidade sub-template; tratativas viram regras 'se <condição> → ação' na Fase 6; TPL-02 migra 4→6 | ✓ |
| Sub-template leve na Fase 4 | Lista ordenada de tratativas = condição + automação, estrutura/UI na Fase 4 | |
| Deixar de fora do v1 | Tratativa condicional vira v2 | |

**User's choice:** Regras condicionais na automação (Fase 6)
**Notes:** Decisão re-escopa TPL-02 da Fase 4 → Fase 6. Ação de manutenção do ROADMAP/REQUIREMENTS registrada no CONTEXT. As perguntas anteriores sobre herança e seleção de sub-template ficaram resolvidas por esta decisão (sub-templates não existem como entidade na Fase 4).

---

## Campos + validações (EXT-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Conjunto comum tipado | texto, número, data, moeda, CPF/CNPJ, booleano (tipo opcional, padrão texto) | ✓ |
| Mínimo (texto/número/data) | Só os três básicos | |
| Você decide | — | |

**User's choice:** Conjunto comum tipado, padrão texto
**Notes:** Usuário não entendeu a pergunta inicialmente ("CPF/CNPJ seria uma string"). Após explicação de que o tipo é opcional e só destrava validação/comparação/normalização: "pode seguir assim mesmo, deixar mais robusto."

| Option | Description | Selected |
|--------|-------------|----------|
| Obrigatório + por tipo + regex | Inclui DV de CPF/CNPJ (Módulo 11) + regex opcional | ✓ |
| Obrigatório + por tipo (sem regex) | — | |
| Você decide | — | |

**User's choice:** Obrigatório + por tipo + regex

| Option | Description | Selected |
|--------|-------------|----------|
| Aplica e marca válido/inválido | Documento segue sem aplicar automação; score/fila são Fase 5 | ✓ |
| Campo obrigatório inválido → quarentena | Manda direto para quarentena na Fase 4 | |
| Você decide | — | |

**User's choice:** Aplica e marca válido/inválido

| Option | Description | Selected |
|--------|-------------|----------|
| Sim: guardar bruto + normalizado | data→ISO, moeda→decimal, CNPJ→só dígitos; valor bruto preservado | ✓ |
| Só validar, não normalizar | — | |
| Você decide | — | |

**User's choice:** Sim: guardar bruto + normalizado

---

## Claude's Discretion

- Estrutura dos novos modelos (template, campo de template, registro de campos por documento×template) e persistência dos sinais identificadores e validações — via Alembic.
- Formato dos sinais identificadores (como declarar "presença de X/Y/Z" e virar regra + dica para IA).
- Limiar e política de desempate da classificação (limiar por template é v2; aqui global se houver).
- Como a classificação entra no pipeline (novo step="classify", despacho por step no worker, idempotência por bloco).
- Prompt/schema das chamadas de IA (desempate e campos faltantes); medição de tokens via Usage(step="classify").
- UI do construtor de template (TemplatesPage hoje é mock); eventual seed de campos a partir de documento extraído.

## Deferred Ideas

- TPL-02 (sub-templates / tratativas condicionais) → Fase 6 (regras condicionais de automação).
- Auto-identificar cliente pelo CNPJ sem config (INT2-01) → v2.
- Limiar de confiança por template (INT2-05) → v2.
- Score/limiar/fila de revisão/quarentena visível (REV-01..05) → Fase 5.
- Extração local custo-zero por layout + roteamento determinístico (EXT-03, EXT-05) → Fase 7.
- Correções da revisão virando hints/few-shot (INT2-04) → v2.
- Seed de campos do template a partir de documento já extraído → considerar no planejamento/UI-phase.

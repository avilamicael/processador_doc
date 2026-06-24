# Phase 9: Automação — destino configurável e transformação de valores - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 09-automacao-destino-de-arquivo-configuravel-e-transformacao-de
**Areas discussed:** Política de destino, Destino inexistente/inválido, Sintaxe das transformações, Escopo das transformações no v1

---

## Política de destino

| Option | Description | Selected |
|--------|-------------|----------|
| Absoluto por automação | Caminho absoluto completo com tokens, validado, sem mutilar; relativo cai numa base padrão | ✓ |
| Pasta-base na UI + relativo | Uma raiz de saída global; automações usam caminho relativo | |
| Os dois (base + caminho) | Campo de base + aceita absoluto | |

**User's choice:** Absoluto por automação
**Notes:** Single-tenant na máquina do cliente justifica abrir mão do confinamento V4 para destinos absolutos. Caso real do teste reforçou: usuário digitou caminho absoluto e queria exatamente ele.

---

## Destino inexistente/inválido

| Option | Description | Selected |
|--------|-------------|----------|
| Criar automaticamente | mkdir recursivo ao aplicar, exigindo raiz/drive existir | ✓ |
| Bloquear e avisar no dry-run | Exige pasta existir; erro no preview | |

**User's choice:** Criar automaticamente
**Notes:** Esperado em "mover para {fornecedor}/{data}". Raiz/drive inexistente continua sendo erro.

---

## Sintaxe das transformações

| Option | Description | Selected |
|--------|-------------|----------|
| Inline no token + preview | Filtros no próprio token, ex.: {fornecedor:maiusc:palavras=2} | ✓ |
| Config estruturada por campo na UI | Menu de regras por campo (dropdowns) | |

**User's choice:** Inline no token + preview
**Notes:** Encaixa no padrão {campo} atual; preview no construtor mostra o resultado.

---

## Escopo das transformações no v1

| Option | Description | Selected |
|--------|-------------|----------|
| Essencial + substituir | Truncar, N palavras/letras, caixa, remover acento, valor-padrão, substituir simples | ✓ |
| Completo (com regex e mapa) | + regex + mapa de valores | |
| Mínimo | Só truncar/N palavras/caixa | |

**User's choice:** Essencial + substituir
**Notes:** Cobre ~90% (inclui encurtar nome do fornecedor). Regex e mapa de valores adiados para v2.

---

## Claude's Discretion

- Nomes/gramática exatos dos filtros inline (mantendo a sintaxe e o conjunto v1).
- Detecção de caminho absoluto (drive/UNC/leading slash) e normalização.
- Texto das mensagens de aviso/erro do dry-run.
- Base padrão continuar via env vs. editável na UI (preferência: via env).

## Deferred Ideas

- Substituição por regex + mapa de valores (Item 11, v2).
- Base de saída editável na UI.
- Confinamento opt-in / allowlist de raízes (V4 opcional).

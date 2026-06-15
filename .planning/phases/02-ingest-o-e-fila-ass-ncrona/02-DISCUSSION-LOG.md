# Phase 2: Ingestão e Fila Assíncrona - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-15
**Phase:** 2-Ingestão e Fila Assíncrona
**Areas discussed:** Separação de páginas, Hot folder + estabilização, Comportamento de duplicata, UI de ingestão

---

## Separação de páginas

### O que cada bloco vira

| Option | Description | Selected |
|--------|-------------|----------|
| Cada bloco = Document independente | Cada bloco vira um Document próprio (hash/estado/pipeline próprios); original inteiro no CAS | ✓ |
| Blocos = sub-unidades do mesmo Document | PDF continua 1 Document; blocos viram grupos de Page | |
| Você decide | Planejador escolhe | |

**User's choice:** Cada bloco = Document independente.

### Onde a regra de separação é configurada

| Option | Description | Selected |
|--------|-------------|----------|
| Config global, padrão = não separar | Uma config global | |
| Por caminho de ingestão | Cada caminho com sua qtd. | |
| Você decide | — | |

**User's choice:** Free-text — "o usuário define uma pasta de entrada de documento e define a quantidade de páginas que ele quer; cria uma pasta onde todo documento que entrar é separado a cada 1 página, ou a cada 2", etc.
**Notes:** Regra de separação é **por pasta monitorada** → implica múltiplas pastas, cada uma com sua regra.

### Separação no upload/CLI

| Option | Description | Selected |
|--------|-------------|----------|
| Usuário informa na hora | Campo no upload / flag no CLI | |
| Sem separação | Só hot folder separa | |
| Você decide | — | |

**User's choice:** Free-text — "na verdade não iremos fazer upload manual, vamos trabalhar apenas com pastas."
**Notes:** Disparou a redução de escopo (sem upload manual).

---

## Escopo de ingestão (redução)

### Confirmação do escopo

| Option | Description | Selected |
|--------|-------------|----------|
| Só pasta monitorada + CLI | Hot folder + CLI; ING-01 sai | |
| Só pasta monitorada | Só hot folder; ING-01 e ING-03 saem | ✓ |
| Manter upload também | Voltar atrás | |

**User's choice:** Só pasta monitorada.

### Confirmação do CLI (segunda checagem)

| Option | Description | Selected |
|--------|-------------|----------|
| Remover do v1 | Só hot folder ingere | ✓ |
| Manter o CLI | Útil para backfill de pasta cheia | |

**User's choice:** Remover do v1.
**Notes:** Confirmado mesmo após explicar que o CLI também é "só pasta" e serve para backfill. ING-01 e ING-03 saem do v1.

---

## Hot folder + estabilização

### Onde configurar as pastas

| Option | Description | Selected |
|--------|-------------|----------|
| Na interface (UI) | Tela para gerenciar pastas + regra de split | ✓ |
| Arquivo de config | Como a chave OpenAI | |
| Você decide | — | |

**User's choice:** Na interface (UI).

### Destino do original após ingestão

| Option | Description | Selected |
|--------|-------------|----------|
| Move para subpasta 'processados' | Mantém a pasta limpa | |
| Deixa no lugar (dedup protege) | Original permanece; dedup evita reprocessar | ✓ |
| Você decide | — | |

**User's choice:** Deixa no lugar (dedup protege). Coerente com D-07 da Fase 1.

### Janela de estabilização configurável

| Option | Description | Selected |
|--------|-------------|----------|
| Padrão fixo, sensível | Embutido, sem expor | |
| Configurável (global) | Config global da janela | ✓ |
| Você decide | — | |

**User's choice:** Configurável (global).

---

## Comportamento de duplicata

### Escopo do dedup

| Option | Description | Selected |
|--------|-------------|----------|
| Global e para sempre (por conteúdo) | Mesmo hash em qualquer lugar = duplicata | ✓ |
| Por pasta | Mesmo conteúdo em pastas diferentes = distinto | |
| Você decide | — | |

**User's choice:** Global e para sempre (por conteúdo).
**Notes:** Levantada a implicação de dedup no hash do original pré-split (D-09).

### O que o usuário vê na duplicata

| Option | Description | Selected |
|--------|-------------|----------|
| Ignora em silêncio (só log) | Sem UI | |
| Contador/indicador na UI | Ignora + visibilidade | ✓ |
| Você decide | — | |

**User's choice:** Contador/indicador na UI.

---

## UI de ingestão

### O que a visão da fila mostra

| Option | Description | Selected |
|--------|-------------|----------|
| Lista de documentos com estado | Nome, estado, pasta, data; polling | ✓ |
| Lista + contadores por estado | Resumo no topo | |
| Você decide | — | |

**User's choice:** Lista de documentos com estado.
**Notes:** UI da fase = gerenciador de pastas + lista de documentos + contador de duplicados. Sem upload.

---

## Claude's Discretion

- Estrutura das tabelas de fila/jobs e da config de pastas; algoritmo de polling/backoff; nº máx. de tentativas antes de FALHA; concorrência do worker.
- Lib do watcher (preferência: watchfiles) e detecção de estabilidade no Windows.
- Lib de split de PDF (preferência: pikepdf; atenção AGPL do PyMuPDF na Fase 3).
- Modelagem do gate de dedup do original pré-split vs schema atual.
- Estado/marcador terminal da Fase 2 (aguardando extração) sem marcar CONCLUIDO.
- Tratamento de extensões não suportadas (ignorar no v1).
- Valores padrão (janela de estabilização; split padrão = não separar).

## Deferred Ideas

- Upload manual (ING-01) → v2.
- Lote CLI / backfill (ING-03) → v2.
- Mover original para subpasta "processados" → futuro.
- Estabilização e threshold por pasta → v1 mantém global.

# Phase 1: Fundação de Estado e Storage - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-15
**Phase:** 1-Fundação de Estado e Storage
**Areas discussed:** Local dos dados no Windows, Configuração da chave OpenAI, Ciclo de vida do documento, Retenção dos originais

---

## Local dos dados no Windows

| Option | Description | Selected |
|--------|-------------|----------|
| Pasta de dados configurável | Pasta única (padrão %ProgramData%\ProcessadorDocumentos) com banco + CAS; backup = copiar uma pasta; caminho ajustável | ✓ |
| Por usuário (%APPDATA%) | Dados no perfil do usuário Windows | |
| Ao lado do app | Pasta data/ junto do executável | |

**User's choice:** Pasta de dados configurável
**Notes:** Motivado por backup como "copiar uma pasta só" e sobreviver à troca de usuário Windows.

---

## Configuração da chave OpenAI

| Option | Description | Selected |
|--------|-------------|----------|
| Config na instalação + editável na UI | Chave em arquivo de config, vista/trocada depois numa tela | |
| Só arquivo de config | Chave só num arquivo (.env/config), sem tela | ✓ |
| Só tela de configurações | Cola a chave numa tela ao abrir | |

**User's choice:** Só arquivo de config
**Notes:** Sem tela no v1; trocar chave = editar arquivo de config na máquina do cliente.

---

## Ciclo de vida do documento

| Option | Description | Selected |
|--------|-------------|----------|
| Conjunto completo (11 estados) | recebido→deduplicado→separado→extraído→classificado→validado→pendente-automação→aplicado + laterais | |
| Mais simples | Menos estados (recebido/processando/revisão/concluído/falha) | ✓ |
| Você decide | Confiar na arquitetura | |

**User's choice:** Mais simples → travado como `RECEBIDO → PROCESSANDO → EM_REVISÃO → CONCLUÍDO` + `QUARENTENA`, `FALHA`
**Notes:** Subetapas internas viram marcador interno de "última etapa concluída" (retomada + idempotência sem poluir a UI). Confirmado em pergunta de follow-up: "Sim, travar assim".

---

## Retenção dos originais

| Option | Description | Selected |
|--------|-------------|----------|
| Manter para sempre | Originais imutáveis nunca apagados pelo sistema | ✓ |
| Retenção configurável | Política de expiração (ex.: apagar N dias após aplicados) | |
| Você decide | Padrão mais seguro agora | |

**User's choice:** Manter para sempre o original
**Notes:** O cliente monitora uma pasta (ex.: Downloads); ao entrar um documento, ele é **copiado** para o sistema e tratado internamente, preservando o original na origem. Mencionou suporte futuro a outros formatos (Excel, txt, csv) — registrado como ideia futura.

---

## Claude's Discretion

- Estrutura concreta de tabelas/modelos, nomes de colunas e implementação da state machine.
- Mecanismo do CAS (layout por hash, algoritmo — SHA-256 sugerido) e persistência do marcador de etapa.
- Formato exato do arquivo de config e nomes das chaves.

## Deferred Ideas

- Suporte a outros formatos de entrada (Excel, TXT, CSV) além de PDF/imagens — fase futura / v2.
- Tela de configuração para a chave OpenAI (settings na UI) — v1 usa só arquivo de config.
- Política de retenção/expiração configurável dos originais — adiada; v1 mantém para sempre.

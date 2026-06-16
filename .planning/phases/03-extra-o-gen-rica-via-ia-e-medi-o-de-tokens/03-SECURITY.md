---
phase: 03-extra-o-gen-rica-via-ia-e-medi-o-de-tokens
audited: 2026-06-16
status: secured
asvs_level: 1
block_on: high
threats_total: 16
threats_closed: 16
threats_open: 0
threats_accepted: 2
register_authored_at_plan_time: true
---

# SECURITY.md — Fase 03: Extração genérica via IA e medição de tokens

**Auditado em:** 2026-06-16
**ASVS Level:** 1
**Block-on:** high
**Resultado:** SECURED — 16/16 ameaças fechadas (13 mitigadas + verificadas, 2 aceitas + documentadas, 1 supply-chain verificada)

> Auditoria de verificação de mitigações: cada ameaça do registro autorado em tempo de plano
> (`register_authored_at_plan_time: true`) foi conferida CONTRA O CÓDIGO implementado. Nenhum
> arquivo de implementação foi modificado. Não houve varredura por ameaças novas além do registro.

---

## Fronteiras de confiança (Fase 03)

| Fronteira | Descrição | Dado que cruza |
|-----------|-----------|----------------|
| app → OpenAI | chave + conteúdo do documento saem da máquina (LGPD) | `OPENAI_API_KEY`, texto nativo OU imagem da página (CPF/CNPJ/salário) |
| env → config | chave + tunables entram via env/`.env` | `OPENAI_API_KEY` (SecretStr) + `OPENAI_EXTRACT_*` |
| fila/worker → extract_stage | job de extract dispara trabalho PAGO sobre o bloco | `(content_hash, "extract")` |
| extract_stage → DB | Extraction + Usage persistidos = base de cobrança | tokens por documento |

---

## Verificação de ameaças

| Threat ID | Categoria | Disposição | Status | Evidência (arquivo:linha) |
|-----------|-----------|------------|--------|---------------------------|
| T-03-01 | Information Disclosure | mitigate | CLOSED | `config.py:55` `openai_api_key: SecretStr`; `config.py:9-11` docstring "nunca aparecer em repr/str/logs"; `.get_secret_value()` NÃO ocorre em `config.py` (só em `openai_client.py:71`) |
| T-03-02 | Tampering | mitigate | CLOSED | `alembic/versions/0003_extractions.py:31-55` schema só via Alembic; `downgrade()` em `:58-63`; teste de downgrade `tests/test_migrations.py:133` `test_downgrade_um_passo_remove_so_a_fase_3` |
| T-03-SC | Tampering (supply-chain) | mitigate | CLOSED | Pacotes oficiais prescritos no `CLAUDE.md` e auditados em `03-RESEARCH.md §Package Legitimacy Audit` (openai/PyMuPDF/respx [VERIFIED: PyPI]); sem [ASSUMED]/[SUS] |
| T-03-03 | Information Disclosure (chave em log) | mitigate | CLOSED | `openai_client.py:71` única chamada `.get_secret_value()` (ponto de criação do cliente); grep confirma ZERO ocorrências em chamadas de log; `__init__.py:8` documenta isolamento da chave |
| T-03-04 | Information Disclosure (conteúdo em log) | mitigate | CLOSED | `openai_client.py:102` loga só `reason` (metadado do bloco refusal); `_refusal_reason:107-114` retorna só o motivo; nenhum `full_text`/`fields`/`native_text` em chamada de logger |
| T-03-05 | Information Disclosure (envio à OpenAI / LGPD) | accept (v1) | CLOSED | Risco aceito documentado abaixo (Registro de riscos aceitos). `router.choose` prefere `native_text` quando há texto (`router.py:40-42`), enviando texto nativo (menos cru que imagem) — postura conservadora; controle por-documento é v2 (INT2-03) |
| T-03-06 | DoS (custo) — PDF malformado | mitigate | CLOSED | `pdf_io.py:60` `fitz.open(stream=...)`; `:58` exceção do fitz propaga; stage NÃO captura (`stage.py:88-91`); worker captura em `worker.py:211` `except Exception` → `schedule_retry`/FALHA — worker não cai |
| T-03-07 | Custo — cobrança dupla | mitigate | CLOSED | `stage.py:106-111` checa `Extraction` existente ANTES da chamada paga → no-op; `models/extraction.py:36-41` UNIQUE(document_id); `stage.py:176` commit único antes de `mark_done`; teste `tests/extraction/test_idempotency.py:77` `call_count==1`, `:91-92` `n_ext==1`/`n_usage==1` |
| T-03-08 | Repudiation/Integrity — medição de tokens | mitigate | CLOSED | `stage.py:151-176` `Extraction` + `Usage(step="extract")` no MESMO `session.commit()`; teste `tests/extraction/test_usage.py:81` `len(usages)==1`, `:104` `count==1` (exatamente 1 por extração) |
| T-03-09 | DoS (custo) — PyMuPDF crash | mitigate | CLOSED | Igual T-03-06: erro propaga como exceção controlada (`pdf_io.py`), worker faz FALHA (`worker.py:211-232`), worker não cai; cada job usa sessão própria (`worker.py:151,180`) |
| T-03-10 | Information Disclosure — log full_text/fields/chave | mitigate | CLOSED | `stage.py:179-184` loga só `document_id`/`route`/`doc_type_guess`; `stage.py:110` log de no-op só com `doc.id`; grep confirma nenhum log de conteúdo/chave |
| T-03-11 | Tampering (dado) — alucinação de campo | accept | CLOSED | Risco aceito documentado abaixo. Sem gate de qualidade na Fase 3 (D-09); `schema.py:42` documenta "conformidade ao schema é a única validação"; mitigado a jusante (Fase 5) |
| T-03-12 | DoS — await em to_thread (RuntimeError) | mitigate | CLOSED | `worker.py:149-152` extract roda como coroutine (`await extract_stage`) no loop; `stage.py:116,123,134,141` só PyMuPDF vai a `asyncio.to_thread`; chamada OpenAI é `await` direto (`stage.py:128,146`); teste `tests/queue/test_dispatch.py:76` cobre caminho async |
| T-03-13 | Custo — colisão de idempotência entre blocos | mitigate | CLOSED | `worker.py:271` job key = `(doc.content_hash, "extract")`; `models/job.py:42` UNIQUE `uq_jobs_hash_step`; migração `alembic/versions/0002_ingestion.py:88`; teste `tests/extraction/test_enqueue_sweep.py:68,75` `first==1`/`len(jobs)==1` |
| T-03-14 | DoS (custo) — chave OpenAI inválida → retry caro | mitigate | CLOSED (com ressalva — ver abaixo) | `worker.py:197-210` `except AuthenticationError` → `repo.mark_failed` (dead-letter IMEDIATO, não `schedule_retry`) → FALHA no bloco. Hierarquia confirmada: `AuthenticationError` é subclasse de `OpenAIError` |
| T-03-15 | Information Disclosure — log de chave/conteúdo no worker | mitigate | CLOSED | `worker.py:202-206` loga só `job_id`/`step`; `:212-218` só `job_id`/`step`/`attempts`/`exc`; nenhum log de chave nem conteúdo do documento |

---

## Ressalva sobre T-03-14 (chave inválida vs chave AUSENTE) — WARNING, não bloqueante

A mitigação **declarada** de T-03-14 ("`AuthenticationError` não-retryável → dead-letter imediato")
**está presente no código** (`worker.py:197-210`) e cobre o caso de chave **inválida**. Status: CLOSED.

Porém, conforme `03-REVIEW.md WR-01` (confirmado nesta auditoria): o caso mais comum de
má-configuração — chave **AUSENTE** (`openai_api_key is None`, instalação Windows nova sem `.env`) —
constrói `AsyncOpenAI(api_key=None)`, que levanta `openai.OpenAIError` (NÃO `AuthenticationError`).
Essa exceção cai no `except Exception` genérico (`worker.py:211`) → `schedule_retry` → backoff 5× →
só então FALHA.

**Por que isto NÃO reabre T-03-14 como BLOCKER:**
- T-03-14 descreve um risco de **custo** ("retry caro infinito"). No caso chave-ausente a chamada
  HTTP **nunca sai da máquina** (a exceção dispara na construção do cliente, antes de `responses.parse`),
  logo **não há tokens gastos** — o dano que a ameaça descreve não se materializa. WR-01 confirma:
  "Não custa tokens (a chamada nunca sai)".
- O efeito real é **atraso de diagnóstico** (5 retries até FALHA) numa instalação mal-configurada,
  classificado como WARNING (WR-01), não como vazamento nem custo.

**Recomendação de follow-up (não bloqueia o ship desta fase):** tratar chave ausente como
não-retryável junto de `AuthenticationError` — preferir checagem explícita de
`settings.openai_api_key is None` no início de `extract_stage`/`_client` (NÃO capturar `OpenAIError`
de forma ampla, pois é base de exceções transitórias de rede/rate-limit). Ver `03-REVIEW.md WR-01`.

---

## Registro de riscos aceitos (accepted)

### T-03-05 — Envio de dado pessoal à OpenAI (LGPD, minimização) — ACEITO (v1)

- **Risco:** texto nativo ou imagem da página do documento (podendo conter CPF/CNPJ/salário)
  é enviado à OpenAI, cruzando a fronteira da máquina.
- **Mitigação parcial em vigor:** o roteador prefere o caminho `native_text` quando há texto
  suficiente (`router.py:40-42`, `pdf_io.extract_text_and_decide`), enviando texto nativo
  (menos cru/mais barato que imagem). Postura conservadora mantida (premissa "uso interno"
  não confirmada).
- **Por que aceito em v1:** controle por-documento explícito do que sai da máquina é escopo v2
  (INT2-03). Decisão registrada em `03-02-PLAN.md` threat_model.
- **Condição de revisão:** reabrir na implementação de INT2-03 (controle granular LGPD) ou se a
  premissa de uso interno for revertida.

### T-03-11 — Alucinação de campo passa como verdade — ACEITO

- **Risco:** a IA pode inventar/errar um valor de campo; na Fase 3 não há gate de qualidade que o
  detecte (D-09). `schema.py:42` documenta que a conformidade ao schema é a única validação.
- **Por que aceito:** mitigado a jusante (evals offline + revisão humana / Fase 5). Decisão de
  produto registrada em `03-03-PLAN.md` threat_model (D-09).
- **Condição de revisão:** Fase 5 (gate de qualidade / revisão humana) deve fechar o resíduo.

---

## Flags de ameaça não registradas (unregistered_flag)

Nenhuma. As seções `## Threat Flags` de `03-01-SUMMARY.md` a `03-04-SUMMARY.md` declaram
explicitamente "Nenhuma surface nova além do `<threat_model>` do plano" e cada flag mapeia para
um Threat ID já existente (T-03-03/04/06/07/08/09/10/11/12/13/14/15). Nenhuma surface de ataque
nova surgiu durante a implementação sem mapeamento.

---

## Achados do code review relevantes à segurança (informativo)

| ID | Severidade | Relação com ameaça | Disposição |
|----|------------|--------------------|------------|
| WR-01 | Warning | T-03-14 (caso chave ausente) | Follow-up recomendado; não bloqueia (sem custo de tokens) |
| CR-01 | Critical (review) | Truncamento por `max_output_tokens` tratado como recusa | Aceito para v1 por decisão humana 2026-06-16 (`openai_client.py:91-97`, `03-HUMAN-UAT.md`). NÃO é uma ameaça do registro STRIDE desta fase; é perda de dado parcial / classificação de falha, mitigável aumentando `OPENAI_EXTRACT_MAX_OUTPUT_TOKENS`. Fora do escopo de bloqueio desta auditoria de segurança |

---

_Auditor: gsd-security-auditor — verificação de mitigações contra o código, arquivos de implementação read-only._

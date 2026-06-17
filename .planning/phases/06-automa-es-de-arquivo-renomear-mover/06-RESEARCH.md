# Phase 6: Automações de Arquivo (Renomear/Mover) — Research

**Researched:** 2026-06-17 (re-pesquisa pós REDESIGN para modelo de PIPELINE)
**Domain:** Pipeline ordenado de etapas componíveis de automação sobre documentos classificados, executando operações de arquivo seguras/reversíveis no Windows (rename/move atômico, cross-device, anti-colisão), com audit-log write-ahead agrupado por execução + undo do pipeline inteiro
**Confidence:** HIGH (tijolos de fileops/CAS/Windows/EXDEV já implementados e testados; padrões do código existente; reuso de classificação para o gate) / MEDIUM (semântica exata de composição nome+pasta no pipeline — Open Question principal; undo agrupado sobre múltiplas etapas)

> **NOTA DE RE-PESQUISA.** Esta versão SUBSTITUI o modelo de "regra única (condição→nome+pasta, primeira-que-casa-vence)" pela arquitetura de **pipeline ordenado de steps componíveis** (D-12..D-16). Os achados técnicos de operação de arquivo (CAS/EXDEV/Windows/anti-colisão/write-ahead) **permanecem válidos e foram preservados** — os tijolos (`naming.py`, `fileops.py`, `undo.py`) já estão implementados e testados, e são reusados como blocos atômicos do pipeline. O que muda é a **camada de orquestração** (`stage.py`, modelos, API) e o **modelo de dados** (de `automation_rules`/`rule_conditions` para `automation_pipelines`/`pipeline_steps`/`step_filters`).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**REDESIGN — Modelo de PIPELINE (2026-06-17) — substitui D-04, D-05 e o acoplamento de D-06**
- **D-12:** Automações = **pipeline ORDENADO de etapas (steps)**. Cada documento passa por **TODAS as etapas cujo filtro casa, na ordem** definida pelo usuário (encadeado), não "primeira que casa vence". (SUBSTITUI D-05.)
- **D-13:** Cada etapa = **um filtro de entrada + UMA ação atômica**. Ações do v1: **Mover** (pasta destino com tokens), **Renomear** (tokens dos campos), **Identificar tipo (gate)** (classifica contra template; porteiro p/ etapas seguintes), **Rotear/decidir tratar** (enviar p/ revisão humana / marcar não-tratar / ignorar). Renomear+mover = duas etapas encadeadas. (SUBSTITUI D-04 e o acoplamento de D-06.)
- **D-14:** **Filtros de entrada** combináveis por etapa: pasta de origem monitorada, tipo de arquivo (extensão), tipo/template classificado, valor de campo extraído, **nome do arquivo, tamanho** (e atributos simples afins).
- **D-15:** A ação **Identificar tipo** REUSA a classificação/extração já existentes (Fases 3/4) — não cria parsers novos. Parser de linha digitável de boleto e afins permanecem na Fase 7.
- **D-16:** **Escopo v1 do pipeline:** ações de arquivo (mover/renomear/rotear) + identificação de tipo como etapa. **Fora do v1:** etapas que extraem campo específico (ex. buscar linha digitável) — Fase 7.

**Disparo da automação (MANTIDO)**
- **D-01:** Auto-aplica para documentos de alta confiança (acima do `review_confidence_threshold` da Fase 5). Baixa confiança / em revisão só aplica **após** aprovação humana.
- **D-02:** Mesmo no auto-aplica, log-antes-de-agir e undo continuam valendo. O auto-aplica só dispensa o clique humano.
- **D-03:** Aplicação disponível **por documento E por lote/execução** (espelha o undo de AUT-05).

**Padrões de nome e pasta (MANTIDO — AUT-01/AUT-02)**
- **D-06:** Padrões usam tokens `{campo}` referenciando os campos extraídos.
- **D-07:** Campo vazio/inválido no padrão → bloqueia e manda pra revisão humana.
- **D-08:** Sanitiza automaticamente caracteres inválidos no Windows e formata datas via sufixo no token (`{data:aaaa-mm}`).

**Política de colisão (MANTIDO — AUT-04)**
- **D-09:** Conteúdo DIFERENTE (mesmo nome) → sufixo incremental automático (`nome_1.pdf`). Nunca sobrescreve.
- **D-10:** Conteúdo IDÊNTICO (mesmo SHA-256 do CAS) → considera já-feito e pula como duplicata.

**Arquivo físico de destino (MANTIDO — D-11)**
- **D-11:** A operação **materializa o destino a partir do CAS** (`cas.read_bytes(content_hash)` → escreve + verifica hash), em vez de mover o original. Comportamento uniforme p/ blocos separados e não-separados. AUT-06 = "materializar do CAS + verificar hash". O caminho de origem resolvido é persistido no `AuditLog` no apply.

### Claude's Discretion
- Comportamento do **undo quando o arquivo de destino já foi alterado** pelo usuário (checagem de integridade + falha controlada, sem corromper estado).
- **Formato/estrutura do audit log** (extensão do `AuditLog` para origem→destino + dados de undo, agora **agrupado por execução do pipeline**).
- **Onde a automação aparece na UI**: nova aba de Automações (construtor de PIPELINE de etapas) + tela de dry-run/preview. Honra o design system travado.
- Mecânica cross-device (AUT-06): copia→verifica(hash)→remove a origem.

### Deferred Ideas (OUT OF SCOPE)
- Automações além de arquivo (chamar API, e-mail/WhatsApp) — fora do v1.
- Etapas que extraem campo específico (linha digitável de boleto etc.) — **Fase 7** (D-16).
- Separação de documentos dirigida por IA e roteamento determinístico de custo (boleto/NF-e sem IA) — Fase 7.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support (modelo de PIPELINE) |
|----|-------------|------------------|
| AUT-01 | Padrões de renomeação com `{campo}` | Ação **Renomear** do step → reusa `naming.resolve_pattern` (já implementado, sanitização D-08). |
| AUT-02 | Padrões de pasta-destino com `{campo}` | Ação **Mover** do step → reusa `naming.resolve_dest_folder` (confinamento V4, já implementado). |
| AUT-03 | Dry-run/preview origem→destino, colisões sinalizadas | `pipeline_dry_run` agora simula o **pipeline inteiro** por documento, resolvendo o caminho-alvo final SEM tocar o disco; sinaliza colisão/bloqueio/skip por step. |
| AUT-04 | Audit log ANTES de agir + anti-colisão | Write-ahead por **execução do pipeline** (`run_id` agrupa os steps de arquivo de um documento); `resolve_collision` já garante nunca-sobrescrever. |
| AUT-05 | Undo por-documento E por-lote/execução | `undo.py` já reverte por-doc e por-run; com o pipeline o undo cobre **todas as etapas de arquivo de um documento** (agrupadas por `run_id`/`pipeline_run_id`). |
| AUT-06 | Cross-device seguro | `fileops.materialize_to_dest`/`safe_move` (EXDEV→copy+fsync+verifica-hash+remove) — já implementado e testado. |
| TPL-02 | Regras condicionais por tipo/cliente/emissor/valor | **Filtros de entrada por step** (D-14) — reusa o avaliador `rules.evaluate_condition` para condições sobre campos extraídos; estende para filtros de pasta/extensão/nome/tamanho/template. |

> **Status no REQUIREMENTS.md:** AUT-01..06 estão marcados "Complete" (modelo de regra-única). O REDESIGN reabre a fase: o critério de aceite agora exige que esses requisitos sejam satisfeitos **através de etapas do pipeline**, não de uma regra única. O replan deve re-verificar cada um sob o novo modelo.
</phase_requirements>

## Summary

O REDESIGN troca a **estrutura de configuração** das automações (de uma regra única que decide nome+pasta para um pipeline ordenado de etapas componíveis) sem mudar a **física da operação de arquivo**, que já está construída e testada. Os três tijolos puros/seguros — `naming.py` (tokens→caminho confinado V4), `fileops.py` (materialização verificada do CAS, anti-colisão, EXDEV) e `undo.py` (reversão por-doc/por-run com fallback CAS) — **permanecem intactos e são reusados como ações atômicas dos steps**. O trabalho do replan concentra-se em (1) um novo modelo de dados de pipeline, (2) um avaliador de **filtros de entrada por step** (generalizando o avaliador de condições existente), (3) uma reescrita do `apply_stage` para **executar o pipeline ordenado por documento** resolvendo o caminho-alvo incrementalmente, e (4) um audit-log/undo agrupado por **execução do pipeline** (não por operação isolada).

A decisão de arquitetura mais importante — e a Open Question principal — é a **semântica do "caminho-alvo" ao longo do pipeline**. A recomendação (HIGH confidence, alinhada a D-11) é: o pipeline **resolve o caminho-alvo em memória** ao passar por etapas Renomear (muda o nome-alvo) e Mover (muda a pasta-alvo), e **materializa do CAS UMA única vez ao final**, quando o documento sai do pipeline com um caminho-alvo final. Isto é estritamente mais seguro e idempotente do que executar uma operação física por etapa: evita N materializações/cópias intermediárias no disco do cliente, evita estados-intermediários órfãos no NTFS, e dá um único par origem→destino por documento para o write-ahead/undo. As etapas Renomear/Mover tornam-se **transformações puras do plano-alvo**; só a saída do pipeline toca o disco.

O segundo eixo é o **gate "Identificar tipo"** (D-15): uma etapa-porteiro que reusa a classificação existente (`classify_stage`, inclusive o caminho `forced_template_id`) para decidir se o documento casa um template-alvo. Combinado com D-12 (passa por todas as etapas cujo filtro casa), o gate é modelado como um **filtro de entrada** das etapas seguintes (`template_id == X`), não como um desvio de fluxo imperativo — mantendo o avaliador puro e o pipeline declarativo.

**Primary recommendation:** Modele o pipeline como `AutomationPipeline 1:N PipelineStep`, cada step com `action_type` (move | rename | identify_type | route) + `params_json` + `filters` (1:N `StepFilter`). O `apply_stage` itera os steps ordenados por `position`, mantém um **plano-alvo em memória** (`(target_folder, target_name)`) mutado pelas ações Renomear/Mover, executa o gate `identify_type` reusando a classificação, aplica `route` como transição de estado, e **materializa do CAS uma vez** quando o plano-alvo final é conhecido — sob o mesmo write-ahead `intent→done`+`run_id` já implementado. Os tijolos `naming`/`fileops`/`undo` **não mudam**. **Resolva a Open Question 1 (composição incremental vs. materialização por etapa) antes de planejar tarefas** — a recomendação é materialização única ao final.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Definição/CRUD do pipeline (steps, filtros, params) | API/Backend (CRUD aninhado) | Database | Espelha `api/templates.py` (1:N aninhado) — config do operador, sem IA |
| Avaliação de filtros de entrada por step (D-14) | API/Backend (módulo puro) | Database (lê `FilledField`, atributos do arquivo) | Determinístico sobre campos extraídos + metadados de arquivo; reusa `rules.evaluate_condition` |
| Resolução incremental do caminho-alvo (Renomear/Mover) | API/Backend (módulo puro) | Database (lê `FilledField`) | Transformação pura do plano-alvo `(folder, name)` — reusa `naming.resolve_pattern`/`resolve_dest_folder` |
| Gate "Identificar tipo" (D-15) | API/Backend (reusa classificação) | OpenAI (só se a classificação precisar de IA) | Reusa `classify_stage` (matcher local custo-0 → IA desempate só se necessário) |
| Ação "Rotear" (revisão/não-tratar/ignorar) | API/Backend (state machine) | — | Transição de estado via `transition` (allowlist) — nunca seta `document.state` direto |
| Materialização física (uma vez ao final) | API/Backend (worker step) | Filesystem/OS + CAS | `fileops.materialize_to_dest` do CAS — já implementado, verifica hash |
| Audit write-ahead + undo do pipeline inteiro | Database / Storage | Filesystem (CAS) | `run_id`/`pipeline_run_id` agrupa todas as operações de um documento; CAS é a rede |
| Dry-run/preview do pipeline | API/Backend (puro) → API | Frontend (render) | Simula o pipeline completo por doc; React renderiza origem→destino-final |
| UI: construtor de pipeline + dry-run | Frontend (SPA Vite) | API/Backend | Token-driven, mesmos padrões TanStack Query das Fases 2/4/5 |

## Standard Stack

### Core

**Nenhuma dependência nova é necessária.** A fase é construída inteiramente sobre a stdlib do Python 3.12 e bibliotecas já presentes no projeto. O REDESIGN não introduz nada novo no stack — só reorganiza a orquestração.

| Lib / Módulo | Origem | Propósito nesta fase | Por que é o padrão |
|--------------|--------|----------------------|--------------------|
| `os`/`shutil`/`pathlib`/`hashlib` | stdlib | Materialização verificada do CAS, EXDEV, anti-colisão (já encapsulados em `fileops.py`) | `os.replace` é a primitiva atômica portável; já em uso no `cas.py` e `fileops.py` `[VERIFIED: backend/app/automation/fileops.py:154]` |
| `SQLAlchemy 2.0` + `Alembic` | já no projeto | Tabelas de pipeline/steps/filtros; migração **0007** (redesenha as tabelas da 0006) | Padrão travado: "Migrações somente via Alembic" `[VERIFIED: backend/alembic/versions/ — 0001..0006 presentes]` |
| `Pydantic 2.13` | já no projeto | Schemas In/Patch/Out do CRUD de pipeline (aninhado: pipeline→steps→filtros) | Espelha `api/automations.py`/`api/templates.py` `[VERIFIED: codebase]` |
| `app/automation/naming.py` | **já implementado** | Ações Renomear (`resolve_pattern`) e Mover (`resolve_dest_folder`, confinamento V4) | Funções puras testadas; reusadas como ações atômicas — NÃO reescrever `[VERIFIED: backend/app/automation/naming.py:156,174]` |
| `app/automation/fileops.py` | **já implementado** | Materialização do CAS + anti-colisão + EXDEV (`materialize_to_dest`, `resolve_collision`, `safe_move`, `remove_original`, `hash_file`) | Máquina segura verify-then-remove; reusada na materialização final — NÃO reescrever `[VERIFIED: backend/app/automation/fileops.py:91,201,244]` |
| `app/automation/undo.py` | **já implementado** | Undo por-doc/por-run com fallback CAS (`undo_document`, `undo_run`, `undo_operation`) | Já reverte por `run_id` agrupando operações; serve ao undo do pipeline inteiro `[VERIFIED: backend/app/automation/undo.py:146,164]` |
| `app/automation/rules.py` | **já implementado** | Avaliador puro de condições (`evaluate_condition`, dispatch por operador, coerção Decimal) | Base do avaliador de **filtros de entrada** (D-14) — estender, não substituir `[VERIFIED: backend/app/automation/rules.py:71]` |
| `app/classification/stage.py` | já no projeto | Gate "Identificar tipo" (D-15) — `classify_stage` + caminho `forced_template_id` | Reuso direto: matcher local custo-0 → IA só em desempate `[VERIFIED: backend/app/classification/stage.py:132,190]` |
| `validation/fields.py`, `dates.py`, `money.py` | já no projeto | Format de `{data:...}` e coerção numérica das condições dos filtros | Reuso direto (já consumido por `naming`/`rules`) `[VERIFIED: codebase]` |

### Supporting (opcional — avaliar, não obrigatório)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathvalidate` | 3.3.1 | Sanitização robusta de nome (nomes reservados Windows, MAX_PATH) | Já coberto à mão em `naming.sanitize_component` (`_WIN_RESERVED`, truncamento). Só considerar se surgir um gap; **recomendação: continuar hand-roll** (já implementado e testado). `[ASSUMED]` — ver Package Legitimacy Audit |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Materialização ÚNICA ao final do pipeline (recomendado) | Operação física por etapa Renomear/Mover | Por-etapa cria N cópias/renames intermediários no NTFS, multiplica janelas de falha parcial, e gera múltiplos pares origem→destino confusos para o undo. Materialização única é mais segura, idempotente e dá 1 par origem→destino-final por doc. **Recomendação forte: materialização única.** (Open Q1.) |
| Gate como **filtro de entrada** das etapas seguintes (recomendado) | Gate como desvio imperativo (`if !match: stop`) | D-12 já diz "passa por todas as etapas cujo filtro casa". Modelar o gate como um filtro `template_id == X` mantém o pipeline declarativo e o avaliador puro; o "porteiro" emerge naturalmente (etapas seguintes filtram pelo template identificado). |
| Estender as tabelas 0006 via nova migração 0007 (recomendado) | Editar a migração 0006 in-place | A 0006 já existe e pode ter sido aplicada em ambientes; **sem dados em prod** (CONTEXT diz que pode redesenhar), mas o padrão Alembic é forward-only: 0007 dropa/redesenha as tabelas de regra e cria as de pipeline. Mantém o histórico de migração íntegro e o `trigger` de `documents` intacto. |
| Linguagem de expressão (eval/AST) p/ filtros | Filtros estruturados (`field/op/value` + tipo de filtro) | Nunca usar `eval` (V5). Os filtros estruturados (D-14) são exatamente o que evita injeção e mantém depurável. |

**Installation:**
```bash
# NENHUMA dependência nova obrigatória. Tudo é stdlib + libs já instaladas + os
# tijolos já implementados (naming/fileops/undo/rules/classify).
```

**Version verification:** Python do projeto: 3.12.x `[VERIFIED: CLAUDE.md TL;DR + research anterior backend/.venv]`. Migrações 0001..0006 presentes em `backend/alembic/versions/` `[VERIFIED: ls]`. `pathvalidate` (opcional) confirmado no PyPI 3.3.1 MIT na pesquisa anterior.

## Package Legitimacy Audit

> slopcheck **não pôde ser instalado** (pip offline no sandbox). A recomendação primária é **zero-dependência nova**; o REDESIGN não adiciona pacotes. Se o planejador optar pela lib opcional `pathvalidate`, ela vira `[ASSUMED]` e exige `checkpoint:human-verify` antes do `uv add`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `pathvalidate` | PyPI | ~10 anos (atual 3.3.1) | alto | github.com/thombashi/pathvalidate (MIT) | indisponível (offline) | **Flagged** — opcional; já coberto por hand-roll em `naming.py`. Se adotada, gate humano. |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none por evidência; `pathvalidate` marcado `[ASSUMED]` só por slopcheck offline.

*A stack desta fase é stdlib-only + código já no projeto; preferir o hand-roll já implementado evita o gate inteiramente.*

## Architecture Patterns

### System Architecture Diagram

```
                  Documento classificado (PROCESSANDO + "classificado")
                  alta confiança → auto-aplica (D-01)  |  pós-aprovação humana
                                    │
                                    ▼
                  ┌──────────────────────────────────────┐
                  │  Worker: step "apply" (fila in-process)│  ← espelha classify dispatch
                  │  enqueue_pending_applications (D-01)   │
                  └──────────────────────────────────────┘
                                    │
                                    ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  apply_stage(session, content_hash, run_id)   [EXECUTA O PIPELINE]      │
   │                                                                        │
   │  IDEMPOTÊNCIA: AuditLog(status="done") p/ este run/doc já existe? no-op │
   │                                                                        │
   │  PLANO-ALVO em memória := (target_folder=base_root, target_name=orig)  │
   │  fields := {field_name: normalized_value}  (campos válidos do doc)      │
   │  file_attrs := {ext, size, source_folder_id, original_filename}        │
   │                                                                        │
   │  PARA CADA step em pipeline.steps ORDENADO por position (D-12):         │
   │    ── filtro de entrada do step casa? (D-14: campo/pasta/ext/nome/      │
   │       tamanho/template) ── NÃO → PULA este step (continua)              │
   │    ── SIM, despacha por action_type (D-13):                             │
   │       • IDENTIFY_TYPE (gate, D-15): classify (reusa classify_stage /    │
   │           forced_template_id); resultado vira atributo "template_id"    │
   │           consumível pelos filtros das etapas seguintes (porteiro)      │
   │       • RENAME: target_name := naming.resolve_pattern(pattern, fields)  │
   │           None (campo faltante) → BLOQUEIA → transition(EM_REVISAO) D-07 │
   │       • MOVE: target_folder := naming.resolve_dest_folder(pat, fields,  │
   │           base_root)  None (confinamento V4 / campo faltante) → BLOQUEIA │
   │       • ROUTE: transition(EM_REVISAO | marca não-tratar/ignorar) e SAI   │
   │                                                                        │
   │  ── pipeline terminou com plano-alvo final (folder/target_name)?        │
   │     dest := target_folder / target_name                                │
   │     ── DRY-RUN? → retorna o preview (source→dest, colisão) SEM disco    │
   │     ── anti-colisão (resolve_collision): idêntico → skip (D-10);        │
   │        diferente → sufixo _1/_2 (D-09)                                  │
   │     ── WRITE-AHEAD: AuditLog(status="intent", src, dest, run_id,        │
   │        content_hash) + commit  ── ANTES de tocar o disco (AUT-04)       │
   │     ── materialize_to_dest(content_hash, dest) do CAS + verifica hash   │  ← UMA vez (D-11)
   │     ── remove_original(source) só após verificar (AUT-06 crit 5)        │
   │     ── audit.status="done" + transition(CONCLUIDO) [1 commit]           │
   └──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
            CAS (SHA-256) preserva o conteúdo original PARA SEMPRE — rede de undo
                                    │
                                    ▼
        UNDO (por-doc ou por-run/pipeline-run): undo.undo_document/undo_run
        reverte dst→origem (ou restaura do CAS); CONCLUIDO→PROCESSANDO; status=undone
```

### Recommended Project Structure
```
backend/app/
├── automation/
│   ├── rules.py            # MANTÉM avaliador puro; ESTENDE p/ filtros de entrada (D-14)
│   │                       #   (novos tipos de filtro: pasta-origem, extensão, nome, tamanho, template)
│   ├── naming.py           # INALTERADO — resolve_pattern / resolve_dest_folder (ações Rename/Move)
│   ├── fileops.py          # INALTERADO — materialize_to_dest / resolve_collision / safe_move
│   ├── undo.py             # INALTERADO (ou pequeno ajuste de agrupamento por pipeline_run)
│   ├── pipeline.py         # NOVO: executor PURO do pipeline → resolve plano-alvo + decisões (testável sem disco)
│   └── stage.py            # REESCRITO: apply_stage executa o pipeline ordenado + materializa 1x
├── models/
│   ├── audit_log.py        # MANTÉM colunas write-ahead (status/src/dst/run_id/content_hash);
│   │                       #   considerar pipeline_run_id (alias de run_id) p/ agrupar o pipeline inteiro
│   └── automation_pipeline.py  # NOVO: AutomationPipeline + PipelineStep + StepFilter (substitui automation_rule.py)
├── api/
│   └── automations.py      # REESCRITO: CRUD de pipeline/steps/filtros + dry-run/apply/undo (ações preservadas)
└── alembic/versions/
    └── 0007_automation_pipeline.py  # NOVO: dropa automation_rules/rule_conditions, cria pipeline/steps/filters
                                     #   NÃO toca `documents` (trigger trg_documents_updated_at intacto)
```

### Pattern 1: Pipeline como executor PURO + materialização única (NOVO — coração do REDESIGN)
**What:** Separar a EXECUÇÃO LÓGICA do pipeline (puro, sem disco) da MATERIALIZAÇÃO FÍSICA (uma vez, ao final). O executor puro recebe `(steps, fields, file_attrs)` e devolve uma **decisão**: ou um plano-alvo final `(target_folder, target_name)`, ou um sinal de bloqueio (D-07), ou um sinal de roteamento (EM_REVISAO/não-tratar/ignorar).
**When to use:** Sempre — é o que torna o pipeline testável sem tocar o disco (dry-run = chamar o executor puro e parar antes da materialização) e idempotente.
```python
# backend/app/automation/pipeline.py (NOVO, PURO)
# @dataclass PipelinePlan: target_folder: Path|None, target_name: str|None,
#                          blocked: bool, route_to: str|None, identified_template_id: int|None
#
# def run_pipeline(steps, fields, file_attrs, *, base_root, classify_fn) -> PipelinePlan:
#     folder = base_root.resolve(); name = file_attrs["original_filename"]
#     identified = None
#     for step in sorted(steps, key=lambda s: s.position):       # D-12 ordem
#         if not filter_matches(step.filters, step.conjunction, fields, file_attrs, identified):
#             continue                                            # filtro não casa → pula
#         if step.action_type == "identify_type":
#             identified = classify_fn(step.params["template_id"])  # gate (D-15)
#             file_attrs["template_id"] = identified
#         elif step.action_type == "rename":
#             name = naming.resolve_pattern(step.params["name_pattern"], fields)
#             if name is None: return PipelinePlan(blocked=True)   # D-07
#         elif step.action_type == "move":
#             folder = naming.resolve_dest_folder(step.params["folder_pattern"], fields, base_root=base_root)
#             if folder is None: return PipelinePlan(blocked=True) # D-07 / V4
#         elif step.action_type == "route":
#             return PipelinePlan(route_to=step.params["target"]) # em_revisao / nao_tratar / ignorar
#     return PipelinePlan(target_folder=folder, target_name=name, identified_template_id=identified)
```
**Por quê materialização única (Open Q1):** Cada etapa Rename/Move muda só o **plano-alvo em memória**. O disco só é tocado quando o pipeline produz um caminho-alvo final — uma única `materialize_to_dest`. Isso elimina N operações físicas, N janelas de falha e N pares no audit. **Recomendação HIGH.**

### Pattern 2: Filtros de entrada por step (NOVO — generaliza o avaliador de regras, D-14)
**What:** Cada step tem 0..N filtros combinados por `conjunction` (and/or). Cada filtro é estruturado (`filter_type`, `operator`, `value`) — **sem eval**. O avaliador despacha por `filter_type`:
- `field` — reusa `rules.evaluate_condition` EXATAMENTE (campo extraído `{campo}[op]valor`, coerção Decimal/data);
- `source_folder` — `file_attrs["source_folder_id"]` == valor (pasta monitorada de origem);
- `extension` — `file_attrs["ext"]` casa (ex.: `.pdf`, `.jpg`); case-insensitive;
- `filename` — nome do arquivo (`contains`/`eq` sobre `original_filename`);
- `size` — `file_attrs["size"]` `gt`/`lt` valor (coerção numérica, Pitfall 2);
- `template` — `identified_template_id` == valor (porteiro do gate, D-15).
**When to use:** Em todo step. Step sem filtros = casa sempre (aplica-se a todo documento).
```python
# Estende rules.py: reusa evaluate_condition p/ filter_type="field"; novos ramos
# para os demais. NUNCA eval. Filtro desconhecido → não casa (falha fechada, V5).
def filter_matches(filters, conjunction, fields, file_attrs, identified_template_id) -> bool:
    if not filters:
        return True                                  # sem filtro = aplica-se a tudo
    results = (evaluate_filter(f, fields, file_attrs, identified_template_id) for f in filters)
    return any(results) if conjunction == "or" else all(results)
```
**Anti-pattern:** Materializar o "tamanho" lendo o disco a cada filtro — ler `file_attrs["size"]` uma vez (do CAS/`os.stat` da origem) e passar adiante; o avaliador é puro.

### Pattern 3: Gate "Identificar tipo" reusa a classificação (D-15)
**What:** A etapa `identify_type` chama a classificação já existente para decidir o template. Reusa `classify_stage` (matcher local custo-0; IA só em desempate) ou, quando o operador trava o template-alvo no step, o caminho `forced_template_id` (já implementado em `classify_stage`, linha 190). O resultado (`template_id`) vira um atributo consumível pelos **filtros `template`** das etapas seguintes (o porteiro de D-12).
**When to use:** Quando o pipeline precisa decidir/confirmar o tipo no meio do fluxo. Se o doc já está classificado (caminho normal), o gate pode só LER o `ClassificationResult` existente (custo 0) em vez de re-classificar.
```python
# Reuso: se o doc JÁ tem ClassificationResult, o gate lê template_id existente (custo 0).
#        Só re-classifica/força quando o step pede um template específico ainda não confirmado.
# NUNCA cria parser novo (D-15) — linha digitável de boleto etc. = Fase 7 (D-16).
```
**Cuidado de custo (LGPD/tokens):** o gate NÃO deve re-cobrar a IA se a classificação já existe — espelhar a idempotência do `classify_stage` (`ClassificationResult` existente → no-op).

### Pattern 4: Stage com persistência atômica num único commit (REUSAR — INALTERADO)
**What:** O `apply_stage` continua seguindo a forma de `classify_stage`: idempotente, write-ahead `intent→done`, persistência via `transition` (commit único). O REDESIGN só muda **o que** se resolve antes da materialização (o pipeline, não uma regra única).
**Atenção crítica:** NUNCA `session.commit()` manual antes de um `transition` `[VERIFIED: backend/app/automation/stage.py:440]`.

### Pattern 5: Audit write-ahead agrupado por execução do pipeline (AUT-04/AUT-05)
**What:** Como a materialização é única por documento (Pattern 1), há **um** `AuditLog(intent→done)` por documento por execução, agrupado pelo `run_id` do lote. O undo do "pipeline inteiro" de um documento é então o undo de seus `AuditLog(status="done")` — já coberto por `undo.undo_document` (seleciona todos os `done` do doc) e `undo.undo_run` (por `run_id`).
**Nota sobre múltiplas operações:** se o planejador escolher materialização por-etapa (NÃO recomendado), aí sim haveria N AuditLogs por doc e seria necessário um `pipeline_run_id` distinto do `run_id` de lote para agrupar as etapas de UM documento. Com materialização única, `run_id` (lote) + `document_id` já agrupam corretamente — `undo.py` não precisa mudar.

### Anti-Patterns to Avoid
- **Materializar por etapa:** multiplica janelas de falha e confunde o undo (ver Pattern 1).
- **Gate como desvio imperativo:** modelar como filtro mantém o pipeline declarativo e testável.
- **Sobrescrever silenciosamente:** anti-colisão é a montante (`resolve_collision`); `os.replace` sobrescreve por design. (INALTERADO — já tratado em `fileops.py`.)
- **`document.state = ...` direto:** sempre via `transition` (allowlist) `[VERIFIED: backend/app/queue/worker.py:106]`.
- **Re-cobrar a IA no gate:** se `ClassificationResult` já existe, ler em vez de re-classificar (custo/LGPD).
- **Comparar `>`/`<` de moeda/tamanho como string:** coerção Decimal obrigatória nos filtros numéricos (Pitfall 2 — já tratado em `rules._as_decimal`).
- **Editar a migração 0006 in-place:** criar 0007 forward-only (dropa regras, cria pipeline); não tocar `documents`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Resolução de tokens→caminho + sanitização Windows | novo resolver | `automation/naming.py` (já implementado) | Confinamento V4, reservados, MAX_PATH, `{data:fmt}` já cobertos e testados |
| Materialização verificada do CAS / EXDEV / anti-colisão | nova máquina de arquivo | `automation/fileops.py` (já implementado) | Verify-then-remove, copy+fsync+hash, sufixo D-09/skip D-10 — já testados |
| Undo por-doc/por-run + fallback CAS | nova reversão | `automation/undo.py` (já implementado) | Já agrupa por `run_id`, restaura do CAS quando o destino sumiu |
| Avaliador de condições sobre campos (`field` filter) | novo dispatch | `automation/rules.evaluate_condition` (já implementado) | Coerção Decimal/data, dispatch por operador sem eval — só ESTENDER para os novos tipos de filtro |
| Decisão de tipo no gate | novo classificador/parser | `classification/stage.classify_stage` (+ `forced_template_id`) | D-15 manda reusar; parser de boleto etc. = Fase 7 |
| Recuperação do conteúdo original | backup paralelo | CAS (`cas.read_bytes`) | Rede imutável já existente |

**Key insight:** O REDESIGN é uma mudança de **orquestração e modelo de dados**, não de física. Toda a parte perigosa (tocar o NTFS sob falha parcial) já está construída, testada e **não muda**. O valor do replan é montar o pipeline declarativo por cima dos tijolos existentes, com materialização única ao final.

## Runtime State Inventory

> Fase de **efeito sobre o filesystem do cliente** + **reestruturação de modelo de dados** (regras → pipeline). Cobre tanto o estado de runtime quanto a migração de schema.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | (1) `automation_rules` + `rule_conditions` (criadas na 0006) — **sem dados em prod** (CONTEXT autoriza redesenhar). (2) `AuditLog` estendido (status/src/dst/run_id/content_hash) — **MANTÉM** (write-ahead/undo independem do modelo de regra/pipeline). (3) `ClassificationResult`/`FilledField` — fonte dos tokens e do gate. (4) `IngestedOriginal.source_folder_id`→`WatchedFolder.path` — reconstrói o caminho de origem (+ filtro `source_folder`, D-14). | Migração **0007**: DROP `automation_rules`/`rule_conditions`, CREATE `automation_pipelines`/`pipeline_steps`/`step_filters`. NÃO tocar `audit_log` nem `documents`. |
| Live service config | Nenhuma. Single-tenant, fila in-process SQLite, sem broker. | None — verificado. |
| OS-registered state | O arquivo FÍSICO do cliente no NTFS é o estado mutável crítico. Após materializar, o destino pode ser mexido pelo usuário (undo checa integridade). | INALTERADO pelo REDESIGN — `fileops`/`undo` já tratam. |
| Secrets/env vars | `review_confidence_threshold` (auto-aplica D-01); `automation_dest_root` (base de confinamento V4, `stage._base_root`). Nenhum segredo novo. | None — reusa config da Fase 5/6 `[VERIFIED: backend/app/automation/stage.py:170]`. |
| Build artifacts | Nenhum compilado. CAS blobs imutáveis crescem (rede). O `apply` step e os sweeps no `worker.py` já referenciam `APPLY_STEP`/`enqueue_pending_applications` — **permanecem válidos** (o contrato do step não muda, só o que `apply_stage` faz por dentro). | None. |

**A pergunta canônica respondida:** depois de aplicar o pipeline e mover/renomear o arquivo, o que ainda tem estado antigo? **(1)** o `AuditLog` guarda o caminho de origem resolvido no momento do apply (já persistido — D-11/risco A2 resolvido); **(2)** o CAS mantém o conteúdo por hash; **(3)** as tabelas `automation_rules`/`rule_conditions` ficam órfãs após a 0007 (dropadas). Nenhum runtime externo guarda o modelo de regra antigo.

## Common Pitfalls

> Os pitfalls de operação de arquivo (1, 3, 4, 5, 6, 7) **permanecem válidos e já estão tratados** nos tijolos (`fileops.py`/`naming.py`). Listados resumidamente; os novos pitfalls do pipeline (8, 9, 10) recebem detalhe.

### Pitfall 1 (MANTIDO): `os.replace` sobrescreve — anti-colisão a montante
Tratado em `fileops.resolve_collision` (sufixo D-09 / skip D-10 antes de qualquer escrita). Teste: dois docs diferentes para o mesmo padrão → ambos sobrevivem.

### Pitfall 2 (MANTIDO): comparação numérica/data como string
Tratado em `rules._as_decimal` (coerção Decimal; data ISO já ordenável). **Aplica-se agora também ao filtro `size`** (tamanho do arquivo) — coerção numérica obrigatória.

### Pitfall 3 (MANTIDO): EXDEV (errno 18) cross-device
Tratado em `fileops` (`materialize_to_dest` do CAS torna cross-device um não-caso especial — a verificação de hash é a salvaguarda). Teste com mounts/temp dirs distintos.

### Pitfall 4 (MANTIDO): nomes reservados Windows
Tratado em `naming.sanitize_component` (`_WIN_RESERVED` CON/PRN/NUL/COM1…). Teste com campo que normaliza para `NUL`.

### Pitfall 5 (MANTIDO): MAX_PATH 260
Tratado em `naming.sanitize_component` (truncamento preservando extensão, teto da config). Teste com caminho > 260.

### Pitfall 6 (MANTIDO): lock de arquivo Windows (WinError 32)
Tratado: `safe_move`/materialização propagam `PermissionError` como FALHA retryável; o worker roteia. Não corrompe.

### Pitfall 7 (MANTIDO): crash entre intent e done
Tratado em `stage.reconcile_orphans` (startup do worker; destino íntegro → done, senão → orphaned). **Com materialização única, há um intent por doc por run — a reconciliação não muda.**

### Pitfall 8 (NOVO): ordem dos steps importa — Renomear depois de Mover vs. antes
**What goes wrong:** Se o usuário ordena Mover antes de Renomear, o caminho-alvo evolui pasta→nome; ordenar Renomear antes de Mover evolui nome→pasta. Com materialização por-etapa isso geraria arquivos intermediários; com materialização única (recomendada) a ORDEM só afeta o plano em memória — o resultado final é o mesmo conjunto `(folder, name)` desde que cada ação seja idempotente sobre seu eixo.
**Why it happens:** D-12 (ordem definida pelo usuário) + duas ações que mutam eixos diferentes do plano-alvo.
**How to avoid:** Manter o plano-alvo como `(target_folder, target_name)` independentes; Rename só toca `target_name`, Move só toca `target_folder`. A ordem entre eles não muda o destino final (materialização única). Documentar isso para a UI (o usuário pode pôr Renomear e Mover em qualquer ordem relativa).
**Warning signs:** Teste: pipeline [Move, Rename] e [Rename, Move] produzem o MESMO destino final.

### Pitfall 9 (NOVO): step "Rotear" deve interromper o pipeline
**What goes wrong:** Se um step `route` (enviar a revisão / não-tratar / ignorar) não interrompe o pipeline, etapas seguintes de arquivo podem materializar um documento que deveria ter sido desviado.
**Why it happens:** `route` é uma decisão terminal de fluxo, não uma transformação do plano-alvo.
**How to avoid:** No executor puro, `route` retorna imediatamente um `PipelinePlan(route_to=...)` — o `apply_stage` aplica a transição (EM_REVISAO via `transition`) ou marca não-tratar/ignorar e **NÃO materializa**. Confirmar no plan a semântica de "não-tratar"/"ignorar" (provavelmente um estado/marcador, não um DocState novo — manter o enum enxuto).
**Warning signs:** Teste: pipeline [Move, Route→revisão, Rename] → doc vai a EM_REVISAO e NÃO é materializado.

### Pitfall 10 (NOVO): filtro que casa em NENHUM step ⇒ documento sem destino
**What goes wrong:** Se nenhum step casa (todos os filtros falham), o pipeline termina sem mutar o plano-alvo. Com o default (`base_root` + nome original), o doc seria materializado para a raiz — pode não ser o desejado.
**Why it happens:** D-12 diz "passa por todas as etapas cujo filtro casa" — pode ser zero.
**How to avoid:** Decisão de produto a confirmar no plan: documento que não casa NENHUM step deve (a) ficar na raiz organizada (default atual), (b) ir a EM_REVISAO, ou (c) ser ignorado. Recomendação: tratar "nenhum step casou" como no-op explícito (não materializa, conclui logicamente OU permanece para revisão) — evitar materializar silenciosamente para a raiz. **Open Question.**
**Warning signs:** Teste: doc cujos atributos não casam nenhum filtro → comportamento explícito e documentado.

## Code Examples

### Modelo de dados do pipeline (NOVO — substitui automation_rule.py)
```python
# backend/app/models/automation_pipeline.py (NOVO)
# AutomationPipeline 1:N PipelineStep 1:N StepFilter (espelha Template→Field, cascade)
#
# class AutomationPipeline(Base):
#     __tablename__ = "automation_pipelines"
#     id; name (str); active (bool, default True); created_at; updated_at
#     steps: list[PipelineStep]  (cascade="all, delete-orphan")
#
# class PipelineStep(Base):
#     __tablename__ = "pipeline_steps"
#     id; pipeline_id (FK CASCADE, index)
#     position (Integer, index)                       # ordem D-12
#     action_type (str)  # "move" | "rename" | "identify_type" | "route"  (D-13)
#     conjunction (str, default "and")                # combinação dos filtros do step (D-14)
#     params_json (Text)  # ação: {"folder_pattern": ...} | {"name_pattern": ...}
#                         #       | {"template_id": N} | {"target": "em_revisao"|"nao_tratar"|"ignorar"}
#     filters: list[StepFilter]  (cascade="all, delete-orphan")
#
# class StepFilter(Base):
#     __tablename__ = "step_filters"
#     id; step_id (FK CASCADE, index)
#     filter_type (str)  # "field" | "source_folder" | "extension" | "filename" | "size" | "template" (D-14)
#     operator (str)     # eq | gt | lt | contains   (reusa o vocabulário de rules.py)
#     value (str)        # alvo da comparação
#     field_name (str|None)  # só p/ filter_type="field": qual campo extraído
#     position (Integer, default 0)
```

### Migração Alembic 0007 (esqueleto) — dropa regras, cria pipeline
```python
# backend/alembic/versions/0007_automation_pipeline.py (NOVO)
# down_revision = "0006"
# CAVEAT: NÃO tocar `documents` → trigger trg_documents_updated_at (0002) intacto.
#         NÃO tocar `audit_log` → as colunas write-ahead da 0006 permanecem.
def upgrade() -> None:
    # Sem dados em prod (CONTEXT): as tabelas de regra da 0006 são redesenhadas.
    op.drop_table("rule_conditions")
    op.drop_table("automation_rules")
    op.create_table("automation_pipelines", ...)   # name, active, timestamps
    op.create_table("pipeline_steps", ...)          # pipeline_id, position(idx), action_type, conjunction, params_json
    op.create_table("step_filters", ...)            # step_id, filter_type, operator, value, field_name, position
    op.create_index("ix_pipeline_steps_position", "pipeline_steps", ["pipeline_id", "position"])

def downgrade() -> None:
    op.drop_table("step_filters")
    op.drop_table("pipeline_steps")
    op.drop_table("automation_pipelines")
    op.create_table("automation_rules", ...)        # recria a forma da 0006
    op.create_table("rule_conditions", ...)
```

### Resolução de plano-alvo (Renomear/Mover) — REUSO de naming (INALTERADO)
```python
# As ações Rename/Move chamam EXATAMENTE as funções já implementadas:
#   target_name   = naming.resolve_pattern(name_pattern, fields)        # None → D-07 bloqueia
#   target_folder = naming.resolve_dest_folder(folder_pattern, fields, base_root=base)  # None → D-07/V4
# Nada a reimplementar; o pipeline só ORQUESTRA a ordem dessas chamadas.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Regra única (condição→nome+pasta, 1ª que casa vence) | **Pipeline ordenado de steps componíveis** (D-12, passa por todas que casam) | 2026-06-17 (REDESIGN) | Reescreve modelo de dados (0007), `stage.py`, `api/automations.py`; tijolos `naming`/`fileops`/`undo` intactos |
| `name_pattern`+`folder_pattern` acoplados numa regra | Ações **Renomear** e **Mover** como steps separados encadeáveis | 2026-06-17 | Plano-alvo `(folder, name)` mutado por etapas independentes; materialização única ao final |
| Sub-templates por emissor (Fase 4 original) | Filtros de entrada por step (D-14) sobre campos/pasta/extensão/template | 2026-06-16/17 | O que variava era a automação por etapa; modelado como filtro, não template |
| `os.rename` | `os.replace`/`materialize_to_dest` do CAS | já adotado | Inalterado pelo REDESIGN |

**Deprecated/outdated:**
- Modelo `automation_rules`/`rule_conditions` (0006): substituído por `automation_pipelines`/`pipeline_steps`/`step_filters` (0007).
- `first_matching_rule` (primeira-que-casa-vence): substituído por iteração ordenada com filtro por step (D-12). O avaliador `evaluate_condition` permanece (vira o filtro `field`).
- `api/automations.py` CRUD de regras: vira CRUD de pipeline/steps/filtros (ações dry-run/apply/undo preservadas).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Sem dados em prod nas tabelas `automation_rules`/`rule_conditions` (a 0007 pode dropar) | Migração 0007 | Baixo — CONTEXT autoriza redesenhar a 0006; se houver dados de teste, são descartáveis |
| A2 | Materialização ÚNICA ao final é mais segura/idempotente que por-etapa | Pattern 1 / Open Q1 | Médio — é a recomendação; se o produto exigir efeito físico visível por etapa, reavaliar (improvável p/ rename/move) |
| A3 | O gate "Identificar tipo" pode LER o `ClassificationResult` existente (custo 0) na maioria dos casos | Pattern 3 | Baixo — o doc chega ao apply já classificado; re-classificar só quando o step força um template não confirmado |
| A4 | "não-tratar"/"ignorar" do step Rotear são marcadores/no-op, não novos DocState | Pitfall 9 | Médio — manter o enum enxuto; o plan confirma a representação (marcador interno vs. estado) |
| A5 | `run_id` (lote) + `document_id` agrupam o undo do pipeline inteiro sem precisar de `pipeline_run_id` distinto | Pattern 5 | Baixo — verdadeiro SE materialização única (1 audit por doc/run); por-etapa exigiria coluna nova |
| A6 | O filtro `size` lê `os.stat`/CAS uma vez (atributo do arquivo), não a cada filtro | Pattern 2 | Baixo — detalhe de performance, não corretude |

## Open Questions

1. **Semântica do caminho-alvo no pipeline: composição incremental (materialização única) vs. operação física por etapa?** (PRINCIPAL — decide o design)
   - **O que sabemos:** D-11 já trava que a operação materializa do CAS e verifica hash; `fileops.materialize_to_dest` faz isso uma vez. As ações Rename/Move mutam eixos independentes do plano-alvo (`name` vs. `folder`).
   - **O que não está claro:** O pipeline deve executar uma operação física a CADA etapa de arquivo, ou resolver o plano-alvo final em memória e materializar UMA vez?
   - **Recommendation (HIGH):** **Materialização única ao final.** Cada etapa Rename/Move é uma transformação pura do plano-alvo `(folder, name)`; o disco só é tocado quando o pipeline produz o caminho-alvo final (uma `materialize_to_dest` + um `AuditLog intent→done`). Mais seguro, idempotente, e o undo (`undo.py`) não precisa mudar. Decisão a confirmar no plan, mas com viés forte para esta opção.

2. **Documento que não casa NENHUM step** (Pitfall 10)
   - **O que sabemos:** D-12 permite zero etapas casando.
   - **O que não está claro:** Materializar para a raiz default, ir a EM_REVISAO, ou ignorar?
   - **Recommendation:** Tratar como no-op explícito (não materializar silenciosamente para a raiz). Confirmar no plan; provável: concluir logicamente sem mover, OU manter para revisão se o produto exigir que todo doc tenha destino.

3. **Representação de "não-tratar"/"ignorar" do step Rotear** (Pitfall 9 / A4)
   - **O que sabemos:** O enum `DocState` é deliberadamente enxuto (RECEBIDO/PROCESSANDO/EM_REVISAO/CONCLUIDO/QUARENTENA/FALHA). "Enviar a revisão" mapeia a EM_REVISAO (aresta existe).
   - **O que não está claro:** "não-tratar"/"ignorar" são um novo estado, um marcador interno (`last_completed_step`), ou um campo no documento?
   - **Recommendation:** Usar um marcador interno / campo dedicado, NÃO um novo DocState — preservar o enum enxuto. O plan define. "Enviar a revisão" reusa `transition(EM_REVISAO)`.

4. **Gate `identify_type`: quando re-classificar vs. ler o resultado existente** (A3)
   - **O que sabemos:** `classify_stage` é idempotente e tem o caminho `forced_template_id`.
   - **O que não está claro:** O step sempre confia no `ClassificationResult` existente, ou pode forçar uma re-classificação contra um template específico do step?
   - **Recommendation:** Ler o `ClassificationResult` existente por padrão (custo 0); só usar `forced_template_id` quando o step explicitamente trava um template-alvo ainda não confirmado. Nunca re-cobrar a IA se já há classificação (idempotência/LGPD).

5. **Undo quando o destino foi alterado pelo usuário** (MANTIDO — Claude's Discretion)
   - **O que sabemos:** `undo.undo_operation` já restaura do CAS quando o destino sumiu/mudou (`undone_from_cas`).
   - **Recommendation:** Manter o comportamento já implementado — checa integridade do destino; bate → reverte; sumiu/mudou → restaura do CAS. Falha controlada, nunca perda. Inalterado pelo REDESIGN.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python stdlib (`os`,`shutil`,`hashlib`,`pathlib`) | Toda a fase (via tijolos já implementados) | ✓ | 3.12.x | — |
| SQLAlchemy 2.0 + Alembic | Migração 0007 + modelos de pipeline | ✓ | já instalado | — |
| CAS / hashing do projeto | Materialização D-11, undo, D-10 | ✓ | `storage/cas.py`, `fileops.py` | — |
| `automation/naming.py`, `fileops.py`, `undo.py`, `rules.py` | Ações atômicas + filtros | ✓ | **já implementados e testados** | — |
| `classification/stage.py` (`classify_stage`, `forced_template_id`) | Gate "Identificar tipo" (D-15) | ✓ | já implementado | — |
| `validation/*` (dates/money/fields) | Tokens + filtros numéricos | ✓ | já instalado | — |
| Ambiente Windows real para teste NTFS | Pitfalls 1,3,5,6 (já tratados nos tijolos) | ✗ (dev em WSL2/Linux) | — | Testar EXDEV/colisão com temp dirs; testes Windows-only marcados p/ verificação manual |

**Missing dependencies with no fallback:** Nenhuma bloqueia a fase. Testes Windows-only (lock/MAX_PATH/reservados) cobertos por testes da LÓGICA + verificação manual no cliente Windows.
**Missing dependencies with fallback:** `pathvalidate` (opcional) → hand-roll já presente em `naming.py`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio `[VERIFIED: backend/tests/, conftest.py]` |
| Config file | `backend/tests/conftest.py` (fixtures de sessão/engine SQLite em memória) |
| Quick run command | `cd backend && . .venv/bin/activate && pytest tests/automation -x -q` |
| Full suite command | `cd backend && . .venv/bin/activate && pytest -q` |

### Phase Requirements → Test Map (modelo de PIPELINE)
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TPL-02/D-14 | filtros por step (field/source_folder/extension/filename/size/template) + and/or | unit | `pytest tests/automation/test_pipeline.py -k filter -x` | ❌ Wave 0 |
| D-12 | pipeline passa por TODAS as etapas cujo filtro casa, em ORDEM | unit | `pytest tests/automation/test_pipeline.py -k ordering -x` | ❌ Wave 0 |
| D-13 | despacho por action_type (move/rename/identify_type/route) | unit | `pytest tests/automation/test_pipeline.py -k actions -x` | ❌ Wave 0 |
| Pitfall 8 | [Move,Rename] e [Rename,Move] → MESMO destino final (materialização única) | unit | `pytest tests/automation/test_pipeline.py -k order_independent -x` | ❌ Wave 0 |
| Pitfall 9 | step Route interrompe o pipeline e NÃO materializa | unit | `pytest tests/automation/test_pipeline.py -k route_stops -x` | ❌ Wave 0 |
| Pitfall 10 | nenhum step casa → comportamento explícito (no-op/revisão) | unit | `pytest tests/automation/test_pipeline.py -k no_match -x` | ❌ Wave 0 |
| D-15 | gate identify_type reusa classificação; NÃO re-cobra IA se já classificado | unit | `pytest tests/automation/test_pipeline.py -k gate -x` | ❌ Wave 0 |
| AUT-01/D-07 | ação Rename: token faltante → bloqueia → EM_REVISAO | unit | `pytest tests/automation/test_naming.py -x` (existente, mantido) | ✅ (tijolo) |
| AUT-02/V4 | ação Move: confinamento sob base_root | unit | `pytest tests/automation/test_naming.py -k folder -x` | ✅ (tijolo) |
| AUT-03 | dry-run simula o pipeline inteiro sem tocar disco | unit | `pytest tests/automation/test_stage.py -k dry_run -x` | ❌ atualizar |
| AUT-04/D-09/D-10 | write-ahead + anti-colisão sufixo/skip | unit | `pytest tests/automation/test_fileops.py -x` | ✅ (tijolo) |
| AUT-05 | undo por-doc e por-run cobre a materialização do pipeline | unit | `pytest tests/automation/test_undo.py -x` | ✅ (tijolo) |
| AUT-06 | cross-device verify-then-remove (EXDEV) | unit | `pytest tests/automation/test_fileops.py -k cross_device -x` | ✅ (tijolo) |
| AUT-04/Pitfall 7 | crash entre intent/done → reconciliação no startup | unit | `pytest tests/automation/test_stage.py -k reconcile -x` | ✅ atualizar |
| API | CRUD pipeline/steps/filtros (409/422/404) + dry-run/apply/undo | integration | `pytest tests/test_api_automations.py -x` | ❌ reescrever |
| Migração | 0007 dropa regras, cria pipeline; trigger de documents intacto | unit | `pytest tests/test_migrations.py -x` | ❌ atualizar |

### Sampling Rate
- **Per task commit:** `pytest tests/automation -x -q`
- **Per wave merge:** `pytest -q` (suite completa)
- **Phase gate:** Suite verde + verificação manual no Windows (lock/MAX_PATH/reservados) antes de `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/automation/test_pipeline.py` — **NOVO**: executor puro do pipeline (filtros D-14, ordem D-12, ações D-13, gate D-15, Pitfalls 8/9/10)
- [ ] `tests/automation/test_stage.py` — **ATUALIZAR**: `apply_stage` executa o pipeline, dry-run do pipeline inteiro, reconciliação
- [ ] `tests/test_api_automations.py` — **REESCREVER**: CRUD de pipeline/steps/filtros (espelha `test_api_templates.py`)
- [ ] `tests/test_migrations.py` — **ATUALIZAR**: cobrir 0007 (drop regras + create pipeline; documents intacto)
- [ ] `tests/automation/test_naming.py`, `test_fileops.py`, `test_undo.py`, `test_rules.py` — **MANTIDOS** (tijolos inalterados); `test_rules.py` ganha casos dos novos tipos de filtro
- [ ] `tests/automation/conftest.py` — estender fixtures: pipeline com steps/filtros; doc com `file_attrs` (ext/size/source_folder)

## Security Domain

> `security_enforcement: true`, ASVS level 1, block_on: high `[VERIFIED: research anterior / .planning/config.json]`. As mitigações de arquivo já estão implementadas nos tijolos; o REDESIGN adiciona superfície na configuração do pipeline (filtros/params).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | App single-tenant local; sem contas |
| V3 Session Management | no | Idem |
| V4 Access Control | yes | **Path traversal** via tokens `{campo}` (valores da IA/documento). `naming.resolve_dest_folder` confina o destino sob `base_root` via `is_relative_to` (já implementado). **Inalterado** — a ação Move reusa essa função. |
| V5 Input Validation | yes | Filtros e params do step são input do operador; filtros são **dados estruturados** (`filter_type`/`operator`/`value`) — **sem eval**. `operator`/`action_type`/`filter_type` validados contra conjuntos explícitos (422 fora deles). Valores de campo (IA) tratados como não-confiáveis ao virar caminho (V4). |
| V6 Cryptography | no | SHA-256 é integridade/dedup (hashlib stdlib) |
| V7/V9 Logging | yes | **Não vazar conteúdo do documento em log** — padrão já estabelecido (`stage`/`naming`/`rules` logam só metadados: ids/paths/status, nunca valores de campo). O audit guarda paths (necessário ao undo), não os campos sensíveis. |

### Known Threat Patterns for Python file-ops + Windows (pipeline)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via campo extraído (`{cliente}` = `..\..\Windows`) | Elevation / Tampering | `naming.sanitize_component` + confinamento `is_relative_to(base_root)` (já implementado) |
| Sobrescrita destrutiva | Tampering / Denial | `resolve_collision` a montante (D-09) + CAS como rede (já implementado) |
| Symlink/junction no destino | Tampering | Não seguir symlinks; checar `is_symlink()` (padrão de `watched_folders.py`) |
| TOCTOU colisão→materializa | Tampering | Write-ahead reconciliável + criação verificada (já implementado) |
| Perda por crash mid-apply | Denial / data loss | Write-ahead + CAS + `reconcile_orphans` (já implementado) |
| Injeção via `action_type`/`filter_type`/`operator` desconhecido | Tampering | Dispatch explícito + validação contra conjuntos (falha fechada, V5) — **novo na superfície do pipeline** |
| ReDoS em filtro (se houver operador regex) | Denial | Não há operador regex no v1; se adicionado, teto de tamanho (`validation/fields._MAX_REGEX_LEN`) |

**Nota:** o vetor DOMINANTE continua sendo **integridade/perda de dados** (Tampering/Denial). O REDESIGN adiciona uma superfície menor de **validação de configuração** (filtros/params/action_type) — mitigada por dispatch explícito e validação de conjunto, exatamente como `api/automations.py` já faz com `operator`/`conjunction`.

## Sources

### Primary (HIGH confidence)
- Codebase do projeto, lido diretamente nesta re-pesquisa: `backend/app/automation/{naming,fileops,undo,stage,rules}.py`, `backend/app/api/automations.py`, `backend/app/models/{automation_rule,audit_log,enums}.py`, `backend/app/queue/worker.py`, `backend/app/classification/stage.py`, `backend/app/pipeline/states.py` — interfaces reais dos tijolos, padrões de stage/worker/transition, allowlist de estados.
- `.planning/phases/06-.../06-CONTEXT.md` (bloco REDESIGN D-12..D-16 + decisões mantidas), `.planning/REQUIREMENTS.md` (AUT-01..06, TPL-02), `./CLAUDE.md` (stack, constraints integridade/Windows/LGPD).
- `backend/alembic/versions/` — confirma 0001..0006 presentes (próxima = 0007).
- docs.python.org — `os.replace`/`shutil` (semântica das primitivas; preservado da pesquisa anterior).

### Secondary (MEDIUM confidence)
- learn.microsoft.com — caracteres/nomes reservados Windows e MAX_PATH 260 (preservado; já tratado em `naming.py`).
- alexwlchan.net/2019/atomic-cross-filesystem-moves-in-python — EXDEV errno 18 (preservado; já tratado em `fileops.py`).

### Tertiary (LOW confidence)
- github.com/untitaker/python-atomicwrites#25 — `MoveFileEx` pode cair em `CopyFile` não-atômico (motiva o write-ahead; AUT-04 já o exige).

## Metadata

**Confidence breakdown:**
- Tijolos de arquivo (naming/fileops/undo/rules): HIGH — já implementados, testados, e reusados sem alteração.
- Modelo de dados do pipeline (pipelines/steps/filters + 0007): HIGH — espelha o padrão Template→Field já provado; sem dados em prod.
- Executor do pipeline + materialização única: HIGH para a recomendação; MEDIUM até a Open Q1 ser confirmada no plan (composição incremental vs. por-etapa).
- Gate "Identificar tipo": HIGH — reusa `classify_stage`/`forced_template_id` existentes.
- Filtros de entrada D-14: HIGH — generaliza `rules.evaluate_condition`; os tipos novos (pasta/ext/nome/tamanho/template) são comparações simples sobre atributos de arquivo.
- Undo agrupado por pipeline: HIGH se materialização única (1 audit/doc/run — `undo.py` inalterado); MEDIUM se por-etapa (exigiria `pipeline_run_id`).

**Research date:** 2026-06-17 (re-pesquisa pós REDESIGN)
**Valid until:** ~2026-07-17 (stack estável, stdlib + código do projeto; reavaliar se a Open Q1 mudar para materialização por-etapa)

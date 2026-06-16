---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 3 context gathered
last_updated: "2026-06-16T16:01:53.998Z"
last_activity: 2026-06-16
progress:
  total_phases: 8
  completed_phases: 2
  total_plans: 13
  completed_plans: 10
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-15)

**Core value:** Transformar uma pilha de documentos heterogêneos (PDFs e imagens, de tipos variados) em arquivos classificados, nomeados e organizados corretamente de forma automática e confiável — sem o usuário perder arquivos nem confiar cegamente na IA.
**Current focus:** Phase 03 — extra-o-gen-rica-via-ia-e-medi-o-de-tokens

## Current Position

Phase: 03 (extra-o-gen-rica-via-ia-e-medi-o-de-tokens) — EXECUTING
Plan: 2 of 4
Status: Ready to execute
Last activity: 2026-06-16

Progress: [█░░░░░░░░░] 13%

## Performance Metrics

**Velocity:**

- Total plans completed: 9
- Average duration: ~6 min
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |
| 02 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 02 P01 | 12 | 3 tasks | 17 files |
| Phase 02 P02 | 3 | 2 tasks | 7 files |
| Phase 02 P03 | 18 | 3 tasks | 9 files |
| Phase 02 P04 | 5 | 3 tasks | 8 files |
| Phase 02 P05 | 8 | 3 tasks | 10 files |
| Phase 03 P01 | 18 | 3 tasks | 14 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Motor é GENÉRICO — extração por IA dirigida pelo template (EXT-02) é o núcleo e vem primeiro (Phase 3); parsing determinístico (EXT-05) é módulo opcional/plugável movido para depois (Phase 7).
- [Roadmap]: Windows é plataforma primária; modo padrão usa fila in-process (SQLite), sem broker externo (refletido nas Phases 1 e 2).
- [Roadmap]: Reversibilidade (dry-run + audit write-ahead + undo + anti-colisão) é definição de pronto da Phase 6, não extra posterior.
- [Roadmap]: Documentação e atualização segura entre versões são entregáveis de v1 (Phase 8).
- [01-01]: Camada de banco atrás de interface única (Base/create_db_engine/get_session); PRAGMAs WAL aplicados só no dialeto sqlite — porta aberta para Postgres pela connection string.
- [01-01]: Chave OpenAI lida da config como SecretStr; nunca em repr/str/logs nem em respostas (USE-01 atendido na fundação).
- [01-02]: Modelos de domínio SQLAlchemy 2.0 (Document/Page/AuditLog/Usage); DocState com 6 estados enxutos (D-04); last_completed_step como marcador interno (D-05).
- [01-02]: Alembic desde o dia 1 — schema versionado (0001_initial), URL/metadata da app, render_as_batch; nenhum create_all em produção (D-10).
- [01-03]: CAS imutável endereçado por SHA-256 dentro da pasta de dados única (data_dir/cas) — store copia preservando o original (D-07), recuperável por hash para sempre (D-08), idempotente por conteúdo; escrita atômica via temporário + os.replace, sem delete/update.
- [Phase ?]: [01-04]: Máquina de estados explícita — TRANSITIONS allowlist (D-04) + transition() valida antes de atribuir e faz rollback em transição inválida, mantendo o estado persistido intacto (D-06); mark_step avança só o marcador interno (D-05). Auto-laços X->X inválidos por desenho.
- [Phase ?]: [02-01]: Substrato de schema da Fase 2 — jobs (fila durável, UNIQUE(original_hash, step) = idempotência PROC-03), ingested_originals (original_hash unique = gate de dedup D-09), watched_folders (D-02); coluna documents.origin_original_id; migração 0002 recria o trigger updated_at após batch recreate.
- [Phase ?]: [02-02]: Estabilizador por quiescência size/mtime + lock-test Windows (wait_stable) e separador de PDF por N páginas via pikepdf (MPL, não PyMuPDF AGPL); 'não separar' (None/0) = 1 bloco (D-05); PDF malformado vira ValueError controlado (T-02-04); janela de estabilização global default 4.0s configurável (D-04).
- [Phase ?]: [02-03]: Fila SQLite com claim atômico via UPDATE...RETURNING (single-writer D-11); claim compara next_run_at contra :now bind-ado em Python para evitar mismatch tz-aware vs segundos; backoff exponencial+jitter + dead-letter→FALHA (PROC-02).
- [Phase ?]: [02-03]: ingest_stage — gate de dedup pré-split (D-09/D-10) + 1 Document/bloco ligado ao original; estado terminal PROCESSANDO+'aguardando_extracao' (nunca CONCLUIDO); worker despacha split em asyncio.to_thread com sessão própria por thread.
- [Phase ?]: [02-04]: Watcher com supervisor que relê pastas ativas do DB (polling 5s) e reinicia awatch quando o conjunto muda (reconfiguração runtime A5); scan_and_enqueue (estabiliza→hash→gate→enqueue) compartilhado por startup, /rescan e watcher.
- [Phase ?]: [02-04]: Lifespan sobe watcher+worker como asyncio.Task e encerra limpo (stop→cancel→gather) preservando check WAL; requer uvicorn --workers 1 (T-02-12). API de pastas valida path com Path.resolve (T-02-10); DELETE preserva Documents (D-03).
- [Phase ?]: [02-05]: Frontend fiado à API real — TanStack Query 5.101 + cliente fetch tipado; polling 4s com placeholderData=prev (sem flicker); StatusPill mapeia estados de domínio reais (Aguardando extração, nunca Tratado nesta fase).
- [Phase ?]: [02-05]: Cadastro de pasta mantido por caminho absoluto via texto (decisão do usuário na verificação visual); seletor visual/normalização de aspas/validação de existência adiados para a fase desktop — fora de escopo.
- [03-01]: Schema genérico de extração modelado como list-of-pairs (ExtractionResult.fields: list[ExtractedField]), NUNCA dict aberto — strict mode dos Structured Outputs rejeita additionalProperties:true; descriptions Pydantic guiam o modelo, sem validação de domínio (Fase 4).
- [03-01]: Tabela extractions (Alembic 0003) com UNIQUE(document_id) = 1 extração por bloco = idempotência (não re-chamar/re-cobrar a IA); migração só cria a tabela e não toca documents, logo não recria o trigger trg_documents_updated_at.
- [03-01]: Scaffold de testes da extração mocka a OpenAI via respx em POST /v1/responses com JSON real da Responses API (output_parsed válido + variante de recusa output_parsed is None), sem gastar token — base reusável dos Plans 02-04.

### Pending Todos

None yet.

### Blockers/Concerns

[From research — a confirmar durante o planejamento das fases]

- Licença PyMuPDF (AGPL-3.0): resolver antes de extração de PDF (Phase 3); avaliar pypdfium2/pdfminer permissivos. (research/SUMMARY.md)
- Modelo de confiança: OpenAI não expõe score por campo; usar validação determinística pós-extração (Phase 5). (research/SUMMARY.md)
- Fila in-process SQLite sem lib consagrada: validar polling de tabela próprio (Phase 2). (research/SUMMARY.md)
- Parser de boleto Python: sem lib madura; portar lógica + fixtures reais (Phase 7). (research/SUMMARY.md)

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-16T16:01:34.616Z
Stopped at: Phase 3 context gathered
Resume file: None

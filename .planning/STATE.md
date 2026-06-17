---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 06-02-PLAN.md
last_updated: "2026-06-17T21:23:52.318Z"
last_activity: 2026-06-17
progress:
  total_phases: 8
  completed_phases: 5
  total_plans: 28
  completed_plans: 27
  percent: 63
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-15)

**Core value:** Transformar uma pilha de documentos heterogêneos (PDFs e imagens, de tipos variados) em arquivos classificados, nomeados e organizados corretamente de forma automática e confiável — sem o usuário perder arquivos nem confiar cegamente na IA.
**Current focus:** Phase 06 — automa-es-de-arquivo-renomear-mover

## Current Position

Phase: 06 (automa-es-de-arquivo-renomear-mover) — EXECUTING
Plan: 5 of 5
Status: Ready to execute
Last activity: 2026-06-17
Next: Phase 5 (Confiança, Revisão Humana e Quarentena) — requer discuss/plan

Progress: [█░░░░░░░░░] 13%

## Performance Metrics

**Velocity:**

- Total plans completed: 13
- Average duration: ~6 min
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |
| 02 | 5 | - | - |
| 03 | 4 | - | - |

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
| Phase 03 P02 | 9 | 3 tasks | 6 files |
| Phase 03 P03 | 14 | 2 tasks | 5 files |
| Phase 03 P04 | 12 | 2 tasks | 5 files |
| Phase 04 P01 | 9 | 3 tasks | 12 files |
| Phase 04 P02 | 3 | 2 tasks | 7 files |
| Phase 04 P03 | 8 | 2 tasks | 7 files |
| Phase 04 P04 | 7 | 2 tasks | 5 files |
| Phase 04 P05 | 6 | 2 tasks | 4 files |
| Phase 04 P06 | 12 | 2 tasks | 6 files |
| Phase 05 P01 | 6 | 2 tasks | 9 files |
| Phase 05 P02 | 5 | 2 tasks | 6 files |
| Phase 05 P03 | 8 | 3 tasks | 6 files |
| Phase 05 P04 | 5 | 3 tasks | 9 files |
| Phase 06 P01 | 7 | 3 tasks | 16 files |
| Phase 06 P02 | 9 | 2 tasks | 3 files |
| Phase 06 P04 | 20min | 3 tasks | 6 files |

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
- [Phase ?]: [03-02]: Três primitivas de extração como funções de módulo atrás de interface — pdf_io (magic bytes + heurística texto-vs-visão + render PNG), router.choose (seam D-03 plugável: Fases 4/7 plugam atalho local custo-zero), openai_client (Responses API + Structured Outputs, recusa→ExtractionRefused, ExtractionUsage mapeia input→prompt/output→completion). Chave nunca logada (testado).
- [Phase ?]: [03-03]: extract_stage liga CAS→router(D-03)→pdf_io→openai_client→persistência num commit ÚNICO (Extraction+Usage(step=extract)+marcador 'extraido'); idempotência checa Extraction existente ANTES da chamada paga (called_ai=False=no-op, não re-cobra); estado via set-em-memória do marcador (NÃO mark_step/transition) mantendo state=PROCESSANDO (D-07); só PyMuPDF em asyncio.to_thread, OpenAI await direto; recusa/PDF malformado propagam ao worker sem corromper estado.
- [Phase ?]: [03-04]: Worker bifurca dispatch por step — extract roda como coroutine (await extract_stage no loop, Pitfall 1 async-vs-thread), ingest segue em to_thread; FALHA roteada por content_hash do bloco (Pitfall 2); AuthenticationError não-retryável (dead-letter imediato, T-03-14); sweep idempotente no startup (enqueue_pending_extractions) enfileira extract p/ blocos aguardando_extracao sem job, cobrindo legados da Fase 2 sem quebrar a atomicidade do ingest. Pipeline ingest→extract completo end-to-end.
- [Phase ?]: [04-01]: 4 tabelas da Fase 4 (templates/template_fields/classification_results/filled_fields) via Alembic 0004; ClassificationResult.document_id UNIQUE = rede de banco contra double-charge (EXT-04/Pitfall 2); template_id FK SET NULL nullable = quarentena/nao-casou (D-03); limiar de classificacao GLOBAL no v1 (classify_match_threshold), por-template adiado p/ v2.
- [Phase ?]: [04-03]: decide(matches, threshold) separada de match_templates preserva o seam D-03; MissingFieldsResult REUSA ExtractedField (list-of-pairs strict-safe, Pitfall 1); matcher/filler puros (sem IA/DB).
- [Phase ?]: [04-04]: API fina /templates espelha watched_folders.py (In/Patch/Out, 409 duplicado, 422 inválido, 204 DELETE); GET /documents/{id} de detalhe somente leitura expõe a classificação (template casado/campos bruto+normalizado/marca/quarentena, TPL-03/TPL-04) enquanto a lista de polling permanece leve.
- [Phase ?]: [04-05]: classify_stage espelha extract_stage (idempotencia por checagem previa de ClassificationResult ANTES de qualquer chamada paga, commit atomico unico, marcador classificado em memoria, recusa propaga ao worker); quarentena via transition(QUARENTENA) com add(ClassificationResult template_id=None)+Usage ANTES (transition comita junto); merge D-06 por field_name normalizado; campo invalido marca FilledField.valid=False sem bloquear (D-10); worker despacha classify como coroutine (await, nunca to_thread) + sweep idempotente enqueue_pending_classifications cobre legados; pipeline ingest->extract->classify completo end-to-end.
- [Phase ?]: [04-06]: Frontend de templates fiado à API real (TemplatesPage substitui mock por useTemplates espelhando useWatchedFolders); construtor schema-first inline com 6 tipos de campo D-08/Switch/regex/dica/sinais; CTAs contextuais sem 'Cancelar' conforme 04-UI-SPEC.
- [Phase ?]: [04-06]: Classificacao S4 somente leitura via modal sob demanda (GET /documents/{id}); badge do template/tabela Campo-Valor-Normalizado com marca valido-invalido/pilula Quarentena reusando --st-leitura sem alterar StatusPill; valores como texto puro (T-04-12).
- [Phase 05-01]: confidence_score (qualidade de extração, D-01) distinto de confidence (matcher); compute_confidence puro (fração de obrigatórios válidos) com has_invalid_required forçando revisão mesmo com score alto (D-04); review_confidence_threshold global default 0.8 (D-03); migração 0005 não toca documents (trigger intacto, T-05-01).
- [Phase ?]: [05-02]: classify_stage roteia EM_REVISAO (score < limiar OU obrigatório inválido, D-04) vs PROCESSANDO+classificado num commit atômico (sem commit antes do transition); NUNCA CONCLUIDO (Open Q1, T-05-05); forced_template_id (D-09) pula matcher/decide/desempate, inexistente → ValueError (T-05-03); repo.requeue_step reseta job existente para pending (Open Q2); worker repassa forced_template_id do payload.
- [Phase ?]: [05-03]: 4 endpoints de revisão em api/documents.py com allowlist (transition) + pré-condição de estado explícita como guard (retry só FALHA, reclassify só QUARENTENA → 409); reclassify valida template (404) + apaga CR de quarentena ANTES + requeue_step com forced_template_id; patch revalida via validate_field SEM IA + manually_corrected + recalcula confidence_score; approve via _has_invalid_required (D-07); GET /documents/attention dedicado (3 baldes, selectinload evita N+1); GET/PUT /config/review-threshold persiste no .env + cache_clear (REV-02/D-03).
- [Phase ?]: [05-04]: Frontend da triagem — visão 'Precisam de atenção' (3 baldes) molde DocumentsPage com polling sem flicker; ConfidenceBadge espelha StatusPill (faixas TRAVADAS por token --st-*, número mono, fallback neutro); gate D-07 na UI (Aprovar disabled enquanto inválido, backend guard autoritativo); S6 limiar 0-100% na Config; valores texto puro (0 dangerouslySetInnerHTML); sem visualizador (D-06); code-and-config (sem npm novo).
- [Phase ?]: [06-01]: AuditLog estendido p/ write-ahead (status intent/done/undone + source/dest_path + run_id + content_hash) base de reversibilidade AUT-04/05; AutomationRule 1:N RuleCondition (priority D-05, operador eq/gt/lt/contains, conjunction E/OU) espelha Template/TemplateField (TPL-02); migracao 0006 estende SO audit_log + cria tabelas de regra, NUNCA toca documents (trigger trg_documents_updated_at intacto, T-06-01); aresta CONCLUIDO->PROCESSANDO unica saida nova do terminal (undo reabre doc, AUT-05); scaffold Wave 0 RED via importorskip.
- [Phase ?]: [06-04]: apply_stage liga rules→naming→fileops→audit write-ahead→estado idempotente; AuditLog(intent)+commit ANTES de materialize (AUT-04); idempotência por AuditLog(done); D-07 rebaixa para EM_REVISAO sem tocar disco; remove_original só após verificação (AUT-06 crit 5); reconcile_orphans adjudica intents órfãos no startup; blob ausente no CAS=conclusão lógica, blob corrompido propaga.
- [Phase ?]: [06-04]: worker despacha APPLY_STEP como coroutine; enqueue_pending_applications auto-aplica alta confiança (D-01), baixa só após approve; FALHA por content_hash; API /automations CRUD+dry-run(AUT-03)+apply lote run_id(D-03)+undo run reabre CONCLUIDO→PROCESSANDO(AUT-05); approve dispara apply (Open Q3).

### Pending Todos

None yet.

### Blockers/Concerns

[From research — a confirmar durante o planejamento das fases]

- Licença PyMuPDF (AGPL-3.0): resolver antes de extração de PDF (Phase 3); avaliar pypdfium2/pdfminer permissivos. (research/SUMMARY.md)
- Modelo de confiança: OpenAI não expõe score por campo; usar validação determinística pós-extração (Phase 5). (research/SUMMARY.md)
- Fila in-process SQLite sem lib consagrada: validar polling de tabela próprio (Phase 2). (research/SUMMARY.md)
- Parser de boleto Python: sem lib madura; portar lógica + fixtures reais (Phase 7). (research/SUMMARY.md)
- [04-VERIFICATION, WARNING] Encadeamento da fila: ingest_stage/extract_stage NÃO enfileiram o próximo step; os sweeps (enqueue_pending_extractions/classifications) rodam só no startup do worker. Doc ingerido em runtime não avança ingest→extract→classify sem reiniciar o worker. Fix recomendado (pequeno, idempotente): após mark_done de um job extract bem-sucedido em _run_once, enfileirar job classify do mesmo content_hash. Decidir se vira fix rápido avulso ou entra no escopo da Phase 5.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-17T21:21:14.358Z
Stopped at: Completed 06-02-PLAN.md
Resume file: None

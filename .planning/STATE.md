---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 10 context gathered
last_updated: "2026-06-25T13:33:36.221Z"
last_activity: 2026-06-25 -- Phase 10 planning complete
progress:
  total_phases: 13
  completed_phases: 8
  total_plans: 46
  completed_plans: 44
  percent: 62
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-15)

**Core value:** Transformar uma pilha de documentos heterogêneos (PDFs e imagens, de tipos variados) em arquivos classificados, nomeados e organizados corretamente de forma automática e confiável — sem o usuário perder arquivos nem confiar cegamente na IA.
**Current focus:** Phase 09 — automacao-destino-de-arquivo-configuravel-e-transformacao-de

## Current Position

Phase: 09 (automacao-destino-de-arquivo-configuravel-e-transformacao-de) — EXECUTING
Plan: 3 of 3
Status: Ready to execute
Last activity: 2026-06-25 -- Phase 10 planning complete
Next: Phase 5 (Confiança, Revisão Humana e Quarentena) — requer discuss/plan

Progress: [█░░░░░░░░░] 13%

## Performance Metrics

**Velocity:**

- Total plans completed: 17
- Average duration: ~6 min
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 4 | - | - |
| 02 | 5 | - | - |
| 03 | 4 | - | - |
| 06.1 | 4 | - | - |
| 06.2 | 1 (de 3) | 4 min | 4 min |

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
| Phase 06 P06 | 14 | 2 tasks | 6 files |
| Phase 06 P07 | 22 | 3 tasks | 7 files |
| Phase 06.1 P01 | 12 | 2 tasks | 3 files |
| Phase 06.1 P02 | 4 | 2 tasks | 3 files |
| Phase 06.1 P03 | 6 | 2 tasks | 3 files |
| Phase 06.1 P04 | 3 | 3 tasks | 5 files |
| Phase 06.2 P02 | 18 | 3 tasks | 6 files |
| Phase 06.2 P03 | 25 | 3 tasks | 3 files |
| Phase 09 P01 | 22 | 4 tasks | 6 files |
| Phase 09 P02 | ~8 min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [06.2-01]: Executor das automações passa a plano MULTI-SAÍDA — PlannedCopy(folder,name) acumulado em AutomationPlan.copies (tuple, default vazio preserva single-output). copy espelha o move (confinamento V4 / bloqueio D-07) mas é ADITIVO: não muta o alvo, não remove o original (D-01/D-03). action_type segue String livre — ZERO migração. Contrato puro pronto para o stage (Plano 02) materializar.
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
- [Phase ?]: [06-06]: Modelo de pipeline AutomationPipeline 1:N PipelineStep 1:N StepFilter (D-12..D-14) substitui regra única; espelha Template→TemplateField (cascade delete-orphan + FK CASCADE); migração 0007 forward-only dropa regras da 0006 e cria pipeline sem tocar documents (trigger intacto) nem audit_log (write-ahead preservado); automation_rule.py deletado, stage/api ficam com import quebrado intencional até o 06-07.
- [Phase ?]: 06-07: materialização única ao final do pipeline (Open Q1); Route não materializa (P9); no-match no-op (P10); apply_stage async; gate D-15 custo 0
- [Phase ?]: [06.1-01]: matcher passou a confiança BOOLEANA (1.0/0.0) — grupos E/OU (OU entre grupos, E dentro do grupo) substituem fração de termos; sinais casam contra full_text (A2/D-T2); decide() byte-idêntico mantém seam D-03; doc_type bonus removido (D-T5/A3) com doc_type_guess mantido na assinatura por compat; regex de sinal endurecida ReDoS (teto pattern 512 + teto input 200000 + try/except re.error, falha fechada); _parse_groups forward-compatible lê legado list[str] e grupos novos; forma canônica de signals_json definida p/ Planos 02/03.
- [Phase ?]: [06.1-02]: API /templates com sinais como GRUPOS E/OU (list[list[SignalConditionIn]], D-T2); _loads_signals_groups forward-compatible réplica de matcher._parse_groups; mode por Literal → 422 sem eval (T-06.1-07); regex string-only no endpoint sem import re (T-04-10); doc_type rebaixado a coluna dormente (D-T5) sem migração; field.name preservado byte-a-byte (D-T9); documents/trigger intactos.
- [Phase ?]: [06.1-03]: Frontend de Templates redesenhado 1:1 com o mockup — Passo 1 'Como reconhecer' (sem IA, grupos OU de condições E texto|regex, D-T0/D-T3/D-T4) + Passo 2 'O que extrair' (com IA, linhas densas com ⚙ Avançado revelando regex+dica, D-T7); tooltips ⓘ via CSS :hover puro zero-lib (D-T8); doc_type removido do form (D-T5); field.name preservado (D-T6/D-T9); types.ts espelha signals=list[list[{mode,value}]] do Plano 02; npm run build verde fecha o gate de drift T-06.1-13.
- [Phase ?]: [06.2-02]: apply_stage MULTI-SAÍDA — materializa N cópias (write-ahead action='copy' por cópia) SEM remove_original (D-01); move por ÚLTIMO e só então remove a origem (D-03); copy-only conclui o doc sem mover. undo discrimina action='copy' (apaga a cópia, nunca toca o original/CAS, D-06); undo por-run reverte copy+move juntos. API valida copy (exige dest_folder, V5) e dry-run emite 1 linha por saída (action_kind/removes_original). Sem migração; suíte inteira verde (399), zero regressão (D-04).
- [Phase ?]: [06.2-03]: Ação Copiar exposta na UI de forma estritamente aditiva — reusa o caminho do move (input/validação/mapeamento, pattern=dest_folder genérico) com toCreateBody preservando a.action_type; diferenciação mínima (dot --st-encontrado + nota D-05 'o original permanece'); dry-run dispara badge 'Copiado — original mantido' por action_kind/removes_original do backend (Plano 02). Fluxo criar→dry-run→aplicar→desfazer verificado ao vivo (cópia no destino, original intacto, undo apaga só a cópia, nada se perde — D-01/D-06). Phase 06.2 (Copiar) encerrada; Cortar adiada p/ v2.
- [Phase ?]: [09-01] resolve_dest_folder com 3 ramos (Windows drive/UNC, POSIX /..., relativo+base): absoluto literal sem .resolve() e sem is_relative_to (D-03), anchor nunca sanitizado, segmentos sim (D-08); _is_abs_windows exige DRIVE real para nao confundir /tmp POSIX com Windows. D-05 via _anchor_missing/_plan_anchor_missing checa exists() do anchor ANTES do mkdir no dry-run e apply. D-04 provado por teste de integracao de API. Sem schema.
- [Phase ?]: [09-02] Engine de filtros inline em _substitute via pipeline split-por-':' + dispatch EXPLICITO (_apply_filter), nunca eval (T-09-05); filtro desconhecido e int() invalido = inerte. padrao= resolvido ANTES de _MissingField (A3): campo ausente + padrao=X usa X. Atalho legado {data:aaaa-mm} preservado (A1). Sanitize DEPOIS dos filtros por segmento (D-08). Sem schema, sem dep nova (so unicodedata stdlib).

### Pending Todos

None yet.

### Blockers/Concerns

[From research — a confirmar durante o planejamento das fases]

- Licença PyMuPDF (AGPL-3.0): resolver antes de extração de PDF (Phase 3); avaliar pypdfium2/pdfminer permissivos. (research/SUMMARY.md)
- Modelo de confiança: OpenAI não expõe score por campo; usar validação determinística pós-extração (Phase 5). (research/SUMMARY.md)
- Fila in-process SQLite sem lib consagrada: validar polling de tabela próprio (Phase 2). (research/SUMMARY.md)
- Parser de boleto Python: sem lib madura; portar lógica + fixtures reais (Phase 7). (research/SUMMARY.md)
- [04-VERIFICATION, WARNING — RESOLVIDO 2026-06-22] Encadeamento da fila: a nota original alertava que ingest_stage/extract_stage não enfileiravam o próximo step e os sweeps só rodavam no startup do worker. **Já corrigido no código atual**: `run_worker` chama `_sweep_pending(engine)` a CADA ciclo ocioso (worker.py:476), não só no startup — isso encadeia ingest→extract→classify→apply em runtime (docstring em worker.py:463-465). Documento jogado na pasta com o worker rodando avança sozinho. Nenhuma ação pendente.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260622-ebo | Instalação Windows (Python+uv): servir frontend no FastAPI (single-origin), instalar.ps1, atualizar.ps1, INSTALL-WINDOWS.md | 2026-06-22 | 2c16a67 | [260622-ebo-criar-instalacao-windows-python-uv-servi](./quick/260622-ebo-criar-instalacao-windows-python-uv-servi/) |
| 260622-f4b | Entrega Windows via ZIP sem Git (GitHub Releases): empacotar.ps1, atualizar.ps1 (Releases + -LocalZip), instalar.ps1 pula build com dist, guia 2 fluxos | 2026-06-22 | c81dcfe | [260622-f4b-entrega-windows-via-zip-sem-git-empacota](./quick/260622-f4b-entrega-windows-via-zip-sem-git-empacota/) |
| 260623-kly | Serviço Windows via NSSM: servico.ps1 (instalar/iniciar/parar/reiniciar/status/remover/logs), auto-start no boot + auto-restart + health-check falha-fechada; empacotar inclui nssm.exe; guia | 2026-06-23 | 25f5fdb | [260623-kly-servico-windows-via-nssm-servico-ps1-ins](./quick/260623-kly-servico-windows-via-nssm-servico-ps1-ins/) |
| 260623-lpj | Persistência Windows: servico.ps1 vira 2 modos — Tarefa Agendada no logon (PADRÃO, como usuário, contorna Pegadinha 1) + NSSM via --modo servico; launcher tools/iniciar-servidor.py; guia 2 modos. Valida correção do piloto (NSSM-LocalSystem falhou: Python per-user) | 2026-06-23 | 7fb3451 | [260623-lpj-persistencia-windows-servico-ps1-padrao-](./quick/260623-lpj-persistencia-windows-servico-ps1-padrao-/) |
| 260623-mod | Logs de execução nos scripts Windows: Start-Transcript fail-soft em instalar/atualizar/servico.ps1 (logs timestampados em %ProgramData%\...\logs\, caminho impresso no fim); subcomando servico.ps1 diagnostico (relatório único sem segredos); fix Resolve-ModoInstalado; guia. Para depurar instalações remotas | 2026-06-23 | 3b15bae | [260623-mod-logs-de-execucao-nos-scripts-windows-sta](./quick/260623-mod-logs-de-execucao-nos-scripts-windows-sta/) |
| 260623-no9 | Modo startup (pasta Inicializar, pythonw invisível, sem janela/admin) vira PADRÃO do servico.ps1; guarda de instância única no launcher; controles+diagnóstico cobrem startup. VALIDADO ao vivo (instalar do WSL → .vbs + servidor invisível + health 200) | 2026-06-23 | 8221d72 | [260623-no9-servico-ps1-modo-startup-pasta-inicializ](./quick/260623-no9-servico-ps1-modo-startup-pasta-inicializ/) |
| 260623-pzy | Separar PDF em arquivos na pasta monitorada (opt-in split_to_files, default OFF): materializa os blocos na pasta substituindo o original ANTES da IA; reversível (CAS+audit), anti-loop (hash no dedup antes de gravar), migração 0009; API+UI toggle; 419 testes verdes | 2026-06-23 | 0b90b8c | [260623-pzy-separar-pdf-em-arquivos-na-pasta-monitor](./quick/260623-pzy-separar-pdf-em-arquivos-na-pasta-monitor/) |
| 260624-far | Ajustes UI/UX + backend: remover documento(s) na aba Documentos (POST /documents/delete em lote, só registro — NUNCA toca no arquivo; anti-órfão de dedup remove IngestedOriginal/Jobs quando sobra sem blocos); status real do watcher na Sidebar (GET /watcher/status: ativo, nº pastas, última varredura); desabilitar busca+sino no Header; desabilitar abas Regras/Integrações e controles mock da Leitura (mantendo Limiar funcional). 431 testes verdes, build frontend verde | 2026-06-24 | 7081b0c | [260624-far-ajustes-ui-remover-documentos-desabilita](./quick/260624-far-ajustes-ui-remover-documentos-desabilita/) |
| fast | Integrações: remove SharePoint/ERP Omie, tira o aviso "em breve" e neutraliza as tags (badge cinza "Indisponível") | 2026-06-24 | e9fa026 | — |

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-06-24T20:50:39.902Z
Stopped at: Phase 10 context gathered
Resume file: .planning/phases/10-robustez-de-ingestao-e-classificacao-varredura-de-pasta-nova/10-CONTEXT.md

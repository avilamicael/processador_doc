# Phase 5: Confiança, Revisão Humana e Quarentena - Research

**Researched:** 2026-06-16
**Domain:** Score de confiança determinístico + roteamento de estado + endpoints de ação (retry/reclassify/patch/approve) + visão web de triagem (TanStack Query)
**Confidence:** HIGH (esta fase estende código próprio já lido integralmente; quase nenhuma dependência externa nova; as escolhas são de arquitetura interna, não de ecossistema)

## Summary

Esta é uma fase **brownfield, code-and-config only** — não instala nenhum pacote externo novo. Todo o trabalho assenta sobre código já existente e lido por inteiro: `classify_stage` (que já produz `FilledField.valid`/`invalid_reason` por campo), `validate_field` (reusável para revalidar correções sem IA), a allowlist `TRANSITIONS` (que já contém TODAS as transições que a fase precisa: `PROCESSANDO→EM_REVISAO`, `EM_REVISAO→CONCLUIDO`, `QUARENTENA→PROCESSANDO`, `FALHA→PROCESSANDO`), o `worker.py` com sweeps idempotentes encadeados, e o padrão de routers finos + hooks TanStack Query da Fase 4.

O coração técnico é fechar 5 lacunas: (1) **onde persistir o score** — recomendação: coluna `confidence_score` em `classification_results` (não em `documents`), porque o score é uma propriedade da classificação/extração, é 1:1 com `ClassificationResult` e já há migração-padrão para essa tabela; (2) **onde calcular/rotear** no `classify_stage` — substituir o trecho final que hoje seta `last_completed_step="classificado"` e mantém `PROCESSANDO`, passando a calcular o score (fração de obrigatórios válidos) e fazer `transition(EM_REVISAO)` ou `transition(CONCLUIDO)` mantendo o commit atômico único; (3) **forçar template** — adicionar parâmetro opcional `forced_template_id: int | None` a `classify_stage` que pula `matcher`+`decide` e vai direto a `filler`+IA-faltantes+validação; (4) **endpoints de ação** — novos POSTs em `documents.py` que validam contra a allowlist via `transition` e reenfileiram via `repo.enqueue`; (5) **coluna `manually_corrected`** em `FilledField` + endpoint de patch que chama `validate_field` e marca a origem.

**Primary recommendation:** Persistir `confidence_score` em `classification_results` (migração Alembic 0005) + `manually_corrected` em `filled_fields`; calcular o score e rotear o estado **dentro** do commit atômico único do `classify_stage` (substituindo o set de `"classificado"` por um `transition` para EM_REVISAO/CONCLUIDO); adicionar `forced_template_id` opcional ao `classify_stage`; criar 4 endpoints de ação espelhando os routers finos da Fase 4; honrar integralmente o design system TRAVADO em `04-UI-SPEC.md`/`05-UI-SPEC.md`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Cálculo do score de confiança (D-01) | API/Backend (`classify_stage`) | — | É derivação determinística pós-extração; o backend é a única fonte de verdade; nunca calcular no frontend |
| Roteamento de estado CONCLUIDO/EM_REVISAO/QUARENTENA (D-04) | API/Backend (`classify_stage` + `state_machine`) | Database (allowlist persistida em `state`) | Transição de estado é responsabilidade da máquina de estados; commit atômico no backend |
| Persistência do score + marca de correção (D-02/D-08) | Database (Alembic 0005) | — | Schema evolui só via Alembic; score e marca são colunas |
| Limiar global de confiança (D-03) | API/Backend (`config.py` tunable) | Frontend (campo de edição em S6) | Mesmo padrão dos tunables existentes; lido pelo stage, editável pela UI |
| Ações retry/reclassify/approve (REV-04/05) | API/Backend (endpoints + `transition` + `repo.enqueue`) | Queue (`worker.py` reusa o sweep) | Transições validadas pela allowlist; reprocessamento pela fila existente |
| Revalidação de campo corrigido (D-08) | API/Backend (`validate_field`) | — | Reusa o validador determinístico; NÃO chama IA |
| Visão "Precisam de atenção" + polling (REV-03) | Frontend (página + hooks TanStack Query) | API (lista filtrada por estado) | Gestão/triagem é responsabilidade da UI; dado vem da API |

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Confiança por documento = **fração de campos obrigatórios que passaram na validação determinística** (Módulo 11 CNPJ/CPF, data, moeda, regex do template). Campos obrigatórios inválidos OU faltantes derrubam o score. NÃO usar o auto-relato de confiança da IA como base. A `confidence` do matcher (já em `ClassificationResult`) é sinal de classificação, separada deste indicador de qualidade de extração.
- **D-02:** Armazenar **score 0–100%** + **derivar rótulo legível** (alta/média/baixa) para a UI. Ambos, com o número como fonte de verdade.
- **D-03:** Limiar de confiança **global, na config** (mesmo padrão dos tunables em `config.py`, ex.: `classify_match_threshold`). Por-template é evolução futura (deferido).
- **D-04:** Documento vai para **EM_REVISAO** quando: **confiança < limiar OU qualquer campo obrigatório inválido/faltante**. Garante que erros determinísticos sempre são revisados, mesmo com score geral alto.
- **D-05:** Web tem **uma visão "Precisam de atenção"** nos **3 baldes** (FALHA → "tentar de novo"; QUARENTENA → "atribuir template + reclassificar"; EM_REVISAO → "corrigir valores inline + aprovar"), cada um com o **motivo**.
- **D-06:** **Sem visualizador de documento na web** (imagem/embed/texto bruto). A UI mostra motivo + valores de campo.
- **D-07:** Aprovar = **EM_REVISAO → CONCLUIDO** (transição já na allowlist). Só permitido quando os campos obrigatórios estão válidos.
- **D-08:** Correção de campo: **atualiza `raw_value`/`normalized_value` do `FilledField`, revalida pelo tipo (`validation/fields.py`), marca origem "corrigido manualmente"** (coluna nova). NÃO re-chama a IA.
- **D-09:** Resolver quarentena = **atribuir template manualmente + reclassificar via fila** (reusa matcher→filler→validação do `classify_stage` com template forçado).

### Claude's Discretion

- Forma de persistir o indicador (coluna em `documents` vs `classification_results`) — decidir no planejamento. **Esta pesquisa recomenda `classification_results` (ver Architecture Patterns / Pattern 1).**
- Layout/UX fino da visão "Precisam de atenção" (seções por balde vs filtros) — o mock aprovado é o norte.
- Mecânica de "forçar template" no `classify_stage` (parâmetro opcional vs novo caminho) — desde que pule o matcher e use filler+validação. **Esta pesquisa recomenda parâmetro opcional `forced_template_id` (ver Pattern 3).**

### Deferred Ideas (OUT OF SCOPE)

- Visualizador de documento na web (render/embed) — fora de escopo absoluto (D-06).
- Limiar de confiança por template (v1 usa global; INT2-05).
- Combinar auto-relato de confiança da IA no indicador — rejeitado para v1.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REV-01 | Indicador de confiança por documento, baseado em validação determinística pós-extração | `classify_stage` já tem `FilledField.valid` por campo; score = `len(obrigatórios válidos) / len(obrigatórios)` calculado no commit atômico (Pattern 2). Persistir em `classification_results.confidence_score` (Pattern 1). |
| REV-02 | Limiar de confiança global que decide o que vai para revisão | Novo tunable `review_confidence_threshold` em `config.py` (mesmo padrão de `classify_match_threshold`), lido pelo stage; editável em S6 da UI. |
| REV-03 | Visão "Precisam de atenção" (3 baldes) com motivo + campos editáveis, sem visualizador | Lista filtrada por estado (FALHA/QUARENTENA/EM_REVISAO); página React + hooks TanStack Query (Pattern 5); design TRAVADO em 05-UI-SPEC.md. |
| REV-04 | Aprovar/corrigir valores antes de qualquer automação (aprovar→CONCLUIDO; correção marcada manual) | Endpoint patch chama `validate_field` + marca `manually_corrected` (Pattern 4); endpoint approve faz `transition(CONCLUIDO)` só com obrigatórios válidos (Pattern 4). |
| REV-05 | Quarentena visível, com motivo, resolúvel (atribuir template + reclassificar/reprocessar) | Endpoint reclassify: `transition(QUARENTENA→PROCESSANDO)` + reenfileira job classify com `forced_template_id` (Pattern 3/4). |

## Standard Stack

### Core (TODOS já instalados — nenhum pacote novo)

| Library | Version (pinned) | Purpose nesta fase | Why Standard |
|---------|------------------|--------------------|--------------|
| FastAPI | 0.137.1 | Novos endpoints de ação em `documents.py` | Já é o framework de toda a API; routers finos são o padrão estabelecido (Fase 4) |
| Pydantic | 2.13.4 | Schemas `In`/`Out` dos endpoints de ação | Mesma camada de validação já usada em `templates.py`/`documents.py` |
| SQLAlchemy | 2.0.x | Coluna `confidence_score` + `manually_corrected`; queries da lista filtrada | ORM já em uso; mantém porta Postgres aberta |
| Alembic | 1.18.4 | Migração 0005 (2 colunas novas) | Schema evolui SÓ via Alembic (D-10 do projeto); nunca `create_all` |
| React | 19.2.7 | Página "Precisam de atenção" | Já é o frontend; estende o design system TRAVADO |
| @tanstack/react-query | 5.101.0 | Hooks de lista (polling) + mutations (ações) com `invalidateQueries` | Padrão estabelecido em `useDocuments`/`useTemplates` |

### Supporting (já no repo, reusados sem mudança)

| Module | Purpose | When to Use |
|--------|---------|-------------|
| `app.validation.fields.validate_field` | Revalida valor corrigido por tipo (D-08) | No endpoint de patch de campo — reusar EXATAMENTE; não duplicar lógica |
| `app.pipeline.state_machine.transition` | Valida + persiste transição de estado | Em TODOS os endpoints de ação e no roteamento do stage |
| `app.queue.repo.enqueue` | Reenfileira job `(content_hash, step)` idempotente | Retry (FALHA) e reclassify (QUARENTENA) |
| `app.classification.{matcher,filler,openai_client}` | Motor de classificação | Reusados pelo caminho de `forced_template_id` (filler + IA-faltantes apenas) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `confidence_score` em `classification_results` | Coluna em `documents` | `documents` é a tabela central de estado; poluí-la com derivação de extração quebra a separação de responsabilidades; a classificação é 1:1 com o doc mas conceitualmente o score pertence ao resultado da classificação, não ao documento. Ver Pattern 1. |
| Parâmetro `forced_template_id` no `classify_stage` | Função separada `reclassify_with_template` | Duplicaria filler+validação+commit atômico; o parâmetro opcional mantém DRY e o commit único num só lugar. Ver Pattern 3. |
| Reusar campo `confidence` existente para o score | — | NÃO: `confidence` já significa "confiança do matcher/desempate de classificação" (D-01 explicita que são sinais SEPARADOS). Reusar misturaria semânticas. Coluna nova é obrigatória. |

**Installation:** Nenhuma. Esta fase não adiciona dependências Python nem npm.

## Package Legitimacy Audit

> **Não aplicável.** Esta fase é code-and-config only e **não instala nenhum pacote externo novo** (Python ou npm). Todas as bibliotecas usadas já estão pinadas em `backend/pyproject.toml` e `frontend/package.json` desde fases anteriores. Sem instalação = sem superfície de slopsquatting nesta fase.

| Package | Disposition |
|---------|-------------|
| (nenhum pacote novo) | N/A |

## Architecture Patterns

### System Architecture Diagram

```
                          ┌─────────────────────────────────────────────┐
                          │  FLUXO DE CLASSIFICAÇÃO (estendido nesta fase)│
                          └─────────────────────────────────────────────┘

  worker._dispatch(step="classify")
        │
        ▼
  classify_stage(session, content_hash, forced_template_id=None)   ◄── NOVO param (D-09)
        │
        ├─ [idempotência] ClassificationResult existe? ──► sim ──► no-op
        │
        ├─ forced_template_id setado? ──► sim ──► PULA matcher/decide
        │                                          usa template forçado ──┐
        │                                                                 │
        ├─ não ──► matcher.match_templates → decide ──┐                   │
        │                                              ▼                   ▼
        │                          ┌──────────┬──────────────┬───────────────┐
        │                          │quarantine│  ambiguous    │   matched     │
        │                          ▼          ▼               ▼               │
        │                  transition()   disambiguate()  filler.map_fields   │
        │                  (QUARENTENA)    (IA paga)          │               │
        │                       │                             ▼               │
        │                       │              missing_required? ─► IA faltantes
        │                       │                             │               │
        │                       │                             ▼               │
        │                       │                   validate_field() por campo │
        │                       │                             │               │
        │                       │                             ▼               │
        │                       │        ┌──── score = válidos_obrig / total_obrig ────┐  ◄── NOVO (D-01)
        │                       │        │                                              │
        │                       │        ▼                                              ▼
        │                       │   score < limiar OU algum obrig inválido?      todos válidos E
        │                       │        │ sim                                   score >= limiar
        │                       │        ▼                                              │ sim
        │                       │   transition(EM_REVISAO)  ◄── NOVO (D-04)             ▼
        │                       │   + CR(confidence_score)                    transition(CONCLUIDO)? 
        │                       │   + FilledFields                            ◄── NOTA: ver Open Q1
        │                       │   (commit atômico único)                    (auto-CONCLUIDO vs manual)
        │                       ▼
        │              [estado terminal persistido]
        │
        └─────────────────────────────────────────────────────────────────────────────┘


            ┌────────────────────────────────────────────────────────────┐
            │  AÇÕES DE TRIAGEM (novos endpoints em api/documents.py)      │
            └────────────────────────────────────────────────────────────┘

  Frontend "Precisam de atenção"
        │
        ├─ POST /documents/{id}/retry      ─► transition(FALHA→PROCESSANDO) + repo.enqueue(classify ou extract)
        ├─ POST /documents/{id}/reclassify ─► transition(QUARENTENA→PROCESSANDO) + apaga CR + repo.enqueue(classify, forced_template_id)
        ├─ PATCH /documents/{id}/fields/{name} ─► validate_field() + marca manually_corrected (NÃO IA)
        └─ POST /documents/{id}/approve    ─► guard: todos obrig válidos ─► transition(EM_REVISAO→CONCLUIDO)
```

### Recommended Project Structure

Sem novas pastas. Arquivos tocados/criados:

```
backend/
├── alembic/versions/0005_confidence_review.py   # NOVO: 2 colunas
├── app/
│   ├── classification/stage.py                  # EDITA: score + roteamento + forced_template_id
│   ├── classification/confidence.py             # NOVO (opcional): função pura compute_confidence()
│   ├── models/classification.py                 # EDITA: confidence_score + manually_corrected
│   ├── config.py                                # EDITA: review_confidence_threshold tunable
│   ├── api/documents.py                         # EDITA: 4 endpoints de ação
│   └── queue/worker.py                          # EDITA (talvez): _dispatch passa forced_template_id via payload
└── tests/classification/
    ├── test_confidence.py                       # NOVO: cálculo do score (pura)
    ├── test_stage_routing.py                    # NOVO: EM_REVISAO vs CONCLUIDO vs QUARENTENA
    └── test_forced_template.py                  # NOVO: reclassify com template forçado
tests/
└── test_api_review.py                           # NOVO: retry/reclassify/patch/approve

frontend/src/
├── pages/AttentionPage.tsx                      # NOVO: visão "Precisam de atenção" (S1-S4)
├── components/ConfidenceBadge.tsx               # NOVO: indicador reutilizável (S5)
├── hooks/useAttention.ts                        # NOVO: useAttentionDocuments + 4 mutations
├── lib/api.ts                                   # EDITA: 4 funções de ação + getAttention
└── types.ts                                     # EDITA: confidence_score + manually_corrected
```

### Pattern 1: Persistir o score em `classification_results` (Discretion D-02)

**What:** Adicionar `confidence_score: Mapped[float | None]` a `ClassificationResult`, NÃO a `Document`.
**When to use:** Sempre (recomendação firme).
**Rationale:**
- `ClassificationResult` é **1:1 com `Document`** (UNIQUE em `document_id`), então não há perda de capacidade de query — o join é trivial e já feito em `GET /documents/{id}`.
- O score é uma **propriedade derivada da extração/classificação** (D-01: fração de obrigatórios válidos), conceitualmente parte do resultado, não do estado do documento.
- `documents` é a tabela central de estado/máquina-de-estados; mantê-la enxuta evita acoplar derivações de domínio a ela (já carrega `state`/`last_completed_step`/CAS).
- A tabela `classification_results` já tem o padrão de migração-só-cria (0004 não toca `documents`, logo **não recria o trigger `trg_documents_updated_at`** — ver Pitfall 1). Adicionar coluna a `documents` exigiria batch recreate e recriação do trigger.

**Distinção semântica crítica (D-01):** `ClassificationResult.confidence` (já existe) = confiança do **matcher/desempate** de qual template casou. `ClassificationResult.confidence_score` (novo) = **qualidade de extração** (fração de obrigatórios válidos). São métricas diferentes; NÃO reusar a coluna existente.

```python
# Source: backend/app/models/classification.py (edição)
# Score 0.0–1.0 (D-02; a UI multiplica por 100 e deriva rótulo). nullable:
# quarentena não tem score (sem template = sem campos obrigatórios para avaliar).
confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
```

### Pattern 2: Calcular o score e rotear o estado DENTRO do commit atômico único (D-01/D-04)

**What:** No `classify_stage`, no caminho "casou" (passo 8/9 atual), substituir o set `doc.last_completed_step = CLASSIFIED_STEP` + `session.commit()` por: (a) calcular o score, (b) decidir CONCLUIDO vs EM_REVISAO, (c) chamar `transition` (que comita).
**When to use:** No final do caminho de match do stage.

O cálculo é **puro** e deve ficar isolável (sugestão: `app/classification/confidence.py`):

```python
# Source: novo confidence.py — função PURA, testável sem DB/IA
def compute_confidence(filled_fields, template_fields) -> tuple[float | None, bool]:
    """Retorna (score 0.0-1.0, has_invalid_required).

    score = fração de campos OBRIGATÓRIOS válidos (D-01).
    has_invalid_required = True se algum obrigatório está inválido/faltante (D-04).
    Sem campos obrigatórios → score=1.0, has_invalid=False (nada para revisar).
    """
    required = [f for f in template_fields if f.required]
    if not required:
        return 1.0, False
    valid_by_name = {ff.field_name: ff.valid for ff in filled_fields}
    valid_count = sum(1 for f in required if valid_by_name.get(f.name, False))
    has_invalid = valid_count < len(required)
    return valid_count / len(required), has_invalid
```

**Roteamento (D-04) — substitui o passo 9 atual no caminho match:**

```python
# Source: backend/app/classification/stage.py (edição do passo 9)
score, has_invalid_required = compute_confidence(cr.filled_fields, template.fields)
cr.confidence_score = score
for u in usages:
    session.add(u)

settings = get_settings()  # já lido acima
below_threshold = score < settings.review_confidence_threshold
if has_invalid_required or below_threshold:
    # D-04: erro determinístico OU score baixo → revisão humana.
    # ATÔMICO: add já feito (cr + filled_fields + usages na sessão);
    # transition faz o commit interno, persistindo TUDO junto.
    transition(session, doc, DocState.EM_REVISAO, completed_step=CLASSIFIED_STEP)
else:
    # Ver Open Question 1 sobre auto-CONCLUIDO vs aguardando automação.
    transition(session, doc, DocState.CONCLUIDO, completed_step=CLASSIFIED_STEP)
```

**CRÍTICO — mantém a atomicidade da Fase 4:** Hoje o caminho match faz `session.commit()` direto porque `PROCESSANDO→PROCESSANDO` é auto-laço fora da allowlist. Agora que roteamos para EM_REVISAO/CONCLUIDO (transições VÁLIDAS), usamos `transition` (que comita internamente, igual ao caminho de quarentena já faz). Os `add` de `cr`/`filled_fields`/`usages` continuam ANTES do `transition` → commit único atômico. **Não** chamar `session.commit()` manual antes do `transition` (quebraria a atomicidade e deixaria estado parcial em caso de falha).

### Pattern 3: Forçar template via parâmetro opcional (D-09 / Discretion)

**What:** `classify_stage(session, *, content_hash, forced_template_id: int | None = None)`. Quando setado, pula `matcher.match_templates`/`decide` e o ramo de desempate; vai direto a `filler.map_fields` + IA-faltantes + validação com o template forçado.
**When to use:** Reclassificação de quarentena (REV-05).

```python
# Source: backend/app/classification/stage.py (novo ramo após idempotência + Extraction)
if forced_template_id is not None:
    template = session.get(Template, forced_template_id)
    if template is None:
        raise ValueError("Template forçado inexistente")
    matched_template_id = forced_template_id
    confidence = None  # sem score de matcher quando forçado manualmente
    # ... segue DIRETO ao passo 7 (filler) — pula matcher/decide/disambiguate
else:
    # caminho atual: matcher → decide → (ambiguous → disambiguate)
    ...
```

**IMPORTANTE — idempotência na reclassificação:** O endpoint de reclassify DEVE **apagar o `ClassificationResult` existente** (que era `template_id=None`, quarentena) ANTES de reenfileirar, senão a checagem de idempotência no início do `classify_stage` faz no-op (linha 162-173). Apagar o CR é seguro: cascade `delete-orphan` remove os FilledFields; o `transition(QUARENTENA→PROCESSANDO)` reabre o doc para reprocessamento.

**Como o worker passa `forced_template_id`:** Via payload do job. `repo.enqueue(..., payload=json.dumps({"content_hash": ..., "forced_template_id": tid}))`; o `worker._dispatch` no ramo CLASSIFY_STEP lê `forced_template_id` do payload e passa ao `classify_stage`. **Atenção à UNIQUE `(original_hash, step)`:** um job classify pode já existir/ter rodado para esse content_hash. Como o CR foi apagado, é preciso garantir que um NOVO job classify seja enfileirável — ver Open Question 2.

### Pattern 4: Endpoints de ação espelhando os routers finos da Fase 4

**What:** 4 POSTs/PATCH em `api/documents.py`, cada um validando a transição via `transition` (a allowlist é o guard) e reenfileirando via `repo.enqueue` quando aplicável.
**When to use:** Todas as ações de triagem.

Padrão de cada endpoint (espelha `templates.py`: `request.app.state.engine` + `with get_session`, 404 em ausente, schema Pydantic):

```python
# Source: padrão derivado de api/documents.py + api/templates.py
@router.post("/documents/{document_id}/approve", response_model=DocumentDetailOut)
def approve_document(request: Request, document_id: int) -> DocumentDetailOut:
    engine = request.app.state.engine
    with get_session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            raise HTTPException(404, "documento não encontrado")
        # GUARD D-07: só aprova com TODOS os obrigatórios válidos.
        cr = session.scalar(select(ClassificationResult).where(
            ClassificationResult.document_id == document_id))
        if cr is None or _has_invalid_required(cr, session):
            raise HTTPException(409, "corrija os campos obrigatórios inválidos antes de aprovar")
        # transition é o guard de estado: EM_REVISAO→CONCLUIDO está na allowlist;
        # qualquer outro estado de origem → InvalidTransition → 409.
        try:
            transition(session, doc, DocState.CONCLUIDO)
        except InvalidTransition as exc:
            raise HTTPException(409, str(exc)) from exc
        # ... retorna o detalhe atualizado
```

**Mapeamento estado→ação (todos os 4):**

| Endpoint | Transição (allowlist verificada) | Reenfileira? | Notas |
|----------|----------------------------------|--------------|-------|
| `POST /documents/{id}/retry` | `FALHA→PROCESSANDO` ✅ | sim — `repo.enqueue` do step apropriado | Step depende de `last_completed_step`: se "extraido"→classify, se "aguardando_extracao"→extract. Ver Open Question 2 sobre re-enqueue. |
| `POST /documents/{id}/reclassify` | `QUARENTENA→PROCESSANDO` ✅ | sim — classify com `forced_template_id` | **Apagar CR existente antes** (Pattern 3). Body: `{ template_id: int }`. |
| `PATCH /documents/{id}/fields/{field_name}` | nenhuma (não muda estado) | não | Revalida via `validate_field`, marca `manually_corrected=True`. Doc permanece EM_REVISAO. |
| `POST /documents/{id}/approve` | `EM_REVISAO→CONCLUIDO` ✅ | não | Guard: obrigatórios válidos (D-07). |

**Validação contra a allowlist (CLAUDE.md-equivalente):** NUNCA setar `document.state` direto. SEMPRE `transition` — ele valida contra `TRANSITIONS` e faz rollback em transição inválida (Anti-Pattern documentado no worker). Um `retry` chamado num doc que não está em FALHA → `InvalidTransition` → 409, comportamento correto.

### Pattern 5: Frontend — página + hooks TanStack Query (espelha Fase 4)

**What:** Página `AttentionPage` com lista filtrada em 3 baldes + hooks de query (polling) e mutation (ações com `invalidateQueries`).
**When to use:** Visão "Precisam de atenção".

```typescript
// Source: padrão derivado de hooks/useDocuments.ts + hooks/useTemplates.ts
export function useAttentionDocuments() {
  return useQuery({
    queryKey: ['attention'],
    queryFn: getAttention,          // GET /documents?states=falha,quarentena,em_revisao (ou endpoint dedicado)
    refetchInterval: 4000,
    refetchIntervalInBackground: false,
    placeholderData: keepPreviousData,  // sem flicker (padrão estabelecido)
  })
}
export function useApproveDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => postApprove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attention'] })
      qc.invalidateQueries({ queryKey: ['documents'] })  // item some da lista geral também
    },
  })
}
```

**Fonte de dados da lista:** Recomendação — estender `GET /documents` com um parâmetro de filtro de estado OU criar `GET /documents/attention` dedicado que já devolve por balde + o motivo + os campos editáveis (para EM_REVISAO) num só payload (evita N+1 de `GET /documents/{id}` por item). Ver Open Question 3.

### Anti-Patterns to Avoid

- **Calcular o score no frontend:** O score é determinístico e é a fonte de verdade do roteamento de estado (D-04) — deve viver no backend. O frontend só EXIBE.
- **Setar `document.state` direto em qualquer endpoint:** Sempre `transition` (Anti-Pattern já documentado no worker). A allowlist é o único guard de estado válido.
- **Re-chamar a IA na correção de campo (D-08):** O patch usa SÓ `validate_field`. Re-chamar IA gastaria tokens e contraria a decisão travada.
- **Reusar a coluna `confidence` existente para o score:** Semânticas diferentes (D-01). Coluna nova obrigatória.
- **Commit manual antes do `transition` no stage:** Quebra a atomicidade. `transition` comita; os `add` vêm antes dele.
- **Esquecer de apagar o CR de quarentena antes de reclassificar:** A idempotência faz no-op se o CR existir. Apagar primeiro.
- **`dangerouslySetInnerHTML` em valores de campo:** Valores vêm da IA/documento; renderizar como TEXTO PURO (padrão de segurança da Fase 4, T-04-12).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Validação de campo corrigido | Novo validador por tipo | `app.validation.fields.validate_field` | Já cobre data/moeda/CNPJ-Módulo11/regex-com-teto-ReDoS; duplicar divergiria as regras |
| Guard de transição de estado | `if doc.state == X: doc.state = Y` | `app.pipeline.state_machine.transition` | A allowlist `TRANSITIONS` é a fonte de verdade; `transition` faz rollback em inválida |
| Reenfileiramento de job | INSERT manual em `jobs` | `app.queue.repo.enqueue` | Idempotência por UNIQUE(hash,step) + backoff já implementados |
| Polling sem flicker na UI | `setInterval` + fetch manual | TanStack Query `refetchInterval` + `keepPreviousData` | Padrão já provado em `useDocuments`; pausa em background, sem piscar |
| Cálculo de confiança ad-hoc no SQL | Query agregada por documento | Função pura `compute_confidence` no Python | Testável sem DB; o roteamento de estado precisa do resultado em memória no mesmo commit |

**Key insight:** Esta fase é quase inteiramente **composição de primitivas existentes**. O risco real não é construir errado — é **quebrar a atomicidade/idempotência já estabelecida** ao inserir o roteamento de estado e a reclassificação. Toda a alavanca está em reusar `transition`, `validate_field`, `repo.enqueue` e o commit-único do stage exatamente como já fazem.

## Runtime State Inventory

> Esta é uma fase de **schema + lógica nova**, não rename/refactor/migração de dados. Mesmo assim, há um item de estado existente a considerar.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `documents.state` e `classification_results` de docs JÁ classificados pela Fase 4: hoje terminam em `state=PROCESSANDO` + `last_completed_step="classificado"` (nunca EM_REVISAO/CONCLUIDO). Após esta fase, novos docs roteiam para EM_REVISAO/CONCLUIDO, mas os **legados** ficam presos em PROCESSANDO+classificado. | **Decisão de planejamento:** os legados PROCESSANDO+classificado não têm `confidence_score`. Opções: (a) deixá-los como estão (não bloqueiam — nenhum há em produção real ainda, projeto em dev); (b) um sweep idempotente único que recalcula score e roteia. Recomendação: (a) — projeto ainda não tem dados de produção (STATE.md: dev). Documentar como aceito. |
| Live service config | Nenhum serviço externo embute estado desta fase. | None — verificado: sem n8n/Datadog/etc. no projeto. |
| OS-registered state | Nenhum. O worker/watcher sobem no lifespan do FastAPI (não há tarefa de SO registrada). | None — verificado em `main.py`. |
| Secrets/env vars | Novo tunable `REVIEW_CONFIDENCE_THRESHOLD` (env, NÃO secreto). A chave OpenAI não muda (a fase NÃO chama IA). | Adicionar o tunable a `config.py` com `AliasChoices` + default (padrão existente). |
| Build artifacts | Nenhum. Sem mudança em `pyproject.toml`/`package.json` (sem deps novas). | None — sem reinstalação necessária. |

**Migração de dados nova:** A migração 0005 adiciona DUAS colunas nullable (`confidence_score`, `manually_corrected`) — ambas com default seguro, sem backfill obrigatório. `manually_corrected` deve ter `server_default="0"` (Boolean), `confidence_score` é nullable sem default. Ver Pitfall 1 sobre o trigger.

## Common Pitfalls

### Pitfall 1: Migração que toca `documents` recria o trigger `updated_at`

**What goes wrong:** Se o score fosse para `documents` (rejeitado — Pattern 1), o batch recreate do SQLite no Alembic dropa e recria a tabela, **destruindo o trigger `trg_documents_updated_at`** criado na 0002. As migrações 0003/0004 documentam explicitamente que evitam isso por NÃO tocar `documents`.
**Why it happens:** SQLite não tem `ALTER COLUMN`; o Alembic usa batch recreate (drop+create+copy), que perde triggers não redeclarados.
**How to avoid:** Persistir `confidence_score` em `classification_results` e `manually_corrected` em `filled_fields` (Pattern 1) — **nenhuma das duas toca `documents`**, então não há trigger a recriar (mesma situação resolvida em 0003/0004). Se por qualquer motivo `documents` for alterada, a migração DEVE recriar o trigger (como a 0002 faz após batch recreate).
**Warning signs:** `updated_at` para de atualizar em UPDATEs de documento após a migração.

### Pitfall 2: Quebra da atomicidade no roteamento de estado

**What goes wrong:** Inserir `session.commit()` antes do `transition` no stage deixa `ClassificationResult`/`FilledFields` persistidos mas o estado ainda PROCESSANDO se o processo morrer entre os dois commits — estado parcial.
**Why it happens:** O caminho match atual comita direto (porque PROCESSANDO→PROCESSANDO é auto-laço). Ao trocar para transition, é tentador manter o commit antigo + adicionar o transition.
**How to avoid:** Remover o `session.commit()` do passo 9; deixar os `add` na sessão e chamar `transition` (que comita TUDO junto). Espelha exatamente o caminho de quarentena já existente (add CR → transition).
**Warning signs:** Teste que mata a sessão entre commit e transition encontra CR sem estado correspondente.

### Pitfall 3: Idempotência impede a reclassificação de quarentena

**What goes wrong:** Reenfileirar classify para um doc em quarentena → `classify_stage` vê o `ClassificationResult` existente (template_id=None) → no-op. O doc nunca reclassifica.
**Why it happens:** A checagem de idempotência (linha 162-173) é por existência de CR, sem distinguir quarentena de classificação completa.
**How to avoid:** O endpoint de reclassify **apaga** o CR de quarentena antes de `transition(PROCESSANDO)` + `repo.enqueue`. Cascade delete-orphan limpa os FilledFields. Ver Open Question 2 sobre o re-enqueue do job (UNIQUE hash,step).
**Warning signs:** Reclassify retorna 200 mas o doc volta a quarentena sem mudar nada.

### Pitfall 4: `manually_corrected` não recalcula o score / não destrava o approve

**What goes wrong:** Usuário corrige um campo obrigatório inválido → vira válido, mas o `confidence_score` persistido continua o antigo, e o botão Aprovar continua bloqueado (ou aprova com score desatualizado).
**Why it happens:** O patch só atualiza o FilledField; o score em `classification_results` não é recalculado.
**How to avoid:** O endpoint de patch DEVE recalcular `compute_confidence` sobre os FilledFields atualizados e regravar `cr.confidence_score` no mesmo commit. O guard de approve (D-07) deve checar a validade ATUAL dos obrigatórios (re-derivar de FilledField.valid), não confiar só no score persistido.
**Warning signs:** Aprovar fica bloqueado mesmo após o campo virar verde; ou score na UI não muda após correção.

### Pitfall 5: N+1 ao montar a visão "Precisam de atenção"

**What goes wrong:** A página busca a lista de docs em revisão e depois `GET /documents/{id}` por item para ter os campos editáveis → N+1 requests + polling amplifica.
**Why it happens:** `GET /documents` é leve (sem classificação, por design da Fase 4); o detalhe é por-id.
**How to avoid:** Endpoint dedicado `GET /documents/attention` que devolve os 3 baldes com motivo + (para EM_REVISAO) os campos editáveis num payload só. Ou aceitar o N+1 só para o balde EM_REVISAO aberto (lazy). Ver Open Question 3.
**Warning signs:** Network tab mostra dezenas de requests por ciclo de polling.

## Code Examples

### Migração 0005 (padrão das migrações que NÃO tocam `documents`)

```python
# Source: derivado de backend/alembic/versions/0004_templates_classification.py
def upgrade() -> None:
    with op.batch_alter_table('classification_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('confidence_score', sa.Float(), nullable=True))
    with op.batch_alter_table('filled_fields', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('manually_corrected', sa.Boolean(), nullable=False, server_default='0')
        )
# NOTA: nenhuma das tabelas é `documents` → o trigger trg_documents_updated_at
# NÃO é afetado (mesma situação documentada nas migrações 0003/0004).
```

### Tunable do limiar (padrão `config.py`)

```python
# Source: derivado de backend/app/config.py (padrão classify_match_threshold)
review_confidence_threshold: float = Field(
    default=0.8,  # ≥80% = alta (alinha com a faixa "Alta" do 05-UI-SPEC); calibrar
    validation_alias=AliasChoices(
        "REVIEW_CONFIDENCE_THRESHOLD", "review_confidence_threshold"
    ),
)
```

### Endpoint de patch de campo (revalidação sem IA, D-08)

```python
# Source: padrão api/documents.py + validation.fields.validate_field
class FieldPatchIn(BaseModel):
    raw_value: str | None

@router.patch("/documents/{document_id}/fields/{field_name}", response_model=DocumentDetailOut)
def patch_field(request: Request, document_id: int, field_name: str, body: FieldPatchIn):
    engine = request.app.state.engine
    with get_session(engine) as session:
        cr = session.scalar(select(ClassificationResult).where(
            ClassificationResult.document_id == document_id))
        if cr is None:
            raise HTTPException(404, "classificação não encontrada")
        ff = session.scalar(select(FilledField).where(
            FilledField.classification_result_id == cr.id,
            FilledField.field_name == field_name))
        if ff is None:
            raise HTTPException(404, "campo não encontrado")
        # Reusa o TemplateField para o tipo/required/regex (join via template).
        tf = _template_field(session, cr.template_id, field_name)
        v = validate_field(field_type=tf.field_type, raw=body.raw_value,
                           required=tf.required, regex=tf.regex)
        ff.raw_value = v.raw_value
        ff.normalized_value = v.normalized_value
        ff.valid = v.valid
        ff.invalid_reason = v.invalid_reason
        ff.manually_corrected = True            # D-08: origem manual
        # Pitfall 4: recalcular o score no mesmo commit.
        cr.confidence_score, _ = compute_confidence(cr.filled_fields, _template_fields(session, cr.template_id))
        session.commit()
        # ... retorna detalhe
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `state=PROCESSANDO` + `last_completed_step="classificado"` ao final do classify (Fase 4) | `transition` para EM_REVISAO ou CONCLUIDO com base no score/validação (Fase 5) | Esta fase | O estado terminal do classify deixa de ser PROCESSANDO; novos docs roteiam corretamente. Legados ficam em PROCESSANDO+classificado (ver Runtime State Inventory). |
| Confiança = só `confidence` do matcher (classificação) | + `confidence_score` (qualidade de extração, D-01) | Esta fase | Duas métricas distintas coexistem; a UI exibe o `confidence_score` como "Confiança". |
| Detalhe de classificação somente leitura (S4, Fase 4) | Detalhe editável (patch de campo + approve) na visão de atenção | Esta fase | `DocumentDetailModal` ganha modo editável OU a nova `AttentionPage` traz a edição. |

**Deprecated/outdated:** Nada deprecado. O `DocumentDetailModal` somente-leitura da Fase 4 permanece válido para docs CONCLUIDO/quarentena vistos da lista geral; a edição vive na visão de atenção.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Versões pinadas (FastAPI 0.137.1, openai 2.41.x, TanStack 5.101) permanecem corretas e não precisam de bump nesta fase | Standard Stack | Baixo — a fase não toca a integração OpenAI nem instala nada; mesmo que uma versão esteja stale, não afeta este escopo |
| A2 | Default do limiar de revisão = 0.8 (alinha com a faixa "Alta ≥80%" do 05-UI-SPEC) | Code Examples | Médio — valor de produto, deve ser confirmado pelo usuário/discuss; é só o default, ajustável por env (D-03) |
| A3 | Auto-CONCLUIDO ao final do classify quando score alto + obrigatórios válidos | Pattern 2 / Open Q1 | **Alto** — ver Open Question 1: CONCLUIDO pode ser prematuro porque as automações de arquivo são a Fase 6. Precisa de decisão. |
| A4 | Legados PROCESSANDO+classificado podem ficar como estão (sem backfill) | Runtime State Inventory | Baixo — projeto em dev sem dados de produção (STATE.md) |

## Open Questions (RESOLVED)

> **As 3 questões foram RESOLVIDAS no planejamento da Fase 5 (2026-06-16).** Resumo das resoluções inline abaixo; a implementação completa está nos planos 05-02 e 05-03.

1. **CONCLUIDO automático vs estado intermediário antes da Fase 6?** — **RESOLVED:** o `classify_stage` NUNCA transita para CONCLUIDO. Doc que passa (score ≥ limiar + obrigatórios válidos) **permanece PROCESSANDO + last_completed_step="classificado"** (estado terminal da Fase 4, preserva o ponto de captura da Fase 6); CONCLUIDO só ocorre via `approve` humano de EM_REVISAO (Plan 03-T1). Grep-gate em 05-02-PLAN.md Task 1 acceptance_criteria confirma a AUSÊNCIA de `DocState.CONCLUIDO` no stage.
   - What we know: D-07 diz "aprovar = EM_REVISAO→CONCLUIDO" e "CONCLUIDO = pronto; automações são a Fase 6". O sucesso-critério 4 da fase fala de aprovar→CONCLUIDO. CONCLUIDO é terminal (sem saídas na allowlist).
   - What's unclear: Quando um doc passa direto (score alto + obrigatórios válidos), ele deve ir AUTO para CONCLUIDO no stage, ou permanecer num estado que a Fase 6 consome para aplicar automações? Se CONCLUIDO é terminal e a Fase 6 precisa agir sobre docs "prontos para automação", ir direto a CONCLUIDO no classify pode pular o ponto de captura da Fase 6.
   - Recommendation: **Levar isto ao planejamento/discuss.** Duas leituras válidas: (a) auto-CONCLUIDO e a Fase 6 reabre/age sobre CONCLUIDO (mas CONCLUIDO é terminal — exigiria mudar a allowlist); (b) score alto NÃO auto-conclui — vai para EM_REVISAO de qualquer forma OU para um estado "pronto" só-Fase-6. A leitura mais conservadora com a allowlist ATUAL: docs que passam ficam aptos a CONCLUIDO, mas a transição CONCLUIDO só ocorre quando há ação humana (approve) OU quando a Fase 6 define o gatilho. **Sugestão para o plano:** rotear "passou" para CONCLUIDO só se isso não conflitar com a Fase 6; caso contrário, manter EM_REVISAO ou introduzir o estado de automação na Fase 6. NÃO resolver nesta pesquisa — é decisão de produto + arquitetura cross-fase.

2. **Re-enqueue de job classify viola a UNIQUE `(original_hash, step)`?** — **RESOLVED:** novo helper `repo.requeue_step(session, *, content_hash, step, payload)` (Plan 02-T2), análogo a `requeue_running` — `UPDATE jobs SET status='pending', payload=:payload, next_run_at=:now, attempts=0 WHERE original_hash=:hash AND step=:step` — reseta a linha existente para pending, mantendo a UNIQUE. O endpoint de reclassify apaga o CR de quarentena ANTES e usa `requeue_step` (não `enqueue`).
   - What we know: `repo.enqueue` é no-op se já existe `(content_hash, "classify")`. Um doc que já passou por classify TEM esse job (provavelmente `done`).
   - What's unclear: Para reclassificar (quarentena) ou retry, precisamos de um NOVO job classify, mas a linha antiga (status `done`) ainda satisfaz a UNIQUE → `enqueue` retorna None → nada roda.
   - Recommendation: Resolver no plano. Opções: (a) apagar/atualizar o job antigo para `pending` (reset) em vez de inserir novo — `UPDATE jobs SET status='pending', next_run_at=now WHERE original_hash=X AND step='classify'`; (b) incluir um discriminador no `step` (ex.: `classify:reclassify`) — mas isso fragmenta a idempotência. **Recomendação firme: reset do job existente para pending** (novo helper em `repo.py`, ex.: `requeue_step(content_hash, step)`), análogo a `requeue_running`. Isso reusa a linha e mantém a UNIQUE. Confirmar no plano que o sweep idempotente não re-cria o job antes do reset.

3. **Endpoint dedicado de atenção vs filtro em `GET /documents`?** — **RESOLVED:** endpoint dedicado `GET /documents/attention` (Plan 03-T2) que devolve os 3 baldes (FALHA/QUARENTENA/EM_REVISAO) num payload único — para EM_REVISAO inclui os campos editáveis via join/selectinload, evitando o N+1 (Pitfall 5).
   - What we know: `GET /documents` é leve (sem classificação, por design). A visão de atenção precisa de motivo + campos editáveis (EM_REVISAO).
   - What's unclear: Criar `GET /documents/attention` (payload rico, 1 request) ou parametrizar `GET /documents` + lazy `GET /documents/{id}` por item aberto.
   - Recommendation: `GET /documents/attention` dedicado evita N+1 (Pitfall 5) e casa com o mock de "3 baldes num payload". Decidir no plano; ambos são viáveis.

## Environment Availability

> Fase code-and-config only. Dependências externas mínimas — todas já validadas em fases anteriores.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Backend | ✓ (assumido — fases 1-4 rodaram) | 3.12 | — |
| Node/npm | Frontend build | ✓ (assumido — Fase 4 buildou UI) | ≥20.19 | — |
| SQLite RETURNING | `repo.py` (já em uso) | ✓ | ≥3.35 (ambiente 3.50.4 confirmado em repo.py) | — |
| OpenAI API | **NÃO usada nesta fase** | N/A | — | A fase não chama IA (D-08); reclassify re-roda o stage que PODE chamar IA-faltantes se o template forçado tiver obrigatórios sem par — mas isso é o caminho normal já testado |

**Missing dependencies with no fallback:** Nenhuma.
**Missing dependencies with fallback:** Nenhuma.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.0 + pytest-asyncio (`asyncio_mode = "auto"`) |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| Quick run command | `cd backend && uv run pytest tests/classification/ -x -q` |
| Full suite command | `cd backend && uv run pytest -q` |
| OpenAI mocking | `respx` interceptando `POST /v1/responses` (padrão em `tests/classification/conftest.py` — 0 token) |
| API testing | `fastapi.testclient.TestClient` com `app.state.engine` sobrescrito por `schema_engine` (padrão `test_api_documents.py`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REV-01 | Score = fração de obrigatórios válidos (pura) | unit | `pytest tests/classification/test_confidence.py -x` | ❌ Wave 0 |
| REV-01 | Score 0% quando todos obrigatórios inválidos; 100% sem obrigatórios | unit | `pytest tests/classification/test_confidence.py -x` | ❌ Wave 0 |
| REV-01/REV-02 | `confidence_score` persistido em `classification_results` após classify | unit | `pytest tests/classification/test_stage_routing.py -x` | ❌ Wave 0 |
| REV-02/REV-04 | Roteia EM_REVISAO quando score < limiar | unit | `pytest tests/classification/test_stage_routing.py -x` | ❌ Wave 0 |
| REV-04 | Roteia EM_REVISAO quando obrigatório inválido mesmo com score alto (D-04) | unit | `pytest tests/classification/test_stage_routing.py -x` | ❌ Wave 0 |
| REV-04 | Roteia CONCLUIDO quando todos válidos + score ≥ limiar (ver Open Q1) | unit | `pytest tests/classification/test_stage_routing.py -x` | ❌ Wave 0 |
| REV-05 | `forced_template_id` pula matcher e usa filler+validação | unit | `pytest tests/classification/test_forced_template.py -x` | ❌ Wave 0 |
| REV-05 | Reclassify apaga CR de quarentena + reenfileira (não no-op) | integration | `pytest tests/test_api_review.py -x` | ❌ Wave 0 |
| REV-04 | Patch de campo revalida via `validate_field`, marca `manually_corrected`, NÃO chama IA (respx call_count==0) | integration | `pytest tests/test_api_review.py -x` | ❌ Wave 0 |
| REV-04 | Patch recalcula `confidence_score` (Pitfall 4) | integration | `pytest tests/test_api_review.py -x` | ❌ Wave 0 |
| REV-04 | Approve bloqueado (409) com obrigatório inválido; sucesso após correção (D-07) | integration | `pytest tests/test_api_review.py -x` | ❌ Wave 0 |
| REV-04 | Retry de doc não-FALHA → 409 (InvalidTransition via allowlist) | integration | `pytest tests/test_api_review.py -x` | ❌ Wave 0 |
| REV-03 | (Frontend) lista 3 baldes, polling, invalidação após ação | manual/visual | verificação visual (ui-phase) | N/A frontend |

### Sampling Rate

- **Per task commit:** `cd backend && uv run pytest tests/classification/ -x -q` (cálculo de confiança + roteamento — rápido, sem rede)
- **Per wave merge:** `cd backend && uv run pytest -q` (suite completa, respx mocka OpenAI)
- **Phase gate:** Suite completa verde + verificação visual da `AttentionPage` antes de `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/classification/test_confidence.py` — cobre REV-01 (função pura `compute_confidence`)
- [ ] `tests/classification/test_stage_routing.py` — cobre REV-02/REV-04 (EM_REVISAO vs CONCLUIDO vs QUARENTENA; persistência do score)
- [ ] `tests/classification/test_forced_template.py` — cobre REV-05 (caminho de template forçado, pula matcher)
- [ ] `tests/test_api_review.py` — cobre REV-04/REV-05 (4 endpoints: retry/reclassify/patch/approve, guards de allowlist, sem-IA no patch)
- [ ] Confirmar que `compute_confidence` é função PURA (sem DB/IA) para teste rápido isolado
- [ ] Reusar `_envelope`/`mock_openai_classify` de `tests/classification/conftest.py` para os casos de reclassify que disparam IA-faltantes

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1`. Fase com endpoints novos que aceitam input do usuário (correção de campo, atribuição de template).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Produto single-tenant local; sem autenticação no v1 (out of scope do projeto) |
| V3 Session Management | no | Sem sessão/login |
| V4 Access Control | no | Single-tenant; um operador, sem multiusuário (out of scope) |
| V5 Input Validation | **yes** | Pydantic nos bodies (`FieldPatchIn`, `{template_id}`); `validate_field` com teto `_MAX_REGEX_LEN` (ReDoS) já aplicado; `document_id`/`template_id` tipados `int` na rota (sem string-building de SQL); valores renderizados como TEXTO PURO no React (sem `dangerouslySetInnerHTML`, T-04-12) |
| V6 Cryptography | no | Sem cripto nova nesta fase; a chave OpenAI (SecretStr) não é tocada |

### Known Threat Patterns for FastAPI + SQLAlchemy + React (esta fase)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `document_id`/`field_name`/`template_id` | Tampering | ORM SQLAlchemy parametrizado; ids tipados `int`; `field_name` usado em `where(... == field_name)` parametrizado, nunca concatenado (padrão T-04-09) |
| ReDoS via regex do template na revalidação | DoS | `validate_field` já limita o valor a `_MAX_REGEX_LEN` antes do `re.fullmatch` (V5, já implementado) |
| XSS via valor de campo corrigido renderizado na UI | Tampering/Elevation | React renderiza como texto puro; proibido `dangerouslySetInnerHTML` (padrão da Fase 4) |
| Transição de estado ilegal forçada por endpoint (ex.: approve de doc em QUARENTENA) | Tampering | `transition` valida contra a allowlist `TRANSITIONS` e faz rollback; endpoint converte `InvalidTransition`→409 |
| Information disclosure: valores extraídos sensíveis (CNPJ/CPF) em logs | Information Disclosure | Endpoints NÃO logam valores de campo (padrão T-04-11 já em `documents.py`); valores só no corpo da resposta |
| Custo não autorizado: re-chamar IA na correção | (custo) | Patch de campo NÃO chama IA (D-08); teste prova `call_count==0` |

## Sources

### Primary (HIGH confidence)
- Código-fonte do repositório (lido integralmente nesta sessão): `backend/app/classification/stage.py`, `matcher.py`, `filler.py`, `openai_client.py`; `models/classification.py`, `document.py`, `enums.py`; `pipeline/states.py`, `state_machine.py`; `validation/fields.py`; `queue/worker.py`, `repo.py`; `config.py`, `main.py`; `api/documents.py`, `templates.py`; `alembic/versions/0004_templates_classification.py` — base autoritativa de todas as recomendações de arquitetura interna.
- `frontend/src/`: `lib/api.ts`, `hooks/useDocuments.ts`, `useTemplates.ts`, `types.ts`, `pages/DocumentsPage.tsx`, `components/StatusPill.tsx` — padrões de UI estabelecidos.
- `backend/tests/classification/test_stage.py`, `conftest.py`, `test_api_documents.py`, `pyproject.toml` — padrões de teste (respx, TestClient, schema_engine).
- `.planning/phases/05-.../05-CONTEXT.md` (D-01..D-09) e `05-UI-SPEC.md` (design TRAVADO) — constraints travadas.
- `.planning/REQUIREMENTS.md` (REV-01..05), `ROADMAP.md` (Phase 5 goal/SC), `STATE.md` — escopo e histórico.
- `CLAUDE.md` do projeto — stack prescritivo (FastAPI/SQLAlchemy/Alembic/TanStack), versões pinadas.

### Secondary (MEDIUM confidence)
- Nenhuma busca externa necessária — fase brownfield code-and-config sem deps novas.

### Tertiary (LOW confidence)
- Nenhuma.

## Project Constraints (from CLAUDE.md)

- **Stack travado:** FastAPI + Pydantic 2 + SQLAlchemy 2.0 + Alembic + React 19 + Vite + TanStack Query. Esta fase usa exatamente isso; nenhuma lib nova.
- **Schema só via Alembic** — nenhum `create_all` em produção (migração 0005).
- **SQLite (WAL) + fila in-process** — sem broker; reusar `repo.enqueue`.
- **Integridade de arquivos / reversibilidade** — esta fase NÃO mexe em arquivos (web = gestão; arquivos via Explorer, D-06); automações de arquivo são a Fase 6.
- **Chave OpenAI como SecretStr, nunca em logs** — não tocada nesta fase.
- **GSD workflow enforcement** — mudanças de arquivo só via comando GSD (esta pesquisa não edita código).
- **Idioma das respostas / docs:** pt-BR.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — todas as libs já pinadas e em uso; nenhuma instalação nova
- Architecture: HIGH — recomendações derivadas de código lido por inteiro; os 3 padrões (score em classification_results, roteamento no commit único, forced_template_id) encaixam nas garantias existentes (atomicidade/idempotência/allowlist)
- Pitfalls: HIGH — cada pitfall é ancorado em código real (trigger updated_at nas migrações 0003/0004; idempotência por CR no stage; UNIQUE hash,step no repo)
- Open Questions: As 3 são decisões de planejamento/produto genuínas (auto-CONCLUIDO cross-fase; re-enqueue do job; endpoint dedicado), corretamente deferidas

**Research date:** 2026-06-16
**Valid until:** ~2026-07-16 (estável — fase interna; o único risco de staleness é o bump de versão de libs, irrelevante para este escopo)

## RESEARCH COMPLETE

"""Estágio de automação — orquestra regras→naming→fileops→audit write-ahead→estado
num fluxo IDEMPOTENTE (Fase 6, coração: AUT-03/AUT-04/AUT-06, D-01/D-07).

Espelha `classification/stage.py` em forma e garantias: função isolável (sem HTTP),
idempotente e com persistência ATÔMICA via `transition`. REDESIGN (06-07): executa o
PIPELINE ordenado (`pipeline.run_pipeline`) e materializa do CAS UMA ÚNICA VEZ ao
final (Open Q1). Liga as peças puras:
- `automation.pipeline` (executor PURO `run_pipeline` — itera as etapas, D-12..D-15);
- `automation.rules` (filtros de entrada `filter_matches`, D-14);
- `automation.naming` (`resolve_pattern`/`resolve_dest_folder`, confinado V4 — usado
  dentro do executor);
- `automation.fileops` (`materialize_to_dest` do CAS + `remove_original`, AUT-06);
à persistência do Plan 01 (`AuditLog` write-ahead) e à máquina de estados (`transition`).

Garantias materializadas:
- **Idempotência (Pattern 1):** checa `AuditLog(document_id, status="done")` ANTES de
  qualquer operação física → no-op (NÃO re-materializa). Espelha o `existing is not
  None` do classify_stage.
- **Write-ahead (AUT-04 / T-06-12):** `AuditLog(status="intent", source_path,
  dest_path, run_id, content_hash)` é persistido (commit) ANTES de tocar o disco
  (`materialize_to_dest`). Um crash entre intent e done deixa um `intent` órfão
  RECONCILIÁVEL no startup (`reconcile_orphans`).
- **Copia→verifica→remove a origem (AUT-06 crit 5):** `materialize_to_dest` escreve
  do CAS e verifica o hash; só ENTÃO `remove_original(source_path)` remove o
  original da pasta de origem. Falha de disco propaga (a origem fica intacta).
- **Estado via transition (commit único):** ao concluir, `transition(CONCLUIDO,
  completed_step="aplicado")` comita o `status="done"` + o estado JUNTOS. NUNCA
  `session.commit()` manual antes do transition (quebraria a atomicidade).
- **Bloqueio → revisão (D-07):** token referenciando campo faltante/inválido (ou
  destino que escaparia da raiz-base, V4) → `resolve_*` devolve None →
  `transition(EM_REVISAO)` SEM tocar o disco e SEM AuditLog de operação.
- **Duplicata idêntica (D-10):** destino já contém o mesmo conteúdo → conclui sem
  mover (no-op de disco).
- **Não vazar conteúdo (V7/V9):** loga só metadados (doc.id, paths, run_id, status)
  — NUNCA valores de campo.

Interface pública: `apply_stage`, `dry_run`, `reconcile_orphans`, `ApplyStageResult`,
`APPLY_STEP`.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.automation import fileops
from app.automation.pipeline import PipelinePlan, PipelineStepSpec, run_pipeline
from app.automation.rules import FilterSpec
from app.config import get_settings
from app.models.audit_log import AuditLog
from app.models.automation_pipeline import (
    AutomationPipeline,
    PipelineStep,
)
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.models.ingested_original import IngestedOriginal
from app.models.watched_folder import WatchedFolder
from app.pipeline.state_machine import transition
from app.storage import cas

logger = logging.getLogger(__name__)

# Step do job de automação despachado pelo worker (Plan 04). A fila enfileira
# (block.content_hash, APPLY_STEP) quando o doc está pronto para aplicar.
APPLY_STEP = "apply"

# Marcador interno avançado ao concluir a automação (D-05). NÃO é estado de topo.
APPLIED_STEP = "aplicado"

# Marcador ao qual o documento volta quando rebaixado para revisão (D-07).
CLASSIFIED_STEP = "classificado"

# Marcador interno do step Rotear "não-tratar"/"ignorar" (Pitfall 9 / A4): conclui
# logicamente sem materializar; NÃO é um DocState novo (mantém o enum enxuto).
ROUTED_STEP = "roteado"

# Ação registrada no AuditLog write-ahead.
_ACTION = "apply"


@dataclass(frozen=True)
class ApplyStageResult:
    """Resultado de `apply_stage`/`dry_run`: o plano origem→destino e o que ocorreu.

    `materialized=True` só quando a operação física de fato escreveu no destino
    (não em no-op idempotente, duplicata idêntica D-10, dry-run ou bloqueio D-07).
    `blocked=True` quando o destino não pôde ser resolvido (campo faltante/inválido
    ou confinamento V4) e o documento foi rebaixado para revisão.
    `collision=True` quando o nome de destino colidiu e foi resolvido por sufixo
    (D-09) — informativo para o preview do dry-run.
    """

    document_id: int
    source_path: str | None
    dest_path: str | None
    materialized: bool
    blocked: bool
    collision: bool
    skipped_identical: bool
    # Pipeline REDESIGN (06-07): sinaliza Rotear (Pitfall 9) e no-match (Pitfall 10)
    # para o preview da UI. routed=True quando uma etapa Rotear interrompeu o
    # pipeline; route_target é o alvo ("em_revisao"/"nao_tratar"/"ignorar").
    # no_match=True quando NENHUMA etapa casou (no-op explícito, doc fica na origem).
    routed: bool = False
    route_target: str | None = None
    no_match: bool = False


def _filters_to_pure(step: PipelineStep) -> list[FilterSpec]:
    """Mapeia os `StepFilter` ORM da etapa para a forma pura `FilterSpec` (D-14).

    Ordena por `position`. Só metadados de configuração — sem valores de campo do
    documento.
    """
    return [
        FilterSpec(
            filter_type=f.filter_type,
            operator=f.operator,
            value=f.value,
            field_name=f.field_name,
        )
        for f in sorted(step.filters, key=lambda f: f.position)
    ]


def _load_pipeline_specs(session: Session) -> list[PipelineStepSpec]:
    """Carrega o pipeline ATIVO e mapeia seus steps ORM → `PipelineStepSpec` puros.

    Decisão de produto (v1): assume UM `AutomationPipeline` ativo. Carrega TODOS os
    seus steps (inclusive os pausados — o executor puro pula os `active=False`,
    mantendo a decisão num único lugar), ordenados por `position`. `params_json` é
    desserializado (json.loads; vazio/inválido → {}). Sem pipeline ativo → lista
    vazia (o executor produz um plano default que o caller trata como no-match).
    """
    pipeline = session.scalar(
        select(AutomationPipeline)
        .where(AutomationPipeline.active.is_(True))
        .order_by(AutomationPipeline.id)
    )
    if pipeline is None:
        return []

    specs: list[PipelineStepSpec] = []
    for step in sorted(pipeline.steps, key=lambda s: s.position):
        try:
            params = json.loads(step.params_json) if step.params_json else {}
        except (ValueError, TypeError):
            params = {}
        if not isinstance(params, dict):
            params = {}
        specs.append(
            PipelineStepSpec(
                position=step.position,
                action_type=step.action_type,
                conjunction=step.conjunction,
                params=params,
                filters=_filters_to_pure(step),
                active=step.active,
            )
        )
    return specs


def _fields_map(session: Session, doc: Document) -> dict[str, str]:
    """Monta `{field_name: normalized_value}` dos campos VÁLIDOS do documento.

    Consome o `ClassificationResult` + `FilledField`s do doc. Só os campos válidos
    com valor normalizado entram (D-07: um campo faltante/inválido simplesmente não
    está no mapa, então um token que o referencie resolve para None → bloqueio). NÃO
    loga valores (V7/V9).
    """
    cr = session.scalar(
        select(ClassificationResult).where(ClassificationResult.document_id == doc.id)
    )
    if cr is None:
        return {}
    fields = session.scalars(
        select(FilledField).where(FilledField.classification_result_id == cr.id)
    ).all()
    result: dict[str, str] = {}
    for ff in fields:
        if ff.valid and ff.normalized_value is not None and ff.normalized_value.strip():
            result[ff.field_name] = ff.normalized_value
    return result


def _source_path(session: Session, doc: Document) -> Path:
    """Reconstrói o caminho de ORIGEM do arquivo do documento.

    Padrão de documents.py: `WatchedFolder.path / IngestedOriginal.original_filename`
    via `origin_original_id`. Sem original registrado (ex.: testes/legados) → cai no
    `original_filename` do próprio documento como caminho relativo. NÃO loga conteúdo.
    """
    if doc.origin_original_id is not None:
        row = session.execute(
            select(WatchedFolder.path, IngestedOriginal.original_filename)
            .join(
                IngestedOriginal,
                IngestedOriginal.source_folder_id == WatchedFolder.id,
            )
            .where(IngestedOriginal.id == doc.origin_original_id)
        ).first()
        if row is not None:
            folder_path, original_filename = row
            return Path(folder_path) / original_filename
    return Path(doc.original_filename)


def _base_root() -> Path:
    """Raiz-base de confinamento dos destinos (V4).

    `automation_dest_root` da config quando definido (o cliente trava a base por env);
    caso contrário, uma pasta padrão sob a pasta de dados única (`data_dir/organizados`).
    Confinamento é responsabilidade de `naming.resolve_dest_folder` (is_relative_to).
    """
    settings = get_settings()
    if settings.automation_dest_root:
        return Path(settings.automation_dest_root)
    return settings.data_dir / "organizados"


def _file_attrs(session: Session, doc: Document, source: Path) -> dict:
    """Monta os atributos de arquivo do documento — base dos filtros D-14.

    `ext` (suffix do original), `size` (do CAS pelo content_hash; A6 — lido UMA vez),
    `source_folder_id` (via `IngestedOriginal`), `original_filename` e `template_id`
    (do `ClassificationResult` existente, porteiro do gate). NÃO loga valores.
    """
    original_filename = doc.original_filename
    source_folder_id: int | None = None
    if doc.origin_original_id is not None:
        original = session.get(IngestedOriginal, doc.origin_original_id)
        if original is not None:
            source_folder_id = original.source_folder_id
            original_filename = original.original_filename

    # Tamanho: lê o blob do CAS uma vez (A6). Ausente/erro → 0 (filtro size não casa).
    size = 0
    try:
        if cas.exists(doc.content_hash):
            size = len(cas.read_bytes(doc.content_hash))
    except OSError:
        size = 0

    template_id: int | None = None
    cr = session.scalar(
        select(ClassificationResult).where(
            ClassificationResult.document_id == doc.id
        )
    )
    if cr is not None:
        template_id = cr.template_id

    return {
        "ext": Path(original_filename).suffix,
        "size": size,
        "source_folder_id": source_folder_id,
        "original_filename": Path(original_filename).name,
        "template_id": template_id,
    }


def _make_classify_fn(session: Session, doc: Document):
    """Closure do gate identify_type (D-15): LÊ o `ClassificationResult` existente.

    Gate v1 (06-RESEARCH A3): o doc chega ao apply já classificado, então o gate lê
    o `template_id` do `ClassificationResult` existente (custo 0, NÃO re-cobra a IA).
    Quando o step trava um `template_id` específico no params, esse valor é usado
    como o template confirmado (porteiro dos filtros `template` seguintes). A
    re-classificação forçada no meio do pipeline (await `classify_stage`) fica como
    evolução fora do v1 — documentada (não bloqueia este plano).
    """
    cr = session.scalar(
        select(ClassificationResult).where(
            ClassificationResult.document_id == doc.id
        )
    )
    existing = cr.template_id if cr is not None else None

    def classify_fn(forced_template_id: int | None) -> int | None:
        # Step fixa um template-alvo → usa-o; senão devolve o já classificado (custo 0).
        return forced_template_id if forced_template_id is not None else existing

    return classify_fn


def _resolve_plan(session: Session, doc: Document) -> tuple[Path, PipelinePlan]:
    """Executa o pipeline ATIVO e devolve (source_path, PipelinePlan). NÃO toca o disco.

    Monta `fields` (campos extraídos), `file_attrs` (dimensão de arquivo, D-14) e os
    `PipelineStepSpec` do pipeline ativo, e chama `run_pipeline` (PURO). O caller
    (dry_run/apply_stage) interpreta o `PipelinePlan`: `blocked` → revisão; `route_to`
    → transição/marcador; `matched_any=False` → no-op explícito; senão materializa o
    par `(target_folder, target_name)` UMA vez. NÃO loga valores.
    """
    fields = _fields_map(session, doc)
    base_root = _base_root()
    source = _source_path(session, doc)
    file_attrs = _file_attrs(session, doc, source)
    specs = _load_pipeline_specs(session)
    classify_fn = _make_classify_fn(session, doc)

    plan = run_pipeline(
        specs, fields, file_attrs, base_root=base_root, classify_fn=classify_fn
    )
    return source, plan


def _plan_dest(source: Path, plan: PipelinePlan) -> Path:
    """Compõe o caminho-destino final do `PipelinePlan` (pasta/nome), preservando ext.

    Sanitiza o nome-alvo como componente; se o padrão não trouxe extensão e a origem
    tem, preserva a extensão do original (igual ao comportamento anterior). Só faz
    sentido quando o plano NÃO está bloqueado/roteado.
    """
    folder = plan.target_folder if plan.target_folder is not None else source.parent
    name = plan.target_name if plan.target_name is not None else source.name
    if not Path(name).suffix and source.suffix:
        name = name + source.suffix
    return folder / name


def _has_done(session: Session, document_id: int) -> bool:
    """True se já existe um AuditLog(status="done") para o doc (idempotência)."""
    existing = session.scalar(
        select(AuditLog).where(
            AuditLog.document_id == document_id,
            AuditLog.status == "done",
        )
    )
    return existing is not None


def dry_run(session: Session, *, content_hash: str) -> ApplyStageResult | None:
    """Simula o pipeline INTEIRO por doc SEM tocar o disco e SEM AuditLog (AUT-03).

    Localiza o documento por `content_hash`; executa o pipeline ativo (`_resolve_plan`)
    e interpreta o `PipelinePlan`, sinalizando para o preview da UI: `routed`+
    `route_target` (Pitfall 9), `no_match` (Pitfall 10), `blocked` (D-07), `collision`
    (D-09) e `skipped_identical` (D-10). NUNCA move nem escreve AuditLog. Documento
    inexistente → None. NÃO loga valores.
    """
    doc = session.scalar(select(Document).where(Document.content_hash == content_hash))
    if doc is None:
        return None

    source, plan = _resolve_plan(session, doc)

    # Rotear (Pitfall 9): o pipeline desviou — não há destino a materializar.
    if plan.route_to is not None:
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
            routed=True,
            route_target=plan.route_to,
        )

    # Bloqueio (D-07): campo faltante/inválido ou confinamento V4.
    if plan.blocked:
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=True,
            collision=False,
            skipped_identical=False,
        )

    # No-match (Pitfall 10): nenhuma etapa casou — doc fica na origem (no-op).
    if not plan.matched_any:
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
            no_match=True,
        )

    dest = _plan_dest(source, plan)

    # Sinaliza colisão/duplicata SEM tocar o disco: só consulta a existência.
    collision = False
    skipped_identical = False
    if dest.exists():
        try:
            resolved = fileops.resolve_collision(dest, source)
        except OSError:
            resolved = None
        if resolved is None:
            skipped_identical = True  # D-10 (idêntico)
        elif resolved != dest:
            collision = True  # D-09 (sufixo)
            dest = resolved

    return ApplyStageResult(
        document_id=doc.id,
        source_path=str(source),
        dest_path=str(dest),
        materialized=False,
        blocked=False,
        collision=collision,
        skipped_identical=skipped_identical,
    )


async def apply_stage(
    session: Session, *, content_hash: str, run_id: str | None = None, dry_run: bool = False
) -> ApplyStageResult:
    """Executa o pipeline ATIVO no bloco `content_hash`: write-ahead → materializa 1x → conclui.

    Coroutine (espelha `classify_stage`; o worker faz `await`). Fluxo (06-RESEARCH
    Pattern 1/4/5):
      1. Localiza o `Document` por `content_hash` (None → ValueError, o worker re-tenta).
      2. IDEMPOTÊNCIA: `AuditLog(status="done")` existente → no-op (NÃO re-materializa).
      3. Executa o pipeline (`_resolve_plan` → `PipelinePlan`):
         - `route_to` (Pitfall 9): "em_revisao" → `transition(EM_REVISAO)`; "nao_tratar"/
           "ignorar" → marcador interno (NÃO novo DocState — conclui logicamente). NUNCA
           materializa;
         - `blocked` (D-07): `transition(EM_REVISAO)` SEM tocar o disco e SEM AuditLog;
         - `matched_any=False` (Pitfall 10): NO-OP explícito — doc MANTIDO NA ORIGEM,
           SEM transição e SEM tocar o disco. NUNCA materializa p/ a raiz.
      4. `dry_run=True` → devolve o plano SEM AuditLog e SEM disco (AUT-03).
      5. Anti-colisão (`resolve_collision`): idêntico → conclui sem mover (D-10);
         diferente → sufixo (D-09).
      6. WRITE-AHEAD: `AuditLog(status="intent", ...)` + `session.commit()` ANTES de
         materializar (AUT-04) — materialização ÚNICA (Open Q1).
      7. `materialize_to_dest` (do CAS, verifica hash). Erros de disco PROPAGAM ao
         worker (a origem fica intacta — AUT-06).
      8. `remove_original(source)` — só APÓS a verificação passar (AUT-06 crit 5).
      9. `audit.status="done"` + `transition(CONCLUIDO, completed_step="aplicado")`
         num COMMIT ÚNICO (NUNCA commit manual antes do transition).

    Recusa/erros de disco PROPAGAM (sem try/catch aqui). NÃO loga valores de campo.
    """
    doc = session.scalar(select(Document).where(Document.content_hash == content_hash))
    if doc is None:
        raise ValueError("Document inexistente para content_hash informado")

    # (2) Idempotência (Pattern 1): operação já concluída → no-op.
    if _has_done(session, doc.id):
        logger.debug("Automação já aplicada para document_id=%s — no-op", doc.id)
        return ApplyStageResult(
            document_id=doc.id,
            source_path=None,
            dest_path=None,
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
        )

    # (3) Executar o pipeline ativo. Interpreta route/blocked/no-match ANTES de tocar
    # o disco.
    source, plan = _resolve_plan(session, doc)

    # (3a) Rotear (Pitfall 9): interrompe e NÃO materializa.
    if plan.route_to is not None:
        target = (plan.route_to or "").strip().casefold()
        if target == "em_revisao":
            if doc.state == DocState.PROCESSANDO:
                transition(
                    session, doc, DocState.EM_REVISAO, completed_step=CLASSIFIED_STEP
                )
            logger.info("Documento %s roteado para EM_REVISAO (Rotear, P9)", doc.id)
        else:
            # "nao_tratar"/"ignorar": marcador interno (A4) — conclui logicamente sem
            # mover. Avança o marcador de etapa sem materializar; NÃO cria novo DocState.
            doc.last_completed_step = ROUTED_STEP
            session.commit()
            logger.info(
                "Documento %s marcado '%s' pelo pipeline (Rotear, P9) — sem mover",
                doc.id,
                target,
            )
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
            routed=True,
            route_target=plan.route_to,
        )

    # (3b) Bloqueio (D-07): revisão sem tocar o disco e sem AuditLog de operação.
    if plan.blocked:
        # NUNCA `session.commit()` antes do `transition` (atomicidade). Só transita
        # se o doc estiver num estado com aresta para EM_REVISAO (PROCESSANDO).
        if doc.state == DocState.PROCESSANDO:
            transition(
                session, doc, DocState.EM_REVISAO, completed_step=CLASSIFIED_STEP
            )
        logger.info(
            "Documento %s rebaixado para EM_REVISAO (campo faltante no padrão, D-07)",
            doc.id,
        )
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=True,
            collision=False,
            skipped_identical=False,
        )

    # (3c) No-match (Pitfall 10): nenhuma etapa casou → NO-OP explícito. O documento
    # é MANTIDO NA ORIGEM, SEM transição de estado e SEM tocar o disco. NUNCA
    # materializa para a raiz.
    if not plan.matched_any:
        logger.info(
            "Documento %s: nenhuma etapa do pipeline casou (P10) — mantido na origem",
            doc.id,
        )
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=None,
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
            no_match=True,
        )

    dest = _plan_dest(source, plan)

    # (4) dry-run: plano puro, sem AuditLog e sem disco (AUT-03). (Mantido por
    # simetria; o endpoint usa `dry_run()` diretamente.)
    if dry_run:
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=str(dest),
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=False,
        )

    # (5) Anti-colisão a MONTANTE (resolve_collision). Só consulta o disco para
    # decidir o caminho livre; não escreve. dst inexistente é o caso comum.
    collision = False
    skipped_identical = False
    if dest.exists():
        resolved = fileops.resolve_collision(dest, source)
        if resolved is None:
            # D-10: destino já contém conteúdo idêntico → conclui sem mover.
            skipped_identical = True
        elif resolved != dest:
            collision = True
            dest = resolved

    if skipped_identical:
        # No-op de disco mas CONCLUI o documento (operação já-feita, D-10).
        if doc.state in (DocState.PROCESSANDO, DocState.EM_REVISAO):
            transition(session, doc, DocState.CONCLUIDO, completed_step=APPLIED_STEP)
        logger.info("Documento %s: destino idêntico já presente (D-10), concluído", doc.id)
        return ApplyStageResult(
            document_id=doc.id,
            source_path=str(source),
            dest_path=str(dest),
            materialized=False,
            blocked=False,
            collision=False,
            skipped_identical=True,
        )

    # (6) WRITE-AHEAD (AUT-04 / T-06-12): a INTENÇÃO é persistida ANTES de tocar o
    # disco. Commit explícito aqui (não é o commit final do transition) para que um
    # crash entre intent e done deixe um registro reconciliável.
    audit = AuditLog(
        document_id=doc.id,
        action=_ACTION,
        status="intent",
        source_path=str(source),
        dest_path=str(dest),
        run_id=run_id,
        content_hash=content_hash,
    )
    session.add(audit)
    session.commit()
    session.refresh(audit)

    # (7) Materializa do CAS e verifica o hash (AUT-06). Erros de disco PROPAGAM —
    # a origem fica intacta (verify-then-remove). EXCEÇÃO controlada: se o blob NÃO
    # existe no CAS (FileNotFoundError E `cas.exists` falso), não há conteúdo físico
    # a relocar — a automação conclui logicamente (o audit `done` já registra a
    # intenção) sem fabricar/perder arquivo. Um blob PRESENTE mas corrompido levanta
    # IntegrityError (NÃO capturado aqui) — propaga ao worker (nunca mascarado).
    physically_moved = True
    try:
        fileops.materialize_to_dest(content_hash, dest)
    except FileNotFoundError:
        if cas.exists(content_hash):
            raise  # blob existe mas o destino falhou — propaga (retryável)
        physically_moved = False
        logger.info(
            "Documento %s: sem conteúdo físico no CAS para mover — conclusão lógica",
            doc.id,
        )

    # (8) Verificação passou → remove a origem (AUT-06 crit 5: copia→verifica→remove).
    # Só remove a origem se houve materialização física verificada.
    if physically_moved:
        fileops.remove_original(source)

    # (9) status="done" + transition(CONCLUIDO) num COMMIT ÚNICO. NUNCA commit
    # manual antes do transition (o transition comita audit + estado juntos).
    audit.status = "done"
    if doc.state in (DocState.PROCESSANDO, DocState.EM_REVISAO):
        transition(session, doc, DocState.CONCLUIDO, completed_step=APPLIED_STEP)
    else:
        # Estado sem aresta para CONCLUIDO (ex.: já concluído): persiste só o done.
        session.commit()

    logger.info(
        "Automação aplicada document_id=%s run_id=%s status=done",
        doc.id,
        run_id,
    )
    return ApplyStageResult(
        document_id=doc.id,
        source_path=str(source),
        dest_path=str(dest),
        materialized=physically_moved,
        blocked=False,
        collision=collision,
        skipped_identical=False,
    )


def reconcile_orphans(session: Session) -> int:
    """Reconcilia AuditLog(status="intent") órfãos (crash entre intent e done).

    Espelha `repo.requeue_running`: roda no STARTUP do worker (UMA vez). Para cada
    `intent` pendente (um crash entre o write-ahead e o `done`), ADJUDICA o registro
    checando a integridade do DESTINO:
    - destino existe com o hash esperado (`content_hash`) → a materialização DE FATO
      ocorreu antes do crash → marca `status="done"` (idempotente, evita re-mover);
    - destino ausente/divergente/sem caminho registrado → a operação NÃO se
      completou → marca `status="orphaned"` para que o `intent` não fique pendurado.
      O documento permanece SEM `AuditLog(status="done")`, logo o sweep de
      auto-aplica (ou o apply manual) o re-captura e re-materializa do CAS; a
      idempotência por "done" cobre o caso comum.

    Devolve quantos intents foram reconciliados (adjudicados). NÃO loga conteúdo.
    """
    intents = session.scalars(
        select(AuditLog).where(AuditLog.status == "intent")
    ).all()
    reconciled = 0
    for audit in intents:
        dest = Path(audit.dest_path) if audit.dest_path else None
        expected = audit.content_hash
        completed = False
        if dest is not None and expected and dest.exists():
            try:
                completed = fileops.hash_file(dest) == expected
            except OSError:
                logger.warning(
                    "Reconcile: destino ilegivel para audit %s — tratado como orfao",
                    audit.id,
                )
        if completed:
            # Destino integro prova que a materializacao ocorreu antes do crash.
            audit.status = "done"
            logger.info("Reconcile: intent %s confirmado done (destino integro)", audit.id)
        else:
            # A operacao nao se completou: marca orfao (nao fica pendurado). O doc
            # segue sem 'done' → o sweep/apply o re-captura e materializa do CAS.
            audit.status = "orphaned"
            logger.info(
                "Reconcile: intent orfao %s sem destino integro — marcado orphaned",
                audit.id,
            )
        reconciled += 1
    if reconciled:
        session.commit()
    return reconciled

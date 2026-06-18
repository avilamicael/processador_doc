"""API de automações — CRUD ANINHADO de pipeline/steps/filtros + dry-run/apply/undo
(Fase 6 REDESIGN, TPL-02/AUT-01..AUT-06).

Router fino (`/automations`) que a UI (Plano 08) usa para o construtor do PIPELINE de
automação e para disparar/reverter aplicações. Espelha o padrão de `api/templates.py`
(CRUD aninhado em 2 níveis: pipeline → steps → filtros): schemas `In`/`Patch`/`Out`
Pydantic, `request.app.state.engine` + `with get_session(engine)`, `IntegrityError →
409`, `404` em ausente, `204` no DELETE, coleção filha substituída inteira no PATCH
(delete-orphan). As AÇÕES (dry-run/apply/undo) espelham `api/documents.py`.

Garantias materializadas:
- **AUT-01/AUT-02/TPL-02:** `AutomationPipeline` 1:N `PipelineStep` 1:N `StepFilter`
  (lista ORDENADA de etapas, cada etapa com UMA ação atômica + 0..N filtros). Steps
  retornados em ordem de `position`; filtros idem.
- **D-13/D-17 (ações):** `action_type ∈ {move, rename, identify_type, identify_file,
  route}`; os `params` obrigatórios por tipo são validados (move→folder_pattern,
  rename→name_pattern, identify_type→template_id, identify_file→extensions,
  route→target ∈ {em_revisao,nao_tratar,ignorar}). `route` (D-22) é aceito mas NÃO
  obrigatório — pipelines sem route funcionam e a UI não o expõe.
- **D-14 (filtros):** `filter_type ∈ {field, source_folder, extension, filename,
  size, template}`; `operator ∈ {eq, gt, lt, contains}`; combinados por `conjunction`.
- **AUT-03 (dry-run):** `POST /dry-run` simula o pipeline por documento SEM tocar o
  disco nem escrever AuditLog (chama `stage.dry_run`).
- **D-03 (apply por-doc e por-lote):** `POST /apply` aceita um único id OU lista; gera
  um `run_id` único e reenfileira `(content_hash, APPLY_STEP)` (o worker materializa).
- **AUT-05 (undo por-doc e por-run):** `POST /undo` aceita `document_id` OU `run_id`.

SEGURANÇA:
- V5 (injeção em operador/ação): `action_type`/`filter_type`/`operator`/`route target`
  validados contra conjuntos explícitos (422 fora); o executor é dispatch explícito,
  nunca `eval`.
- V4 (path traversal): o confinamento do destino é responsabilidade de naming
  (consumido por apply_stage) — base = `automation_dest_root`.
- V7/V9 (info disclosure): NÃO logamos/retornamos valores de campo nem conteúdo de
  documento — só ids/paths/run_id/status.
"""

import json
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.documents import _requeue
from app.automation import stage, undo
from app.automation.rules import normalize_extensions
from app.automation.stage import APPLY_STEP
from app.models.automation_pipeline import (
    AutomationPipeline,
    PipelineStep,
    StepFilter,
)
from app.models.document import Document
from app.models.enums import DocState
from app.pipeline.state_machine import transition
from app.pipeline.states import InvalidTransition
from app.storage.db import get_session

router = APIRouter(prefix="/automations", tags=["automations"])

# Vocabulário validado na borda HTTP (V5). Fora dos conjuntos → 422.
# `identify_file` (D-17): gate por extensão digitável. `route` (D-22) mantido aceito
# mas NÃO obrigatório — pipelines sem route funcionam e a UI não o expõe.
_ACTION_TYPES = frozenset(
    {"move", "rename", "identify_type", "identify_file", "route"}
)
_FILTER_TYPES = frozenset(
    {"field", "source_folder", "extension", "filename", "size", "template"}
)
_OPERATORS = frozenset({"eq", "gt", "lt", "contains"})
_CONJUNCTIONS = frozenset({"and", "or"})
_ROUTE_TARGETS = frozenset({"em_revisao", "nao_tratar", "ignorar"})


# --------------------------------------------------------------------------- #
# Schemas In/Patch/Out (CRUD aninhado pipeline → steps → filtros)             #
# --------------------------------------------------------------------------- #


class StepFilterIn(BaseModel):
    """Filtro de entrada `{filter_type} {operator} {value}` (D-14).

    `field_name` só é usado quando `filter_type == "field"`.
    """

    filter_type: str
    operator: str
    value: str
    field_name: str | None = None

    @field_validator("filter_type")
    @classmethod
    def _filter_type_known(cls, v: str) -> str:
        if v not in _FILTER_TYPES:
            raise ValueError(
                f"filter_type inválido: {v!r} "
                "(use field/source_folder/extension/filename/size/template)"
            )
        return v

    @field_validator("operator")
    @classmethod
    def _operator_known(cls, v: str) -> str:
        # V5: operador fora do conjunto explícito é rejeitado (422).
        if v not in _OPERATORS:
            raise ValueError(f"operador inválido: {v!r} (use eq/gt/lt/contains)")
        return v


class StepIn(BaseModel):
    """Etapa do pipeline: UMA ação atômica + 0..N filtros (D-13)."""

    action_type: str
    conjunction: str = "and"
    params: dict = {}
    active: bool = True
    filters: list[StepFilterIn] = []

    @field_validator("action_type")
    @classmethod
    def _action_known(cls, v: str) -> str:
        if v not in _ACTION_TYPES:
            raise ValueError(
                f"action_type inválido: {v!r} "
                "(use move/rename/identify_type/identify_file/route)"
            )
        return v

    @field_validator("conjunction")
    @classmethod
    def _conjunction_known(cls, v: str) -> str:
        if v not in _CONJUNCTIONS:
            raise ValueError("conjunção inválida (use 'and' ou 'or')")
        return v

    @model_validator(mode="after")
    def _params_required_by_action(self) -> "StepIn":
        """Valida o param obrigatório por `action_type` (D-13). Faltante → 422."""
        p = self.params or {}
        if self.action_type == "move" and not p.get("folder_pattern"):
            raise ValueError("ação 'move' exige params.folder_pattern")
        if self.action_type == "rename" and not p.get("name_pattern"):
            raise ValueError("ação 'rename' exige params.name_pattern")
        if self.action_type == "identify_type" and p.get("template_id") is None:
            raise ValueError("ação 'identify_type' exige params.template_id")
        if self.action_type == "identify_file":
            # D-17: o gate exige ao menos UMA extensão digitada válida. Reusa a
            # normalização do executor (case/dot-insensitive) para rejeitar branco.
            if not normalize_extensions(p.get("extensions")):
                raise ValueError(
                    "ação 'identify_file' exige params.extensions "
                    "(uma ou mais extensões, ex.: '.pdf')"
                )
        if self.action_type == "route":
            target = p.get("target")
            if target not in _ROUTE_TARGETS:
                raise ValueError(
                    "ação 'route' exige params.target ∈ "
                    "{em_revisao, nao_tratar, ignorar}"
                )
        return self


class PipelineIn(BaseModel):
    """Body de criação de pipeline: nome + estado + lista ordenada de etapas."""

    name: str
    active: bool = True
    steps: list[StepIn] = []

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Informe o nome do pipeline.")
        return v.strip()


class PipelinePatch(BaseModel):
    """Body de edição parcial (todos opcionais).

    Quando `steps` é informado, SUBSTITUI a coleção inteira (delete-orphan).
    Quando omitido (`None`), as etapas atuais são preservadas.
    """

    name: str | None = None
    active: bool | None = None
    steps: list[StepIn] | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Informe o nome do pipeline.")
        return v.strip() if v is not None else v


class StepFilterOut(BaseModel):
    """Representação de resposta de um filtro."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filter_type: str
    operator: str
    value: str
    field_name: str | None
    position: int


class StepOut(BaseModel):
    """Representação de resposta de uma etapa com filtros aninhados."""

    id: int
    position: int
    action_type: str
    conjunction: str
    params: dict
    active: bool
    filters: list[StepFilterOut]


class PipelineOut(BaseModel):
    """Representação de resposta de um pipeline com etapas aninhadas (ordenadas)."""

    id: int
    name: str
    active: bool
    steps: list[StepOut]


def _serialize(pipeline: AutomationPipeline) -> PipelineOut:
    """Converte um `AutomationPipeline` ORM no schema de saída (ordens preservadas)."""
    steps_sorted = sorted(pipeline.steps, key=lambda s: s.position)
    steps_out: list[StepOut] = []
    for step in steps_sorted:
        try:
            params = json.loads(step.params_json) if step.params_json else {}
        except (ValueError, TypeError):
            params = {}
        if not isinstance(params, dict):
            params = {}
        filters_sorted = sorted(step.filters, key=lambda f: f.position)
        steps_out.append(
            StepOut(
                id=step.id,
                position=step.position,
                action_type=step.action_type,
                conjunction=step.conjunction,
                params=params,
                active=step.active,
                filters=[StepFilterOut.model_validate(f) for f in filters_sorted],
            )
        )
    return PipelineOut(
        id=pipeline.id,
        name=pipeline.name,
        active=pipeline.active,
        steps=steps_out,
    )


def _apply_steps(pipeline: AutomationPipeline, steps: list[StepIn]) -> None:
    """Substitui a coleção de etapas (e seus filtros) do pipeline (delete-orphan).

    `params` é serializado em `params_json`; cada etapa recebe sua `position` pela
    ordem informada (D-12), e cada filtro idem.
    """
    new_steps: list[PipelineStep] = []
    for i, s in enumerate(steps):
        step = PipelineStep(
            position=i,
            action_type=s.action_type,
            conjunction=s.conjunction,
            params_json=json.dumps(s.params or {}),
            active=s.active,
        )
        step.filters = [
            StepFilter(
                filter_type=f.filter_type,
                operator=f.operator,
                value=f.value,
                field_name=f.field_name,
                position=j,
            )
            for j, f in enumerate(s.filters)
        ]
        new_steps.append(step)
    pipeline.steps = new_steps


@router.get("", response_model=list[PipelineOut])
def list_pipelines(request: Request) -> list[PipelineOut]:
    """Lista os pipelines cadastrados (ordenados por id)."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        pipelines = session.scalars(
            select(AutomationPipeline).order_by(AutomationPipeline.id)
        ).all()
        return [_serialize(p) for p in pipelines]


@router.get("/{pipeline_id}", response_model=PipelineOut)
def get_pipeline(request: Request, pipeline_id: int) -> PipelineOut:
    """Detalhe de um pipeline; 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        pipeline = session.get(AutomationPipeline, pipeline_id)
        if pipeline is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"pipeline {pipeline_id} não encontrado"
            )
        return _serialize(pipeline)


@router.post("", response_model=PipelineOut, status_code=status.HTTP_201_CREATED)
def create_pipeline(request: Request, body: PipelineIn) -> PipelineOut:
    """Cria um pipeline + etapas + filtros num único commit."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        pipeline = AutomationPipeline(name=body.name, active=body.active)
        _apply_steps(pipeline, body.steps)
        session.add(pipeline)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"pipeline já cadastrado: {body.name}",
            ) from exc
        session.refresh(pipeline)
        return _serialize(pipeline)


@router.patch("/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(request: Request, pipeline_id: int, body: PipelinePatch) -> PipelineOut:
    """Edita campos/etapas; ao trocar `steps`, substitui a coleção. 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        pipeline = session.get(AutomationPipeline, pipeline_id)
        if pipeline is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"pipeline {pipeline_id} não encontrado"
            )
        if body.name is not None:
            pipeline.name = body.name
        if body.active is not None:
            pipeline.active = body.active
        if body.steps is not None:
            _apply_steps(pipeline, body.steps)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT, "pipeline já cadastrado com este nome"
            ) from exc
        session.refresh(pipeline)
        return _serialize(pipeline)


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(request: Request, pipeline_id: int) -> None:
    """Remove o pipeline (cascade apaga etapas e filtros). 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        pipeline = session.get(AutomationPipeline, pipeline_id)
        if pipeline is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"pipeline {pipeline_id} não encontrado"
            )
        session.delete(pipeline)
        session.commit()


# --------------------------------------------------------------------------- #
# Ações: dry-run / apply / undo                                               #
# --------------------------------------------------------------------------- #


class ActionIn(BaseModel):
    """Body do dry-run: lista de document_ids (vazia = todos os prontos)."""

    document_ids: list[int] = []


class DryRunRow(BaseModel):
    """Uma linha do preview de dry-run: origem→destino + sinalização (AUT-03)."""

    document_id: int
    original_filename: str
    source_path: str | None
    dest_path: str | None
    blocked: bool
    collision: bool
    skipped_identical: bool
    # REDESIGN (06-07): Rotear (P9) e no-match (P10) para a UI sinalizar.
    routed: bool
    route_target: str | None
    no_match: bool


class DryRunOut(BaseModel):
    """Resultado do dry-run: os pares origem→destino sem tocar o disco."""

    rows: list[DryRunRow]


class ApplyIn(BaseModel):
    """Body do apply: um único id OU uma lista (lote, D-03)."""

    document_id: int | None = None
    document_ids: list[int] = []


class ApplyOut(BaseModel):
    """Resultado do apply: o run_id do lote + quantos docs foram enfileirados."""

    run_id: str
    enqueued: int


class UndoIn(BaseModel):
    """Body do undo: por-doc (document_id) OU por-run (run_id), D-03/AUT-05."""

    document_id: int | None = None
    run_id: str | None = None


class UndoOut(BaseModel):
    """Resultado do undo: quantos documentos/operações foram revertidos."""

    reverted: int


def _ready_documents(session) -> list[Document]:
    """Documentos PROCESSANDO + classificado (prontos para preview/aplicar)."""
    return list(
        session.scalars(
            select(Document).where(
                Document.state == DocState.PROCESSANDO,
                Document.last_completed_step == stage.CLASSIFIED_STEP,
            )
        ).all()
    )


@router.post("/dry-run", response_model=DryRunOut)
def dry_run(request: Request, body: ActionIn) -> DryRunOut:
    """Preview do pipeline por documento SEM tocar o disco (AUT-03).

    `document_ids` vazio = todos os documentos prontos (PROCESSANDO + classificado).
    Chama `stage.dry_run` por doc (que NÃO escreve AuditLog nem move arquivo) e
    sinaliza blocked/collision/skipped_identical/routed/no_match para a UI. NÃO loga
    valores de campo — os paths vão só no corpo da resposta.
    """
    engine = request.app.state.engine
    rows: list[DryRunRow] = []
    with get_session(engine) as session:
        if body.document_ids:
            docs = [
                d
                for d in (session.get(Document, did) for did in body.document_ids)
                if d is not None
            ]
        else:
            docs = _ready_documents(session)

        for doc in docs:
            plan = stage.dry_run(session, content_hash=doc.content_hash)
            if plan is None:
                continue
            rows.append(
                DryRunRow(
                    document_id=doc.id,
                    original_filename=doc.original_filename,
                    source_path=plan.source_path,
                    dest_path=plan.dest_path,
                    blocked=plan.blocked,
                    collision=plan.collision,
                    skipped_identical=plan.skipped_identical,
                    routed=plan.routed,
                    route_target=plan.route_target,
                    no_match=plan.no_match,
                )
            )
    return DryRunOut(rows=rows)


@router.post("/apply", response_model=ApplyOut)
def apply(request: Request, body: ApplyIn) -> ApplyOut:
    """Dispara a aplicação do pipeline por-doc OU por-lote (D-03).

    Gera um `run_id` único (base do undo por-run, AUT-05) e reenfileira
    `(content_hash, APPLY_STEP)` com o `run_id` no payload para cada documento — o
    WORKER materializa (NÃO movemos síncrono no request). Idempotente: o apply_stage
    no-op se o doc já tem AuditLog(status="done"). 404 se nenhum id válido; 422 se
    nenhum id informado.
    """
    engine = request.app.state.engine
    ids: list[int] = list(body.document_ids)
    if body.document_id is not None:
        ids.append(body.document_id)
    if not ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "informe document_id ou document_ids",
        )

    run_id = uuid.uuid4().hex
    enqueued = 0
    with get_session(engine) as session:
        for did in ids:
            doc = session.get(Document, did)
            if doc is None:
                continue
            _requeue(
                session,
                content_hash=doc.content_hash,
                step=APPLY_STEP,
                payload={"content_hash": doc.content_hash, "run_id": run_id},
            )
            enqueued += 1
    if enqueued == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nenhum documento encontrado")
    return ApplyOut(run_id=run_id, enqueued=enqueued)


@router.post("/undo", response_model=UndoOut)
def undo_action(request: Request, body: UndoIn) -> UndoOut:
    """Desfaz o pipeline aplicado por-doc OU por-run (AUT-05/D-03).

    `document_id` → `undo.undo_document` (reverte os 'done' do doc); `run_id` →
    `undo.undo_run` (reverte tudo do lote). AMBOS já reabrem o documento revertido
    (CONCLUIDO→PROCESSANDO) dentro do undo. Por robustez, garantimos a reabertura
    também aqui para docs que tenham ficado em CONCLUIDO. 422 se nenhum dos dois for
    informado.
    """
    engine = request.app.state.engine
    if body.document_id is None and body.run_id is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "informe document_id ou run_id",
        )
    with get_session(engine) as session:
        if body.run_id is not None:
            reverted = undo.undo_run(session, run_id=body.run_id)
        else:
            results = undo.undo_document(session, document_id=body.document_id)
            reverted = len(results)
            _reopen_if_concluded(session, body.document_id)
    return UndoOut(reverted=reverted)


def _reopen_if_concluded(session, document_id: int | None) -> None:
    """Reabre CONCLUIDO→PROCESSANDO se o doc ainda estiver concluído (idempotente).

    O `undo.undo_document` já reabre internamente; este guard é defesa em
    profundidade. Doc fora de CONCLUIDO → pula sem erro.
    """
    if document_id is None:
        return
    doc = session.get(Document, document_id)
    if doc is None or doc.state != DocState.CONCLUIDO:
        return
    try:
        transition(session, doc, DocState.PROCESSANDO, completed_step=stage.CLASSIFIED_STEP)
    except InvalidTransition:
        session.rollback()

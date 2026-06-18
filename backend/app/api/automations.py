"""API de automações — CRUD de automações com CONDIÇÕES → AÇÕES + dry-run/apply/undo
(Fase 6, MODELO FINAL D-23..D-26; TPL-02/AUT-01..AUT-06).

Router fino (`/automations`) que a UI usa para o construtor de automações e para
disparar/reverter aplicações. Espelha o padrão de `api/templates.py` (CRUD com
coleções filhas aninhadas substituídas inteiras no PATCH): schemas `In`/`Patch`/`Out`
Pydantic, `request.app.state.engine` + `with get_session(engine)`, `IntegrityError →
409`, `404` em ausente, `204` no DELETE. As AÇÕES (dry-run/apply/undo) espelham
`api/documents.py`.

Garantias materializadas:
- **D-23/D-24:** `Automation` 1:N `AutomationCondition` + 1:N `AutomationAction`.
  Várias automações nomeadas (a UI lista N); ordem entre automações via `position`;
  ordem das ações via `position` (drag-and-drop / ↑↓). Saída ordenada.
- **D-24 (condições):** `field ∈ {source_folder, extension, template, field,
  filename, size}`; `operator ∈ {eq, contains, gt, lt}`; combinadas por E (AND).
- **D-24 (ações):** `action_type ∈ {rename, move}`; param obrigatório por tipo
  (rename→name_pattern, move→dest_folder) validado. Sem "route" (D-22).
- **AUT-03 (dry-run):** `POST /dry-run` simula as automações por documento SEM tocar
  o disco nem escrever AuditLog (chama `stage.dry_run`).
- **D-03 (apply por-doc e por-lote):** `POST /apply` aceita um único id OU lista; gera
  um `run_id` único e reenfileira `(content_hash, APPLY_STEP)` (o worker materializa).
- **AUT-05 (undo por-doc e por-run):** `POST /undo` aceita `document_id` OU `run_id`.

SEGURANÇA:
- V5 (injeção): `field`/`action_type`/`operator` validados contra conjuntos
  explícitos (422 fora); o executor é dispatch explícito, nunca `eval`.
- V4 (path traversal): o confinamento do destino é responsabilidade de naming
  (consumido por apply_stage) — base = `automation_dest_root`. Aspas normalizadas (D-21).
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
from app.automation.stage import APPLY_STEP
from app.models.automation import (
    Automation,
    AutomationAction,
    AutomationCondition,
)
from app.models.document import Document
from app.models.enums import DocState
from app.pipeline.state_machine import transition
from app.pipeline.states import InvalidTransition
from app.storage.db import get_session

router = APIRouter(prefix="/automations", tags=["automations"])

# Vocabulário validado na borda HTTP (V5). Fora dos conjuntos → 422.
_ACTION_TYPES = frozenset({"rename", "move"})
_CONDITION_FIELDS = frozenset(
    {"source_folder", "extension", "template", "field", "filename", "size"}
)
_OPERATORS = frozenset({"eq", "contains", "gt", "lt"})


# --------------------------------------------------------------------------- #
# Schemas In/Patch/Out (CRUD automação → conditions[] + actions[])            #
# --------------------------------------------------------------------------- #


class ConditionIn(BaseModel):
    """Condição `{field} {operator} {value}` (D-24).

    `field_name` só é usado quando `field == "field"` (qual campo extraído comparar).
    """

    field: str
    operator: str
    value: str
    field_name: str | None = None

    @field_validator("field")
    @classmethod
    def _field_known(cls, v: str) -> str:
        if v not in _CONDITION_FIELDS:
            raise ValueError(
                f"field inválido: {v!r} "
                "(use source_folder/extension/template/field/filename/size)"
            )
        return v

    @field_validator("operator")
    @classmethod
    def _operator_known(cls, v: str) -> str:
        # V5: operador fora do conjunto explícito é rejeitado (422).
        if v not in _OPERATORS:
            raise ValueError(f"operador inválido: {v!r} (use eq/contains/gt/lt)")
        return v


class ActionIn(BaseModel):
    """Ação ordenada: rename (name_pattern) | move (dest_folder) (D-24)."""

    action_type: str
    params: dict = {}

    @field_validator("action_type")
    @classmethod
    def _action_known(cls, v: str) -> str:
        if v not in _ACTION_TYPES:
            raise ValueError(
                f"action_type inválido: {v!r} (use rename/move)"
            )
        return v

    @model_validator(mode="after")
    def _params_required_by_action(self) -> "ActionIn":
        """Valida o param obrigatório por `action_type` (D-24). Faltante → 422."""
        p = self.params or {}
        if self.action_type == "rename" and not p.get("name_pattern"):
            raise ValueError("ação 'rename' exige params.name_pattern")
        if self.action_type == "move" and not p.get("dest_folder"):
            raise ValueError("ação 'move' exige params.dest_folder")
        return self


class AutomationIn(BaseModel):
    """Body de criação: nome + estado + ordem + condições + ações."""

    name: str
    active: bool = True
    position: int = 0
    conditions: list[ConditionIn] = []
    actions: list[ActionIn] = []

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Informe o nome da automação.")
        return v.strip()


class AutomationPatch(BaseModel):
    """Body de edição parcial (todos opcionais).

    Quando `conditions`/`actions` são informados, SUBSTITUEM a coleção inteira
    (delete-orphan). Quando omitidos (`None`), as coleções atuais são preservadas.
    """

    name: str | None = None
    active: bool | None = None
    position: int | None = None
    conditions: list[ConditionIn] | None = None
    actions: list[ActionIn] | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Informe o nome da automação.")
        return v.strip() if v is not None else v


class ConditionOut(BaseModel):
    """Representação de resposta de uma condição."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    field: str
    operator: str
    value: str
    field_name: str | None
    position: int


class ActionOut(BaseModel):
    """Representação de resposta de uma ação (params desserializados)."""

    id: int
    position: int
    action_type: str
    params: dict


class AutomationOut(BaseModel):
    """Representação de resposta de uma automação com condições/ações aninhadas."""

    id: int
    name: str
    active: bool
    position: int
    conditions: list[ConditionOut]
    actions: list[ActionOut]


def _serialize(automation: Automation) -> AutomationOut:
    """Converte um `Automation` ORM no schema de saída (ordens preservadas)."""
    conds_sorted = sorted(automation.conditions, key=lambda c: c.position)
    actions_sorted = sorted(automation.actions, key=lambda a: a.position)
    actions_out: list[ActionOut] = []
    for action in actions_sorted:
        try:
            params = json.loads(action.params_json) if action.params_json else {}
        except (ValueError, TypeError):
            params = {}
        if not isinstance(params, dict):
            params = {}
        actions_out.append(
            ActionOut(
                id=action.id,
                position=action.position,
                action_type=action.action_type,
                params=params,
            )
        )
    return AutomationOut(
        id=automation.id,
        name=automation.name,
        active=automation.active,
        position=automation.position,
        conditions=[ConditionOut.model_validate(c) for c in conds_sorted],
        actions=actions_out,
    )


def _apply_conditions(
    automation: Automation, conditions: list[ConditionIn]
) -> None:
    """Substitui a coleção de condições do automation (delete-orphan)."""
    automation.conditions = [
        AutomationCondition(
            field=c.field,
            operator=c.operator,
            value=c.value,
            field_name=c.field_name,
            position=i,
        )
        for i, c in enumerate(conditions)
    ]


def _apply_actions(automation: Automation, actions: list[ActionIn]) -> None:
    """Substitui a coleção de ações do automation (delete-orphan); ordem por posição."""
    automation.actions = [
        AutomationAction(
            position=i,
            action_type=a.action_type,
            params_json=json.dumps(a.params or {}),
        )
        for i, a in enumerate(actions)
    ]


@router.get("", response_model=list[AutomationOut])
def list_automations(request: Request) -> list[AutomationOut]:
    """Lista as automações cadastradas (ordenadas por position, depois id)."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        automations = session.scalars(
            select(Automation).order_by(Automation.position, Automation.id)
        ).all()
        return [_serialize(a) for a in automations]


@router.get("/{automation_id}", response_model=AutomationOut)
def get_automation(request: Request, automation_id: int) -> AutomationOut:
    """Detalhe de uma automação; 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        automation = session.get(Automation, automation_id)
        if automation is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"automação {automation_id} não encontrada",
            )
        return _serialize(automation)


@router.post("", response_model=AutomationOut, status_code=status.HTTP_201_CREATED)
def create_automation(request: Request, body: AutomationIn) -> AutomationOut:
    """Cria uma automação + condições + ações num único commit."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        automation = Automation(
            name=body.name, active=body.active, position=body.position
        )
        _apply_conditions(automation, body.conditions)
        _apply_actions(automation, body.actions)
        session.add(automation)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"automação já cadastrada: {body.name}",
            ) from exc
        session.refresh(automation)
        return _serialize(automation)


@router.patch("/{automation_id}", response_model=AutomationOut)
def update_automation(
    request: Request, automation_id: int, body: AutomationPatch
) -> AutomationOut:
    """Edita campos/condições/ações; ao trocar as coleções, substitui-as. 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        automation = session.get(Automation, automation_id)
        if automation is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"automação {automation_id} não encontrada",
            )
        if body.name is not None:
            automation.name = body.name
        if body.active is not None:
            automation.active = body.active
        if body.position is not None:
            automation.position = body.position
        if body.conditions is not None:
            _apply_conditions(automation, body.conditions)
        if body.actions is not None:
            _apply_actions(automation, body.actions)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT, "automação já cadastrada com este nome"
            ) from exc
        session.refresh(automation)
        return _serialize(automation)


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(request: Request, automation_id: int) -> None:
    """Remove a automação (cascade apaga condições e ações). 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        automation = session.get(Automation, automation_id)
        if automation is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"automação {automation_id} não encontrada",
            )
        session.delete(automation)
        session.commit()


# --------------------------------------------------------------------------- #
# Ações: dry-run / apply / undo                                               #
# --------------------------------------------------------------------------- #


class DocSelectionIn(BaseModel):
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
    no_match: bool
    automation_id: int | None


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
def dry_run(request: Request, body: DocSelectionIn) -> DryRunOut:
    """Preview das automações por documento SEM tocar o disco (AUT-03).

    `document_ids` vazio = todos os documentos prontos (PROCESSANDO + classificado).
    Chama `stage.dry_run` por doc (que NÃO escreve AuditLog nem move arquivo) e
    sinaliza blocked/collision/skipped_identical/no_match para a UI. NÃO loga valores
    de campo — os paths vão só no corpo da resposta.
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
                    no_match=plan.no_match,
                    automation_id=plan.automation_id,
                )
            )
    return DryRunOut(rows=rows)


@router.post("/apply", response_model=ApplyOut)
def apply(request: Request, body: ApplyIn) -> ApplyOut:
    """Dispara a aplicação das automações por-doc OU por-lote (D-03).

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
    """Desfaz as automações aplicadas por-doc OU por-run (AUT-05/D-03).

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

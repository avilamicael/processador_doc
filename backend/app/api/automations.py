"""API de automações — CRUD de regras + dry-run + apply + undo (Fase 6, TPL-02).

Router fino (`/automations`) que a UI (Plano 05) usa para o construtor de REGRAS de
automação e para disparar/reverter aplicações. Espelha exatamente o padrão de
`api/templates.py` (1:N aninhado: regra → condições): schemas `In`/`Patch`/`Out`
Pydantic, `request.app.state.engine` + `with get_session(engine)`, `IntegrityError →
409`, `404` em ausente, `204` no DELETE, coleção filha substituída inteira no PATCH
(delete-orphan). As AÇÕES (dry-run/apply/undo) espelham `api/documents.py`
(approve/retry/reclassify): guard semântico → ação → reenqueue do step `apply`.

Garantias materializadas:
- **TPL-02:** uma `AutomationRule` 1:N `RuleCondition` (operador eq/gt/lt/contains,
  conjunção E/OU, prioridade D-05). Regras listadas em ordem de `priority`.
- **AUT-03 (dry-run):** `POST /dry-run` resolve origem→destino por documento SEM
  tocar o disco nem escrever AuditLog (chama `stage.dry_run`).
- **D-03 (apply por-doc e por-lote):** `POST /apply` aceita um único id OU uma lista
  (lote). Em lote, gera um `run_id` único; reenfileira `(content_hash, APPLY_STEP)`
  via o helper `_requeue` (o worker materializa — NÃO move síncrono no request).
- **AUT-05 (undo por-doc e por-run):** `POST /undo` aceita `document_id` OU `run_id`;
  reverte o arquivo (`undo.undo_document`/`undo_run`) — que JÁ reabre CONCLUIDO→
  PROCESSANDO (aresta nova da allowlist, Fase 6), tornando a reversão observável.

SEGURANÇA:
- V5 (injeção em operador): `operator` validado contra o conjunto eq/gt/lt/contains
  (422 fora dele); o avaliador (Plan 02) é dispatch explícito, nunca `eval`.
- V4 (path traversal): o confinamento do destino é responsabilidade de naming
  (consumido por apply_stage) — base = `automation_dest_root`.
- V7/V9 (info disclosure): NÃO logamos valores de campo nem conteúdo de documento —
  só ids/paths/run_id/status.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.documents import _requeue
from app.automation import stage, undo
from app.automation.stage import APPLY_STEP
from app.models.automation_rule import AutomationRule, RuleCondition
from app.models.document import Document
from app.models.enums import DocState
from app.pipeline.state_machine import transition
from app.pipeline.states import InvalidTransition
from app.storage.db import get_session

router = APIRouter(prefix="/automations", tags=["automations"])

# Operadores suportados (D-04 / V5). Fora do conjunto → 422.
_OPERATORS = frozenset({"eq", "gt", "lt", "contains"})
# Conjunções suportadas (D-04). Default "and".
_CONJUNCTIONS = frozenset({"and", "or"})


class ConditionIn(BaseModel):
    """Condição `{field_name} {operator} {value}` informada na regra (D-04)."""

    field_name: str
    operator: str
    value: str

    @field_validator("field_name")
    @classmethod
    def _field_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Informe o nome do campo da condição.")
        return v.strip()

    @field_validator("operator")
    @classmethod
    def _operator_known(cls, v: str) -> str:
        # V5: operador fora do conjunto explícito é rejeitado (422) — nunca chega
        # ao avaliador, que de qualquer forma falha fechado.
        if v not in _OPERATORS:
            raise ValueError(f"operador inválido: {v!r} (use eq/gt/lt/contains)")
        return v


class RuleIn(BaseModel):
    """Body de criação de regra: nome + prioridade + padrões + condições."""

    name: str
    priority: int = 0
    conjunction: str = "and"
    name_pattern: str | None = None
    folder_pattern: str | None = None
    active: bool = True
    conditions: list[ConditionIn] = []

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Informe o nome da regra.")
        return v.strip()

    @field_validator("conjunction")
    @classmethod
    def _conjunction_known(cls, v: str) -> str:
        if v not in _CONJUNCTIONS:
            raise ValueError("conjunção inválida (use 'and' ou 'or')")
        return v


class RulePatch(BaseModel):
    """Body de edição parcial de regra (todos opcionais).

    Quando `conditions` é informado, SUBSTITUI a coleção inteira (delete-orphan).
    Quando omitido (`None`), as condições atuais são preservadas.
    """

    name: str | None = None
    priority: int | None = None
    conjunction: str | None = None
    name_pattern: str | None = None
    folder_pattern: str | None = None
    active: bool | None = None
    conditions: list[ConditionIn] | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Informe o nome da regra.")
        return v.strip() if v is not None else v

    @field_validator("conjunction")
    @classmethod
    def _conjunction_known(cls, v: str | None) -> str | None:
        if v is not None and v not in _CONJUNCTIONS:
            raise ValueError("conjunção inválida (use 'and' ou 'or')")
        return v


class ConditionOut(BaseModel):
    """Representação de resposta de uma condição."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    field_name: str
    operator: str
    value: str
    position: int


class RuleOut(BaseModel):
    """Representação de resposta de uma regra com condições aninhadas."""

    id: int
    name: str
    priority: int
    conjunction: str
    name_pattern: str | None
    folder_pattern: str | None
    active: bool
    conditions: list[ConditionOut]


def _serialize(rule: AutomationRule) -> RuleOut:
    """Converte um `AutomationRule` ORM (condições carregadas) no schema de saída."""
    conditions = sorted(rule.conditions, key=lambda c: c.position)
    return RuleOut(
        id=rule.id,
        name=rule.name,
        priority=rule.priority,
        conjunction=rule.conjunction,
        name_pattern=rule.name_pattern,
        folder_pattern=rule.folder_pattern,
        active=rule.active,
        conditions=[ConditionOut.model_validate(c) for c in conditions],
    )


def _apply_conditions(rule: AutomationRule, conditions: list[ConditionIn]) -> None:
    """Substitui a coleção de condições da regra (delete-orphan cuida do resto)."""
    rule.conditions = [
        RuleCondition(
            field_name=c.field_name,
            operator=c.operator,
            value=c.value,
            position=i,
        )
        for i, c in enumerate(conditions)
    ]


@router.get("", response_model=list[RuleOut])
def list_rules(request: Request) -> list[RuleOut]:
    """Lista as regras cadastradas em ordem de prioridade (D-05)."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        rules = session.scalars(
            select(AutomationRule).order_by(AutomationRule.priority, AutomationRule.id)
        ).all()
        return [_serialize(r) for r in rules]


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(request: Request, rule_id: int) -> RuleOut:
    """Detalhe de uma regra; 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        rule = session.get(AutomationRule, rule_id)
        if rule is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"regra {rule_id} não encontrada"
            )
        return _serialize(rule)


@router.post("", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(request: Request, body: RuleIn) -> RuleOut:
    """Cria uma regra + condições num único commit."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        rule = AutomationRule(
            name=body.name,
            priority=body.priority,
            conjunction=body.conjunction,
            name_pattern=body.name_pattern,
            folder_pattern=body.folder_pattern,
            active=body.active,
        )
        _apply_conditions(rule, body.conditions)
        session.add(rule)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"regra já cadastrada: {body.name}",
            ) from exc
        session.refresh(rule)
        return _serialize(rule)


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(request: Request, rule_id: int, body: RulePatch) -> RuleOut:
    """Edita campos/condições; ao trocar `conditions`, substitui a coleção. 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        rule = session.get(AutomationRule, rule_id)
        if rule is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"regra {rule_id} não encontrada"
            )
        if body.name is not None:
            rule.name = body.name
        if body.priority is not None:
            rule.priority = body.priority
        if body.conjunction is not None:
            rule.conjunction = body.conjunction
        if body.name_pattern is not None:
            rule.name_pattern = body.name_pattern
        if body.folder_pattern is not None:
            rule.folder_pattern = body.folder_pattern
        if body.active is not None:
            rule.active = body.active
        if body.conditions is not None:
            _apply_conditions(rule, body.conditions)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT, "regra já cadastrada com este nome"
            ) from exc
        session.refresh(rule)
        return _serialize(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(request: Request, rule_id: int) -> None:
    """Remove a regra (cascade apaga suas condições). 404 se ausente."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        rule = session.get(AutomationRule, rule_id)
        if rule is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"regra {rule_id} não encontrada"
            )
        session.delete(rule)
        session.commit()


# --------------------------------------------------------------------------- #
# Ações: dry-run / apply / undo                                               #
# --------------------------------------------------------------------------- #


class ActionIn(BaseModel):
    """Body das ações por-doc/lote: lista de document_ids (vazia = todos os prontos)."""

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
    """Preview origem→destino por documento SEM tocar o disco (AUT-03).

    `document_ids` vazio = todos os documentos prontos (PROCESSANDO + classificado).
    Chama `stage.dry_run` por doc (que NÃO escreve AuditLog nem move arquivo). NÃO
    loga valores de campo — os paths vão só no corpo da resposta.
    """
    engine = request.app.state.engine
    rows: list[DryRunRow] = []
    with get_session(engine) as session:
        if body.document_ids:
            docs = [
                d
                for d in (
                    session.get(Document, did) for did in body.document_ids
                )
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
                )
            )
    return DryRunOut(rows=rows)


@router.post("/apply", response_model=ApplyOut)
def apply(request: Request, body: ApplyIn) -> ApplyOut:
    """Dispara a aplicação das automações por-doc OU por-lote (D-03).

    Gera um `run_id` único (base do undo por-run, AUT-05) e reenfileira
    `(content_hash, APPLY_STEP)` com o `run_id` no payload para cada documento — o
    WORKER materializa (NÃO movemos síncrono no request). Idempotente: o
    apply_stage no-op se o doc já tem AuditLog(status="done"). 404 se nenhum id válido.
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
    """Desfaz automações por-doc OU por-run (AUT-05/D-03).

    `document_id` → `undo.undo_document` (reverte os 'done' do doc); `run_id` →
    `undo.undo_run` (reverte tudo do lote). AMBOS já reabrem o documento revertido
    (CONCLUIDO→PROCESSANDO) dentro do undo — a reversão fica observável no estado,
    não só no arquivo. Por robustez, garantimos a reabertura também aqui para docs
    que tenham ficado em CONCLUIDO (idempotente: docs fora de CONCLUIDO são pulados).
    422 se nenhum dos dois for informado.
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
    profundidade para o caso de o documento ter ficado em CONCLUIDO (a aresta nova da
    allowlist da Fase 6). Doc fora de CONCLUIDO → pula sem erro.
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

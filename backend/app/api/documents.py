"""API de documentos — lista + counts por estado, duplicados, rescan.

Router fino (`/documents` + `/rescan`) que a UI (Plano 05) consome por polling:

- `GET /documents` — lista os Documents (os BLOCOS — D-06), cada um com `state`
  (string do enum) e `last_completed_step` para a UI distinguir o estado terminal
  da Fase 2 (PROCESSANDO + "aguardando_extracao" → rótulo "Aguardando extração").
  Duplicatas NUNCA aparecem como linhas (D-10) — só Documents existem na lista.
  Inclui um bloco `counts` por estado (recebido/processando/em_revisao/concluido/
  quarentena/falha + total) para os stat-cards/chips. Paginação simples opcional.
- `GET /documents/duplicates-count` — `SUM(ingested_originals.duplicate_hits)`
  (D-10): quantos arquivos repetidos foram ignorados sem reprocessar/cobrar.
- `POST /rescan` — "Forçar varredura" do UI-SPEC: chama `scan_and_enqueue` sobre
  as pastas ATIVAS e retorna quantos candidatos foram enfileirados. Idempotente
  por dedup (gate + UNIQUE da fila): re-varrer não duplica trabalho.
- `GET /documents/{id}` — DETALHE de classificação SOMENTE LEITURA (S4, TPL-03/04):
  os dados base do documento + um bloco `classification` derivado do
  `ClassificationResult` (join com Template para o nome) e seus `FilledField`s
  (campo, valor bruto, valor normalizado, marca válido/inválido). `classification`
  é `null` quando o doc ainda não foi classificado ("Aguardando classificação");
  quando casou nenhum template (`template_id` null) o estado de QUARENTENA fica
  visível (TPL-04). Esta superfície NÃO edita/resolve nada (Fase 5). A lista
  `GET /documents` permanece LEVE (sem classificação) para o polling barato.

SEGURANÇA — Information Disclosure (T-04-11): os valores extraídos vão SÓ no corpo
da resposta (consumo legítimo da UI), NUNCA em log; o endpoint não loga valores.
`document_id` é tipado `int` na rota (T-04-09 — sem string-building de SQL).
"""

import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.classification.confidence import compute_confidence
from app.ingest.watcher import active_folder_paths, scan_and_enqueue
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.models.ingested_original import IngestedOriginal
from app.models.job import Job
from app.models.template import Template, TemplateField
from app.models.watched_folder import WatchedFolder
from app.pipeline.state_machine import transition
from app.pipeline.states import InvalidTransition
from app.queue import repo
from app.storage.db import get_session
from app.validation.fields import validate_field

# Steps do worker (duplicados aqui para evitar importar worker.py — que sobe
# imports pesados; as strings são contrato estável da fila, ver queue/worker.py).
EXTRACT_STEP = "extract"
CLASSIFY_STEP = "classify"
APPLY_STEP = "apply"
EXTRACTED_STEP = "extraido"

# Copy dos motivos de balde (espelha 05-UI-SPEC). FALHA usa a mensagem persistida
# do job (last_error) quando existe; senão o fallback abaixo.
_MOTIVO_QUARENTENA = (
    "Nenhum template casou com este documento. Atribua um template para reclassificar."
)
_MOTIVO_FALHA_FALLBACK = (
    "Falha no processamento. Tente novamente; se persistir, verifique o arquivo de origem."
)

router = APIRouter(tags=["documents"])


def _as_utc(dt: datetime) -> datetime:
    """Marca um datetime naive como UTC tz-aware SEM deslocar a hora (D-13).

    Causa-raiz: o SQLite grava `func.now()` como string naive; ao ler vem um
    `datetime` sem `tzinfo` e o Pydantic o serializa sem offset. O frontend faz
    `new Date(iso)` sobre essa string e a interpreta no fuso LOCAL, errando a
    hora. A correção canônica é marcar o instante como UTC (o valor gravado pelo
    banco JÁ é UTC) — `replace`, não `astimezone`: 18:04 permanece 18:04 e ganha
    `+00:00`. Quando o datetime já carrega `tzinfo` (ex.: colunas tz-aware), é
    devolvido inalterado.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class DocumentOut(BaseModel):
    """Linha de documento exposta à UI."""

    id: int
    original_filename: str
    state: str
    last_completed_step: str | None
    source_folder_path: str | None
    created_at: datetime


class DocumentListOut(BaseModel):
    """Lista de documentos + contagens por estado para os stat-cards."""

    items: list[DocumentOut]
    counts: dict[str, int]
    total: int


class ClassificationFieldOut(BaseModel):
    """Campo preenchido de uma classificação — bruto/normalizado + marca (D-10/D-11)."""

    field_name: str
    raw_value: str | None
    normalized_value: str | None
    valid: bool
    invalid_reason: str | None
    # D-08: campo corrigido manualmente pelo operador (não veio da IA/documento).
    manually_corrected: bool


class ClassificationOut(BaseModel):
    """Bloco de classificação de um documento (somente leitura — S4).

    `template_id`/`template_name` são `null` quando nenhum template casou
    (quarentena, D-03/TPL-04).
    """

    template_id: int | None
    template_name: str | None
    confidence: float | None
    # Score 0.0–1.0 de QUALIDADE DE EXTRAÇÃO (D-01/D-02): fração de obrigatórios
    # válidos. `null` em quarentena (sem template = sem obrigatórios).
    confidence_score: float | None
    fields: list[ClassificationFieldOut]


class FieldPatchIn(BaseModel):
    """Body do patch de campo — só expõe `raw_value` (D-08; mass-assignment, T-05-08)."""

    raw_value: str | None


class ReclassifyIn(BaseModel):
    """Body do reclassify — o template forçado a aplicar (D-09)."""

    template_id: int


class AttentionItemOut(BaseModel):
    """Item de um balde de triagem (FALHA/QUARENTENA) — id + nome + motivo."""

    id: int
    original_filename: str
    motivo: str | None


class ReviewItemOut(BaseModel):
    """Item de EM_REVISAO — estende AttentionItemOut com score + campos editáveis."""

    id: int
    original_filename: str
    motivo: str | None
    confidence_score: float | None
    fields: list[ClassificationFieldOut]


class AttentionOut(BaseModel):
    """Os 3 baldes de triagem num payload só (Open Q3 — evita N+1)."""

    falha: list[AttentionItemOut]
    quarentena: list[AttentionItemOut]
    em_revisao: list[ReviewItemOut]
    counts: dict[str, int]


class DocumentDetailOut(BaseModel):
    """Detalhe de um documento: dados base + classificação (ou `null` se ausente)."""

    id: int
    original_filename: str
    state: str
    last_completed_step: str | None
    source_folder_path: str | None
    created_at: datetime
    classification: ClassificationOut | None


class DuplicatesCountOut(BaseModel):
    """Total de arquivos duplicados ignorados (D-10)."""

    count: int


class RescanOut(BaseModel):
    """Resultado de uma varredura forçada: enfileirados + pulados por duplicata (D-04)."""

    enqueued: int
    # Candidatos pulados pelo gate de dedup nesta varredura — alimenta o toast
    # pós-varredura do frontend ("N enfileirados, M duplicatas ignoradas").
    skipped_duplicates: int


class DeleteDocumentsIn(BaseModel):
    """Body do delete em lote — a lista de ids de Document a remover (só registro)."""

    ids: list[int]


class DeleteDocumentsOut(BaseModel):
    """Resultado do delete em lote: quantos Documents foram realmente removidos."""

    deleted: int


class ReprocessBatchIn(BaseModel):
    """Body do reprocess em lote (D-12).

    Exatamente UM de `bucket` ou `ids` deve ser informado (XOR — 422 se ambos
    None ou ambos preenchidos). `bucket` ("quarentena"|"em_revisao") faz o backend
    resolver os ids elegíveis do balde (botão "reprocessar todos"); `ids` aceita uma
    lista explícita (ids fora dos estados elegíveis são ignorados).
    """

    bucket: Literal["quarentena", "em_revisao"] | None = None
    ids: list[int] | None = None


class ReprocessBatchOut(BaseModel):
    """Resultado do reprocess em lote: quantos Documents foram re-enfileirados."""

    reprocessed: int


def _field_out(f: FilledField) -> ClassificationFieldOut:
    """Mapeia um FilledField para o schema de saída (bruto/normalizado + marcas)."""
    return ClassificationFieldOut(
        field_name=f.field_name,
        raw_value=f.raw_value,
        normalized_value=f.normalized_value,
        valid=f.valid,
        invalid_reason=f.invalid_reason,
        manually_corrected=f.manually_corrected,
    )


def _build_detail(session: Session, doc: Document, folder_path: str | None) -> DocumentDetailOut:
    """Monta o DocumentDetailOut (base + bloco classification) — reuso pelas ações.

    Extraído da montagem de `get_document` para que os endpoints de ação devolvam
    o mesmo detalhe sem duplicar a query do CR/FilledFields. NÃO loga valores
    (T-04-11) — eles vão só no corpo da resposta.
    """
    classification: ClassificationOut | None = None
    result = session.scalar(
        select(ClassificationResult).where(ClassificationResult.document_id == doc.id)
    )
    if result is not None:
        template_name: str | None = None
        if result.template_id is not None:
            template_name = session.scalar(
                select(Template.name).where(Template.id == result.template_id)
            )
        fields = session.scalars(
            select(FilledField)
            .where(FilledField.classification_result_id == result.id)
            .order_by(FilledField.id)
        ).all()
        classification = ClassificationOut(
            template_id=result.template_id,
            template_name=template_name,
            confidence=result.confidence,
            confidence_score=result.confidence_score,
            fields=[_field_out(f) for f in fields],
        )

    return DocumentDetailOut(
        id=doc.id,
        original_filename=doc.original_filename,
        state=doc.state.value,
        last_completed_step=doc.last_completed_step,
        source_folder_path=folder_path,
        created_at=_as_utc(doc.created_at),
        classification=classification,
    )


def _folder_path_for(session: Session, doc: Document) -> str | None:
    """Deriva a pasta de origem de um documento (mesmo outerjoin da lista)."""
    if doc.origin_original_id is None:
        return None
    return session.scalar(
        select(WatchedFolder.path)
        .join(IngestedOriginal, IngestedOriginal.source_folder_id == WatchedFolder.id)
        .where(IngestedOriginal.id == doc.origin_original_id)
    )


def _template_field(
    session: Session, template_id: int | None, field_name: str
) -> TemplateField | None:
    """Busca o TemplateField (template_id, name) — fonte de tipo/required/regex."""
    if template_id is None:
        return None
    return session.scalar(
        select(TemplateField).where(
            TemplateField.template_id == template_id,
            TemplateField.name == field_name,
        )
    )


def _has_invalid_required(session: Session, cr: ClassificationResult) -> bool:
    """Re-deriva a validade ATUAL dos obrigatórios (D-07 / Pitfall 4 — não confia no
    score persistido).

    Junta os FilledField do `cr` com os TemplateField obrigatórios do
    `cr.template_id`; retorna True se algum obrigatório está inválido ou ausente.
    Sem template (quarentena) → True (não há como aprovar sem classificação).
    """
    if cr.template_id is None:
        return True
    required = session.scalars(
        select(TemplateField).where(
            TemplateField.template_id == cr.template_id,
            TemplateField.required.is_(True),
        )
    ).all()
    if not required:
        return False
    valid_by_name = {
        ff.field_name: ff.valid
        for ff in session.scalars(
            select(FilledField).where(FilledField.classification_result_id == cr.id)
        ).all()
    }
    return any(not valid_by_name.get(tf.name, False) for tf in required)


@router.get("/documents", response_model=DocumentListOut)
def list_documents(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> DocumentListOut:
    """Lista Documents (blocos) com counts por estado; duplicatas fora (D-10)."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        # Mapa origin_original_id → folder path (para derivar a pasta de origem).
        rows = session.execute(
            select(Document, WatchedFolder.path)
            .outerjoin(
                IngestedOriginal,
                Document.origin_original_id == IngestedOriginal.id,
            )
            .outerjoin(
                WatchedFolder,
                IngestedOriginal.source_folder_id == WatchedFolder.id,
            )
            .order_by(Document.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        items = [
            DocumentOut(
                id=doc.id,
                original_filename=doc.original_filename,
                state=doc.state.value,
                last_completed_step=doc.last_completed_step,
                source_folder_path=folder_path,
                created_at=_as_utc(doc.created_at),
            )
            for doc, folder_path in rows
        ]

        # Contagens por estado (todos os estados aparecem, mesmo com 0).
        counts: dict[str, int] = {state.value: 0 for state in DocState}
        for state, count in session.execute(
            select(Document.state, func.count(Document.id)).group_by(Document.state)
        ).all():
            key = state.value if isinstance(state, DocState) else str(state)
            counts[key] = count
        total = sum(counts.values())

    return DocumentListOut(items=items, counts=counts, total=total)


@router.get("/documents/duplicates-count", response_model=DuplicatesCountOut)
def duplicates_count(request: Request) -> DuplicatesCountOut:
    """Soma dos `duplicate_hits` de todos os originais ingeridos (D-10)."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        total = session.scalar(select(func.coalesce(func.sum(IngestedOriginal.duplicate_hits), 0)))
    return DuplicatesCountOut(count=int(total or 0))


@router.get("/documents/attention", response_model=AttentionOut)
def get_attention(request: Request) -> AttentionOut:
    """Visão de triagem: os 3 baldes (FALHA/QUARENTENA/EM_REVISAO) num payload só.

    REGISTRADO ANTES de `GET /documents/{document_id}` (defensivo: senão "attention"
    seria capturado como `document_id` e daria 422). Open Q3: endpoint dedicado em
    vez de N+1 de `GET /documents/{id}` por item — a montagem de EM_REVISAO faz
    `selectinload` do CR+FilledFields num passo (sem loop de get_document).

    Motivo de QUARENTENA: texto fixo do UI-SPEC. Motivo de FALHA: `last_error` do
    job (achado por content_hash) quando existe, senão o fallback do UI-SPEC.
    Documentos em PROCESSANDO/CONCLUIDO/RECEBIDO NÃO aparecem.
    """
    engine = request.app.state.engine
    with get_session(engine) as session:
        # FALHA — id, filename, motivo (last_error do job ou fallback).
        falha_docs = session.scalars(
            select(Document).where(Document.state == DocState.FALHA).order_by(Document.id.desc())
        ).all()
        falha: list[AttentionItemOut] = []
        for doc in falha_docs:
            last_error = session.scalar(
                select(Job.last_error)
                .where(Job.original_hash == doc.content_hash)
                .order_by(Job.updated_at.desc())
            )
            falha.append(
                AttentionItemOut(
                    id=doc.id,
                    original_filename=doc.original_filename,
                    motivo=last_error or _MOTIVO_FALHA_FALLBACK,
                )
            )

        # QUARENTENA — motivo fixo do UI-SPEC.
        quarentena = [
            AttentionItemOut(
                id=doc.id,
                original_filename=doc.original_filename,
                motivo=_MOTIVO_QUARENTENA,
            )
            for doc in session.scalars(
                select(Document)
                .where(Document.state == DocState.QUARENTENA)
                .order_by(Document.id.desc())
            ).all()
        ]

        # EM_REVISAO — CR + FilledFields eager-loaded (sem N+1).
        rev_rows = session.execute(
            select(Document, ClassificationResult)
            .outerjoin(
                ClassificationResult,
                ClassificationResult.document_id == Document.id,
            )
            .where(Document.state == DocState.EM_REVISAO)
            .order_by(Document.id.desc())
            .options(selectinload(ClassificationResult.filled_fields))
        ).all()
        em_revisao: list[ReviewItemOut] = []
        for doc, cr in rev_rows:
            fields = (
                [_field_out(f) for f in sorted(cr.filled_fields, key=lambda x: x.id)]
                if cr is not None
                else []
            )
            em_revisao.append(
                ReviewItemOut(
                    id=doc.id,
                    original_filename=doc.original_filename,
                    motivo=None,
                    confidence_score=cr.confidence_score if cr is not None else None,
                    fields=fields,
                )
            )

    counts = {
        "falha": len(falha),
        "quarentena": len(quarentena),
        "em_revisao": len(em_revisao),
    }
    return AttentionOut(falha=falha, quarentena=quarentena, em_revisao=em_revisao, counts=counts)


@router.post("/documents/delete", response_model=DeleteDocumentsOut)
def delete_documents(request: Request, body: DeleteDocumentsIn) -> DeleteDocumentsOut:
    """Remove em LOTE SÓ o registro de cada documento — NUNCA o arquivo físico.

    Constraint forte do projeto (CLAUDE.md): operações sobre documentos do cliente
    nunca podem causar perda de arquivos. Este endpoint apaga PURAMENTE do banco;
    não importa/chama `os`/`shutil`/`Path.unlink` — o arquivo de origem na pasta
    monitorada e o blob no CAS permanecem intactos. Se o arquivo ainda estiver na
    pasta monitorada e o original ficar sem nenhum bloco, o watcher pode
    re-ingeri-lo numa próxima varredura — comportamento ESPERADO (o gate de dedup é
    liberado junto, ver passo de anti-órfão).

    REGISTRADO ANTES de `GET /documents/{document_id}` (mesma razão de
    `/documents/attention`): o conversor de path `{document_id}: int` rejeitaria
    "delete" com 422 se esta rota viesse depois.

    Algoritmo numa única sessão:
    (1) Para cada id: `session.get(Document, id)`; ausente → ignora silenciosamente.
    (2) Captura `content_hash` e `origin_original_id` ANTES de deletar.
    (3) `session.delete(doc)` — o cascade all,delete-orphan já remove
        extraction/classification/filled_fields/usages/audit_logs/pages.
    (4) Limpa Jobs órfãos do bloco (`original_hash == content_hash`) — senão um Job
        'done' (UNIQUE hash,step) bloquearia uma futura re-ingestão.
    (5) Anti-órfão de dedup: após o flush, para cada `origin_original_id` tocado,
        se NÃO sobrar nenhum Document apontando, apaga o IngestedOriginal e os Jobs
        do `original_hash` dele (libera o gate). Se ainda houver outro bloco (split),
        preserva o original.
    (6) commit; retorna {deleted: nº de Documents efetivamente apagados}.
    """
    engine = request.app.state.engine
    deleted = 0
    block_hashes: list[str] = []
    touched_origin_ids: set[int] = set()

    with get_session(engine) as session:
        for doc_id in body.ids:
            doc = session.get(Document, doc_id)
            if doc is None:
                continue  # id inexistente → ignora silenciosamente (não derruba o lote).
            block_hashes.append(doc.content_hash)
            if doc.origin_original_id is not None:
                touched_origin_ids.add(doc.origin_original_id)
            # Cascade (all, delete-orphan) limpa extraction/classification/
            # filled_fields/usages/audit_logs/pages do bloco.
            session.delete(doc)
            deleted += 1

        # Flush para que os Documents apagados não contem na checagem de blocos
        # restantes (anti-órfão de dedup) — sem commit ainda.
        session.flush()

        # (4) Jobs órfãos do(s) bloco(s) removido(s).
        for content_hash in block_hashes:
            session.execute(delete(Job).where(Job.original_hash == content_hash))

        # (5) Anti-órfão de dedup: IngestedOriginal sem blocos restantes.
        for origin_id in touched_origin_ids:
            remaining = session.scalar(
                select(func.count(Document.id)).where(Document.origin_original_id == origin_id)
            )
            if remaining:
                continue  # Outro bloco ainda aponta (split) → preserva o original.
            original = session.get(IngestedOriginal, origin_id)
            if original is None:
                continue
            original_hash = original.original_hash
            session.delete(original)
            session.execute(delete(Job).where(Job.original_hash == original_hash))

        session.commit()

    return DeleteDocumentsOut(deleted=deleted)


_REPROCESS_STATES = (DocState.QUARENTENA, DocState.EM_REVISAO)


def _reprocess_one(session: Session, doc: Document) -> None:
    """Reprocessa UM doc (D-10/D-11): apaga o CR, transita PROCESSANDO, re-enfileira
    `classify` SEM `forced_template_id`.

    Pré-condição (chamadores garantem): `doc.state in _REPROCESS_STATES`. Apagar o
    `ClassificationResult` ANTES do requeue é obrigatório (Pitfall 3) — senão a
    idempotência do `classify_stage` (no-op se já existe CR) deixaria o doc preso
    em PROCESSANDO sem reclassificar. Sem `forced_template_id`, o stage roda
    matcher→decide→(IA)→filler com TODOS os templates atuais (pega edições pós-
    quarentena de graça, D-11). NÃO loga valores/conteúdo (V7) — só metadados.
    """
    cr = session.scalar(
        select(ClassificationResult).where(ClassificationResult.document_id == doc.id)
    )
    if cr is not None:
        session.delete(cr)
    transition(session, doc, DocState.PROCESSANDO)
    _requeue(
        session,
        content_hash=doc.content_hash,
        step=CLASSIFY_STEP,
        payload={"content_hash": doc.content_hash},
    )


@router.post("/documents/reprocess", response_model=ReprocessBatchOut)
def reprocess_documents(request: Request, body: ReprocessBatchIn) -> ReprocessBatchOut:
    """Reprocessa em LOTE docs de um balde (QUARENTENA|EM_REVISAO) SEM forçar template (D-12).

    Espelha `reprocess_document` (single) numa única sessão. Exatamente UM de
    `bucket`/`ids` é exigido (XOR → 422). Para `bucket`, resolve os ids pelo mesmo
    filtro de `get_attention` (`Document.state == DocState.<BALDE>`); para `ids`, usa
    a lista. Cada doc ausente OU fora de {QUARENTENA, EM_REVISAO} é IGNORADO
    silenciosamente (idempotente — não derruba o lote; T-10-05D). Re-enfileirar
    `classify` não dispara IA por si só (matcher local custo-zero primeiro).

    REGISTRADO ANTES de `GET /documents/{document_id}` (mesma razão de
    `/documents/delete` e `/documents/attention`): o conversor `{document_id}: int`
    rejeitaria "reprocess" com 422 se esta rota viesse depois.
    """
    # XOR: exatamente um de bucket/ids (422 se ambos None ou ambos preenchidos).
    if (body.bucket is None) == (body.ids is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "informe exatamente um de 'bucket' ou 'ids'",
        )

    engine = request.app.state.engine
    reprocessed = 0
    with get_session(engine) as session:
        if body.bucket is not None:
            target_state = (
                DocState.QUARENTENA if body.bucket == "quarentena" else DocState.EM_REVISAO
            )
            docs = list(
                session.scalars(
                    select(Document).where(Document.state == target_state)
                ).all()
            )
        else:
            docs = []
            for doc_id in body.ids or []:
                doc = session.get(Document, doc_id)
                if doc is None:
                    continue  # id inexistente → ignora (idempotente).
                docs.append(doc)

        for doc in docs:
            if doc.state not in _REPROCESS_STATES:
                continue  # fora dos estados elegíveis → ignora silenciosamente.
            try:
                _reprocess_one(session, doc)
            except InvalidTransition:
                continue  # transição inválida (corrida) → ignora, não derruba o lote.
            reprocessed += 1

        session.commit()

    return ReprocessBatchOut(reprocessed=reprocessed)


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(request: Request, document_id: int) -> DocumentDetailOut:
    """Detalhe de classificação SOMENTE LEITURA (S4, TPL-03/04); 404 se ausente.

    Retorna os dados base do documento + um bloco `classification` derivado do
    `ClassificationResult` (join com Template p/ o nome) e seus `FilledField`s.
    `classification=None` quando o doc ainda não foi classificado. Quando
    `template_id is None`, o estado de QUARENTENA fica visível (TPL-04). NÃO loga
    valores extraídos (T-04-11) — eles vão só no corpo da resposta.
    """
    engine = request.app.state.engine
    with get_session(engine) as session:
        # Dados base + pasta de origem (mesmo padrão outerjoin da lista).
        row = session.execute(
            select(Document, WatchedFolder.path)
            .outerjoin(
                IngestedOriginal,
                Document.origin_original_id == IngestedOriginal.id,
            )
            .outerjoin(
                WatchedFolder,
                IngestedOriginal.source_folder_id == WatchedFolder.id,
            )
            .where(Document.id == document_id)
        ).first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"documento {document_id} não encontrado",
            )
        doc, folder_path = row
        return _build_detail(session, doc, folder_path)


def _requeue(session: Session, *, content_hash: str, step: str, payload: dict) -> None:
    """Reenfileira (content_hash, step): reseta o job existente ou enfileira novo.

    `requeue_step` reseta a linha existente para `pending` (resolve a UNIQUE
    uq_jobs_hash_step quando o job antigo já está `done`); se nenhuma linha existia
    (rowcount==0), cai num `enqueue` normal.
    """
    payload_json = json.dumps(payload)
    rows = repo.requeue_step(session, content_hash=content_hash, step=step, payload=payload_json)
    if rows == 0:
        repo.enqueue(session, original_hash=content_hash, step=step, payload=payload_json)


@router.post("/documents/{document_id}/retry", response_model=DocumentDetailOut)
def retry_document(request: Request, document_id: int) -> DocumentDetailOut:
    """Reprocessa um doc em FALHA (FALHA→PROCESSANDO) e reenfileira o step adequado.

    O step depende do marcador interno: `last_completed_step == "extraido"` →
    reenfileira `classify`; senão (aguardando_extracao ou None) → `extract`.
    Doc fora de FALHA → 409 (transição fora da allowlist). 404 se ausente.
    """
    engine = request.app.state.engine
    with get_session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"documento {document_id} não encontrado"
            )
        # Pré-condição semântica de retry: só FALHA. A allowlist permite
        # PROCESSANDO a partir de vários estados (EM_REVISAO/QUARENTENA), então o
        # `transition` sozinho não basta como guard aqui.
        if doc.state != DocState.FALHA:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "retry só é permitido para documentos em FALHA",
            )
        try:
            transition(session, doc, DocState.PROCESSANDO)
        except InvalidTransition as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

        step = CLASSIFY_STEP if doc.last_completed_step == EXTRACTED_STEP else EXTRACT_STEP
        _requeue(
            session,
            content_hash=doc.content_hash,
            step=step,
            payload={"content_hash": doc.content_hash},
        )
        return _build_detail(session, doc, _folder_path_for(session, doc))


@router.post("/documents/{document_id}/reclassify", response_model=DocumentDetailOut)
def reclassify_document(
    request: Request, document_id: int, body: ReclassifyIn
) -> DocumentDetailOut:
    """Atribui um template e reclassifica um doc em QUARENTENA (QUARENTENA→PROCESSANDO).

    Valida que o template existe (404 se não — T-05-07); APAGA o CR de quarentena
    ANTES (Pitfall 3: senão a idempotência do stage faz no-op); transita; reenfileira
    `classify` com `forced_template_id` (D-09). Doc fora de QUARENTENA → 409.
    """
    engine = request.app.state.engine
    with get_session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"documento {document_id} não encontrado"
            )
        template = session.get(Template, body.template_id)
        if template is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"template {body.template_id} não encontrado",
            )
        # Pré-condição semântica de reclassify: só QUARENTENA. A allowlist permite
        # PROCESSANDO a partir de outros estados, então checamos a origem aqui.
        if doc.state != DocState.QUARENTENA:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "reclassify só é permitido para documentos em QUARENTENA",
            )

        # Apagar o CR de quarentena ANTES de reenfileirar (Pitfall 3) — cascade
        # delete-orphan limpa os FilledFields associados.
        cr = session.scalar(
            select(ClassificationResult).where(ClassificationResult.document_id == document_id)
        )
        if cr is not None:
            session.delete(cr)

        try:
            transition(session, doc, DocState.PROCESSANDO)
        except InvalidTransition as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

        _requeue(
            session,
            content_hash=doc.content_hash,
            step=CLASSIFY_STEP,
            payload={
                "content_hash": doc.content_hash,
                "forced_template_id": body.template_id,
            },
        )
        return _build_detail(session, doc, _folder_path_for(session, doc))


@router.post("/documents/{document_id}/reprocess", response_model=DocumentDetailOut)
def reprocess_document(request: Request, document_id: int) -> DocumentDetailOut:
    """Reprocessa um doc em QUARENTENA ou EM_REVISAO SEM forçar template (D-10/D-11).

    Espelha `reclassify_document` com 3 diferenças: (a) aceita QUARENTENA E
    EM_REVISAO; (b) sem body `template_id`; (c) requeue SEM `forced_template_id` — o
    `classify_stage` roda matcher→decide→(IA)→filler com TODOS os templates atuais,
    pegando as edições de template feitas após a quarentena (D-11).

    GUARD (Pitfall 4 / T-10-05): a allowlist da state machine permite PROCESSANDO de
    vários estados (CONCLUIDO inclusive), então checamos a origem semântica AQUI —
    doc fora de {QUARENTENA, EM_REVISAO} → 409 (não 500). 404 se ausente. APAGA o CR
    existente ANTES do requeue (Pitfall 3). NÃO loga valores/conteúdo (V7).
    """
    engine = request.app.state.engine
    with get_session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"documento {document_id} não encontrado"
            )
        # Pré-condição semântica do reprocess: só QUARENTENA ou EM_REVISAO.
        if doc.state not in _REPROCESS_STATES:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "reprocessar só é permitido para documentos em QUARENTENA ou EM_REVISAO",
            )
        try:
            _reprocess_one(session, doc)
        except InvalidTransition as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        return _build_detail(session, doc, _folder_path_for(session, doc))


@router.patch(
    "/documents/{document_id}/fields/{field_name}",
    response_model=DocumentDetailOut,
)
def patch_field(
    request: Request, document_id: int, field_name: str, body: FieldPatchIn
) -> DocumentDetailOut:
    """Corrige manualmente um campo: revalida SEM IA e recalcula o score (D-08).

    Busca o FilledField por (CR do doc-alvo, field_name) (T-05-08: só o campo do
    documento da rota é tocado); revalida via `validate_field` (NUNCA chama OpenAI);
    marca `manually_corrected=True`; recalcula `confidence_score` no MESMO commit
    (Pitfall 4). O documento permanece EM_REVISAO (sem transição).
    """
    engine = request.app.state.engine
    with get_session(engine) as session:
        cr = session.scalar(
            select(ClassificationResult).where(ClassificationResult.document_id == document_id)
        )
        if cr is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "classificação não encontrada")
        ff = session.scalar(
            select(FilledField).where(
                FilledField.classification_result_id == cr.id,
                FilledField.field_name == field_name,
            )
        )
        if ff is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"campo {field_name} não encontrado")
        tf = _template_field(session, cr.template_id, field_name)
        v = validate_field(
            field_type=tf.field_type if tf else "texto",
            raw=body.raw_value,
            required=tf.required if tf else False,
            regex=tf.regex if tf else None,
        )
        ff.raw_value = v.raw_value
        ff.normalized_value = v.normalized_value
        ff.valid = v.valid
        ff.invalid_reason = v.invalid_reason
        ff.manually_corrected = True

        # Recalcular o score no mesmo commit (Pitfall 4). template pode ser None
        # (quarentena), mas patch só ocorre em doc EM_REVISAO (com template).
        template = session.get(Template, cr.template_id) if cr.template_id is not None else None
        if template is not None:
            score, _ = compute_confidence(cr.filled_fields, list(template.fields))
            cr.confidence_score = score

        session.commit()

        doc = session.get(Document, document_id)
        return _build_detail(session, doc, _folder_path_for(session, doc))


@router.post("/documents/{document_id}/approve", response_model=DocumentDetailOut)
def approve_document(request: Request, document_id: int) -> DocumentDetailOut:
    """Aprova um doc em revisão — dispara a AUTOMAÇÃO que conclui o doc (Fase 6, D-07).

    GUARD D-07: re-deriva a validade ATUAL dos obrigatórios (Pitfall 4 — não confia
    no score persistido). Se o CR não existe ou algum obrigatório está inválido →
    409 ("corrija os campos obrigatórios inválidos antes de aprovar"). Doc fora de
    EM_REVISAO → 409.

    MUDANÇA Fase 6: em vez de `transition(CONCLUIDO)` direto, ENFILEIRA o step
    `apply` — é o `apply_stage` (worker) que aplica a automação (renomear/mover) E
    conclui o documento (EM_REVISAO→CONCLUIDO via transition). Doc SEM regra de
    automação aplicável também conclui: o apply é no-op de disco mas faz a transição
    final. Mantém o doc em EM_REVISAO até o worker rodar o apply.
    """
    engine = request.app.state.engine
    with get_session(engine) as session:
        doc = session.get(Document, document_id)
        if doc is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"documento {document_id} não encontrado"
            )
        # Guard de estado semântico: aprovar só faz sentido em EM_REVISAO.
        if doc.state != DocState.EM_REVISAO:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "aprovar só é permitido para documentos em EM_REVISAO",
            )
        cr = session.scalar(
            select(ClassificationResult).where(ClassificationResult.document_id == document_id)
        )
        if cr is None or _has_invalid_required(session, cr):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "corrija os campos obrigatórios inválidos antes de aprovar",
            )
        # Dispara o apply (que conclui o doc). NÃO transitamos aqui — o apply_stage
        # faz EM_REVISAO→CONCLUIDO ao materializar (ou no-op de disco + conclusão
        # para docs sem regra). Reusa o helper _requeue (UNIQUE-safe).
        _requeue(
            session,
            content_hash=doc.content_hash,
            step=APPLY_STEP,
            payload={"content_hash": doc.content_hash},
        )
        return _build_detail(session, doc, _folder_path_for(session, doc))


@router.post("/rescan", response_model=RescanOut)
async def rescan(request: Request) -> RescanOut:
    """Força uma varredura das pastas ativas; idempotente por dedup."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        paths = list(active_folder_paths(session).keys())
    result = await scan_and_enqueue(engine, paths)
    return RescanOut(
        enqueued=result.enqueued,
        skipped_duplicates=result.skipped_duplicates,
    )

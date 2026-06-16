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

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.ingest.watcher import active_folder_paths, scan_and_enqueue
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.models.ingested_original import IngestedOriginal
from app.models.template import Template
from app.models.watched_folder import WatchedFolder
from app.storage.db import get_session

router = APIRouter(tags=["documents"])


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


class ClassificationOut(BaseModel):
    """Bloco de classificação de um documento (somente leitura — S4).

    `template_id`/`template_name` são `null` quando nenhum template casou
    (quarentena, D-03/TPL-04).
    """

    template_id: int | None
    template_name: str | None
    confidence: float | None
    fields: list[ClassificationFieldOut]


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
    """Resultado de uma varredura forçada: quantos candidatos enfileirados."""

    enqueued: int


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
                created_at=doc.created_at,
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
        total = session.scalar(
            select(func.coalesce(func.sum(IngestedOriginal.duplicate_hits), 0))
        )
    return DuplicatesCountOut(count=int(total or 0))


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

        classification: ClassificationOut | None = None
        result = session.scalar(
            select(ClassificationResult).where(
                ClassificationResult.document_id == document_id
            )
        )
        if result is not None:
            # template_id null = quarentena/não-casou (D-03); sem nome de template.
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
                fields=[
                    ClassificationFieldOut(
                        field_name=f.field_name,
                        raw_value=f.raw_value,
                        normalized_value=f.normalized_value,
                        valid=f.valid,
                        invalid_reason=f.invalid_reason,
                    )
                    for f in fields
                ],
            )

        return DocumentDetailOut(
            id=doc.id,
            original_filename=doc.original_filename,
            state=doc.state.value,
            last_completed_step=doc.last_completed_step,
            source_folder_path=folder_path,
            created_at=doc.created_at,
            classification=classification,
        )


@router.post("/rescan", response_model=RescanOut)
async def rescan(request: Request) -> RescanOut:
    """Força uma varredura das pastas ativas; idempotente por dedup."""
    engine = request.app.state.engine
    with get_session(engine) as session:
        paths = list(active_folder_paths(session).keys())
    enqueued = await scan_and_enqueue(engine, paths)
    return RescanOut(enqueued=enqueued)

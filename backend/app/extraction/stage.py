"""Estágio de extração — orquestra CAS→router→pdf_io→OpenAI→persistência atômica.

Coração funcional da Fase 3 (EXT-01 + EXT-02 + USE-02 num fluxo atômico). Espelha
`pipeline/ingest_stage.py` em forma/garantias: função async, isolável (sem HTTP,
mesmo papel de `state_machine.py`), idempotente e com um ÚNICO `session.commit()`
ao final ("crash antes daqui = rollback total"). Liga as primitivas do Plan 02
(`router.choose`, `pdf_io`, `openai_client`) à persistência do Plan 01
(`Extraction` + `Usage`).

Garantias materializadas:
- **Idempotência / não cobrar duas vezes (T-03-07 / CFM 3):** checa `Extraction`
  existente por `document_id` ANTES de qualquer chamada paga. Já existe → no-op
  (NÃO re-chama a IA). A UNIQUE(document_id) é a rede no banco; a checagem prévia
  evita a chamada paga.
- **Atomicidade (CR-02 / T-03-08):** `Extraction` + `Usage(step="extract")` + o
  avanço do marcador para "extraido" são persistidos no MESMO commit, ANTES de o
  worker (Plan 04) marcar o job done. Set-em-memória + commit único (NÃO
  `mark_step`, que comitaria sozinho e quebraria a atomicidade).
- **Estado terminal correto (D-07):** sucesso avança SÓ o marcador interno para
  "extraido"; `state` permanece `PROCESSANDO`. NUNCA `transition(PROCESSANDO→
  PROCESSANDO)` (auto-laço fora da allowlist, `states.py`) nem `CONCLUIDO`.
- **Recusa/erro propaga (D-08 / T-03-09):** `ExtractionRefused`, erro de PyMuPDF
  (PDF malformado) e erros transitórios de rede NÃO são capturados aqui — sobem
  para o worker (Plan 04), que faz schedule_retry/FALHA. Como a exceção ocorre
  ANTES do commit único, nada parcial é persistido (estado intacto).
- **Não vazar conteúdo (V7/V8 / T-03-10):** loga só `document_id`/route/
  doc_type_guess; NUNCA a chave, o `full_text` ou os `fields`.

Concorrência (Pitfall 2): só a parte PyMuPDF (CPU-bound: get_text/render) vai em
`await asyncio.to_thread(...)`; a chamada OpenAI é `await` direto (é o ponto async,
nunca em to_thread, nunca `asyncio.run`).

Interface pública: `extract_stage`, `ExtractStageResult`, `EXTRACTED_STEP`.
"""

import asyncio
import json
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.extraction import openai_client, pdf_io, router
from app.extraction.schema import ExtractionResult
from app.models.document import Document
from app.models.extraction import Extraction
from app.models.usage import Usage
from app.storage import cas

logger = logging.getLogger(__name__)

# Marcador interno avançado em caso de sucesso (D-07). NÃO é um estado de topo
# (DocState); o `state` permanece PROCESSANDO. A UI/worker leem este valor.
EXTRACTED_STEP = "extraido"

# Etapa atribuída ao consumo de tokens no modelo `Usage` (base da cobrança, USE-02).
USAGE_STEP = "extract"


@dataclass(frozen=True)
class ExtractStageResult:
    """Resultado de `extract_stage`: rota usada e se a IA foi de fato chamada.

    `called_ai=False` indica no-op idempotente (Extraction já existia) — útil para
    o worker e para os testes provarem a não-cobrança-dupla (call_count==1).
    """

    route: str
    called_ai: bool


async def extract_stage(session: Session, *, content_hash: str) -> ExtractStageResult:
    """Extrai o bloco `content_hash`, persiste Extraction + Usage e avança "extraido".

    Fluxo (espelha `ingest_stage.process_ingest` em forma/atomicidade):
      1. Localiza o `Document` do bloco por `content_hash`.
      2. IDEMPOTÊNCIA: se já existe `Extraction(document_id)`, retorna no-op SEM
         chamar a IA (evita cobrança dupla — T-03-07).
      3. Lê o blob do CAS e decide a rota (`router.choose` — seam D-03).
      4. Parte PyMuPDF (CPU-bound) em `asyncio.to_thread`: extrai o texto nativo e,
         no caminho visão, renderiza as páginas. Persiste o `full_text` disponível
         mesmo no caminho visão (D-06).
      5. Chama a OpenAI (`await` direto): texto nativo ou imagem.
      6. PERSISTÊNCIA ATÔMICA: `Extraction` + `Usage(step="extract")` + marcador
         "extraido" EM MEMÓRIA, com UM ÚNICO `session.commit()` ao final.

    Recusa/erro (PDF malformado, `ExtractionRefused`, rede) PROPAGAM para o worker
    (Plan 04) — não são capturados aqui. Como ocorrem antes do commit único, nada
    parcial é persistido (D-08; estado permanece PROCESSANDO+"aguardando_extracao").

    Retorna `ExtractStageResult(route, called_ai)`.
    """
    # (1) Localizar o bloco. Documento ausente é erro de orquestração (o worker
    # só despacha extract para blocos existentes) — deixamos propagar.
    doc = session.scalar(
        select(Document).where(Document.content_hash == content_hash)
    )
    if doc is None:
        raise ValueError("Document inexistente para content_hash informado")

    # (2) IDEMPOTÊNCIA (T-03-07 / CFM 3): Extraction já existente → no-op. NÃO
    # re-chamar a IA (não re-cobrar). A UNIQUE(document_id) garante no banco; esta
    # checagem evita a chamada paga.
    existing = session.scalar(
        select(Extraction).where(Extraction.document_id == doc.id)
    )
    if existing is not None:
        logger.debug("Extração já existe para document_id=%s — no-op", doc.id)
        return ExtractStageResult(route=existing.route, called_ai=False)

    # (3) Ler o blob e decidir a rota (seam D-03). `router.choose` distingue imagem
    # (→visão) de PDF (→heurística texto-vs-visão).
    blob = cas.read_bytes(content_hash)
    route = await asyncio.to_thread(router.choose, blob)

    # (4) Parte PyMuPDF (CPU-bound) em to_thread + (5) chamada OpenAI (await direto).
    settings = get_settings()
    if route == "native_text":
        # Texto nativo suficiente: extrair o texto (CPU-bound) e mandar 1 bloco de
        # texto à IA. `full_text` = o texto nativo lido (D-06).
        native_text, _route = await asyncio.to_thread(
            pdf_io.extract_text_and_decide,
            blob,
            settings.openai_extract_min_chars_per_page,
        )
        result, usage = await openai_client.extract_from_text(native_text)
        full_text = native_text
    else:
        # Caminho visão: renderizar páginas → PNG (CPU-bound) e mandar à IA. Para
        # PDF escaneado, persistimos o que houver de texto nativo (D-06); imagem
        # crua não tem texto nativo (full_text vazio do lado local).
        blob_type = await asyncio.to_thread(pdf_io.detect_blob_type, blob)
        if blob_type == "pdf":
            native_text, _route = await asyncio.to_thread(
                pdf_io.extract_text_and_decide,
                blob,
                settings.openai_extract_min_chars_per_page,
            )
            pngs = await asyncio.to_thread(pdf_io.render_pages_png, blob)
        else:
            # Imagem (jpeg/png): a própria imagem é a página; sem texto nativo local.
            native_text = ""
            pngs = [blob]
        result, usage = await openai_client.extract_from_image_pages(pngs)
        full_text = native_text

    # (6) PERSISTÊNCIA ATÔMICA (CR-02 / T-03-08). Extraction + Usage + marcador num
    # único commit. Crash antes daqui = rollback total (nada parcial).
    session.add(
        Extraction(
            document_id=doc.id,
            fields_json=_fields_to_json(result),
            full_text=full_text,
            doc_type_guess=result.doc_type_guess,
            doc_type_confidence=result.doc_type_confidence,
            route=route,
        )
    )
    # Mapeamento já feito no openai_client (input→prompt, output→completion); aqui
    # só gravamos. Exatamente 1 Usage(step="extract") por extração (USE-02 / SC4).
    session.add(
        Usage(
            document_id=doc.id,
            step=USAGE_STEP,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
    )
    # Avança SÓ o marcador interno EM MEMÓRIA (D-07). NÃO `mark_step` (comitaria
    # sozinho, quebrando a atomicidade); NÃO `transition` (PROCESSANDO→PROCESSANDO
    # fora da allowlist). `state` permanece PROCESSANDO.
    doc.last_completed_step = EXTRACTED_STEP

    session.commit()

    # Log seguro: só metadados, NUNCA chave/full_text/fields (V7/V8 / T-03-10).
    logger.info(
        "Extração concluída document_id=%s route=%s doc_type_guess=%s",
        doc.id,
        route,
        result.doc_type_guess,
    )
    return ExtractStageResult(route=route, called_ai=True)


def _fields_to_json(result: ExtractionResult) -> str:
    """Serializa `result.fields` (list[ExtractedField]) em JSON para `fields_json`."""
    return json.dumps([f.model_dump() for f in result.fields])

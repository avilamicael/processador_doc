"""Seed de demonstração da Fase 4 — classificação (S4) com dados reais.

Cria, de forma idempotente, no banco apontado pela config da app:

1. Um Template "Nota Fiscal" com campos (CNPJ, número, emissão, valor total).
2. Um Document CLASSIFICADO (state=CONCLUIDO) com ClassificationResult casando
   o template e FilledFields — incluindo 1 campo INVÁLIDO (CNPJ com DV errado)
   para exercitar a marca válido/inválido (D-10) na tela S4.
3. Um Document em QUARENTENA (state=QUARENTENA) com ClassificationResult de
   template_id=None (D-03/TPL-04) — sem campos preenchidos.

NÃO gasta tokens da OpenAI: os dados são fixos. Rode com:

    uv run python scripts/seed_demo_classification.py

Reexecutar é seguro: os registros são identificados por content_hash/nome e
recriados se ausentes (não duplica).
"""

from __future__ import annotations

import json

from sqlalchemy import select

from app.config import ensure_data_dir, get_settings
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.models.template import Template, TemplateField
from app.storage.db import create_db_engine, get_session

# Hashes sintéticos (64 hex) — marcam os blocos de demonstração de forma estável.
HASH_CLASSIFICADO = "de" * 32
HASH_QUARENTENA = "ad" * 32
TEMPLATE_NAME = "Nota Fiscal (demo)"


def _get_or_create_template(session) -> Template:
    tpl = session.scalar(select(Template).where(Template.name == TEMPLATE_NAME))
    if tpl is not None:
        return tpl
    tpl = Template(
        name=TEMPLATE_NAME,
        doc_type="fiscal",
        signals_json=json.dumps(
            ["nota fiscal", "danfe", "cnpj", "natureza da operação"],
            ensure_ascii=False,
        ),
        fields=[
            TemplateField(
                name="CNPJ do emitente",
                field_type="cpf_cnpj",
                required=True,
                hint="CNPJ de 14 dígitos do emitente",
            ),
            TemplateField(
                name="Número da nota",
                field_type="numero",
                required=True,
            ),
            TemplateField(
                name="Data de emissão",
                field_type="data",
                required=True,
            ),
            TemplateField(
                name="Valor total",
                field_type="moeda",
                required=True,
            ),
        ],
    )
    session.add(tpl)
    session.flush()
    return tpl


def _ensure_classificado(session, template: Template) -> None:
    doc = session.scalar(
        select(Document).where(Document.content_hash == HASH_CLASSIFICADO)
    )
    if doc is None:
        doc = Document(
            content_hash=HASH_CLASSIFICADO,
            original_filename="nota-fiscal-12345.pdf",
            state=DocState.CONCLUIDO,
            last_completed_step="classify",
        )
        session.add(doc)
        session.flush()
    if doc.classification is not None:
        return
    result = ClassificationResult(
        document_id=doc.id,
        template_id=template.id,
        confidence=0.92,
        filled_fields=[
            # CNPJ com dígito verificador INVÁLIDO → marca inválido (D-10).
            FilledField(
                field_name="CNPJ do emitente",
                raw_value="12.345.678/0001-00",
                normalized_value="12345678000100",
                valid=False,
                invalid_reason="Dígito verificador de CNPJ inválido",
            ),
            FilledField(
                field_name="Número da nota",
                raw_value="012345",
                normalized_value="12345",
                valid=True,
                invalid_reason=None,
            ),
            FilledField(
                field_name="Data de emissão",
                raw_value="03/06/2026",
                normalized_value="2026-06-03",
                valid=True,
                invalid_reason=None,
            ),
            FilledField(
                field_name="Valor total",
                raw_value="R$ 1.234,56",
                normalized_value="1234.56",
                valid=True,
                invalid_reason=None,
            ),
        ],
    )
    session.add(result)


def _ensure_quarentena(session) -> None:
    doc = session.scalar(
        select(Document).where(Document.content_hash == HASH_QUARENTENA)
    )
    if doc is None:
        doc = Document(
            content_hash=HASH_QUARENTENA,
            original_filename="documento-desconhecido.pdf",
            state=DocState.QUARENTENA,
            last_completed_step="classify",
        )
        session.add(doc)
        session.flush()
    if doc.classification is not None:
        return
    # template_id=None → quarentena / nenhum template casou (D-03/TPL-04).
    session.add(
        ClassificationResult(
            document_id=doc.id,
            template_id=None,
            confidence=None,
        )
    )


def main() -> None:
    settings = get_settings()
    ensure_data_dir(settings)
    engine = create_db_engine(settings.effective_database_url)
    with get_session(engine) as session:
        template = _get_or_create_template(session)
        _ensure_classificado(session, template)
        _ensure_quarentena(session)
        session.commit()
    print(f"Seed concluído. DB: {settings.effective_database_url}")
    print(f"  Template: {TEMPLATE_NAME} (com 4 campos)")
    print("  Documento classificado: nota-fiscal-12345.pdf (CONCLUIDO, 1 campo inválido)")
    print("  Documento em quarentena: documento-desconhecido.pdf (QUARENTENA)")


if __name__ == "__main__":
    main()

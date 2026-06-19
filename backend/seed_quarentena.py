"""Seed de verificação visual (Fase 5) — restaura 1 documento em QUARENTENA com
uma Extraction real, para que o "reclassificar com template" funcione offline
(o filler preenche nome+cpf do extraction, sem chamar a IA). Fixture descartável:
rode `seed_quarentena.py --remove` para apagar.
"""

import json
import sys

from app.config import get_settings
from app.models.classification import ClassificationResult
from app.models.document import Document
from app.models.enums import DocState
from app.models.extraction import Extraction
from app.models.job import Job
from app.storage.db import create_db_engine, get_session

CONTENT_HASH = "dd" * 32  # 64 hex chars, reconhecível como seed de quarentena

# Pares genéricos que a "extração" teria lido — cobrem os obrigatórios do
# template Exame (nome, cpf), então o reclassify forçado preenche tudo sem IA.
FIELDS = [
    {"key": "nome", "value": "MARINA COSTA ALVES", "confidence": 0.95},
    {"key": "cpf", "value": "390.533.447-05", "confidence": 0.95},
    {"key": "médico", "value": "Dr. Paulo Henrique Souza", "confidence": 0.9},
    {"key": "convênio", "value": "UNIMED", "confidence": 0.9},
    {"key": "data", "value": "10/06/2026", "confidence": 0.9},
    {"key": "protocolo", "value": "02 114477", "confidence": 0.9},
]


def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.effective_database_url)
    remove = "--remove" in sys.argv

    with get_session(engine) as session:
        existing = session.query(Document).filter_by(content_hash=CONTENT_HASH).one_or_none()

        if remove:
            if existing is not None:
                for j in session.query(Job).filter_by(original_hash=CONTENT_HASH).all():
                    session.delete(j)
                session.delete(existing)
                session.commit()
                print(f"removido doc quarentena seed id={existing.id}")
            else:
                print("nada para remover")
            return

        if existing is not None:
            print(f"seed já existe: doc id={existing.id} estado={existing.state}")
            return

        doc = Document(
            content_hash=CONTENT_HASH,
            original_filename="documento-quarentena-fase5.pdf",
            state=DocState.QUARENTENA,
            last_completed_step="extraido",
        )
        session.add(doc)
        session.flush()

        # Extraction real → reclassify forçado consegue preencher os campos offline.
        session.add(
            Extraction(
                document_id=doc.id,
                fields_json=json.dumps(FIELDS, ensure_ascii=False),
                full_text=(
                    "Exame laboratorial. Paciente: MARINA COSTA ALVES. "
                    "CPF: 390.533.447-05. Médico: Dr. Paulo Henrique Souza. "
                    "Convênio: UNIMED. Data: 10/06/2026. Protocolo: 02 114477."
                ),
                doc_type_guess="exame_laboratorial",
                doc_type_confidence=0.4,
                route="texto",
            )
        )

        # CR de quarentena (template_id=None) — é o que marca "não casou".
        session.add(
            ClassificationResult(
                document_id=doc.id,
                template_id=None,
                confidence=None,
                confidence_score=None,
            )
        )
        session.commit()
        print(f"criado doc quarentena seed id={doc.id} (com extração; reclassify funciona)")


if __name__ == "__main__":
    main()

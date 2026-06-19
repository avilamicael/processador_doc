"""Seed de verificação visual (Fase 5) — cria 1 documento em EM_REVISAO com um
campo obrigatório inválido, para conferir o fluxo de revisão (badge + correção +
aprovar) na UI. Fixture descartável: rode `seed_revisao.py --remove` para apagar.
"""

import sys

from app.config import get_settings
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState
from app.storage.db import create_db_engine, get_session

CONTENT_HASH = "ee" * 32  # 64 hex chars, reconhecível como seed
TEMPLATE_ID = 2  # Exame Laboratorial (demo) — nome/cpf obrigatórios


def main() -> None:
    settings = get_settings()
    engine = create_db_engine(settings.effective_database_url)
    remove = "--remove" in sys.argv

    with get_session(engine) as session:
        existing = session.query(Document).filter_by(content_hash=CONTENT_HASH).one_or_none()

        if remove:
            if existing is not None:
                session.delete(existing)
                session.commit()
                print(f"removido doc seed id={existing.id}")
            else:
                print("nada para remover")
            return

        if existing is not None:
            print(f"seed já existe: doc id={existing.id} estado={existing.state}")
            return

        doc = Document(
            content_hash=CONTENT_HASH,
            original_filename="seed-revisao-fase5.pdf",
            state=DocState.EM_REVISAO,
            last_completed_step="classificado",
        )
        session.add(doc)
        session.flush()

        cr = ClassificationResult(
            document_id=doc.id,
            template_id=TEMPLATE_ID,
            confidence=0.92,
            confidence_score=0.5,  # baixa → faixa Baixa no badge
        )
        session.add(cr)
        session.flush()

        fields = [
            ("nome", "EDUARDA PERES TEIXEIRA", "EDUARDA PERES TEIXEIRA", True, None),
            # cpf obrigatório INVÁLIDO → has_invalid_required → trava o Aprovar
            ("cpf", "111", None, False, "CPF inválido (dígito verificador)"),
            ("médico", "Dra. Marjorana M.R. Galvão", "Dra. Marjorana M.R. Galvão", True, None),
            ("convênio", "MEDPREV", "MEDPREV", True, None),
            ("data", "05/06/2026", "2026-06-05", True, None),
            ("protocolo", "01 805928", "01 805928", True, None),
        ]
        for name, raw, norm, valid, reason in fields:
            session.add(
                FilledField(
                    classification_result_id=cr.id,
                    field_name=name,
                    raw_value=raw,
                    normalized_value=norm,
                    valid=valid,
                    invalid_reason=reason,
                    manually_corrected=False,
                )
            )
        session.commit()
        print(f"criado doc seed id={doc.id} em EM_REVISAO (cpf inválido, score 0.5)")


if __name__ == "__main__":
    main()

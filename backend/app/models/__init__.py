"""Modelos de domínio.

Importar este pacote garante que TODOS os modelos sejam registrados em
`Base.metadata` (essencial para o autogenerate do Alembic e para os testes de
schema). Mantenha este `__all__`/imports em sincronia ao adicionar modelos.
"""

from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.enums import DocState
from app.models.page import Page
from app.models.usage import Usage

__all__ = [
    "AuditLog",
    "DocState",
    "Document",
    "Page",
    "Usage",
]

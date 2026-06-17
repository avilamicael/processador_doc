"""Modelos de domínio.

Importar este pacote garante que TODOS os modelos sejam registrados em
`Base.metadata` (essencial para o autogenerate do Alembic e para os testes de
schema). Mantenha este `__all__`/imports em sincronia ao adicionar modelos.
"""

from app.models.audit_log import AuditLog
from app.models.automation_rule import AutomationRule, RuleCondition
from app.models.classification import ClassificationResult, FilledField
from app.models.document import Document
from app.models.enums import DocState, JobStatus
from app.models.extraction import Extraction
from app.models.ingested_original import IngestedOriginal
from app.models.job import Job
from app.models.page import Page
from app.models.template import Template, TemplateField
from app.models.usage import Usage
from app.models.watched_folder import WatchedFolder

__all__ = [
    "AuditLog",
    "AutomationRule",
    "ClassificationResult",
    "DocState",
    "Document",
    "Extraction",
    "FilledField",
    "IngestedOriginal",
    "Job",
    "JobStatus",
    "Page",
    "RuleCondition",
    "Template",
    "TemplateField",
    "Usage",
    "WatchedFolder",
]

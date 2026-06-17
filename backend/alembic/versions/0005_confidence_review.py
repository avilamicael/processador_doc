"""confiança/revisão: 2 colunas da Fase 5 (confidence_score + manually_corrected)

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-17 00:00:00.000000

Adiciona as DUAS colunas novas da Fase 5 (REV-01, D-01/D-08):
- `classification_results.confidence_score` (Float, nullable): score 0.0–1.0 de
  QUALIDADE DE EXTRAÇÃO (fração de obrigatórios válidos) — distinto de `confidence`
  (score do matcher/desempate). nullable: quarentena não tem score.
- `filled_fields.manually_corrected` (Boolean, NOT NULL, server_default '0'):
  origem do valor marcada como corrigida manualmente (auditabilidade + base do
  approve do Plan 03).

CAVEAT do trigger trg_documents_updated_at (criado na 0002) NÃO se aplica: esta
migração só ADICIONA colunas em `classification_results` e `filled_fields` e
**NÃO toca `documents`** (nenhum batch recreate de documents) — logo o trigger
não é destruído (Pitfall 1; mesma garantia documentada nas 0003/0004). `documents`
aparece neste arquivo SOMENTE neste comentário, nunca em batch_alter_table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — adiciona 2 colunas nullable/com server_default."""
    with op.batch_alter_table('classification_results', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('confidence_score', sa.Float(), nullable=True)
        )
    with op.batch_alter_table('filled_fields', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'manually_corrected',
                sa.Boolean(),
                nullable=False,
                server_default='0',
            )
        )


def downgrade() -> None:
    """Downgrade schema — dropa na ordem inversa do upgrade."""
    with op.batch_alter_table('filled_fields', schema=None) as batch_op:
        batch_op.drop_column('manually_corrected')
    with op.batch_alter_table('classification_results', schema=None) as batch_op:
        batch_op.drop_column('confidence_score')

"""extractions: resultado da extração genérica por bloco (Fase 3)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-16 16:10:00.000000

Cria a tabela `extractions` (D-02/D-06/D-10):
- `document_id` FK→documents.id (ondelete=CASCADE), **UNIQUE** = 1 extração por
  bloco = idempotência (não re-chamar a IA / não cobrar duas vezes — Pitfall 3).
- `fields_json` (list[ExtractedField] serializado), `full_text` (texto nativo
  persistido — base das Fases 4/7), `doc_type_guess`/`doc_type_confidence`
  (palpite de tipo), `route` ("native_text"|"vision" — métrica de custo).

CAVEAT do trigger trg_documents_updated_at (do 0002) NÃO se aplica: 0003 só CRIA
`extractions` e NÃO toca a tabela `documents` (nenhum batch recreate de documents),
logo não há trigger a recriar.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'extractions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('fields_json', sa.Text(), nullable=False),
        sa.Column('full_text', sa.Text(), nullable=False),
        sa.Column('doc_type_guess', sa.String(), nullable=False),
        sa.Column('doc_type_confidence', sa.Float(), nullable=False),
        sa.Column('route', sa.String(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('extractions', schema=None) as batch_op:
        # UNIQUE: 1 extração por bloco = idempotência (não re-extrair / não re-cobrar).
        batch_op.create_index(
            batch_op.f('ix_extractions_document_id'), ['document_id'], unique=True
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('extractions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_extractions_document_id'))

    op.drop_table('extractions')

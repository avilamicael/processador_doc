"""templates + classificação: fundação da Fase 4 (templates, campos, resultado)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-16 21:10:00.000000

Cria as 4 tabelas da Fase 4 (TPL-01 / EXT-04, D-08/D-09/D-10/D-11):
- `templates`: tipo de documento configurado pelo cliente (name UNIQUE, doc_type,
  signals_json — sinais identificadores D-02).
- `template_fields`: campos a extrair (field_type D-08, required, regex D-09, hint),
  FK→templates ondelete CASCADE.
- `classification_results`: resultado por bloco. `document_id` FK→documents
  ondelete CASCADE **UNIQUE** (Pitfall 2 — rede contra double-charge); `template_id`
  FK→templates ondelete SET NULL **nullable** (null = quarentena, D-03).
- `filled_fields`: campos preenchidos por classificação (raw/normalized D-11,
  valid D-10, invalid_reason), FK→classification_results ondelete CASCADE.

CAVEAT do trigger trg_documents_updated_at (do 0002) NÃO se aplica: a 0004 só CRIA
tabelas novas e NÃO toca `documents` (nenhum batch recreate de documents), logo não
há trigger a recriar — mesma situação resolvida da 0003.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('doc_type', sa.String(), nullable=True),
        sa.Column('signals_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('templates', schema=None) as batch_op:
        # UNIQUE: não há dois templates com o mesmo nome.
        batch_op.create_index(
            batch_op.f('ix_templates_name'), ['name'], unique=True
        )

    op.create_table(
        'template_fields',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column(
            'field_type', sa.String(), nullable=False, server_default='texto'
        ),
        sa.Column('required', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('regex', sa.String(), nullable=True),
        sa.Column('hint', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('template_fields', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_template_fields_template_id'), ['template_id'], unique=False
        )

    op.create_table(
        'classification_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('classification_results', schema=None) as batch_op:
        # UNIQUE: 1 classificação por bloco = rede contra double-charge (Pitfall 2).
        batch_op.create_index(
            batch_op.f('ix_classification_results_document_id'),
            ['document_id'],
            unique=True,
        )
        # null = quarentena (D-03); índice não-único só para lookup.
        batch_op.create_index(
            batch_op.f('ix_classification_results_template_id'),
            ['template_id'],
            unique=False,
        )

    op.create_table(
        'filled_fields',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('classification_result_id', sa.Integer(), nullable=False),
        sa.Column('field_name', sa.String(), nullable=False),
        sa.Column('raw_value', sa.Text(), nullable=True),
        sa.Column('normalized_value', sa.Text(), nullable=True),
        sa.Column('valid', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('invalid_reason', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ['classification_result_id'],
            ['classification_results.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('filled_fields', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_filled_fields_classification_result_id'),
            ['classification_result_id'],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema — dropa na ordem inversa (filhas antes das pais)."""
    with op.batch_alter_table('filled_fields', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_filled_fields_classification_result_id'))
    op.drop_table('filled_fields')

    with op.batch_alter_table('classification_results', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_classification_results_template_id'))
        batch_op.drop_index(batch_op.f('ix_classification_results_document_id'))
    op.drop_table('classification_results')

    with op.batch_alter_table('template_fields', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_template_fields_template_id'))
    op.drop_table('template_fields')

    with op.batch_alter_table('templates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_templates_name'))
    op.drop_table('templates')

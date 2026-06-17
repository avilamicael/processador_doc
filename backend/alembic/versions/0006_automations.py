"""automações: estende audit_log (write-ahead) + cria as tabelas de regra (Fase 6)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-17 00:00:00.000000

Sobe a fundação da Fase 6 (AUT-04/AUT-05, TPL-02):
- ESTENDE `audit_log` (batch add_column) com as 5 colunas do padrão write-ahead:
  `status` (NOT NULL, server_default 'done'), `source_path`/`dest_path` (Text),
  `run_id` (String, undo por-lote) e `content_hash` (String(64), undo via CAS).
- CRIA `automation_rules` (priority indexado D-05, conjunction E/OU, name_pattern,
  folder_pattern, active) e `rule_conditions` (FK→automation_rules ondelete CASCADE
  indexada; field_name, operator, value, position).

CAVEAT do trigger trg_documents_updated_at (criado na 0002): esta migração só
ADICIONA colunas em `audit_log` e CRIA tabelas novas; **NÃO toca `documents`**
(nenhum batch recreate de documents) — logo o trigger NÃO é destruído (mesma
garantia das 0003/0004/0005). `documents` aparece neste arquivo SOMENTE neste
comentário, nunca em batch_alter_table.

`downgrade` dropa na ordem inversa: tabela-filha `rule_conditions` antes da pai
`automation_rules`, depois remove as 5 colunas de `audit_log`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — estende audit_log + cria automation_rules/rule_conditions."""
    # Estende audit_log via batch add_column (NÃO toca documents).
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('status', sa.String(), nullable=False, server_default='done')
        )
        batch_op.add_column(sa.Column('source_path', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('dest_path', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('run_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('content_hash', sa.String(length=64), nullable=True))

    # Tabela pai: automation_rules (TPL-02).
    op.create_table(
        'automation_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('conjunction', sa.String(), nullable=False, server_default='and'),
        sa.Column('name_pattern', sa.Text(), nullable=True),
        sa.Column('folder_pattern', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='1'),
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
    with op.batch_alter_table('automation_rules', schema=None) as batch_op:
        # priority indexado (D-05): ordenar pela ordem de avaliação.
        batch_op.create_index(
            batch_op.f('ix_automation_rules_priority'), ['priority'], unique=False
        )

    # Tabela filha: rule_conditions (FK→automation_rules ondelete CASCADE).
    op.create_table(
        'rule_conditions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('field_name', sa.String(), nullable=False),
        sa.Column('operator', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(
            ['rule_id'], ['automation_rules.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('rule_conditions', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_rule_conditions_rule_id'), ['rule_id'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema — dropa na ordem inversa (filha antes da pai)."""
    with op.batch_alter_table('rule_conditions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rule_conditions_rule_id'))
    op.drop_table('rule_conditions')

    with op.batch_alter_table('automation_rules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_automation_rules_priority'))
    op.drop_table('automation_rules')

    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_column('content_hash')
        batch_op.drop_column('run_id')
        batch_op.drop_column('dest_path')
        batch_op.drop_column('source_path')
        batch_op.drop_column('status')

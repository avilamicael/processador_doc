"""pipeline de automações: dropa regras (0006) + cria pipeline/steps/filters (Fase 6 REDESIGN)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-17 00:00:00.000000

Redesenho da camada de automação (D-12..D-16). Substitui o modelo de "regra única"
(`automation_rules`/`rule_conditions`, criadas na 0006) pelo PIPELINE ordenado de
etapas componíveis: `automation_pipelines` 1:N `pipeline_steps` 1:N `step_filters`.

As tabelas de regra da 0006 **não têm dados em prod** (CONTEXT autoriza redesenhar
— A1), por isso esta migração é forward-only no sentido de schema: DROP das tabelas
de regra e CREATE das tabelas de pipeline. O `downgrade` recria a forma EXATA da
0006 (reversibilidade do histórico).

CAVEAT do trigger trg_documents_updated_at (criado na 0002) e do write-ahead de
`audit_log` (0006): esta migração só DROPA/CRIA tabelas novas; **NÃO faz
`batch_alter_table('documents')` NEM `batch_alter_table('audit_log')`**. Logo:
- o trigger `trg_documents_updated_at` permanece intacto (mesma garantia das
  0003/0004/0005/0006); `documents` aparece SOMENTE neste comentário;
- as 5 colunas write-ahead de `audit_log` (status/source_path/dest_path/run_id/
  content_hash) — base de AUT-04/AUT-05 — permanecem (independem do modelo
  regra↔pipeline).

`downgrade` dropa na ordem inversa (filhas antes das pais: step_filters →
pipeline_steps → automation_pipelines) e recria automation_rules/rule_conditions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — dropa regras (0006) e cria pipeline/steps/filters."""
    # DROP das tabelas de regra (filha antes da pai). Sem dados em prod (CONTEXT A1).
    with op.batch_alter_table("rule_conditions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_rule_conditions_rule_id"))
    op.drop_table("rule_conditions")

    with op.batch_alter_table("automation_rules", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_automation_rules_priority"))
    op.drop_table("automation_rules")

    # Tabela pai: automation_pipelines (D-12).
    op.create_table(
        "automation_pipelines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Tabela do meio: pipeline_steps (FK→automation_pipelines ondelete CASCADE).
    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("conjunction", sa.String(), nullable=False, server_default="and"),
        sa.Column("params_json", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["pipeline_id"], ["automation_pipelines.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pipeline_steps", schema=None) as batch_op:
        # lookup da FK CASCADE.
        batch_op.create_index(
            batch_op.f("ix_pipeline_steps_pipeline_id"), ["pipeline_id"], unique=False
        )
        # ordem D-12 (indexada para ordenar/reordenar na UI).
        batch_op.create_index(
            batch_op.f("ix_pipeline_steps_position"), ["position"], unique=False
        )
        # ordenação composta por pipeline+posição (iteração do executor 06-07).
        batch_op.create_index(
            "ix_pipeline_steps_pipeline_position",
            ["pipeline_id", "position"],
            unique=False,
        )

    # Tabela filha: step_filters (FK→pipeline_steps ondelete CASCADE).
    op.create_table(
        "step_filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("filter_type", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["step_id"], ["pipeline_steps.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("step_filters", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_step_filters_step_id"), ["step_id"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema — dropa pipeline (ordem inversa) e recria a forma da 0006."""
    with op.batch_alter_table("step_filters", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_step_filters_step_id"))
    op.drop_table("step_filters")

    with op.batch_alter_table("pipeline_steps", schema=None) as batch_op:
        batch_op.drop_index("ix_pipeline_steps_pipeline_position")
        batch_op.drop_index(batch_op.f("ix_pipeline_steps_position"))
        batch_op.drop_index(batch_op.f("ix_pipeline_steps_pipeline_id"))
    op.drop_table("pipeline_steps")

    op.drop_table("automation_pipelines")

    # Recria a forma EXATA da 0006 (reversibilidade do histórico).
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conjunction", sa.String(), nullable=False, server_default="and"),
        sa.Column("name_pattern", sa.Text(), nullable=True),
        sa.Column("folder_pattern", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("automation_rules", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_automation_rules_priority"), ["priority"], unique=False
        )

    op.create_table(
        "rule_conditions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["automation_rules.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("rule_conditions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_rule_conditions_rule_id"), ["rule_id"], unique=False
        )

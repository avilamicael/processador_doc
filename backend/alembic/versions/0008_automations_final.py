"""modelo final de automações: dropa pipeline (0007) + cria automations/conditions/actions

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-18 00:00:00.000000

MODELO FINAL aprovado da Fase 6 (D-23..D-26). Substitui o modelo de "pipeline de
etapas com filtros por etapa + gates" (`automation_pipelines`/`pipeline_steps`/
`step_filters`, 0007) por:

    `automations` 1:N `automation_conditions`
    `automations` 1:N `automation_actions`

Cada automação = CONDIÇÕES (nível da automação, combinadas por E) → AÇÕES ordenadas
(rename/move). A pasta de origem vira uma CONDIÇÃO; os gates identify_file/
identify_type deixam de existir como etapas (viram condições extension/template).

As tabelas de pipeline da 0007 **não têm dados em prod** (CONTEXT autoriza
redesenhar — sem dados), por isso esta migração faz DROP das tabelas de pipeline e
CREATE das tabelas do modelo final. O `downgrade` recria a forma EXATA da 0007
(reversibilidade do histórico).

CAVEAT — esta migração SÓ dropa/cria tabelas de automação. NÃO faz
`batch_alter_table('documents')` NEM `batch_alter_table('audit_log')`. Logo:
- o trigger `trg_documents_updated_at` (0002) permanece intacto;
- as 5 colunas write-ahead de `audit_log` (status/source_path/dest_path/run_id/
  content_hash) — base de AUT-04/AUT-05 — permanecem (independem do modelo).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_pipeline_tables() -> None:
    """DROP das tabelas de pipeline da 0007 (filhas antes das pais)."""
    with op.batch_alter_table("step_filters", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_step_filters_step_id"))
    op.drop_table("step_filters")

    with op.batch_alter_table("pipeline_steps", schema=None) as batch_op:
        batch_op.drop_index("ix_pipeline_steps_pipeline_position")
        batch_op.drop_index(batch_op.f("ix_pipeline_steps_position"))
        batch_op.drop_index(batch_op.f("ix_pipeline_steps_pipeline_id"))
    op.drop_table("pipeline_steps")

    op.drop_table("automation_pipelines")


def _create_pipeline_tables() -> None:
    """CREATE das tabelas de pipeline da 0007 (reversibilidade do histórico)."""
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
        batch_op.create_index(
            batch_op.f("ix_pipeline_steps_pipeline_id"), ["pipeline_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_pipeline_steps_position"), ["position"], unique=False
        )
        batch_op.create_index(
            "ix_pipeline_steps_pipeline_position",
            ["pipeline_id", "position"],
            unique=False,
        )

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


def _create_automation_tables() -> None:
    """CREATE do modelo final: automations + conditions + actions (D-23..D-24)."""
    # Tabela pai: automations (D-23).
    op.create_table(
        "automations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
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
    with op.batch_alter_table("automations", schema=None) as batch_op:
        # Ordem D-25 (indexada para ordenar/reordenar na UI).
        batch_op.create_index(
            batch_op.f("ix_automations_position"), ["position"], unique=False
        )

    # Condições (D-24): FK→automations ondelete CASCADE.
    op.create_table(
        "automation_conditions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_id", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["automation_id"], ["automations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("automation_conditions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_automation_conditions_automation_id"),
            ["automation_id"],
            unique=False,
        )

    # Ações ordenadas (D-24): FK→automations ondelete CASCADE.
    op.create_table(
        "automation_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automation_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["automation_id"], ["automations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("automation_actions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_automation_actions_automation_id"),
            ["automation_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_automation_actions_position"), ["position"], unique=False
        )


def _drop_automation_tables() -> None:
    """DROP do modelo final (filhas antes da pai)."""
    with op.batch_alter_table("automation_actions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_automation_actions_position"))
        batch_op.drop_index(batch_op.f("ix_automation_actions_automation_id"))
    op.drop_table("automation_actions")

    with op.batch_alter_table("automation_conditions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_automation_conditions_automation_id"))
    op.drop_table("automation_conditions")

    with op.batch_alter_table("automations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_automations_position"))
    op.drop_table("automations")


def upgrade() -> None:
    """Upgrade — dropa pipeline (0007) e cria o modelo final (D-23..D-24)."""
    _drop_pipeline_tables()
    _create_automation_tables()


def downgrade() -> None:
    """Downgrade — dropa o modelo final e recria a forma EXATA da 0007."""
    _drop_automation_tables()
    _create_pipeline_tables()

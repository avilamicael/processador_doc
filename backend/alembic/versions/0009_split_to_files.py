"""split-to-files: coluna opt-in split_to_files em watched_folders (forward-only)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-23 00:00:00.000000

Adiciona a ÚNICA coluna nova do opt-in de separação física (QUICK-SPLIT-TO-FILES):
- `watched_folders.split_to_files` (Boolean, NOT NULL, server_default '0'): quando
  LIGADO, ao ingerir um PDF multipágina o original é SEPARADO em arquivos físicos
  na própria pasta (substituindo o original) ANTES da IA. Default 0 (DESLIGADO)
  preserva exatamente o comportamento atual de todas as pastas já cadastradas.

CAVEAT do trigger trg_documents_updated_at (criado na 0002) NÃO se aplica: esta
migração SÓ faz `batch_alter_table('watched_folders')` para adicionar 1 coluna e
**NÃO toca `documents`** (nenhum batch recreate de documents) — logo o trigger
`trg_documents_updated_at` permanece intacto (mesma garantia das 0003/0004/0005).
`documents` aparece neste arquivo SOMENTE neste comentário, nunca em
batch_alter_table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade — adiciona a coluna opt-in `split_to_files` (default OFF)."""
    with op.batch_alter_table("watched_folders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "split_to_files",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    """Downgrade — dropa a coluna `split_to_files`."""
    with op.batch_alter_table("watched_folders", schema=None) as batch_op:
        batch_op.drop_column("split_to_files")

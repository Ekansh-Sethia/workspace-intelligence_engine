"""Add chunk_type column to chunks table

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-08-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add chunk_type column with server_default="text" so all existing rows
    # are backward-compatible without needing to re-index.
    op.add_column(
        'chunks',
        sa.Column(
            'chunk_type',
            sa.String(),
            nullable=False,
            server_default='text',
        )
    )


def downgrade() -> None:
    op.drop_column('chunks', 'chunk_type')

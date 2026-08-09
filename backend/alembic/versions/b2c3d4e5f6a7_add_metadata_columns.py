"""Phase 8: Add metadata columns to workspaces and files

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("workspaces", sa.Column("keywords", JSONB(), nullable=True))
    op.add_column("workspaces", sa.Column("topics", JSONB(), nullable=True))
    op.add_column("workspaces", sa.Column("document_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("workspaces", sa.Column("image_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("workspaces", sa.Column("total_chunk_count", sa.Integer(), server_default="0", nullable=False))

    op.add_column("files", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("files", sa.Column("keywords", JSONB(), nullable=True))
    op.add_column("files", sa.Column("topics", JSONB(), nullable=True))
    op.add_column("files", sa.Column("page_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("workspaces", "summary")
    op.drop_column("workspaces", "keywords")
    op.drop_column("workspaces", "topics")
    op.drop_column("workspaces", "document_count")
    op.drop_column("workspaces", "image_count")
    op.drop_column("workspaces", "total_chunk_count")

    op.drop_column("files", "summary")
    op.drop_column("files", "keywords")
    op.drop_column("files", "topics")
    op.drop_column("files", "page_count")

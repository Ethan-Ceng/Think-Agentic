"""add managed file metadata and storage routing

Revision ID: 20260714_0001
Revises: 20260709_0001
Create Date: 2026-07-14 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260714_0001"
down_revision: Union[str, Sequence[str], None] = "20260709_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("parent_id", sa.String(length=255), nullable=True))
    op.add_column("files", sa.Column("entry_type", sa.String(length=32), server_default=sa.text("'file'"), nullable=False))
    op.add_column("files", sa.Column("storage_provider", sa.String(length=64), server_default=sa.text("'local'"), nullable=False))
    op.add_column("files", sa.Column("storage_config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("files", sa.Column("source_type", sa.String(length=64), server_default=sa.text("'user_upload'"), nullable=False))
    op.add_column("files", sa.Column("status", sa.String(length=32), server_default=sa.text("'available'"), nullable=False))
    op.add_column("files", sa.Column("sha256", sa.String(length=64), server_default=sa.text("''"), nullable=False))
    op.add_column("files", sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("files", sa.Column("origin_session_id", sa.String(length=255), nullable=True))
    op.add_column("files", sa.Column("origin_run_id", sa.String(length=255), nullable=True))
    op.add_column("files", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("files", sa.Column("purge_after", sa.DateTime(), nullable=True))
    op.execute("UPDATE files SET storage_provider = CASE WHEN filepath <> '' THEN 'local' ELSE 'qcloud_cos' END")
    op.create_index("ix_files_user_parent_status", "files", ["user_id", "parent_id", "status"])
    op.create_index("ix_files_user_source", "files", ["user_id", "source_type"])
    op.create_index("ix_files_purge_after", "files", ["purge_after"])


def downgrade() -> None:
    op.drop_index("ix_files_purge_after", table_name="files")
    op.drop_index("ix_files_user_source", table_name="files")
    op.drop_index("ix_files_user_parent_status", table_name="files")
    for column in ("purge_after", "deleted_at", "origin_run_id", "origin_session_id", "metadata", "sha256", "status", "source_type", "storage_config", "storage_provider", "entry_type", "parent_id"):
        op.drop_column("files", column)

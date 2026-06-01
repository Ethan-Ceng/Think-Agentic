"""agent target refs

Revision ID: 20260514_0003
Revises: 20260514_0002
Create Date: 2026-05-14 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260514_0003"
down_revision: str | None = "20260514_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("target_ref_type", sa.String(length=64), server_default="", nullable=False))
    op.add_column("agents", sa.Column("target_ref_id", sa.String(length=128), server_default="", nullable=False))
    op.alter_column("agents", "target_ref_type", server_default=None)
    op.alter_column("agents", "target_ref_id", server_default=None)


def downgrade() -> None:
    op.drop_column("agents", "target_ref_id")
    op.drop_column("agents", "target_ref_type")

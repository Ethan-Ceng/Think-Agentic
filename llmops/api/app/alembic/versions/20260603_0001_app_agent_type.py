"""app agent type

Revision ID: 20260603_0001
Revises: 20260601_0002
Create Date: 2026-06-03 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260603_0001"
down_revision: str | None = "20260601_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app",
        sa.Column(
            "agent_type",
            sa.String(length=32),
            server_default=sa.text("'worker'::character varying"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("app", "agent_type")

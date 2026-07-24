"""add session organization metadata

Revision ID: 20260724_0002
Revises: 20260724_0001
Create Date: 2026-07-24 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0002"
down_revision: Union[str, Sequence[str], None] = "20260724_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "title_is_manual",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "is_pinned",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_sessions_user_archive_pin_latest",
        "sessions",
        ["user_id", "archived_at", "is_pinned", "latest_message_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_user_archive_pin_latest", table_name="sessions")
    op.drop_column("sessions", "archived_at")
    op.drop_column("sessions", "is_pinned")
    op.drop_column("sessions", "title_is_manual")

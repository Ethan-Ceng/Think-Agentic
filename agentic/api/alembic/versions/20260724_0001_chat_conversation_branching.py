"""add immutable conversation branch lineage and context seed

Revision ID: 20260724_0001
Revises: 20260721_0001
Create Date: 2026-07-24 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260724_0001"
down_revision: Union[str, Sequence[str], None] = "20260721_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("source_session_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("forked_from_event_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("branch_operation", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("branch_request_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "context_seed",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_sessions_source_session_id",
        "sessions",
        ["source_session_id"],
        unique=False,
    )
    op.create_index(
        "ux_sessions_branch_request_id",
        "sessions",
        ["branch_request_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_sessions_branch_request_id", table_name="sessions")
    op.drop_index("ix_sessions_source_session_id", table_name="sessions")
    op.drop_column("sessions", "context_seed")
    op.drop_column("sessions", "branch_request_id")
    op.drop_column("sessions", "branch_operation")
    op.drop_column("sessions", "forked_from_event_id")
    op.drop_column("sessions", "source_session_id")

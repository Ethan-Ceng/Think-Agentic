"""add trace execution cursor and safe projection fields

Revision ID: 20260819_0001
Revises: 20260818_0001
Create Date: 2026-08-19 19:35:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0001"
down_revision: Union[str, Sequence[str], None] = "20260818_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE trace_events_ingest_seq_seq")
    op.add_column(
        "trace_events",
        sa.Column(
            "ingest_seq",
            sa.BigInteger(),
            server_default=sa.text("nextval('trace_events_ingest_seq_seq'::regclass)"),
            nullable=True,
        ),
    )
    op.add_column(
        "trace_events",
        sa.Column("schema_version", sa.SmallInteger(), server_default=sa.text("2"), nullable=False),
    )
    op.add_column(
        "trace_events",
        sa.Column("node_id", sa.String(length=255), server_default=sa.text("''"), nullable=False),
    )
    op.add_column(
        "trace_events",
        sa.Column("parent_node_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "trace_events",
        sa.Column("visibility", sa.String(length=32), server_default=sa.text("'user'"), nullable=False),
    )
    op.add_column(
        "trace_events",
        sa.Column("summary", sa.Text(), server_default=sa.text("''"), nullable=False),
    )

    op.execute(
        """
        WITH ordered AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS seq
            FROM trace_events
        )
        UPDATE trace_events AS target
        SET ingest_seq = ordered.seq,
            schema_version = 1
        FROM ordered
        WHERE target.id = ordered.id
        """
    )
    op.execute(
        """
        SELECT setval(
            'trace_events_ingest_seq_seq',
            COALESCE((SELECT MAX(ingest_seq) FROM trace_events), 0) + 1,
            false
        )
        """
    )
    op.alter_column("trace_events", "ingest_seq", nullable=False)
    op.execute(
        "ALTER SEQUENCE trace_events_ingest_seq_seq OWNED BY trace_events.ingest_seq"
    )
    op.create_index(
        "ix_trace_events_run_ingest_seq",
        "trace_events",
        ["run_id", "ingest_seq"],
        unique=False,
    )
    op.create_index(
        "ux_trace_events_ingest_seq",
        "trace_events",
        ["ingest_seq"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_trace_events_ingest_seq", table_name="trace_events")
    op.drop_index("ix_trace_events_run_ingest_seq", table_name="trace_events")
    op.drop_column("trace_events", "summary")
    op.drop_column("trace_events", "visibility")
    op.drop_column("trace_events", "parent_node_id")
    op.drop_column("trace_events", "node_id")
    op.drop_column("trace_events", "schema_version")
    op.drop_column("trace_events", "ingest_seq")


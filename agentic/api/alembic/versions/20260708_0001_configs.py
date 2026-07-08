"""add user scoped configs

Revision ID: 20260708_0001
Revises: 20260707_0001
Create Date: 2026-07-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260708_0001"
down_revision: Union[str, Sequence[str], None] = "20260707_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "configs",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("config_type", sa.String(length=64), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(length=64),
            server_default=sa.text("'config_v1'::character varying"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_configs_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_configs_user_id_users", ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "config_type", name="ux_configs_user_id_config_type"),
    )
    op.create_index("ix_configs_user_id", "configs", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_configs_user_id", table_name="configs")
    op.drop_table("configs")

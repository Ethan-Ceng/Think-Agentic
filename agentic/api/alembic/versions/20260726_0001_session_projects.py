"""add single-level Session projects

Revision ID: 20260726_0001
Revises: 20260724_0002
Create Date: 2026-07-26 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0001"
down_revision: Union[str, Sequence[str], None] = "20260724_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP(0)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP(0)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_projects_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects_id"),
    )
    op.create_index(
        "ix_projects_user_created_at",
        "projects",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ux_projects_user_lower_name",
        "projects",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )
    op.add_column(
        "sessions",
        sa.Column("project_id", sa.String(length=255), nullable=True),
    )
    op.create_foreign_key(
        "fk_sessions_project_id_projects",
        "sessions",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_sessions_user_project_id",
        "sessions",
        ["user_id", "project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_user_project_id", table_name="sessions")
    op.drop_constraint(
        "fk_sessions_project_id_projects",
        "sessions",
        type_="foreignkey",
    )
    op.drop_column("sessions", "project_id")
    op.drop_index("ux_projects_user_lower_name", table_name="projects")
    op.drop_index("ix_projects_user_created_at", table_name="projects")
    op.drop_table("projects")

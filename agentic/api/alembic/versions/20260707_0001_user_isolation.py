"""add users and user isolation

Revision ID: 20260707_0001
Revises: 0e0d242438bc
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260707_0001"
down_revision: Union[str, Sequence[str], None] = "0e0d242438bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # This is an intentional development-stage destructive migration. Existing
    # sessions/files had no owner and cannot be safely assigned to a real user.
    op.execute("DELETE FROM sessions")
    op.execute("DELETE FROM files")

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("avatar", sa.String(length=512), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column(
            "password_hash",
            sa.String(length=255),
            server_default=sa.text("''::character varying"),
            nullable=False,
        ),
        sa.Column(
            "password_salt",
            sa.String(length=255),
            server_default=sa.text("''::character varying"),
            nullable=False,
        ),
        sa.Column(
            "password_algorithm",
            sa.String(length=64),
            server_default=sa.text("'pbkdf2_sha256'::character varying"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'::character varying"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users_id"),
    )
    op.create_index("ux_users_email", "users", ["email"], unique=True)

    op.add_column("sessions", sa.Column("user_id", sa.String(length=255), nullable=False))
    op.create_foreign_key(
        "fk_sessions_user_id_users",
        "sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_sessions_user_latest_message_at", "sessions", ["user_id", "latest_message_at"])
    op.alter_column(
        "sessions",
        "status",
        existing_type=sa.String(length=255),
        server_default=sa.text("'pending'::character varying"),
        existing_nullable=False,
    )

    op.add_column("files", sa.Column("user_id", sa.String(length=255), nullable=False))
    op.create_foreign_key(
        "fk_files_user_id_users",
        "files",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_files_user_created_at", "files", ["user_id", "created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_files_user_created_at", table_name="files")
    op.drop_constraint("fk_files_user_id_users", "files", type_="foreignkey")
    op.drop_column("files", "user_id")

    op.drop_index("ix_sessions_user_latest_message_at", table_name="sessions")
    op.drop_constraint("fk_sessions_user_id_users", "sessions", type_="foreignkey")
    op.drop_column("sessions", "user_id")
    op.alter_column(
        "sessions",
        "status",
        existing_type=sa.String(length=255),
        server_default=sa.text("''::character varying"),
        existing_nullable=False,
    )

    op.drop_index("ux_users_email", table_name="users")
    op.drop_table("users")

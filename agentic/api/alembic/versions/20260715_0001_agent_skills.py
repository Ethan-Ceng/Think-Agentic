"""add agent skills metadata versions installations and run usage

Revision ID: 20260715_0001
Revises: 20260714_0001
Create Date: 2026-07-15 18:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260715_0001"
down_revision: Union[str, Sequence[str], None] = "20260714_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'active'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("auto_invoke", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("current_version_id", sa.String(length=255), nullable=True),
        sa.Column("forked_from_skill_id", sa.String(length=255), nullable=True),
        sa.Column("forked_from_version_id", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.CheckConstraint(
            "(scope = 'personal' AND owner_user_id IS NOT NULL) OR "
            "(scope = 'marketplace' AND owner_user_id IS NULL)",
            name="ck_skills_scope_owner",
        ),
        sa.ForeignKeyConstraint(
            ["forked_from_skill_id"],
            ["skills.id"],
            name="fk_skills_forked_from_skill_id_skills",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_skills_owner_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_skills_id"),
    )
    op.create_index("ix_skills_owner_status", "skills", ["owner_user_id", "status"])
    op.create_index("ix_skills_scope_status", "skills", ["scope", "status"])
    op.create_index(
        "ux_skills_personal_owner_name_active",
        "skills",
        ["owner_user_id", "name"],
        unique=True,
        postgresql_where=sa.text("scope = 'personal' AND status <> 'archived'"),
    )
    op.create_index(
        "ux_skills_marketplace_name_active",
        "skills",
        ["name"],
        unique=True,
        postgresql_where=sa.text("scope = 'marketplace' AND status <> 'archived'"),
    )

    op.create_table(
        "skill_versions",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("skill_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("storage_provider", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("storage_config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("package_sha256", sa.String(length=64), nullable=False),
        sa.Column("package_size", sa.Integer(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'published'"), nullable=False),
        sa.Column("changelog", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_skill_versions_created_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name="fk_skill_versions_skill_id_skills",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_skill_versions_id"),
        sa.UniqueConstraint("skill_id", "version", name="uq_skill_versions_skill_version"),
    )
    op.create_index("ix_skill_versions_sha256", "skill_versions", ["package_sha256"])
    op.create_index("ix_skill_versions_skill_created", "skill_versions", ["skill_id", "created_at"])
    op.create_foreign_key(
        "fk_skills_current_version_id_skill_versions",
        "skills",
        "skill_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_skills_forked_from_version_id_skill_versions",
        "skills",
        "skill_versions",
        ["forked_from_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "skill_installations",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("skill_id", sa.String(length=255), nullable=False),
        sa.Column("pinned_version_id", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("auto_invoke", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("auto_update", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("installed_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.ForeignKeyConstraint(
            ["pinned_version_id"],
            ["skill_versions.id"],
            name="fk_skill_installations_pinned_version_id_skill_versions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name="fk_skill_installations_skill_id_skills",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_skill_installations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_skill_installations_id"),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_skill_installations_user_skill"),
    )
    op.create_index(
        "ix_skill_installations_user_enabled",
        "skill_installations",
        ["user_id", "enabled"],
    )

    op.create_table(
        "run_skills",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("skill_id", sa.String(length=255), nullable=True),
        sa.Column("skill_version_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("selection_mode", sa.String(length=32), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("sandbox_path", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_run_skills_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name="fk_run_skills_skill_id_skills",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"],
            ["skill_versions.id"],
            name="fk_run_skills_skill_version_id_skill_versions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_skills_id"),
    )
    op.create_index("ix_run_skills_run_created", "run_skills", ["run_id", "created_at"])
    op.create_index("ix_run_skills_skill_version", "run_skills", ["skill_id", "skill_version_id"])


def downgrade() -> None:
    op.drop_index("ix_run_skills_skill_version", table_name="run_skills")
    op.drop_index("ix_run_skills_run_created", table_name="run_skills")
    op.drop_table("run_skills")
    op.drop_index("ix_skill_installations_user_enabled", table_name="skill_installations")
    op.drop_table("skill_installations")
    op.drop_constraint(
        "fk_skills_forked_from_version_id_skill_versions",
        "skills",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_skills_current_version_id_skill_versions",
        "skills",
        type_="foreignkey",
    )
    op.drop_index("ix_skill_versions_skill_created", table_name="skill_versions")
    op.drop_index("ix_skill_versions_sha256", table_name="skill_versions")
    op.drop_table("skill_versions")
    op.drop_index("ux_skills_marketplace_name_active", table_name="skills")
    op.drop_index("ux_skills_personal_owner_name_active", table_name="skills")
    op.drop_index("ix_skills_scope_status", table_name="skills")
    op.drop_index("ix_skills_owner_status", table_name="skills")
    op.drop_table("skills")

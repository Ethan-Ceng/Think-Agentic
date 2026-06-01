"""drop experimental tenant and rbac tables

Revision ID: 20260601_0001
Revises: 20260514_0003
Create Date: 2026-06-01 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260601_0001"
down_revision: str | None = "20260514_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.drop_table("member_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("tenant_members")
    op.drop_table("permissions")
    op.drop_table("tenants")


def downgrade() -> None:
    op.create_table(
        "tenants",
        uuid_pk(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )

    op.create_table(
        "permissions",
        uuid_pk(),
        sa.Column("code", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resource", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"], unique=True)

    op.create_table(
        "tenant_members",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_tenant_members_tenant_id_tenants")),
        sa.ForeignKeyConstraint(["user_id"], ["account.id"], name=op.f("fk_tenant_members_user_id_account")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_members")),
    )
    op.create_index("ix_tenant_members_tenant_user", "tenant_members", ["tenant_id", "user_id"], unique=False)

    op.create_table(
        "roles",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_roles_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
    )
    op.create_index("ix_roles_tenant_code", "roles", ["tenant_id", "code"], unique=True)

    op.create_table(
        "role_permissions",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_role_permissions_permission_id_permissions"),
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_role_permissions_role_id_roles")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_role_permissions_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_permissions")),
    )
    op.create_index(
        "ix_role_permissions_role_permission",
        "role_permissions",
        ["role_id", "permission_id"],
        unique=True,
    )

    op.create_table(
        "member_roles",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["tenant_members.id"],
            name=op.f("fk_member_roles_member_id_tenant_members"),
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_member_roles_role_id_roles")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_member_roles_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_roles")),
    )
    op.create_index("ix_member_roles_member_role", "member_roles", ["member_id", "role_id"], unique=True)

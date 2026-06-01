"""initial identity agent platform tables

Revision ID: 20260513_0001
Revises: b017b44df199
Create Date: 2026-05-13 12:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260513_0001"
down_revision: str | None = "b017b44df199"
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
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], name=op.f("fk_role_permissions_permission_id_permissions")),
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
        sa.ForeignKeyConstraint(["member_id"], ["tenant_members.id"], name=op.f("fk_member_roles_member_id_tenant_members")),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name=op.f("fk_member_roles_role_id_roles")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_member_roles_tenant_id_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_roles")),
    )
    op.create_index("ix_member_roles_member_role", "member_roles", ["member_id", "role_id"], unique=True)

    op.create_table(
        "agents",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("icon", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("runtime_type", sa.String(length=32), nullable=False),
        sa.Column("product_category", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("draft_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("visibility_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
    )
    op.create_index("ix_agents_tenant_runtime_status", "agents", ["tenant_id", "runtime_type", "status"], unique=False)

    op.create_table(
        "agent_versions",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_type", sa.String(length=32), nullable=False),
        sa.Column("model_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prompt_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("router_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("worker_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("capability_bindings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], name=op.f("fk_agent_versions_agent_id_agents")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_versions")),
    )
    op.create_index("ix_agent_versions_agent_config", "agent_versions", ["agent_id", "config_type", "version"], unique=False)

    op.create_table(
        "agent_bindings",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("router_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["router_agent_id"], ["agents.id"], name=op.f("fk_agent_bindings_router_agent_id_agents")),
        sa.ForeignKeyConstraint(["worker_agent_id"], ["agents.id"], name=op.f("fk_agent_bindings_worker_agent_id_agents")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_bindings")),
    )
    op.create_index("ix_agent_bindings_router_worker", "agent_bindings", ["router_agent_id", "worker_agent_id"], unique=False)

    op.create_table(
        "capabilities",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("target_ref_type", sa.String(length=64), nullable=False),
        sa.Column("target_ref_id", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("permission", sa.String(length=255), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("side_effect", sa.String(length=32), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("idempotency_required", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("retry_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_scope_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("audit_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capabilities")),
    )
    op.create_index("ix_capabilities_tenant_type_enabled", "capabilities", ["tenant_id", "type", "enabled"], unique=False)

    op.create_table(
        "agent_capability_bindings",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(length=128), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_agent_capability_bindings_agent_version_id_agent_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["capability_id"],
            ["capabilities.id"],
            name=op.f("fk_agent_capability_bindings_capability_id_capabilities"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_capability_bindings")),
    )
    op.create_index(
        "ix_agent_capability_bindings_agent_capability",
        "agent_capability_bindings",
        ["agent_version_id", "capability_id"],
        unique=False,
    )

    op.create_table(
        "agent_tasks",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("router_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("user_input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("final_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["router_agent_id"], ["agents.id"], name=op.f("fk_agent_tasks_router_agent_id_agents")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_tasks")),
    )
    op.create_index("ix_agent_tasks_tenant_status_created", "agent_tasks", ["tenant_id", "status", "created_at"], unique=False)

    op.create_table(
        "agent_plans",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("router_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["router_agent_id"], ["agents.id"], name=op.f("fk_agent_plans_router_agent_id_agents")),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], name=op.f("fk_agent_plans_task_id_agent_tasks")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_plans")),
    )

    op.create_table(
        "agent_steps",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_key", sa.String(length=128), nullable=False),
        sa.Column("worker_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependencies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_plans.id"], name=op.f("fk_agent_steps_plan_id_agent_plans")),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], name=op.f("fk_agent_steps_task_id_agent_tasks")),
        sa.ForeignKeyConstraint(["worker_agent_id"], ["agents.id"], name=op.f("fk_agent_steps_worker_agent_id_agents")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_steps")),
    )
    op.create_index("ix_agent_steps_task_status", "agent_steps", ["task_id", "status"], unique=False)

    op.create_table(
        "worker_calls",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invocation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency", sa.Numeric(precision=12, scale=3), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], name=op.f("fk_worker_calls_step_id_agent_steps")),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], name=op.f("fk_worker_calls_task_id_agent_tasks")),
        sa.ForeignKeyConstraint(["worker_agent_id"], ["agents.id"], name=op.f("fk_worker_calls_worker_agent_id_agents")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_calls")),
    )

    op.create_table(
        "capability_calls",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capability_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("latency", sa.Numeric(precision=12, scale=3), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["capability_id"], ["capabilities.id"], name=op.f("fk_capability_calls_capability_id_capabilities")),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], name=op.f("fk_capability_calls_step_id_agent_steps")),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], name=op.f("fk_capability_calls_task_id_agent_tasks")),
        sa.ForeignKeyConstraint(["worker_call_id"], ["worker_calls.id"], name=op.f("fk_capability_calls_worker_call_id_worker_calls")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capability_calls")),
    )


def downgrade() -> None:
    op.drop_table("capability_calls")
    op.drop_table("worker_calls")
    op.drop_index("ix_agent_steps_task_status", table_name="agent_steps")
    op.drop_table("agent_steps")
    op.drop_table("agent_plans")
    op.drop_index("ix_agent_tasks_tenant_status_created", table_name="agent_tasks")
    op.drop_table("agent_tasks")
    op.drop_index("ix_agent_capability_bindings_agent_capability", table_name="agent_capability_bindings")
    op.drop_table("agent_capability_bindings")
    op.drop_index("ix_capabilities_tenant_type_enabled", table_name="capabilities")
    op.drop_table("capabilities")
    op.drop_index("ix_agent_bindings_router_worker", table_name="agent_bindings")
    op.drop_table("agent_bindings")
    op.drop_index("ix_agent_versions_agent_config", table_name="agent_versions")
    op.drop_table("agent_versions")
    op.drop_index("ix_agents_tenant_runtime_status", table_name="agents")
    op.drop_table("agents")
    op.drop_index("ix_member_roles_member_role", table_name="member_roles")
    op.drop_table("member_roles")
    op.drop_index("ix_role_permissions_role_permission", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_roles_tenant_code", table_name="roles")
    op.drop_table("roles")
    op.drop_index("ix_tenant_members_tenant_user", table_name="tenant_members")
    op.drop_table("tenant_members")
    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")
    op.drop_table("tenants")

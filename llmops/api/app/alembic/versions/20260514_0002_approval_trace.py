"""approval and trace governance tables

Revision ID: 20260514_0002
Revises: 20260513_0001
Create Date: 2026-05-14 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260514_0002"
down_revision: str | None = "20260513_0001"
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
        "approval_requests",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capability_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("proposed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("approver_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_token_hash", sa.String(length=255), nullable=False),
        sa.Column("decision_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["capability_call_id"], ["capability_calls.id"], name=op.f("fk_approval_requests_capability_call_id_capability_calls")),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], name=op.f("fk_approval_requests_step_id_agent_steps")),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], name=op.f("fk_approval_requests_task_id_agent_tasks")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_requests")),
    )
    op.create_index(
        "ix_approval_requests_tenant_status_created",
        "approval_requests",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "trace_events",
        uuid_pk(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("worker_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("capability_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency", sa.Numeric(precision=12, scale=3), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"], name=op.f("fk_trace_events_approval_id_approval_requests")),
        sa.ForeignKeyConstraint(["capability_call_id"], ["capability_calls.id"], name=op.f("fk_trace_events_capability_call_id_capability_calls")),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_plans.id"], name=op.f("fk_trace_events_plan_id_agent_plans")),
        sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"], name=op.f("fk_trace_events_step_id_agent_steps")),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], name=op.f("fk_trace_events_task_id_agent_tasks")),
        sa.ForeignKeyConstraint(["worker_call_id"], ["worker_calls.id"], name=op.f("fk_trace_events_worker_call_id_worker_calls")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trace_events")),
    )
    op.create_index(
        "ix_trace_events_tenant_trace_created",
        "trace_events",
        ["tenant_id", "trace_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_trace_events_task_created", "trace_events", ["task_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trace_events_task_created", table_name="trace_events")
    op.drop_index("ix_trace_events_tenant_trace_created", table_name="trace_events")
    op.drop_table("trace_events")
    op.drop_index("ix_approval_requests_tenant_status_created", table_name="approval_requests")
    op.drop_table("approval_requests")

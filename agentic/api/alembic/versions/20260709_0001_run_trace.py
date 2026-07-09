"""add run trace tables

Revision ID: 20260709_0001
Revises: 20260708_0001
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260709_0001"
down_revision: Union[str, Sequence[str], None] = "20260708_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("trace_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("input_event_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), server_default=sa.text("'pending'::character varying"), nullable=False),
        sa.Column("input_summary", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("final_summary", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("tool_config_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("agent_config_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("llm_config_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_agent_runs_session_id_sessions", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_agent_runs_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs_id"),
    )
    op.create_index("ix_agent_runs_user_created_at", "agent_runs", ["user_id", "created_at"])
    op.create_index("ix_agent_runs_session_created_at", "agent_runs", ["session_id", "created_at"])
    op.create_index("ix_agent_runs_trace_id", "agent_runs", ["trace_id"])
    op.create_index("ix_agent_runs_task_id", "agent_runs", ["task_id"])

    op.create_table(
        "run_steps",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("step_id", sa.String(length=255), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("description", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("status", sa.String(length=64), server_default=sa.text("'started'::character varying"), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("result_summary", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], name="fk_run_steps_run_id_agent_runs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_run_steps_session_id_sessions", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_run_steps_id"),
    )
    op.create_index("ix_run_steps_run_created_at", "run_steps", ["run_id", "created_at"])
    op.create_index("ix_run_steps_session_created_at", "run_steps", ["session_id", "created_at"])
    op.create_index("ix_run_steps_run_step_id", "run_steps", ["run_id", "step_id"])

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("run_step_id", sa.String(length=255), nullable=True),
        sa.Column("step_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("tool_call_id", sa.String(length=255), nullable=False),
        sa.Column("tool_id", sa.String(length=255), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("function_name", sa.String(length=255), nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=True),
        sa.Column("registration_id", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("executor_type", sa.String(length=64), nullable=True),
        sa.Column("risk_level", sa.String(length=64), nullable=True),
        sa.Column("enabled_effective", sa.Boolean(), nullable=True),
        sa.Column("requires_sandbox", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("requires_browser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("requires_credentials", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=64), server_default=sa.text("'calling'::character varying"), nullable=False),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("arguments_preview", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("arguments_hash", sa.String(length=128), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("result_preview", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], name="fk_tool_calls_run_id_agent_runs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_step_id"], ["run_steps.id"], name="fk_tool_calls_run_step_id_run_steps", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_tool_calls_session_id_sessions", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_tool_calls_id"),
    )
    op.create_index("ix_tool_calls_run_created_at", "tool_calls", ["run_id", "created_at"])
    op.create_index("ix_tool_calls_session_created_at", "tool_calls", ["session_id", "created_at"])
    op.create_index("ix_tool_calls_run_tool_call_id", "tool_calls", ["run_id", "tool_call_id"])
    op.create_index("ix_tool_calls_tool_id", "tool_calls", ["tool_id"])

    op.create_table(
        "model_calls",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("run_step_id", sa.String(length=255), nullable=True),
        sa.Column("step_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("base_url", sa.Text(), server_default=sa.text("''::text"), nullable=False),
        sa.Column("model_name", sa.String(length=255), server_default=sa.text("''::character varying"), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("tool_schema_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("message_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tool_choice", sa.String(length=255), nullable=True),
        sa.Column("response_format", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(length=64), server_default=sa.text("'started'::character varying"), nullable=False),
        sa.Column("finish_reason", sa.String(length=255), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("request_preview", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("response_preview", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], name="fk_model_calls_run_id_agent_runs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_step_id"], ["run_steps.id"], name="fk_model_calls_run_step_id_run_steps", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_model_calls_session_id_sessions", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_model_calls_id"),
    )
    op.create_index("ix_model_calls_run_created_at", "model_calls", ["run_id", "created_at"])
    op.create_index("ix_model_calls_session_created_at", "model_calls", ["session_id", "created_at"])

    op.create_table(
        "trace_events",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("trace_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), server_default=sa.text("'agentic'::character varying"), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP(0)"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], name="fk_trace_events_run_id_agent_runs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_trace_events_session_id_sessions", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_trace_events_id"),
    )
    op.create_index("ix_trace_events_trace_created_at", "trace_events", ["trace_id", "created_at"])
    op.create_index("ix_trace_events_run_created_at", "trace_events", ["run_id", "created_at"])
    op.create_index("ix_trace_events_session_created_at", "trace_events", ["session_id", "created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_trace_events_session_created_at", table_name="trace_events")
    op.drop_index("ix_trace_events_run_created_at", table_name="trace_events")
    op.drop_index("ix_trace_events_trace_created_at", table_name="trace_events")
    op.drop_table("trace_events")

    op.drop_index("ix_model_calls_session_created_at", table_name="model_calls")
    op.drop_index("ix_model_calls_run_created_at", table_name="model_calls")
    op.drop_table("model_calls")

    op.drop_index("ix_tool_calls_tool_id", table_name="tool_calls")
    op.drop_index("ix_tool_calls_run_tool_call_id", table_name="tool_calls")
    op.drop_index("ix_tool_calls_session_created_at", table_name="tool_calls")
    op.drop_index("ix_tool_calls_run_created_at", table_name="tool_calls")
    op.drop_table("tool_calls")

    op.drop_index("ix_run_steps_run_step_id", table_name="run_steps")
    op.drop_index("ix_run_steps_session_created_at", table_name="run_steps")
    op.drop_index("ix_run_steps_run_created_at", table_name="run_steps")
    op.drop_table("run_steps")

    op.drop_index("ix_agent_runs_task_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_trace_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_session_created_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_created_at", table_name="agent_runs")
    op.drop_table("agent_runs")

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run and trace ORM models."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


class AgentRunModel(Base):
    """A single user-triggered Agent execution run."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_agent_runs_id"),
        ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_agent_runs_user_id_users", ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_agent_runs_session_id_sessions",
            ondelete="CASCADE",
        ),
        Index("ix_agent_runs_user_created_at", "user_id", "created_at"),
        Index("ix_agent_runs_session_created_at", "session_id", "created_at"),
        Index("ix_agent_runs_trace_id", "trace_id"),
        Index("ix_agent_runs_task_id", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True, default=_new_id)
    trace_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    input_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'pending'::character varying"),
    )
    input_summary: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    final_summary: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_config_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    agent_config_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    llm_config_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )


class RunStepModel(Base):
    """Projected step state for a run."""

    __tablename__ = "run_steps"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_run_steps_id"),
        ForeignKeyConstraint(["run_id"], ["agent_runs.id"], name="fk_run_steps_run_id_agent_runs", ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_run_steps_session_id_sessions",
            ondelete="CASCADE",
        ),
        Index("ix_run_steps_run_created_at", "run_id", "created_at"),
        Index("ix_run_steps_session_created_at", "session_id", "created_at"),
        Index("ix_run_steps_run_step_id", "run_id", "step_id"),
    )

    id: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True, default=_new_id)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    step_id: Mapped[str] = mapped_column(String(255), nullable=False)
    step_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'started'::character varying"))
    success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    result_summary: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attachments: Mapped[List[Any]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )


class ToolCallModel(Base):
    """Projected tool call state for a run."""

    __tablename__ = "tool_calls"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_tool_calls_id"),
        ForeignKeyConstraint(["run_id"], ["agent_runs.id"], name="fk_tool_calls_run_id_agent_runs", ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_tool_calls_session_id_sessions",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_step_id"],
            ["run_steps.id"],
            name="fk_tool_calls_run_step_id_run_steps",
            ondelete="SET NULL",
        ),
        Index("ix_tool_calls_run_created_at", "run_id", "created_at"),
        Index("ix_tool_calls_session_created_at", "session_id", "created_at"),
        Index("ix_tool_calls_run_tool_call_id", "run_id", "tool_call_id"),
        Index("ix_tool_calls_tool_id", "tool_id"),
    )

    id: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True, default=_new_id)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    run_step_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    step_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    function_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    registration_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    executor_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    enabled_effective: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    requires_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    requires_browser: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    requires_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'calling'::character varying"))
    arguments: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    arguments_preview: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    arguments_hash: Mapped[str] = mapped_column(String(128), nullable=False, server_default=text("''::character varying"))
    result: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    result_preview: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )


class ModelCallModel(Base):
    """Observed LLM call metadata for a run."""

    __tablename__ = "model_calls"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_model_calls_id"),
        ForeignKeyConstraint(["run_id"], ["agent_runs.id"], name="fk_model_calls_run_id_agent_runs", ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_model_calls_session_id_sessions",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_step_id"],
            ["run_steps.id"],
            name="fk_model_calls_run_step_id_run_steps",
            ondelete="SET NULL",
        ),
        Index("ix_model_calls_run_created_at", "run_id", "created_at"),
        Index("ix_model_calls_session_created_at", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True, default=_new_id)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    run_step_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    step_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    base_url: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tool_schema_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    tool_choice: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    response_format: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'started'::character varying"))
    finish_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    request_preview: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    response_preview: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )


class TraceEventModel(Base):
    """Append-only runtime event projection."""

    __tablename__ = "trace_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_trace_events_id"),
        ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_trace_events_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_trace_events_session_id_sessions",
            ondelete="CASCADE",
        ),
        Index("ix_trace_events_trace_created_at", "trace_id", "created_at"),
        Index("ix_trace_events_run_created_at", "run_id", "created_at"),
        Index("ix_trace_events_session_created_at", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(255), nullable=False, primary_key=True, default=_new_id)
    trace_id: Mapped[str] = mapped_column(String(255), nullable=False)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'agentic'::character varying"),
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )

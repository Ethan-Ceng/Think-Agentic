#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Public, versioned execution-view contract for an Agent run."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionNodeKind(str, Enum):
    RUN = "run"
    STRATEGY = "strategy"
    PLAN = "plan"
    STEP = "step"
    MODEL = "model"
    TOOL = "tool"
    SKILL = "skill"
    INTERACTION = "interaction"
    ERROR = "error"
    COMPLETION = "completion"


class ExecutionPhase(str, Enum):
    DECIDE = "decide"
    PLAN = "plan"
    EXECUTE = "execute"
    WAIT = "wait"
    RESPOND = "respond"
    FINALIZE = "finalize"


class ExecutionNodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionDetailKind(str, Enum):
    TOOL = "tool"
    MODEL = "model"
    STEP = "step"
    INTERACTION = "interaction"


class ExecutionMetrics(BaseModel):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    ttft_ms: int | None = Field(default=None, ge=0)
    message_count: int | None = Field(default=None, ge=0)
    tool_schema_count: int | None = Field(default=None, ge=0)
    tool_schema_bytes: int | None = Field(default=None, ge=0)
    step_count: int | None = Field(default=None, ge=0)
    completed_steps: int | None = Field(default=None, ge=0)
    tool_count: int | None = Field(default=None, ge=0)
    model_count: int | None = Field(default=None, ge=0)
    replan_count: int | None = Field(default=None, ge=0)
    revision: int | None = Field(default=None, ge=0)
    decision_latency_ms: int | None = Field(default=None, ge=0)


class ExecutionFailure(BaseModel):
    code: str = "AGENT_RUN_FAILED"
    category: str = "runtime"
    scope: str = "run"
    source: str = "agent"
    message: str = "执行失败"
    retryable: bool = False
    recovery_actions: list[str] = Field(default_factory=list)
    provider_id: str | None = None
    tool_call_id: str | None = None
    debug_id: str = ""


class ExecutionNode(BaseModel):
    node_id: str = Field(min_length=1, max_length=255)
    parent_node_id: str | None = Field(default=None, max_length=255)
    kind: ExecutionNodeKind
    phase: ExecutionPhase
    status: ExecutionNodeStatus
    title: str = Field(max_length=120)
    summary: str = Field(default="", max_length=500)
    cursor: int = Field(ge=0)
    ordinal: int | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    failure: ExecutionFailure | None = None
    detail_kind: ExecutionDetailKind | None = None
    detail_id: str | None = Field(default=None, max_length=255)


class RunExecutionOverview(BaseModel):
    run_id: str
    session_id: str
    input_event_id: str | None = None
    status: ExecutionNodeStatus
    mode: str | None = None
    summary: str = Field(default="", max_length=500)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)


class RunExecutionView(BaseModel):
    schema_version: int = 1
    run: RunExecutionOverview
    nodes: list[ExecutionNode]
    next_cursor: int | None = None
    has_more: bool = False
    trace_complete: bool = True
    warnings: list[str] = Field(default_factory=list)


def execution_view_to_dict(view: RunExecutionView) -> dict[str, Any]:
    """Serialize enums and datetimes for the existing response envelope."""
    return view.model_dump(mode="json")

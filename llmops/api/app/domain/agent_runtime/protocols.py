from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RouterPlanStep(BaseModel):
    step_id: str
    worker_id: str
    task: str
    dependencies: list[str] = Field(default_factory=list)
    execution_mode: Literal["sync", "async"] = "sync"
    required_approval: bool = False
    expected_output: str = ""
    success_criteria: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)
    handoff_context: str = ""
    selection_reason: str = ""
    selection_signals: list[str] = Field(default_factory=list)


class RouterPlan(BaseModel):
    schema_version: Literal["router_plan_v1"] = "router_plan_v1"
    router_id: str
    user_intent: str
    risk_assessment: dict[str, Any] = Field(default_factory=dict)
    steps: list[RouterPlanStep]
    final_response_policy: dict[str, Any] = Field(default_factory=dict)


class WorkerInvocation(BaseModel):
    schema_version: Literal["worker_invocation_v1"] = "worker_invocation_v1"
    trace_id: str
    tenant_id: UUID
    account_id: UUID | None = None
    task_id: UUID
    plan_id: UUID | None = None
    step_id: UUID | None = None
    router_id: str
    worker_id: str
    user: dict[str, Any] = Field(default_factory=dict)
    task: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    execution_policy: dict[str, Any] = Field(default_factory=dict)


class ArtifactRef(BaseModel):
    artifact_id: str | None = None
    file_id: str | None = None
    name: str = ""
    type: str = "file"
    source: str = "agent"
    task_id: str | None = None
    step_id: str | None = None
    worker_id: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(BaseModel):
    schema_version: Literal["agent_event_v1"] = "agent_event_v1"
    trace_id: str
    task_id: UUID | None = None
    step_id: UUID | None = None
    worker_id: str | None = None
    event_type: str
    status: str = ""
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkerResult(BaseModel):
    schema_version: Literal["worker_result_v1"] = "worker_result_v1"
    trace_id: str
    task_id: UUID
    step_id: UUID | None = None
    worker_id: str
    status: str
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)
    confidence: float | None = None
    retryable: bool = False
    error_code: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    used_capabilities: list[str] = Field(default_factory=list)

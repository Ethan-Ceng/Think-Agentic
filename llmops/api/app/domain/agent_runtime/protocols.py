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
    task_id: UUID
    plan_id: UUID | None = None
    step_id: UUID | None = None
    router_id: str
    worker_id: str
    user: dict[str, Any] = Field(default_factory=dict)
    task: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    execution_policy: dict[str, Any] = Field(default_factory=dict)


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
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float | None = None
    retryable: bool = False
    error_code: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    used_capabilities: list[str] = Field(default_factory=list)

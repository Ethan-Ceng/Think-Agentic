from uuid import UUID

from pydantic import BaseModel, Field


class CreateRouterAgentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=800)
    llm_model_config: dict = Field(default_factory=dict, alias="model_config")
    prompt_config: dict = Field(default_factory=dict)
    router_config: dict = Field(default_factory=lambda: {"mode": "manager"})
    policies: dict = Field(default_factory=dict)
    status: str = Field(default="draft")


class BindRouterWorkerRequest(BaseModel):
    worker_agent_id: UUID
    priority: int = 0
    conditions: dict = Field(default_factory=dict)
    enabled: bool = True


class CreateAppWorkerAgentRequest(BaseModel):
    app_id: UUID
    status: str = Field(default="published")


class RouterManagerRunRequest(BaseModel):
    query: str = Field(..., min_length=1)
    input: dict = Field(default_factory=dict)
    worker_agent_ids: list[UUID] = Field(default_factory=list)
    session_id: UUID | None = None
    conversation_id: UUID | None = None
    execute: bool = False


class RouterAgentResponse(BaseModel):
    id: UUID
    version_id: UUID
    name: str
    status: str
    runtime_type: str
    target_ref_type: str = ""
    target_ref_id: str = ""


class RouterBindingResponse(BaseModel):
    id: UUID
    router_agent_id: UUID
    worker_agent_id: UUID
    enabled: bool
    priority: int
    conditions: dict


class RouterManagerRunResponse(BaseModel):
    task_id: UUID
    plan_id: UUID
    trace_id: str
    status: str
    steps: list[dict]

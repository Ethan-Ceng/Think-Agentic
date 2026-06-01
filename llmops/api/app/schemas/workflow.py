import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.workflow import WORKFLOW_CONFIG_NAME_PATTERN, WorkflowStatus
from app.models.workflow import Workflow
from app.shared.paginator import PaginatorReq


def datetime_to_timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    return int(value.timestamp())


class CreateWorkflowRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    tool_call_name: str = Field(..., min_length=1, max_length=50)
    icon: str = Field(..., min_length=1)
    description: str = Field(..., max_length=1024)

    @field_validator("tool_call_name")
    @classmethod
    def validate_tool_call_name(cls, value: str) -> str:
        value = value.strip()
        if not re.match(WORKFLOW_CONFIG_NAME_PATTERN, value):
            raise ValueError("tool_call_name only supports letters, numbers and underscores")
        return value

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("icon must be an HTTP URL")
        return value


class UpdateWorkflowRequest(CreateWorkflowRequest):
    pass


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    tool_call_name: str
    icon: str
    description: str
    status: str
    is_debug_passed: bool
    node_count: int
    published_at: int
    updated_at: int
    created_at: int

    @classmethod
    def from_workflow(cls, workflow: Workflow, *, use_draft_graph: bool = True) -> "WorkflowResponse":
        graph = workflow.draft_graph if use_draft_graph else workflow.graph
        return cls(
            id=workflow.id,
            name=workflow.name,
            tool_call_name=workflow.tool_call_name,
            icon=workflow.icon,
            description=workflow.description,
            status=workflow.status,
            is_debug_passed=workflow.is_debug_passed,
            node_count=len((graph or {}).get("nodes", [])),
            published_at=datetime_to_timestamp(workflow.published_at),
            updated_at=datetime_to_timestamp(workflow.updated_at),
            created_at=datetime_to_timestamp(workflow.created_at),
        )


class GetWorkflowsWithPageRequest(PaginatorReq):
    status: str | None = Field(default="")
    search_word: str | None = Field(default="")

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value and value not in {status.value for status in WorkflowStatus}:
            raise ValueError("workflow status is invalid")
        return value


class DraftGraph(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.app import App, AppConfigVersion


def datetime_to_timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    return int(value.timestamp())


AgentType = Literal["worker", "planner"]


class AppBaseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    icon: str
    description: str = Field(default="", max_length=800)

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("icon must be an HTTP URL")
        return value


class CreateAppRequest(AppBaseRequest):
    agent_type: AgentType = "worker"


class UpdateAppRequest(AppBaseRequest):
    pass


class GetAppsWithPageRequest(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search_word: str = ""
    agent_type: AgentType | Literal[""] = ""


class AppPageResponse(BaseModel):
    id: UUID
    name: str
    icon: str
    description: str
    agent_type: str = "worker"
    preset_prompt: str
    model_cfg: dict
    status: str
    updated_at: int
    created_at: int

    @classmethod
    def from_app(cls, app: App, app_config) -> "AppPageResponse":
        model_config = app_config.model_config if app_config else {}
        return cls(
            id=app.id,
            name=app.name,
            icon=app.icon,
            description=app.description,
            agent_type=getattr(app, "agent_type", "worker") or "worker",
            preset_prompt=app_config.preset_prompt if app_config else "",
            model_cfg={
                "provider": model_config.get("provider", ""),
                "model": model_config.get("model", ""),
            },
            status=app.status,
            updated_at=datetime_to_timestamp(app.updated_at),
            created_at=datetime_to_timestamp(app.created_at),
        )


class AppResponse(BaseModel):
    id: UUID
    debug_conversation_id: UUID | None
    name: str
    icon: str
    description: str
    agent_type: str = "worker"
    status: str
    draft_updated_at: int
    updated_at: int
    created_at: int

    @classmethod
    def from_app(cls, app: App, draft_config) -> "AppResponse":
        return cls(
            id=app.id,
            debug_conversation_id=app.debug_conversation_id,
            name=app.name,
            icon=app.icon,
            description=app.description,
            agent_type=getattr(app, "agent_type", "worker") or "worker",
            status=app.status,
            draft_updated_at=datetime_to_timestamp(draft_config.updated_at if draft_config else None),
            updated_at=datetime_to_timestamp(app.updated_at),
            created_at=datetime_to_timestamp(app.created_at),
        )


class GetPublishHistoriesWithPageRequest(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class GetDebugConversationMessagesWithPageRequest(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    created_at: int = Field(0, ge=0)


class PublishHistoryResponse(BaseModel):
    id: UUID
    version: int
    created_at: int

    @classmethod
    def from_version(cls, version: AppConfigVersion) -> "PublishHistoryResponse":
        return cls(
            id=version.id,
            version=version.version,
            created_at=datetime_to_timestamp(version.created_at),
        )


class FallbackHistoryToDraftRequest(BaseModel):
    app_config_version_id: UUID


class UpdateDebugConversationSummaryRequest(BaseModel):
    summary: str = ""


class DebugChatRequest(BaseModel):
    image_urls: list[str] = Field(default_factory=list, max_length=5)
    query: str = Field(..., min_length=1)


class BindPlannerWorkerRequest(BaseModel):
    worker_app_id: UUID
    enabled: bool = True
    priority: int = Field(0, ge=0, le=100)
    conditions: dict = Field(default_factory=dict)


class UpdatePlannerWorkerBindingRequest(BaseModel):
    enabled: bool = True
    priority: int = Field(0, ge=0, le=100)
    conditions: dict = Field(default_factory=dict)


class RefreshCapabilitySummaryRequest(BaseModel):
    preserve_manual_overrides: bool = True


class PatchCapabilitySummaryRequest(BaseModel):
    manual_overrides: dict = Field(default_factory=dict)


class RoutingPolicyRequest(BaseModel):
    routing_policy: dict = Field(default_factory=dict)


class PlannerPreflightRequest(BaseModel):
    message: str = Field(..., min_length=1)
    input_modalities: list[str] = Field(default_factory=list)
    candidate_worker_ids: list[UUID] = Field(default_factory=list)

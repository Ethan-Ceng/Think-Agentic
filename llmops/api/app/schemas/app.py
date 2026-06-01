from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.app import App, AppConfigVersion


def datetime_to_timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    return int(value.timestamp())


class CreateAppRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    icon: str
    description: str = Field(default="", max_length=800)

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("icon must be an HTTP URL")
        return value


class UpdateAppRequest(CreateAppRequest):
    pass


class GetAppsWithPageRequest(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    search_word: str = ""


class AppPageResponse(BaseModel):
    id: UUID
    name: str
    icon: str
    description: str
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

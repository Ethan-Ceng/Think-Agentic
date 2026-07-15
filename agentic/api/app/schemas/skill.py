from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.entities.skill import (
    SKILL_NAME_PATTERN,
    SelectedSkill,
    SkillManifest,
    SkillRef,
    SkillSelectionMode,
    SkillSource,
)


class SkillDraftCreateRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=64,
        pattern=SKILL_NAME_PATTERN,
    )
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1024)


class SkillDraftFileWriteRequest(BaseModel):
    content: str


class SkillDraftPublishRequest(BaseModel):
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    changelog: str = Field(default="", max_length=4096)


class SkillUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, min_length=1, max_length=1024)

    model_config = ConfigDict(extra="forbid")


class SkillAutoInvokeRequest(BaseModel):
    enabled: bool


class SkillResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    scope: str
    status: str
    enabled: bool
    auto_invoke: bool
    current_version_id: str | None
    updated_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillVersionResponse(BaseModel):
    id: str
    skill_id: str
    version: int
    manifest: dict
    package_sha256: str
    package_size: int
    file_count: int
    status: str
    changelog: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillDetailResponse(BaseModel):
    skill: SkillResponse
    version: SkillVersionResponse | None


class PublishedSkillResponse(BaseModel):
    skill: SkillResponse
    version: SkillVersionResponse

__all__ = [
    "SelectedSkill",
    "SkillManifest",
    "SkillRef",
    "SkillSelectionMode",
    "SkillSource",
    "PublishedSkillResponse",
    "SkillAutoInvokeRequest",
    "SkillDetailResponse",
    "SkillDraftCreateRequest",
    "SkillDraftFileWriteRequest",
    "SkillDraftPublishRequest",
    "SkillResponse",
    "SkillUpdateRequest",
    "SkillVersionResponse",
]

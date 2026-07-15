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


class SkillCatalogItem(BaseModel):
    ref: SkillRef
    display_name: str = Field(min_length=1, max_length=128)
    manifest: SkillManifest
    version_id: str | None = None
    version: int | None = Field(default=None, ge=1)
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    auto_invoke: bool = True

    model_config = ConfigDict(extra="forbid")

    @property
    def selector_key(self) -> str:
        identity = self.ref.skill_id or self.ref.name
        return f"{self.ref.source.value}:{identity}"


class SkillSelectionRequest(BaseModel):
    user_id: str = Field(min_length=1)
    message: str
    attachment_media_types: list[str] = Field(default_factory=list)
    manual_refs: list[SkillRef] = Field(default_factory=list)
    available_tool_names: set[str] = Field(default_factory=set)

    model_config = ConfigDict(extra="forbid")


class SkillSelectionSkip(BaseModel):
    ref: SkillRef | None = None
    requested_key: str | None = None
    selection_mode: SkillSelectionMode
    code: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=512)

    model_config = ConfigDict(extra="forbid")


class SkillSelectionResult(BaseModel):
    selected: list[SelectedSkill] = Field(default_factory=list)
    skipped: list[SkillSelectionSkip] = Field(default_factory=list)
    selector_model_call_id: str | None = None

    model_config = ConfigDict(extra="forbid")


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
    "SkillCatalogItem",
    "SkillDetailResponse",
    "SkillDraftCreateRequest",
    "SkillDraftFileWriteRequest",
    "SkillDraftPublishRequest",
    "SkillResponse",
    "SkillSelectionRequest",
    "SkillSelectionResult",
    "SkillSelectionSkip",
    "SkillUpdateRequest",
    "SkillVersionResponse",
]

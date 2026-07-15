import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


SKILL_NAME_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class SkillSource(StrEnum):
    BUNDLED = "bundled"
    PERSONAL = "personal"
    MARKETPLACE = "marketplace"


class SkillSelectionMode(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class SkillScope(StrEnum):
    PERSONAL = "personal"
    MARKETPLACE = "marketplace"


class SkillStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class SkillVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class SkillRef(BaseModel):
    source: SkillSource
    skill_id: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1, max_length=64, pattern=SKILL_NAME_PATTERN)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_source_identity(self) -> "SkillRef":
        if self.source is SkillSource.BUNDLED and self.skill_id is not None:
            raise ValueError("bundled Skill 的 skill_id 必须为空")
        if self.source is not SkillSource.BUNDLED and self.skill_id is None:
            raise ValueError("personal 和 marketplace Skill 必须提供 skill_id")
        return self


class SkillManifest(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=SKILL_NAME_PATTERN)
    description: str = Field(min_length=1, max_length=1024)
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, StrictStr] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list, alias="allowed-tools")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SelectedSkill(BaseModel):
    ref: SkillRef
    version_id: str | None = None
    version: int | None = Field(default=None, ge=1)
    manifest: SkillManifest
    selection_mode: SkillSelectionMode
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = Field(min_length=1)
    package_sha256: str = Field(pattern=SHA256_PATTERN)

    model_config = ConfigDict(extra="forbid")


class Skill(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_user_id: str | None = None
    name: str = Field(min_length=1, max_length=64, pattern=SKILL_NAME_PATTERN)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1024)
    scope: SkillScope
    status: SkillStatus = SkillStatus.ACTIVE
    enabled: bool = True
    auto_invoke: bool = True
    current_version_id: str | None = None
    forked_from_skill_id: str | None = None
    forked_from_version_id: str | None = None
    updated_at: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_owner(self) -> "Skill":
        if self.scope is SkillScope.PERSONAL and not self.owner_user_id:
            raise ValueError("personal Skill 必须提供 owner_user_id")
        if self.scope is SkillScope.MARKETPLACE and self.owner_user_id is not None:
            raise ValueError("marketplace Skill 的 owner_user_id 必须为空")
        return self


class SkillVersion(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    skill_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    manifest: dict[str, Any]
    storage_provider: str = Field(min_length=1, max_length=64)
    storage_key: str = Field(min_length=1)
    storage_config: dict[str, Any] = Field(default_factory=dict)
    package_sha256: str = Field(pattern=SHA256_PATTERN)
    package_size: int = Field(ge=0)
    file_count: int = Field(ge=1)
    status: SkillVersionStatus = SkillVersionStatus.PUBLISHED
    changelog: str = ""
    created_by_user_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(extra="forbid")


class SkillInstallation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    pinned_version_id: str = Field(min_length=1)
    enabled: bool = True
    auto_invoke: bool = True
    auto_update: bool = False
    installed_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(extra="forbid")


class RunSkill(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = Field(min_length=1)
    skill_id: str | None = None
    skill_version_id: str | None = None
    name: str = Field(min_length=1, max_length=64, pattern=SKILL_NAME_PATTERN)
    source: SkillSource
    selection_mode: SkillSelectionMode
    content_sha256: str = Field(pattern=SHA256_PATTERN)
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = Field(min_length=1)
    sandbox_path: str = ""
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(extra="forbid")

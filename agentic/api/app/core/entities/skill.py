from enum import StrEnum

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

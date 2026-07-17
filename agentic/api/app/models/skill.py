import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.skill import RunSkill, Skill, SkillInstallation, SkillVersion

from .base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


class SkillModel(Base):
    __tablename__ = "skills"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_skills_id"),
        CheckConstraint(
            "(scope = 'personal' AND owner_user_id IS NOT NULL) OR "
            "(scope = 'marketplace' AND owner_user_id IS NULL)",
            name="ck_skills_scope_owner",
        ),
        ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_skills_owner_user_id_users",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["current_version_id"],
            ["skill_versions.id"],
            name="fk_skills_current_version_id_skill_versions",
            ondelete="SET NULL",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["forked_from_skill_id"],
            ["skills.id"],
            name="fk_skills_forked_from_skill_id_skills",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["forked_from_version_id"],
            ["skill_versions.id"],
            name="fk_skills_forked_from_version_id_skill_versions",
            ondelete="SET NULL",
            use_alter=True,
        ),
        Index(
            "ux_skills_personal_owner_name_active",
            "owner_user_id",
            "name",
            unique=True,
            postgresql_where=text("scope = 'personal' AND status <> 'archived'"),
        ),
        Index(
            "ux_skills_marketplace_name_active",
            "name",
            unique=True,
            postgresql_where=text("scope = 'marketplace' AND status <> 'archived'"),
        ),
        Index("ix_skills_owner_status", "owner_user_id", "status"),
        Index("ix_skills_scope_status", "scope", "status"),
    )

    id: Mapped[str] = mapped_column(String(255), default=_new_id, nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'active'")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    auto_invoke: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    current_version_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    forked_from_skill_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    forked_from_version_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)")
    )

    @classmethod
    def from_domain(cls, skill: Skill) -> "SkillModel":
        return cls(**skill.model_dump(mode="python"))

    def to_domain(self) -> Skill:
        return Skill.model_validate(self, from_attributes=True)


class SkillVersionModel(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_skill_versions_id"),
        ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name="fk_skill_versions_skill_id_skills",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_skill_versions_created_by_user_id_users",
            ondelete="SET NULL",
        ),
        UniqueConstraint(
            "skill_id", "version", name="uq_skill_versions_skill_version"
        ),
        Index("ix_skill_versions_skill_created", "skill_id", "created_at"),
        Index("ix_skill_versions_sha256", "package_sha256"),
    )

    id: Mapped[str] = mapped_column(String(255), default=_new_id, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    storage_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    storage_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    package_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    package_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'published'")
    )
    changelog: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)")
    )

    @classmethod
    def from_domain(cls, version: SkillVersion) -> "SkillVersionModel":
        return cls(**version.model_dump(mode="python"))

    def to_domain(self) -> SkillVersion:
        return SkillVersion.model_validate(self, from_attributes=True)


class SkillInstallationModel(Base):
    __tablename__ = "skill_installations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_skill_installations_id"),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_skill_installations_user_id_users",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name="fk_skill_installations_skill_id_skills",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["pinned_version_id"],
            ["skill_versions.id"],
            name="fk_skill_installations_pinned_version_id_skill_versions",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "user_id", "skill_id", name="uq_skill_installations_user_skill"
        ),
        Index("ix_skill_installations_user_enabled", "user_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(255), default=_new_id, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False)
    pinned_version_id: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    auto_invoke: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    auto_update: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )

    @classmethod
    def from_domain(
        cls, installation: SkillInstallation
    ) -> "SkillInstallationModel":
        return cls(**installation.model_dump(mode="python"))

    def to_domain(self) -> SkillInstallation:
        return SkillInstallation.model_validate(self, from_attributes=True)


class RunSkillModel(Base):
    __tablename__ = "run_skills"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_run_skills_id"),
        ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_run_skills_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name="fk_run_skills_skill_id_skills",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["skill_version_id"],
            ["skill_versions.id"],
            name="fk_run_skills_skill_version_id_skill_versions",
            ondelete="SET NULL",
        ),
        Index("ix_run_skills_run_created", "run_id", "created_at"),
        Index("ix_run_skills_skill_version", "skill_id", "skill_version_id"),
    )

    id: Mapped[str] = mapped_column(String(255), default=_new_id, nullable=False)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    skill_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    skill_version_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    selection_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    sandbox_path: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)")
    )

    @classmethod
    def from_domain(cls, run_skill: RunSkill) -> "RunSkillModel":
        return cls(**run_skill.model_dump(mode="python"))

    def to_domain(self) -> RunSkill:
        return RunSkill.model_validate(self, from_attributes=True)

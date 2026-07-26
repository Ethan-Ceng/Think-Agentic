#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Single-level Project directory ORM model."""
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.project import Project
from .base import Base


class ProjectModel(Base):
    """A user-owned directory with no recursive hierarchy."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_projects_id"),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_projects_user_id_users",
            ondelete="CASCADE",
        ),
        Index("ix_projects_user_created_at", "user_id", "created_at"),
        Index(
            "ux_projects_user_lower_name",
            "user_id",
            func.lower(name),
            unique=True,
        ),
    )

    @classmethod
    def from_domain(cls, project: Project) -> "ProjectModel":
        return cls(
            **project.model_dump(
                mode="python",
                exclude={"created_at", "updated_at"},
            )
        )

    def to_domain(self) -> Project:
        return Project.model_validate(self, from_attributes=True)

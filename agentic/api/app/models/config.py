#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Config ORM model."""
import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, PrimaryKeyConstraint, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.config import Config
from .base import Base


class ConfigModel(Base):
    """User-scoped typed configuration document."""

    __tablename__ = "configs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_configs_id"),
        ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_configs_user_id_users", ondelete="CASCADE"),
        UniqueConstraint("user_id", "config_type", name="ux_configs_user_id_config_type"),
        Index("ix_configs_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    config_type: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    schema_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'config_v1'::character varying"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )

    def to_domain(self) -> Config:
        return Config.model_validate(self, from_attributes=True)

    @classmethod
    def from_domain(cls, config: Config) -> "ConfigModel":
        return cls(**config.model_dump(mode="python", exclude={"updated_at", "created_at"}))

    def update_from_domain(self, config: Config) -> None:
        for field, value in config.model_dump(mode="python", exclude={"updated_at", "created_at"}).items():
            setattr(self, field, value)

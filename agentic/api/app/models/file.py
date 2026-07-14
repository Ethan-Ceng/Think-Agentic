#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File ORM Model - 新架构（保持业务逻辑不变）
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Integer, DateTime, text, PrimaryKeyConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.file import File
from .base import Base


class FileModel(Base):
    """文件ORM模型 - 直接用于业务逻辑，无需领域模型转换"""
    __tablename__ = "files"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_files_id"),
        Index("ix_files_user_parent_status", "user_id", "parent_id", "status"),
        Index("ix_files_user_source", "user_id", "source_type"),
        Index("ix_files_purge_after", "purge_after"),
    )

    id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    filepath: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    extension: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    mime_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    parent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entry_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'file'::character varying")
    )
    storage_provider: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'local'::character varying")
    )
    storage_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    source_type: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'user_upload'::character varying")
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'available'::character varying")
    )
    sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("''::character varying")
    )
    file_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    origin_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    origin_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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

    @classmethod
    def from_domain(cls, file: File) -> "FileModel":
        """Create an ORM model from a domain file."""
        data = file.model_dump(mode="python")
        data["file_metadata"] = data.pop("metadata")
        return cls(**data)

    def to_domain(self) -> File:
        """Convert this ORM model to a domain file."""
        data = {
            column.name: getattr(self, column.key)
            for column in self.__table__.columns
            if column.name != "metadata"
        }
        data["metadata"] = self.file_metadata
        return File.model_validate(data)

    def update_from_domain(self, file: File) -> None:
        """Update this ORM model from a domain file."""
        for field, value in file.model_dump(mode="python").items():
            if field in {"created_at", "updated_at"}:
                continue
            setattr(self, "file_metadata" if field == "metadata" else field, value)

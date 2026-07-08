#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File ORM Model - 新架构（保持业务逻辑不变）
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, text, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.file import File
from .base import Base


class FileModel(Base):
    """文件ORM模型 - 直接用于业务逻辑，无需领域模型转换"""
    __tablename__ = "files"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_files_id"),
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
        return cls(**file.model_dump(mode="json"))

    def to_domain(self) -> File:
        """Convert this ORM model to a domain file."""
        return File.model_validate(self, from_attributes=True)

    def update_from_domain(self, file: File) -> None:
        """Update this ORM model from a domain file."""
        for field, value in file.model_dump(mode="json").items():
            setattr(self, field, value)

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""User ORM model."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, text, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.user import User
from .base import Base


class UserModel(Base):
    """User ORM model."""

    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_users_id"),
        Index("ux_users_email", "email", unique=True),
    )

    id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    avatar: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        server_default=text("''::character varying"),
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    password_salt: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    password_algorithm: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'pbkdf2_sha256'::character varying"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'active'::character varying"),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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

    def to_domain(self) -> User:
        return User.model_validate(self, from_attributes=True)

    @classmethod
    def from_domain(cls, user: User) -> "UserModel":
        return cls(**user.model_dump(mode="python", exclude={"updated_at", "created_at"}))

    def update_from_domain(self, user: User) -> None:
        for field, value in user.model_dump(mode="python", exclude={"updated_at", "created_at"}).items():
            setattr(self, field, value)

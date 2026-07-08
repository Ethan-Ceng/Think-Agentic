#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Session ORM Model - 合并了领域模型和ORM模型
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Text,
    text,
    PrimaryKeyConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.session import Session
from .base import Base


class SessionStatus(str, Enum):
    """会话状态类型枚举"""
    PENDING = "pending"  # 等待任务
    RUNNING = "running"  # 运行中
    WAITING = "waiting"  # 等待人类响应
    COMPLETED = "completed"  # 已完成


class SessionModel(Base):
    """会话ORM模型 - 直接用于业务逻辑，无需领域模型转换"""
    __tablename__ = "sessions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_sessions_id"),
    )

    id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sandbox_id: Mapped[str] = mapped_column(String(255), nullable=True)
    task_id: Mapped[str] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
    unread_message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    latest_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("''::text"),
    )
    latest_message_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
    )
    events: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    files: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    memories: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("'pending'::character varying"),
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
    def from_domain(cls, session: Session) -> "SessionModel":
        """Create an ORM model from a domain session."""
        return cls(
            **session.model_dump(
                mode="python",
                exclude={"memories", "files", "events", "updated_at", "created_at"},
            ),
            **session.model_dump(
                mode="json",
                include={"memories", "files", "events"},
            ),
        )

    def to_domain(self) -> Session:
        """Convert this ORM model to a domain session."""
        return Session.model_validate(self, from_attributes=True)

    def update_from_domain(self, session: Session) -> None:
        """Update this ORM model from a domain session."""
        base_data = session.model_dump(
            mode="python",
            exclude={"memories", "files", "events", "updated_at", "created_at"},
        )
        json_data = session.model_dump(
            mode="json",
            include={"memories", "files", "events"},
        )

        for field, value in {**base_data, **json_data}.items():
            setattr(self, field, value)

    def get_latest_plan(self) -> Optional[Dict[str, Any]]:
        """获取会话中的最新计划"""
        for event in reversed(self.events):
            if event.get("type") == "plan":
                return event.get("plan")
        return None

    def can_execute(self) -> bool:
        """检查会话是否可以执行"""
        return self.status in [SessionStatus.PENDING.value, SessionStatus.WAITING.value]

    def add_event(self, event: Dict[str, Any]) -> None:
        """添加事件到会话"""
        self.events.append(event)
        if event.get("type") == "message":
            self.latest_message = event.get("message", "")
            self.latest_message_at = datetime.now()

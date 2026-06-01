import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.models.base import Base


def _jsonb(default, server_default: str):
    return mapped_column(JSONB, nullable=False, default=default, server_default=text(server_default))


class Conversation(Base):
    __tablename__ = "conversation"
    __table_args__ = (
        Index("conversation_app_id_idx", "app_id"),
        Index("conversation_app_created_by_idx", "created_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    invoke_from: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        Index("message_conversation_id_idx", "conversation_id"),
        Index("message_created_by_idx", "created_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoke_from: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    image_urls: Mapped[list[str]] = _jsonb(list, "'[]'::jsonb")
    message: Mapped[list[dict[str, Any]]] = _jsonb(list, "'[]'::jsonb")
    message_token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    message_unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False, server_default=text("0.0"))
    message_price_unit: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("0.0"))
    answer: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    answer_token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    answer_unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False, server_default=text("0.0"))
    answer_price_unit: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("0.0"))
    latency: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    error: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    total_token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False, server_default=text("0.0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))

    agent_thoughts: Mapped[list["MessageAgentThought"]] = relationship(
        "MessageAgentThought",
        primaryjoin=lambda: Message.id == foreign(MessageAgentThought.message_id),
        viewonly=True,
    )


class MessageAgentThought(Base):
    __tablename__ = "message_agent_thought"
    __table_args__ = (
        Index("message_agent_thought_app_id_idx", "app_id"),
        Index("message_agent_thought_conversation_id_idx", "conversation_id"),
        Index("message_agent_thought_message_id_idx", "message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoke_from: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    event: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    thought: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    observation: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    tool: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    tool_input: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    message: Mapped[list[dict[str, Any]]] = _jsonb(list, "'[]'::jsonb")
    message_token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    message_unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False, server_default=text("0.0"))
    message_price_unit: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("0"))
    answer: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    answer_token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    answer_unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False, server_default=text("0.0"))
    answer_price_unit: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("0.0"))
    total_token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False, server_default=text("0.0"))
    latency: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _jsonb(default, server_default: str):
    return mapped_column(JSONB, nullable=False, default=default, server_default=text(server_default))


class App(Base):
    __tablename__ = "app"
    __table_args__ = (
        Index("app_account_id_idx", "account_id"),
        Index("app_token_idx", "token"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    app_config_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    draft_app_config_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    debug_conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    icon: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    token: Mapped[str | None] = mapped_column(String(255), nullable=True, server_default=text("''::character varying"))
    status: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class AppConfig(Base):
    __tablename__ = "app_config"
    __table_args__ = (Index("app_config_app_id_idx", "app_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    model_config: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    dialog_round: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    preset_prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    tools: Mapped[list[dict[str, Any]]] = _jsonb(list, "'[]'::jsonb")
    workflows: Mapped[list[str]] = _jsonb(list, "'[]'::jsonb")
    retrieval_config: Mapped[dict[str, Any] | list] = _jsonb(dict, "'[]'::jsonb")
    long_term_memory: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    opening_statement: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    opening_questions: Mapped[list[str]] = _jsonb(list, "'[]'::jsonb")
    speech_to_text: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    text_to_speech: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    suggested_after_answer: Mapped[dict[str, Any]] = _jsonb(dict, "'{\"enable\": true}'::jsonb")
    review_config: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class AppConfigVersion(Base):
    __tablename__ = "app_config_version"
    __table_args__ = (Index("app_config_version_app_id_idx", "app_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    model_config: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    dialog_round: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    preset_prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    tools: Mapped[list[dict[str, Any]]] = _jsonb(list, "'[]'::jsonb")
    workflows: Mapped[list[str]] = _jsonb(list, "'[]'::jsonb")
    datasets: Mapped[list[str]] = _jsonb(list, "'[]'::jsonb")
    retrieval_config: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    long_term_memory: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    opening_statement: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    opening_questions: Mapped[list[str]] = _jsonb(list, "'[]'::jsonb")
    speech_to_text: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    text_to_speech: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    suggested_after_answer: Mapped[dict[str, Any]] = _jsonb(dict, "'{\"enable\": true}'::jsonb")
    review_config: Mapped[dict[str, Any]] = _jsonb(dict, "'{}'::jsonb")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    config_type: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class AppDatasetJoin(Base):
    __tablename__ = "app_dataset_join"
    __table_args__ = (Index("app_dataset_join_app_id_dataset_id_idx", "app_id", "dataset_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))

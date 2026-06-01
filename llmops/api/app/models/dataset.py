import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Dataset(Base):
    __tablename__ = "dataset"
    __table_args__ = (Index("dataset_account_id_name_idx", "account_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    icon: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        Index("document_account_id_idx", "account_id"),
        Index("document_dataset_id_idx", "dataset_id"),
        Index("document_batch_idx", "batch"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    upload_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    process_rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    batch: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    character_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    parsing_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    splitting_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    indexing_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("'waiting'::character varying"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class Segment(Base):
    __tablename__ = "segment"
    __table_args__ = (
        Index("segment_account_id_idx", "account_id"),
        Index("segment_dataset_id_idx", "dataset_id"),
        Index("segment_document_id_idx", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    character_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    hash: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    indexing_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    status: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("'waiting'::character varying"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class KeywordTable(Base):
    __tablename__ = "keyword_table"
    __table_args__ = (Index("keyword_table_dataset_id_idx", "dataset_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    keyword_table: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class DatasetQuery(Base):
    __tablename__ = "dataset_query"
    __table_args__ = (
        Index("dataset_query_dataset_id_idx", "dataset_id"),
        Index("dataset_created_by_idx", "created_by"),
        Index("dataset_source_app_id_idx", "source_app_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    source: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("'HitTesting'::character varying"),
    )
    source_app_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))


class ProcessRule(Base):
    __tablename__ = "process_rule"
    __table_args__ = (
        Index("process_rule_account_id_idx", "account_id"),
        Index("process_rule_dataset_id_idx", "dataset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mode: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("'automic'::character varying"))
    rule: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))

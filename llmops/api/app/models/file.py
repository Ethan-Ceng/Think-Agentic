import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_account_parent", "account_id", "parent_id"),
        Index("ix_files_account_status", "account_id", "status"),
        Index("ix_files_account_source", "account_id", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'file'::character varying"))
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    extension: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("''::character varying"))
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    size: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    storage_provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'local'::character varying"),
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False, server_default=text("''::character varying"))
    hash: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    source: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'upload'::character varying"))
    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default=text("'available'::character varying"),
    )
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))

    @property
    def key(self) -> str:
        return self.file_path

    @key.setter
    def key(self, value: str) -> None:
        self.file_path = value

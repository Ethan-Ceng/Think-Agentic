import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UploadFile(Base):
    __tablename__ = "upload_file"
    __table_args__ = (Index("upload_file_account_id_idx", "account_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    key: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    size: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    extension: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    hash: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ApiKey(Base):
    __tablename__ = "api_key"
    __table_args__ = (
        Index("api_key_account_id_idx", "account_id"),
        Index("api_key_api_key_idx", "api_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    api_key: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    remark: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )


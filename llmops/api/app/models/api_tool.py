import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.models.base import Base


class ApiToolProvider(Base):
    __tablename__ = "api_tool_provider"
    __table_args__ = (
        Index("api_tool_provider_account_id_idx", "account_id"),
        Index("api_tool_name_idx", "name"),
    )

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
    openapi_schema: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    headers: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))

    tools: Mapped[list["ApiTool"]] = relationship(
        "ApiTool",
        primaryjoin=lambda: ApiToolProvider.id == foreign(ApiTool.provider_id),
        viewonly=True,
    )


class ApiTool(Base):
    __tablename__ = "api_tool"
    __table_args__ = (
        Index("api_tool_account_id_idx", "account_id"),
        Index("api_tool_provider_id_name_idx", "provider_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''::text"))
    url: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    method: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    parameters: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
        onupdate=datetime.now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP(0)"))

    provider: Mapped[ApiToolProvider] = relationship(
        "ApiToolProvider",
        primaryjoin=lambda: foreign(ApiTool.provider_id) == ApiToolProvider.id,
        viewonly=True,
    )


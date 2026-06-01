import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (
        Index("account_email_idx", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    email: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    avatar: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    password: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        server_default=text("''::character varying"),
    )
    password_salt: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        server_default=text("''::character varying"),
    )
    assistant_agent_conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(0)"),
    )
    last_login_ip: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
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

    @property
    def is_password_set(self) -> bool:
        return self.password is not None and self.password != ""

    @property
    def assistant_agent_conversation(self) -> uuid.UUID | None:
        return self.assistant_agent_conversation_id

    @property
    def status(self) -> str:
        return "active"


class AccountOAuth(Base):
    __tablename__ = "account_oauth"
    __table_args__ = (
        Index("account_oauth_account_id_idx", "account_id"),
        Index("account_oauth_openid_provider_idx", "openid", "provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("uuid_generate_v4()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    openid: Mapped[str] = mapped_column(String(255), nullable=False, server_default=text("''::character varying"))
    encrypted_token: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )
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

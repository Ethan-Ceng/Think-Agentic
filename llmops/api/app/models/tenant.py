import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Tenant(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="active", nullable=False)


class TenantMember(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tenant_members"
    __table_args__ = (
        Index("ix_tenant_members_tenant_user", "tenant_id", "user_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("account.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(64), default="owner", nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="active", nullable=False)

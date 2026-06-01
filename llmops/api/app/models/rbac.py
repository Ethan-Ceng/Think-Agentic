import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Role(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        Index("ix_roles_tenant_code", "tenant_id", "code", unique=True),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="active", nullable=False)


class Permission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (
        Index("ix_permissions_code", "code", unique=True),
    )

    code: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    resource: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(128), default="", nullable=False)


class RolePermission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        Index("ix_role_permissions_role_permission", "role_id", "permission_id", unique=True),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    permission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("permissions.id"), nullable=False)


class MemberRole(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "member_roles"
    __table_args__ = (
        Index("ix_member_roles_member_role", "member_id", "role_id", unique=True),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenant_members.id"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    data_scope: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

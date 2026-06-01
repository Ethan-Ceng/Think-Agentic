import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Capability(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "capabilities"
    __table_args__ = (
        Index("ix_capabilities_tenant_type_enabled", "tenant_id", "type", "enabled"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    target_ref_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_ref_id: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    permission: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="low", nullable=False)
    side_effect: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    requires_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    idempotency_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    retry_policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    data_scope_policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    audit_policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[str] = mapped_column(String(64), default="1.0.0", nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)


class AgentCapabilityBinding(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_capability_bindings"
    __table_args__ = (
        Index("ix_agent_capability_bindings_agent_capability", "agent_version_id", "capability_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_versions.id"),
        nullable=False,
    )
    capability_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capabilities.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)

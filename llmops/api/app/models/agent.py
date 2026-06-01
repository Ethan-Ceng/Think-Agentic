import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Agent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_tenant_runtime_status", "tenant_id", "runtime_type", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    runtime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    product_category: Mapped[str] = mapped_column(String(64), default="custom", nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="draft", nullable=False)
    draft_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    published_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    visibility_scope: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    target_ref_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    target_ref_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)


class AgentVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        Index("ix_agent_versions_agent_config", "agent_id", "config_type", "version"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    config_type: Mapped[str] = mapped_column(String(32), nullable=False)
    model_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    prompt_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    router_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    worker_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    capability_bindings: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    policies: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AgentBinding(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_bindings"
    __table_args__ = (
        Index("ix_agent_bindings_router_worker", "router_agent_id", "worker_agent_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    router_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    worker_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conditions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

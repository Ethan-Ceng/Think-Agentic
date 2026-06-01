import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class AgentTask(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_tasks"
    __table_args__ = (
        Index("ix_agent_tasks_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    router_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    user_input: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    final_result: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_code: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AgentPlan(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_plans"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=False)
    router_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), default="router_plan_v1", nullable=False)
    plan_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="low", nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)


class AgentStep(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        Index("ix_agent_steps_task_status", "task_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_plans.id"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    dependencies: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(32), default="sync", nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    input_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class WorkerCall(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "worker_calls"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=False)
    step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_steps.id"), nullable=False)
    worker_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    invocation_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    latency: Mapped[float] = mapped_column(Numeric(12, 3), default=0, nullable=False)


class CapabilityCall(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "capability_calls"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=False)
    step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_steps.id"), nullable=False)
    worker_call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worker_calls.id"),
        nullable=True,
    )
    capability_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capabilities.id"), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="low", nullable=False)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    latency: Mapped[float] = mapped_column(Numeric(12, 3), default=0, nullable=False)

import uuid

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class TraceEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "trace_events"
    __table_args__ = (
        Index("ix_trace_events_tenant_trace_created", "tenant_id", "trace_id", "created_at"),
        Index("ix_trace_events_task_created", "task_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_plans.id"), nullable=True)
    step_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_steps.id"), nullable=True)
    worker_call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worker_calls.id"),
        nullable=True,
    )
    capability_call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capability_calls.id"),
        nullable=True,
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approval_requests.id"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    latency: Mapped[float] = mapped_column(Numeric(12, 3), default=0, nullable=False)

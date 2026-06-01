import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ApprovalRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_tenant_status_created", "tenant_id", "status", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_tasks.id"), nullable=False)
    step_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_steps.id"), nullable=True)
    capability_call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capability_calls.id"),
        nullable=True,
    )
    action_type: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    proposed_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="pending", nullable=False)
    approver_policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approval_token_hash: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    decision_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

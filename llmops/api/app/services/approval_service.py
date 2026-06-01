import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import FailException, NotFoundException
from app.models.approval import ApprovalRequest
from app.models.task import CapabilityCall
from app.services.base_service import BaseService


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ApprovalService(BaseService):
    def get_request(self, session: Session, *, tenant_id: uuid.UUID, approval_id: uuid.UUID) -> ApprovalRequest:
        approval = self.get(session, ApprovalRequest, approval_id)
        if approval is None or approval.tenant_id != tenant_id:
            raise NotFoundException("Approval request not found")
        return approval

    def list_pending(self, session: Session, *, tenant_id: uuid.UUID) -> list[ApprovalRequest]:
        return (
            session.query(ApprovalRequest)
            .filter(
                ApprovalRequest.tenant_id == tenant_id,
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
            )
            .order_by(ApprovalRequest.created_at.desc())
            .all()
        )

    def create_request(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        task_id: uuid.UUID,
        action_type: str,
        title: str,
        summary: str = "",
        step_id: uuid.UUID | None = None,
        capability_call: CapabilityCall | None = None,
        proposed_payload: dict[str, Any] | None = None,
        risk_level: str = "medium",
        approver_policy: dict[str, Any] | None = None,
        approval_token_hash: str = "",
        expires_at: datetime | None = None,
    ) -> ApprovalRequest:
        approval = self.create(
            session,
            ApprovalRequest,
            tenant_id=tenant_id,
            task_id=task_id,
            step_id=step_id or (capability_call.step_id if capability_call else None),
            capability_call_id=capability_call.id if capability_call else None,
            action_type=action_type,
            title=title,
            summary=summary,
            proposed_payload=proposed_payload or {},
            risk_level=risk_level,
            status=ApprovalStatus.PENDING.value,
            approver_policy=approver_policy or {},
            approved_by=None,
            approval_token_hash=approval_token_hash,
            decision_payload={},
            expires_at=expires_at,
        )
        if capability_call is not None:
            self.update(session, capability_call, approval_id=approval.id)
        return approval

    def approve(
        self,
        session: Session,
        approval: ApprovalRequest,
        *,
        approved_by: uuid.UUID,
        decision_payload: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        self._ensure_pending(approval)
        return self.update(
            session,
            approval,
            status=ApprovalStatus.APPROVED.value,
            approved_by=approved_by,
            decision_payload=decision_payload or {},
            decided_at=self._now(),
        )

    def reject(
        self,
        session: Session,
        approval: ApprovalRequest,
        *,
        rejected_by: uuid.UUID,
        decision_payload: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        self._ensure_pending(approval)
        payload = {"rejected_by": str(rejected_by), **(decision_payload or {})}
        return self.update(
            session,
            approval,
            status=ApprovalStatus.REJECTED.value,
            approved_by=rejected_by,
            decision_payload=payload,
            decided_at=self._now(),
        )

    def cancel(self, session: Session, approval: ApprovalRequest, *, reason: str = "cancelled") -> ApprovalRequest:
        self._ensure_pending(approval)
        return self.update(
            session,
            approval,
            status=ApprovalStatus.CANCELLED.value,
            decision_payload={"reason": reason},
            decided_at=self._now(),
        )

    def _ensure_pending(self, approval: ApprovalRequest) -> None:
        status = self._status(approval.status)
        if status != ApprovalStatus.PENDING:
            raise FailException(f"Approval request is not pending: {status.value}")

    @staticmethod
    def _status(status: ApprovalStatus | str) -> ApprovalStatus:
        try:
            return status if isinstance(status, ApprovalStatus) else ApprovalStatus(status)
        except ValueError as exc:
            raise FailException(f"Unknown approval status: {status}") from exc

    @staticmethod
    def _now() -> datetime:
        return datetime.now()

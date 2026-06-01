from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApprovalDecisionRequest(BaseModel):
    decision_payload: dict = Field(default_factory=dict)


class ApprovalResponse(BaseModel):
    id: UUID
    task_id: UUID
    step_id: UUID | None
    capability_call_id: UUID | None
    action_type: str
    title: str
    summary: str
    proposed_payload: dict
    risk_level: str
    status: str
    approver_policy: dict
    approved_by: UUID | None
    decision_payload: dict
    expires_at: datetime | None

    @classmethod
    def from_approval(cls, approval) -> "ApprovalResponse":  # noqa: ANN001
        return cls(
            id=approval.id,
            task_id=approval.task_id,
            step_id=approval.step_id,
            capability_call_id=approval.capability_call_id,
            action_type=approval.action_type,
            title=approval.title,
            summary=approval.summary,
            proposed_payload=approval.proposed_payload,
            risk_level=approval.risk_level,
            status=approval.status,
            approver_policy=approval.approver_policy,
            approved_by=approval.approved_by,
            decision_payload=approval.decision_payload,
            expires_at=approval.expires_at,
        )

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TraceEventResponse(BaseModel):
    id: UUID
    trace_id: str
    task_id: UUID | None
    plan_id: UUID | None
    step_id: UUID | None
    worker_call_id: UUID | None
    capability_call_id: UUID | None
    approval_id: UUID | None
    event_type: str
    payload: dict
    token_count: int
    cost: float
    latency: float
    created_at: datetime

    @classmethod
    def from_event(cls, event) -> "TraceEventResponse":  # noqa: ANN001
        return cls(
            id=event.id,
            trace_id=event.trace_id,
            task_id=event.task_id,
            plan_id=event.plan_id,
            step_id=event.step_id,
            worker_call_id=event.worker_call_id,
            capability_call_id=event.capability_call_id,
            approval_id=event.approval_id,
            event_type=event.event_type,
            payload=event.payload,
            token_count=event.token_count,
            cost=float(event.cost or 0),
            latency=float(event.latency or 0),
            created_at=event.created_at,
        )

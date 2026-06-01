import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.task import AgentPlan, AgentStep, AgentTask, CapabilityCall, WorkerCall
from app.models.trace import TraceEvent
from app.services.base_service import BaseService


class TraceService(BaseService):
    def record(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        event_type: str,
        trace_id: str | None = None,
        task: AgentTask | None = None,
        plan: AgentPlan | None = None,
        step: AgentStep | None = None,
        worker_call: WorkerCall | None = None,
        capability_call: CapabilityCall | None = None,
        approval: ApprovalRequest | None = None,
        payload: dict[str, Any] | None = None,
        token_count: int = 0,
        cost: float = 0,
        latency: float = 0,
    ) -> TraceEvent:
        resolved_trace_id = trace_id or self.trace_id_for_task(task.id if task else None)
        return self.create(
            session,
            TraceEvent,
            tenant_id=tenant_id,
            trace_id=resolved_trace_id,
            task_id=task.id if task else None,
            plan_id=plan.id if plan else None,
            step_id=step.id if step else None,
            worker_call_id=worker_call.id if worker_call else None,
            capability_call_id=capability_call.id if capability_call else None,
            approval_id=approval.id if approval else None,
            event_type=event_type,
            payload=payload or {},
            token_count=token_count,
            cost=cost,
            latency=latency,
        )

    def list_for_trace(self, session: Session, *, tenant_id: uuid.UUID, trace_id: str) -> list[TraceEvent]:
        return (
            session.query(TraceEvent)
            .filter(TraceEvent.tenant_id == tenant_id, TraceEvent.trace_id == trace_id)
            .order_by(TraceEvent.created_at.asc())
            .all()
        )

    @staticmethod
    def trace_id_for_task(task_id: uuid.UUID | None) -> str:
        return f"task:{task_id}" if task_id else f"trace:{uuid.uuid4()}"

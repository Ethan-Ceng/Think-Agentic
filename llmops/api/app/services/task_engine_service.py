import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import FailException
from app.models.task import AgentPlan, AgentStep, AgentTask, CapabilityCall, WorkerCall
from app.services.base_service import BaseService


class TaskStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}


class TaskEngineService(BaseService):
    """Own deterministic task, step, worker call, and capability call state."""

    def create_task(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        router_agent_id: uuid.UUID,
        user_input: dict[str, Any] | None = None,
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> AgentTask:
        return self.create(
            session,
            AgentTask,
            tenant_id=tenant_id,
            session_id=session_id,
            conversation_id=conversation_id,
            router_agent_id=router_agent_id,
            user_id=user_id,
            status=TaskStatus.CREATED.value,
            user_input=user_input or {},
            final_result={},
            error_code="",
            error_message="",
            version=0,
        )

    def start_task(self, session: Session, task: AgentTask) -> AgentTask:
        return self._transition(
            session,
            task,
            allowed={TaskStatus.CREATED},
            target=TaskStatus.RUNNING,
            started_at=task.started_at or self._now(),
            version=self._next_version(task),
        )

    def wait_for_approval(self, session: Session, task: AgentTask) -> AgentTask:
        return self._transition(
            session,
            task,
            allowed={TaskStatus.RUNNING},
            target=TaskStatus.WAITING_APPROVAL,
            version=self._next_version(task),
        )

    def resume_task(self, session: Session, task: AgentTask) -> AgentTask:
        return self._transition(
            session,
            task,
            allowed={TaskStatus.WAITING_APPROVAL},
            target=TaskStatus.RUNNING,
            version=self._next_version(task),
        )

    def succeed_task(
        self,
        session: Session,
        task: AgentTask,
        *,
        final_result: dict[str, Any] | None = None,
    ) -> AgentTask:
        return self._transition(
            session,
            task,
            allowed={TaskStatus.CREATED, TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL},
            target=TaskStatus.SUCCEEDED,
            final_result=final_result or {},
            finished_at=self._now(),
            version=self._next_version(task),
        )

    def fail_task(
        self,
        session: Session,
        task: AgentTask,
        *,
        error_code: str,
        error_message: str,
        final_result: dict[str, Any] | None = None,
    ) -> AgentTask:
        return self._transition(
            session,
            task,
            allowed={TaskStatus.CREATED, TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL},
            target=TaskStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
            final_result=final_result or {},
            finished_at=self._now(),
            version=self._next_version(task),
        )

    def cancel_task(
        self,
        session: Session,
        task: AgentTask,
        *,
        error_message: str = "Task cancelled",
    ) -> AgentTask:
        return self._transition(
            session,
            task,
            allowed={TaskStatus.CREATED, TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL},
            target=TaskStatus.CANCELLED,
            error_code="cancelled",
            error_message=error_message,
            finished_at=self._now(),
            version=self._next_version(task),
        )

    def create_plan(
        self,
        session: Session,
        *,
        task: AgentTask,
        plan_json: dict[str, Any],
        risk_level: str = "low",
        schema_version: str = "router_plan_v1",
    ) -> AgentPlan:
        return self.create(
            session,
            AgentPlan,
            tenant_id=task.tenant_id,
            task_id=task.id,
            router_agent_id=task.router_agent_id,
            schema_version=schema_version,
            plan_json=plan_json,
            risk_level=risk_level,
            status=TaskStatus.CREATED.value,
        )

    def create_step(
        self,
        session: Session,
        *,
        plan: AgentPlan,
        step_key: str,
        worker_agent_id: uuid.UUID,
        dependencies: list[str] | None = None,
        input_json: dict[str, Any] | None = None,
        execution_mode: str = "sync",
        timeout_seconds: int = 120,
    ) -> AgentStep:
        return self.create(
            session,
            AgentStep,
            tenant_id=plan.tenant_id,
            task_id=plan.task_id,
            plan_id=plan.id,
            step_key=step_key,
            worker_agent_id=worker_agent_id,
            dependencies=dependencies or [],
            execution_mode=execution_mode,
            status=TaskStatus.CREATED.value,
            input_json=input_json or {},
            output_json={},
            retry_count=0,
            timeout_seconds=timeout_seconds,
        )

    def start_step(self, session: Session, step: AgentStep) -> AgentStep:
        return self._transition(
            session,
            step,
            allowed={TaskStatus.CREATED},
            target=TaskStatus.RUNNING,
            started_at=step.started_at or self._now(),
        )

    def wait_step_for_approval(self, session: Session, step: AgentStep) -> AgentStep:
        return self._transition(
            session,
            step,
            allowed={TaskStatus.RUNNING},
            target=TaskStatus.WAITING_APPROVAL,
        )

    def resume_step(self, session: Session, step: AgentStep) -> AgentStep:
        return self._transition(
            session,
            step,
            allowed={TaskStatus.WAITING_APPROVAL},
            target=TaskStatus.RUNNING,
        )

    def succeed_step(
        self,
        session: Session,
        step: AgentStep,
        *,
        output_json: dict[str, Any] | None = None,
    ) -> AgentStep:
        return self._transition(
            session,
            step,
            allowed={TaskStatus.CREATED, TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL},
            target=TaskStatus.SUCCEEDED,
            output_json=output_json or {},
            finished_at=self._now(),
        )

    def fail_step(
        self,
        session: Session,
        step: AgentStep,
        *,
        error_code: str,
        error_message: str,
    ) -> AgentStep:
        return self._transition(
            session,
            step,
            allowed={TaskStatus.CREATED, TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL},
            target=TaskStatus.FAILED,
            output_json={"error_code": error_code, "error_message": error_message},
            finished_at=self._now(),
        )

    def record_worker_call(
        self,
        session: Session,
        *,
        step: AgentStep,
        invocation_json: dict[str, Any],
    ) -> WorkerCall:
        return self.create(
            session,
            WorkerCall,
            tenant_id=step.tenant_id,
            task_id=step.task_id,
            step_id=step.id,
            worker_agent_id=step.worker_agent_id,
            invocation_json=invocation_json,
            result_json={},
            status=TaskStatus.CREATED.value,
            token_count=0,
            cost=0,
            latency=0,
        )

    def start_worker_call(self, session: Session, worker_call: WorkerCall) -> WorkerCall:
        return self._transition(
            session,
            worker_call,
            allowed={TaskStatus.CREATED},
            target=TaskStatus.RUNNING,
        )

    def complete_worker_call(
        self,
        session: Session,
        worker_call: WorkerCall,
        *,
        result_json: dict[str, Any] | None = None,
        status: TaskStatus | str = TaskStatus.SUCCEEDED,
        token_count: int = 0,
        cost: float = 0,
        latency: float = 0,
    ) -> WorkerCall:
        target = self._status(status)
        if target not in TERMINAL_STATUSES:
            raise FailException("Worker call can only complete with terminal status")
        return self._transition(
            session,
            worker_call,
            allowed={TaskStatus.CREATED, TaskStatus.RUNNING},
            target=target,
            result_json=result_json or {},
            token_count=token_count,
            cost=cost,
            latency=latency,
        )

    def record_capability_call(
        self,
        session: Session,
        *,
        step: AgentStep,
        capability_id: uuid.UUID,
        input_json: dict[str, Any],
        worker_call_id: uuid.UUID | None = None,
        risk_level: str = "low",
        approval_id: uuid.UUID | None = None,
        idempotency_key: str = "",
    ) -> CapabilityCall:
        return self.create(
            session,
            CapabilityCall,
            tenant_id=step.tenant_id,
            task_id=step.task_id,
            step_id=step.id,
            worker_call_id=worker_call_id,
            capability_id=capability_id,
            input_json=input_json,
            output_json={},
            status=TaskStatus.CREATED.value,
            risk_level=risk_level,
            approval_id=approval_id,
            idempotency_key=idempotency_key,
            latency=0,
        )

    def start_capability_call(self, session: Session, capability_call: CapabilityCall) -> CapabilityCall:
        return self._transition(
            session,
            capability_call,
            allowed={TaskStatus.CREATED},
            target=TaskStatus.RUNNING,
        )

    def wait_capability_for_approval(
        self,
        session: Session,
        capability_call: CapabilityCall,
        *,
        approval_id: uuid.UUID,
    ) -> CapabilityCall:
        return self._transition(
            session,
            capability_call,
            allowed={TaskStatus.RUNNING},
            target=TaskStatus.WAITING_APPROVAL,
            approval_id=approval_id,
        )

    def resume_capability_call(
        self,
        session: Session,
        capability_call: CapabilityCall,
    ) -> CapabilityCall:
        return self._transition(
            session,
            capability_call,
            allowed={TaskStatus.WAITING_APPROVAL},
            target=TaskStatus.RUNNING,
        )

    def complete_capability_call(
        self,
        session: Session,
        capability_call: CapabilityCall,
        *,
        output_json: dict[str, Any] | None = None,
        status: TaskStatus | str = TaskStatus.SUCCEEDED,
        approval_id: uuid.UUID | None = None,
        latency: float = 0,
    ) -> CapabilityCall:
        target = self._status(status)
        if target not in TERMINAL_STATUSES:
            raise FailException("Capability call can only complete with terminal status")
        return self._transition(
            session,
            capability_call,
            allowed={TaskStatus.CREATED, TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL},
            target=target,
            output_json=output_json or {},
            approval_id=approval_id or capability_call.approval_id,
            latency=latency,
        )

    def _transition(
        self,
        session: Session,
        model_instance: Any,
        *,
        allowed: set[TaskStatus],
        target: TaskStatus,
        **kwargs: Any,
    ) -> Any:
        current = self._status(model_instance.status)
        if current not in allowed:
            allowed_values = ", ".join(sorted(status.value for status in allowed))
            raise FailException(
                f"Invalid transition for {model_instance.__class__.__name__}: "
                f"{current.value} -> {target.value}; allowed from {allowed_values}",
            )
        return self.update(session, model_instance, status=target.value, **kwargs)

    @staticmethod
    def _status(status: TaskStatus | str) -> TaskStatus:
        try:
            return status if isinstance(status, TaskStatus) else TaskStatus(status)
        except ValueError as exc:
            raise FailException(f"Unknown task status: {status}") from exc

    @staticmethod
    def _next_version(task: AgentTask) -> int:
        return (task.version or 0) + 1

    @staticmethod
    def _now() -> datetime:
        return datetime.now()

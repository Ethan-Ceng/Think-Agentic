import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import FailException, NotFoundException
from app.domain.agent_runtime.protocols import RouterPlan, RouterPlanStep, WorkerInvocation, WorkerResult
from app.domain.agent_runtime.router_runtime import RouterRuntime
from app.domain.agent_runtime.worker_runtime import WorkerRuntime
from app.models.account import Account
from app.models.agent import Agent, AgentBinding, AgentVersion
from app.models.task import AgentPlan, AgentStep, AgentTask
from app.services.app_service import AppService
from app.services.base_service import BaseService
from app.services.task_engine_service import TaskEngineService, TaskStatus
from app.services.trace_service import TraceService


@dataclass(frozen=True)
class RouterManagerRunResult:
    task: AgentTask
    plan: AgentPlan
    steps: list[AgentStep]

    @property
    def trace_id(self) -> str:
        return TraceService.trace_id_for_task(self.task.id)


class RouterAgentManagerService(BaseService):
    """Manager-mode Router Agent service.

    This is a governance shell over existing Worker/App descriptors. It creates
    Router-owned task state and plan steps, but does not replace legacy worker runtimes.
    """

    def __init__(
        self,
        *,
        task_engine: TaskEngineService | None = None,
        router_runtime: RouterRuntime | None = None,
        worker_runtime: WorkerRuntime | None = None,
        app_service: AppService | None = None,
        trace_service: TraceService | None = None,
    ) -> None:
        self.task_engine = task_engine or TaskEngineService()
        self.router_runtime = router_runtime or RouterRuntime()
        self.app_service = app_service or AppService()
        self.worker_runtime = worker_runtime or WorkerRuntime(app_service=self.app_service)
        self.trace_service = trace_service or TraceService()

    def create_router_agent(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        name: str,
        description: str = "",
        created_by: uuid.UUID | None = None,
        model_config: dict[str, Any] | None = None,
        prompt_config: dict[str, Any] | None = None,
        router_config: dict[str, Any] | None = None,
        policies: dict[str, Any] | None = None,
        status: str = "draft",
    ) -> tuple[Agent, AgentVersion]:
        agent = self.create(
            session,
            Agent,
            tenant_id=tenant_id,
            created_by=created_by,
            name=name,
            icon="",
            description=description,
            runtime_type="router",
            product_category="router",
            status=status,
            visibility_scope={},
            target_ref_type="",
            target_ref_id="",
        )
        version = self.create(
            session,
            AgentVersion,
            tenant_id=tenant_id,
            agent_id=agent.id,
            version=1,
            config_type="router",
            model_config=model_config or {},
            prompt_config=prompt_config or {},
            router_config=router_config or {"mode": "manager"},
            worker_config={},
            capability_bindings=[],
            policies=policies or {},
            output_schema={"type": "object"},
        )
        self.update(session, agent, draft_version_id=version.id)
        if status == "published":
            self.update(session, agent, published_version_id=version.id)
        return agent, version

    def create_worker_agent_from_app(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        app_id: uuid.UUID,
        account: Account,
        status: str = "published",
    ) -> tuple[Agent, AgentVersion]:
        descriptor = self.app_service.app_to_worker_agent_descriptor(session, app_id, account)
        existing = (
            session.query(Agent)
            .filter(
                Agent.tenant_id == tenant_id,
                Agent.runtime_type == "worker",
                Agent.target_ref_type == descriptor.target_ref_type,
                Agent.target_ref_id == descriptor.target_ref_id,
            )
            .one_or_none()
        )
        version_payload = descriptor.to_version_payload()
        if existing is not None:
            version = self.create(
                session,
                AgentVersion,
                tenant_id=tenant_id,
                agent_id=existing.id,
                version=self._next_agent_version(session, existing.id),
                config_type="worker",
                **version_payload,
            )
            self.update(
                session,
                existing,
                name=descriptor.name,
                icon=descriptor.icon,
                description=descriptor.description,
                status=status,
                visibility_scope=descriptor.visibility_scope,
                draft_version_id=version.id,
                published_version_id=version.id if status == "published" else existing.published_version_id,
            )
            return existing, version

        agent = self.create(
            session,
            Agent,
            tenant_id=tenant_id,
            created_by=account.id,
            name=descriptor.name,
            icon=descriptor.icon,
            description=descriptor.description,
            runtime_type="worker",
            product_category=descriptor.product_category,
            status=status,
            visibility_scope=descriptor.visibility_scope,
            target_ref_type=descriptor.target_ref_type,
            target_ref_id=descriptor.target_ref_id,
        )
        version = self.create(
            session,
            AgentVersion,
            tenant_id=tenant_id,
            agent_id=agent.id,
            version=1,
            config_type="worker",
            **version_payload,
        )
        self.update(session, agent, draft_version_id=version.id)
        if status == "published":
            self.update(session, agent, published_version_id=version.id)
        return agent, version

    def bind_worker(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        router_agent_id: uuid.UUID,
        worker_agent_id: uuid.UUID,
        priority: int = 0,
        conditions: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> AgentBinding:
        router = self.get_router_agent(session, tenant_id, router_agent_id)
        worker = self.get_worker_agent(session, tenant_id, worker_agent_id)

        binding = (
            session.query(AgentBinding)
            .filter(
                AgentBinding.tenant_id == tenant_id,
                AgentBinding.router_agent_id == router.id,
                AgentBinding.worker_agent_id == worker.id,
            )
            .one_or_none()
        )
        if binding is not None:
            return self.update(
                session,
                binding,
                enabled=enabled,
                priority=priority,
                conditions=conditions or {},
            )

        return self.create(
            session,
            AgentBinding,
            tenant_id=tenant_id,
            router_agent_id=router.id,
            worker_agent_id=worker.id,
            enabled=enabled,
            priority=priority,
            conditions=conditions or {},
        )

    def list_bound_workers(self, session: Session, *, tenant_id: uuid.UUID, router_agent_id: uuid.UUID) -> list[Agent]:
        self.get_router_agent(session, tenant_id, router_agent_id)
        return (
            session.query(Agent)
            .join(AgentBinding, AgentBinding.worker_agent_id == Agent.id)
            .filter(
                AgentBinding.tenant_id == tenant_id,
                AgentBinding.router_agent_id == router_agent_id,
                AgentBinding.enabled.is_(True),
                Agent.tenant_id == tenant_id,
                Agent.runtime_type == "worker",
                Agent.status.in_(["published", "active"]),
            )
            .order_by(AgentBinding.priority.desc(), Agent.updated_at.desc())
            .all()
        )

    def build_manager_plan(
        self,
        *,
        router_agent: Agent,
        workers: list[Agent],
        user_input: dict[str, Any],
        requested_worker_ids: list[uuid.UUID] | None = None,
    ) -> RouterPlan:
        selected_workers = self._select_workers(workers, requested_worker_ids)
        if not selected_workers:
            raise FailException("Router agent has no available worker bindings")

        query = str(user_input.get("query") or user_input.get("input") or user_input.get("message") or "")
        plan = RouterPlan(
            router_id=str(router_agent.id),
            user_intent=query,
            risk_assessment={"risk_level": "low", "source": "manager_rule_v1"},
            steps=[
                RouterPlanStep(
                    step_id=f"worker_{index + 1}",
                    worker_id=str(worker.id),
                    task=query or f"Run worker {worker.name}",
                    dependencies=[],
                    execution_mode="sync",
                    required_approval=False,
                )
                for index, worker in enumerate(selected_workers)
            ],
            final_response_policy={"mode": "summarize_worker_results"},
        )
        allowed_worker_ids = {str(worker.id) for worker in selected_workers}
        return self.router_runtime.validate_plan(plan, allowed_worker_ids=allowed_worker_ids)

    def create_manager_task_from_plan(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        router_agent_id: uuid.UUID,
        plan: RouterPlan,
        user_input: dict[str, Any],
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> RouterManagerRunResult:
        self.router_runtime.validate_plan(plan)
        task = self.task_engine.create_task(
            session,
            tenant_id=tenant_id,
            router_agent_id=router_agent_id,
            user_input=user_input,
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )
        self.task_engine.start_task(session, task)
        persisted_plan = self.task_engine.create_plan(
            session,
            task=task,
            plan_json=plan.model_dump(mode="json"),
            risk_level=str(plan.risk_assessment.get("risk_level") or "low"),
            schema_version=plan.schema_version,
        )
        steps = [
            self.task_engine.create_step(
                session,
                plan=persisted_plan,
                step_key=step.step_id,
                worker_agent_id=uuid.UUID(step.worker_id),
                dependencies=step.dependencies,
                input_json={"task": step.task, "user_input": user_input},
                execution_mode=step.execution_mode,
            )
            for step in plan.steps
        ]
        if any(step.required_approval for step in plan.steps):
            self.task_engine.wait_for_approval(session, task)
        result = RouterManagerRunResult(task=task, plan=persisted_plan, steps=steps)
        self.trace_service.record(
            session,
            tenant_id=tenant_id,
            event_type="router.manager_run.created",
            task=task,
            plan=persisted_plan,
            payload={
                "router_agent_id": str(router_agent_id),
                "step_count": len(steps),
                "risk_level": persisted_plan.risk_level,
                "status": task.status,
            },
        )
        return result

    def execute_manager_run_steps(
        self,
        session: Session,
        *,
        run: RouterManagerRunResult,
        account: Account,
    ) -> RouterManagerRunResult:
        step_outputs = []
        for step in run.steps:
            self.task_engine.start_step(session, step)
            worker = self.get_worker_agent(session, run.task.tenant_id, step.worker_agent_id)
            invocation = self._build_worker_invocation(run=run, step=step, worker=worker, account=account)
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="router.step.started",
                task=run.task,
                plan=run.plan,
                step=step,
                payload={"step_key": step.step_key, "worker_agent_id": str(worker.id)},
            )
            worker_call = self.task_engine.record_worker_call(
                session,
                step=step,
                invocation_json=invocation.model_dump(mode="json"),
            )
            self.task_engine.start_worker_call(session, worker_call)
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="worker.call.started",
                task=run.task,
                plan=run.plan,
                step=step,
                worker_call=worker_call,
                payload={
                    "worker_agent_id": str(worker.id),
                    "target_ref_type": worker.target_ref_type,
                    "target_ref_id": worker.target_ref_id,
                    "execution_agent_type": invocation.execution_policy.get("execution_agent_type"),
                },
            )
            try:
                worker_result = self._invoke_worker(session, worker, invocation, account)
            except Exception as exc:
                self.task_engine.complete_worker_call(
                    session,
                    worker_call,
                    status=TaskStatus.FAILED,
                    result_json={"error": str(exc)},
                )
                self.task_engine.fail_step(
                    session,
                    step,
                    error_code="worker_execution_failed",
                    error_message=str(exc),
                )
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code="worker_execution_failed",
                    error_message=str(exc),
                    final_result={"step_key": step.step_key},
                )
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="worker.call.failed",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    worker_call=worker_call,
                    payload={
                        "step_key": step.step_key,
                        "worker_agent_id": str(worker.id),
                        "error": str(exc),
                    },
                )
                return run

            output = self._worker_result_to_output(worker_result)
            self._record_agent_events(session, run=run, step=step, worker_call=worker_call, worker_result=worker_result)
            if worker_result.status != TaskStatus.SUCCEEDED.value:
                self.task_engine.complete_worker_call(
                    session,
                    worker_call,
                    status=self._worker_terminal_status(worker_result),
                    result_json=output,
                )
                self.task_engine.fail_step(
                    session,
                    step,
                    error_code=worker_result.error_code or "worker_execution_failed",
                    error_message=worker_result.summary or "Worker execution failed",
                )
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code=worker_result.error_code or "worker_execution_failed",
                    error_message=worker_result.summary or "Worker execution failed",
                    final_result={"step_key": step.step_key, "worker_result": output},
                )
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="worker.call.failed",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    worker_call=worker_call,
                    payload={
                        "step_key": step.step_key,
                        "worker_agent_id": str(worker.id),
                        "status": worker_result.status,
                        "error_code": worker_result.error_code,
                        "summary": worker_result.summary,
                    },
                )
                return run

            self.task_engine.complete_worker_call(session, worker_call, result_json=output)
            self.task_engine.succeed_step(session, step, output_json=output)
            step_outputs.append({"step_key": step.step_key, "worker_agent_id": str(worker.id), "output": output})
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="worker.call.succeeded",
                task=run.task,
                plan=run.plan,
                step=step,
                worker_call=worker_call,
                payload={
                    "step_key": step.step_key,
                    "worker_agent_id": str(worker.id),
                    "answer_length": len(str(output.get("answer") or "")),
                    "worker_result_status": worker_result.status,
                },
            )
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="router.step.succeeded",
                task=run.task,
                plan=run.plan,
                step=step,
                payload={"step_key": step.step_key},
            )

        self.task_engine.succeed_task(session, run.task, final_result={"steps": step_outputs})
        self.trace_service.record(
            session,
            tenant_id=run.task.tenant_id,
            event_type="router.manager_run.succeeded",
            task=run.task,
            plan=run.plan,
            payload={"step_count": len(step_outputs)},
        )
        return run

    def create_manager_run(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        router_agent_id: uuid.UUID,
        user_input: dict[str, Any],
        requested_worker_ids: list[uuid.UUID] | None = None,
        user_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> RouterManagerRunResult:
        router = self.get_router_agent(session, tenant_id, router_agent_id)
        workers = self.list_bound_workers(session, tenant_id=tenant_id, router_agent_id=router_agent_id)
        plan = self.build_manager_plan(
            router_agent=router,
            workers=workers,
            user_input=user_input,
            requested_worker_ids=requested_worker_ids,
        )
        return self.create_manager_task_from_plan(
            session,
            tenant_id=tenant_id,
            router_agent_id=router_agent_id,
            plan=plan,
            user_input=user_input,
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

    def get_router_agent(self, session: Session, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
        agent = self.get(session, Agent, agent_id)
        if agent is None or agent.tenant_id != tenant_id or agent.runtime_type != "router":
            raise NotFoundException("Router agent not found")
        return agent

    def get_worker_agent(self, session: Session, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
        agent = self.get(session, Agent, agent_id)
        if agent is None or agent.tenant_id != tenant_id or agent.runtime_type != "worker":
            raise NotFoundException("Worker agent not found")
        return agent

    @staticmethod
    def _select_workers(workers: list[Agent], requested_worker_ids: list[uuid.UUID] | None) -> list[Agent]:
        if not requested_worker_ids:
            return workers
        requested = {str(worker_id) for worker_id in requested_worker_ids}
        return [worker for worker in workers if str(worker.id) in requested]

    def _build_worker_invocation(
        self,
        *,
        run: RouterManagerRunResult,
        step: AgentStep,
        worker: Agent,
        account: Account,
    ) -> WorkerInvocation:
        return WorkerInvocation(
            trace_id=run.trace_id,
            tenant_id=run.task.tenant_id,
            account_id=account.id,
            task_id=run.task.id,
            plan_id=run.plan.id,
            step_id=step.id,
            router_id=str(run.task.router_agent_id),
            worker_id=str(worker.id),
            user={
                "id": str(account.id),
                "name": account.name,
                "email": account.email,
            },
            task=step.input_json,
            context={
                "session_id": str(run.task.session_id) if run.task.session_id else None,
                "conversation_id": str(run.task.conversation_id) if run.task.conversation_id else None,
                "worker_name": worker.name,
                "input_files": [],
                "artifacts": [],
            },
            execution_policy={
                "execution_agent_type": self._worker_execution_agent_type(worker),
                "target_ref_type": worker.target_ref_type,
                "target_ref_id": worker.target_ref_id,
            },
        )

    def _invoke_worker(
        self,
        session: Session,
        worker: Agent,
        invocation: WorkerInvocation,
        account: Account,
    ) -> WorkerResult:
        return self.worker_runtime.invoke(
            invocation,
            session=session,
            worker=worker,
            account=account,
        )

    def _record_agent_events(
        self,
        session: Session,
        *,
        run: RouterManagerRunResult,
        step: AgentStep,
        worker_call,
        worker_result: WorkerResult,
    ) -> None:
        for event in worker_result.events:
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type=f"worker.event.{event.event_type}",
                task=run.task,
                plan=run.plan,
                step=step,
                worker_call=worker_call,
                payload=event.model_dump(mode="json"),
            )

    @staticmethod
    def _worker_execution_agent_type(worker: Agent) -> str:
        if worker.target_ref_type == "app":
            return "react_worker"
        return "react_worker"

    @staticmethod
    def _worker_result_to_output(worker_result: WorkerResult) -> dict[str, Any]:
        output = worker_result.model_dump(mode="json")
        output["answer"] = str(worker_result.data.get("answer") or worker_result.summary or "")
        return output

    @staticmethod
    def _worker_terminal_status(worker_result: WorkerResult) -> TaskStatus:
        try:
            status = TaskStatus(worker_result.status)
        except ValueError:
            return TaskStatus.FAILED
        terminal_statuses = {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        return status if status in terminal_statuses else TaskStatus.FAILED

    @staticmethod
    def _next_agent_version(session: Session, agent_id: uuid.UUID) -> int:
        max_version = (
            session.query(AgentVersion.version)
            .filter(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version.desc())
            .limit(1)
            .scalar()
        )
        return int(max_version or 0) + 1

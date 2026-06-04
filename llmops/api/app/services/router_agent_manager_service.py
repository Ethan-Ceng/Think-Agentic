import time
import uuid
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.agent import AgentThought, QueueEvent
from app.core.conversation import InvokeFrom, MessageStatus
from app.core.exceptions import FailException, NotFoundException
from app.core.memory.token_buffer_memory import TokenBufferMemory
from app.domain.agent_runtime.planner import PlannerInput, PlannerWorkerDescriptor, RouterPlannerAgent
from app.domain.agent_runtime.protocols import ArtifactRef, RouterPlan, RouterPlanStep, WorkerInvocation, WorkerResult
from app.domain.agent_runtime.router_runtime import RouterRuntime
from app.domain.agent_runtime.worker_runtime import WorkerRuntime
from app.models.account import Account
from app.models.agent import Agent, AgentBinding, AgentVersion
from app.models.app import App
from app.models.conversation import Message
from app.models.task import AgentPlan, AgentStep, AgentTask
from app.services.agent_capability_service import AgentCapabilityService
from app.services.app_service import AppService
from app.services.base_service import BaseService
from app.services.file_service import FileService
from app.services.language_model_service import LanguageModelService
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


@dataclass(frozen=True)
class PlannerDebugStreamEvent:
    thought: AgentThought
    conversation_id: uuid.UUID
    message_id: uuid.UUID


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
        planner_agent: RouterPlannerAgent | None = None,
        app_service: AppService | None = None,
        capability_service: AgentCapabilityService | None = None,
        file_service: FileService | None = None,
        language_model_service: LanguageModelService | None = None,
        trace_service: TraceService | None = None,
    ) -> None:
        self.task_engine = task_engine or TaskEngineService()
        self.router_runtime = router_runtime or RouterRuntime()
        self.app_service = app_service or AppService()
        self.worker_runtime = worker_runtime or WorkerRuntime(app_service=self.app_service)
        self.planner_agent = planner_agent or RouterPlannerAgent()
        self.capability_service = capability_service or AgentCapabilityService()
        self.file_service = file_service or FileService()
        self.language_model_service = language_model_service or LanguageModelService()
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

    def create_planner_agent_from_app(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        app_id: uuid.UUID,
        account: Account,
        status: str | None = None,
    ) -> tuple[Agent, AgentVersion]:
        app = self.app_service.get_app(session, app_id, account)
        if (getattr(app, "agent_type", "worker") or "worker") != "planner":
            raise FailException("Only PlannerAgent apps can be used as planner agents")
        draft = self.app_service.get_or_create_draft_config(session, app)
        config = self.app_service._config_to_dict(draft)
        resolved_status = status or app.status or "draft"
        existing = (
            session.query(Agent)
            .filter(
                Agent.tenant_id == tenant_id,
                Agent.runtime_type == "router",
                Agent.target_ref_type == "app",
                Agent.target_ref_id == str(app.id),
            )
            .one_or_none()
        )
        existing_routing_policy = self._routing_policy_for_agent(session, existing) if existing is not None else {}
        version_payload = {
            "model_config": config["model_config"],
            "prompt_config": {
                "preset_prompt": config.get("preset_prompt") or "",
                "opening_statement": config.get("opening_statement") or "",
                "opening_questions": config.get("opening_questions") or [],
                "review_config": config.get("review_config") or {},
            },
            "router_config": {
                "mode": "manager",
                "planner": "llm_planner_v1",
                "max_steps": 5,
                "allow_parallel": False,
                "allow_required_approval": False,
                "routing_policy": existing_routing_policy
                or self.capability_service.validate_routing_policy({})["routing_policy"],
            },
            "worker_config": {},
            "capability_bindings": [],
            "policies": {},
            "output_schema": {"type": "object"},
        }
        if existing is not None:
            version = self.create(
                session,
                AgentVersion,
                tenant_id=tenant_id,
                agent_id=existing.id,
                version=self._next_agent_version(session, existing.id),
                config_type="router",
                **version_payload,
            )
            self.update(
                session,
                existing,
                name=app.name,
                icon=app.icon,
                description=app.description or "",
                status=resolved_status,
                product_category="planner",
                visibility_scope={"account_id": str(app.account_id)},
                target_ref_type="app",
                target_ref_id=str(app.id),
                draft_version_id=version.id,
                published_version_id=version.id if resolved_status == "published" else existing.published_version_id,
            )
            return existing, version

        agent = self.create(
            session,
            Agent,
            tenant_id=tenant_id,
            created_by=account.id,
            name=app.name,
            icon=app.icon or "",
            description=app.description or "",
            runtime_type="router",
            product_category="planner",
            status=resolved_status,
            visibility_scope={"account_id": str(app.account_id)},
            target_ref_type="app",
            target_ref_id=str(app.id),
        )
        version = self.create(
            session,
            AgentVersion,
            tenant_id=tenant_id,
            agent_id=agent.id,
            version=1,
            config_type="router",
            **version_payload,
        )
        self.update(session, agent, draft_version_id=version.id)
        if resolved_status == "published":
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
        existing_summary = self._capability_summary_for_agent(session, existing) if existing is not None else {}
        version_payload = self.capability_service.attach_summary_to_version_payload(
            agent_payload=descriptor.to_agent_payload(),
            version_payload=descriptor.to_version_payload(),
            session=session,
            account=account,
            preserve_manual_overrides_from=existing_summary,
        )
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

    def bind_worker_app_to_planner(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        worker_app_id: uuid.UUID,
        account: Account,
        priority: int = 0,
        conditions: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> AgentBinding:
        planner_agent, _ = self.create_planner_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=planner_app_id,
            account=account,
        )
        worker_agent, _ = self.create_worker_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=worker_app_id,
            account=account,
            status="published",
        )
        return self.bind_worker(
            session,
            tenant_id=account.id,
            router_agent_id=planner_agent.id,
            worker_agent_id=worker_agent.id,
            priority=priority,
            conditions=conditions,
            enabled=enabled,
        )

    def list_planner_worker_bindings(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        account: Account,
    ) -> list[dict[str, Any]]:
        planner_agent, _ = self.create_planner_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=planner_app_id,
            account=account,
        )
        rows = (
            session.query(AgentBinding, Agent)
            .join(Agent, AgentBinding.worker_agent_id == Agent.id)
            .filter(
                AgentBinding.tenant_id == account.id,
                AgentBinding.router_agent_id == planner_agent.id,
                Agent.tenant_id == account.id,
                Agent.runtime_type == "worker",
            )
            .order_by(AgentBinding.priority.desc(), Agent.updated_at.desc())
            .all()
        )
        worker_app_map = self._worker_app_map(session, [worker for _, worker in rows], account.id)
        return [
            {
                "id": str(binding.id),
                "enabled": binding.enabled,
                "priority": binding.priority,
                "conditions": binding.conditions or {},
                "worker_agent": self._agent_payload(worker),
                "worker_app": self._app_payload(worker_app_map.get(str(worker.target_ref_id))),
                "capability_summary": self.capability_service.ensure_worker_capability_summary(
                    session,
                    worker,
                    account=account,
                ),
                "created_at": self._timestamp(binding.created_at),
                "updated_at": self._timestamp(binding.updated_at),
            }
            for binding, worker in rows
        ]

    def update_planner_worker_binding(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        binding_id: uuid.UUID,
        account: Account,
        enabled: bool,
        priority: int,
        conditions: dict[str, Any] | None = None,
    ) -> AgentBinding:
        planner_agent, _ = self.create_planner_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=planner_app_id,
            account=account,
        )
        binding = self._get_planner_binding(session, account.id, planner_agent.id, binding_id)
        return self.update(session, binding, enabled=enabled, priority=priority, conditions=conditions or {})

    def delete_planner_worker_binding(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        binding_id: uuid.UUID,
        account: Account,
    ) -> AgentBinding:
        planner_agent, _ = self.create_planner_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=planner_app_id,
            account=account,
        )
        binding = self._get_planner_binding(session, account.id, planner_agent.id, binding_id)
        return self.delete(session, binding)

    def create_planner_debug_run(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        query: str,
        account: Account,
        requested_worker_app_ids: list[uuid.UUID] | None = None,
        input_file_ids: list[str] | None = None,
        image_urls: list[str] | None = None,
        raise_on_error: bool = True,
    ) -> dict[str, Any]:
        app = self.app_service.get_app(session, planner_app_id, account)
        if (getattr(app, "agent_type", "worker") or "worker") != "planner":
            raise FailException("Only PlannerAgent apps can run planner debug")
        planner_agent, _ = self.create_planner_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=planner_app_id,
            account=account,
        )
        conversation = self.app_service.get_or_create_debug_conversation(session, app, account)
        message = self.create(
            session,
            Message,
            app_id=app.id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.DEBUGGER.value,
            created_by=account.id,
            query=query,
            image_urls=image_urls or [],
            status=MessageStatus.NORMAL.value,
        )
        recent_history = self._debug_recent_history(session, app, conversation.id)
        requested_worker_ids = self._requested_worker_agent_ids(
            session,
            planner_agent_id=planner_agent.id,
            account=account,
            requested_worker_app_ids=requested_worker_app_ids or [],
        )
        user_input = {
            "query": query,
            "recent_history": recent_history,
            "input_file_ids": input_file_ids or [],
            "message_id": str(message.id),
            "conversation_id": str(conversation.id),
            "context": {
                "message_id": str(message.id),
                "conversation_id": str(conversation.id),
                "invoke_from": InvokeFrom.DEBUGGER.value,
            },
        }
        run = None
        try:
            run = self.create_manager_run(
                session,
                tenant_id=account.id,
                router_agent_id=planner_agent.id,
                user_input=user_input,
                requested_worker_ids=requested_worker_ids,
                user_id=account.id,
                conversation_id=conversation.id,
                account=account,
            )
            self.execute_manager_run_steps(session, run=run, account=account)
            answer = self._task_answer(run.task)
            if run.task.status == TaskStatus.FAILED.value:
                self.update(
                    session,
                    message,
                    status=MessageStatus.ERROR.value,
                    error=run.task.error_message,
                    answer=answer,
                )
            else:
                self.update(session, message, answer=answer, status=MessageStatus.NORMAL.value)
        except Exception as exc:
            self.update(session, message, status=MessageStatus.ERROR.value, error=str(exc), answer="")
            if raise_on_error:
                raise
            return {
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "task_id": str(run.task.id) if run is not None else "",
                "status": MessageStatus.ERROR.value,
                "answer": "",
                "error": str(exc),
            }

        return {
            "conversation_id": str(conversation.id),
            "message_id": str(message.id),
            "task_id": str(run.task.id),
            "status": run.task.status,
            "answer": message.answer,
            "error": message.error,
        }

    def stream_planner_debug_run(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        query: str,
        account: Account,
        requested_worker_app_ids: list[uuid.UUID] | None = None,
        input_file_ids: list[str] | None = None,
        image_urls: list[str] | None = None,
        on_task_created: Callable[[uuid.UUID], None] | None = None,
        is_stopped: Callable[[uuid.UUID], bool] | None = None,
    ) -> Generator[PlannerDebugStreamEvent, None, None]:
        app = self.app_service.get_app(session, planner_app_id, account)
        if (getattr(app, "agent_type", "worker") or "worker") != "planner":
            raise FailException("Only PlannerAgent apps can run planner debug")

        planner_agent, _ = self.create_planner_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=planner_app_id,
            account=account,
        )
        conversation = self.app_service.get_or_create_debug_conversation(session, app, account)
        message = self.create(
            session,
            Message,
            app_id=app.id,
            conversation_id=conversation.id,
            invoke_from=InvokeFrom.DEBUGGER.value,
            created_by=account.id,
            query=query,
            image_urls=image_urls or [],
            status=MessageStatus.NORMAL.value,
        )
        recent_history = self._debug_recent_history(session, app, conversation.id)
        requested_worker_ids = self._requested_worker_agent_ids(
            session,
            planner_agent_id=planner_agent.id,
            account=account,
            requested_worker_app_ids=requested_worker_app_ids or [],
        )
        user_input = {
            "query": query,
            "recent_history": recent_history,
            "image_urls": image_urls or [],
            "input_file_ids": input_file_ids or [],
            "message_id": str(message.id),
            "conversation_id": str(conversation.id),
            "context": {
                "message_id": str(message.id),
                "conversation_id": str(conversation.id),
                "invoke_from": InvokeFrom.DEBUGGER.value,
            },
        }
        task = self.task_engine.create_task(
            session,
            tenant_id=account.id,
            router_agent_id=planner_agent.id,
            user_input=user_input,
            user_id=account.id,
            conversation_id=conversation.id,
        )
        self.task_engine.start_task(session, task)
        if on_task_created is not None:
            on_task_created(task.id)

        started_at = time.perf_counter()

        def emit(
            event: QueueEvent,
            *,
            thought: str = "",
            observation: str = "",
            tool: str = "",
            tool_input: dict[str, Any] | None = None,
            answer: str = "",
            total_token_count: int = 0,
        ) -> PlannerDebugStreamEvent:
            return PlannerDebugStreamEvent(
                thought=AgentThought(
                    id=uuid.uuid4(),
                    task_id=task.id,
                    event=event,
                    thought=thought,
                    observation=observation,
                    tool=tool,
                    tool_input=tool_input or {},
                    answer=answer,
                    total_token_count=total_token_count,
                    latency=time.perf_counter() - started_at,
                ),
                conversation_id=conversation.id,
                message_id=message.id,
            )

        def stopped() -> bool:
            return bool(is_stopped is not None and is_stopped(task.id))

        def cancel_task() -> PlannerDebugStreamEvent:
            if task.status not in {TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}:
                self.task_engine.cancel_task(session, task, error_message="PlannerAgent debug stopped")
                self.trace_service.record(
                    session,
                    tenant_id=task.tenant_id,
                    event_type="router.manager_run.cancelled",
                    task=task,
                    payload={"reason": "debug_stop_requested"},
                )
            return emit(QueueEvent.STOP, observation="PlannerAgent 调试已停止")

        workers = self.list_bound_workers(session, tenant_id=account.id, router_agent_id=planner_agent.id)
        selected_workers = self._select_workers(workers, requested_worker_ids)
        self.trace_service.record(
            session,
            tenant_id=account.id,
            event_type="planner.started",
            task=task,
            payload={
                "router_agent_id": str(planner_agent.id),
                "worker_count": len(selected_workers),
                "max_steps": 5,
                "has_input_files": any(self._iter_input_file_ids(user_input)),
            },
        )
        if not selected_workers:
            error = "Router agent has no available worker bindings"
            self.task_engine.fail_task(
                session,
                task,
                error_code="worker_bindings_missing",
                error_message=error,
                final_result={"error": error},
            )
            yield emit(QueueEvent.ERROR, observation=error)
            return

        yield emit(
            QueueEvent.AGENT_THOUGHT,
            thought=f"PlannerAgent 已启动，已选择 {len(selected_workers)} 个 WorkerAgent。",
        )
        if stopped():
            yield cancel_task()
            return

        yield emit(
            QueueEvent.AGENT_ACTION,
            observation="正在生成执行计划",
            tool="planner.generate_plan",
            tool_input={
                "workers": [
                    {"id": str(worker.id), "name": worker.name, "description": worker.description or ""}
                    for worker in selected_workers
                ],
                "query": query,
            },
        )
        if stopped():
            yield cancel_task()
            return

        try:
            plan = self._build_planner_or_fallback_plan(
                session,
                task=task,
                router_agent=planner_agent,
                workers=selected_workers,
                user_input=user_input,
                account=account,
            )
            preflight_result = self._preflight_plan(
                session,
                task=task,
                router_agent=planner_agent,
                workers=selected_workers,
                plan=plan,
                user_input=user_input,
                account=account,
            )
            run = self._persist_manager_plan_for_task(
                session,
                task=task,
                plan=plan,
                user_input=user_input,
                preflight_result=preflight_result,
            )
            self._record_manager_run_created(session, run)
        except Exception as exc:  # noqa: BLE001
            self.task_engine.fail_task(
                session,
                task,
                error_code="planner_execution_failed",
                error_message=str(exc),
                final_result={"error": str(exc)},
            )
            yield emit(QueueEvent.ERROR, observation=str(exc))
            return

        if preflight_result.get("status") == "failed":
            error_code, user_message = self._first_preflight_error(preflight_result)
            self._fail_run_for_preflight(session, run=run, error_code=error_code, user_message=user_message)
            yield emit(QueueEvent.ERROR, observation=user_message, tool="router.capability_preflight")
            return

        yield emit(
            QueueEvent.AGENT_ACTION,
            observation=self._planner_plan_observation(plan, selected_workers),
            tool="planner.plan",
            tool_input={
                "source": plan.risk_assessment.get("source") or "",
                "steps": [
                    {
                        "step_id": step.step_id,
                        "worker_id": step.worker_id,
                        "task": step.task,
                        "dependencies": step.dependencies,
                    }
                    for step in plan.steps
                ],
            },
        )
        if stopped():
            yield cancel_task()
            return

        try:
            input_files = self._input_file_refs(session, account, run.task.user_input)
        except Exception as exc:
            self.task_engine.fail_task(
                session,
                run.task,
                error_code="input_files_invalid",
                error_message=str(exc),
                final_result={"error": str(exc)},
            )
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="router.input_files.failed",
                task=run.task,
                plan=run.plan,
                payload={"error": str(exc)},
            )
            yield emit(QueueEvent.ERROR, observation=str(exc))
            return

        step_outputs = []
        accumulated_artifacts: list[dict[str, Any]] = []
        for step in run.steps:
            if stopped():
                yield cancel_task()
                return

            self.task_engine.start_step(session, step)
            if self._step_preflight_failed(step):
                error_code, user_message = self._step_preflight_error(step)
                self.task_engine.fail_step(session, step, error_code=error_code, error_message=user_message)
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code=error_code,
                    error_message=user_message,
                    final_result={"step_key": step.step_key, "preflight": step.input_json.get("preflight")},
                )
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="router.capability_preflight.failed",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    payload=step.input_json.get("preflight") or {},
                )
                yield emit(QueueEvent.ERROR, observation=user_message, tool="router.capability_preflight")
                return
            worker = self.get_worker_agent(session, run.task.tenant_id, step.worker_agent_id)
            task_text = str((step.input_json or {}).get("task") or "")
            yield emit(
                QueueEvent.AGENT_ACTION,
                observation=f"开始执行 {step.step_key}: {self._truncate(task_text, 500)}",
                tool=worker.name,
                tool_input={
                    "step_key": step.step_key,
                    "worker_agent_id": str(worker.id),
                    "worker_name": worker.name,
                    "task": task_text,
                },
            )

            invocation = self._build_worker_invocation(
                run=run,
                step=step,
                worker=worker,
                account=account,
                input_files=input_files,
                artifacts=accumulated_artifacts,
            )
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
                worker_result = self._with_registered_artifacts(
                    session,
                    account=account,
                    run=run,
                    step=step,
                    worker=worker,
                    worker_result=worker_result,
                )
            except Exception as exc:  # noqa: BLE001
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
                    payload={"step_key": step.step_key, "worker_agent_id": str(worker.id), "error": str(exc)},
                )
                yield emit(QueueEvent.ERROR, observation=str(exc), tool=worker.name)
                return

            output = self._worker_result_to_output(worker_result)
            self._record_agent_events(session, run=run, step=step, worker_call=worker_call, worker_result=worker_result)
            terminal_status = self._worker_terminal_status(worker_result)
            if worker_result.status != TaskStatus.SUCCEEDED.value:
                self.task_engine.complete_worker_call(
                    session,
                    worker_call,
                    status=terminal_status,
                    result_json=output,
                )
                self.task_engine.fail_step(
                    session,
                    step,
                    error_code=worker_result.error_code or terminal_status.value,
                    error_message=worker_result.summary or "Worker execution failed",
                )
                if terminal_status == TaskStatus.CANCELLED:
                    self.task_engine.cancel_task(
                        session,
                        run.task,
                        error_message=worker_result.summary or "PlannerAgent debug stopped",
                    )
                    yield emit(QueueEvent.STOP, observation=worker_result.summary or "PlannerAgent 调试已停止")
                    return

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
                yield emit(
                    QueueEvent.ERROR,
                    observation=worker_result.summary or "Worker execution failed",
                    tool=worker.name,
                )
                return

            self.task_engine.complete_worker_call(session, worker_call, result_json=output)
            self.task_engine.succeed_step(session, step, output_json=output)
            step_artifacts = list(output.get("artifacts") or [])
            accumulated_artifacts.extend(step_artifacts)
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
                    "artifact_count": len(step_artifacts),
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
            yield emit(
                QueueEvent.AGENT_ACTION,
                observation=self._truncate(str(output.get("answer") or worker_result.summary or "执行完成"), 1000),
                tool=worker.name,
                tool_input={"step_key": step.step_key, "status": worker_result.status},
            )

        self.task_engine.succeed_task(
            session,
            run.task,
            final_result={"steps": step_outputs, "artifacts": accumulated_artifacts},
        )
        self.trace_service.record(
            session,
            tenant_id=run.task.tenant_id,
            event_type="router.manager_run.succeeded",
            task=run.task,
            plan=run.plan,
            payload={"step_count": len(step_outputs)},
        )
        answer = self._task_answer(run.task)
        yield emit(
            QueueEvent.AGENT_MESSAGE,
            thought=answer,
            answer=answer,
            total_token_count=max(1, len(answer) // 4) if answer else 0,
        )
        yield emit(QueueEvent.AGENT_END)

    def build_manager_plan(
        self,
        *,
        router_agent: Agent,
        workers: list[Agent],
        user_input: dict[str, Any],
        requested_worker_ids: list[uuid.UUID] | None = None,
    ) -> RouterPlan:
        return self._build_rule_manager_plan(
            router_agent=router_agent,
            workers=workers,
            user_input=user_input,
            requested_worker_ids=requested_worker_ids,
        )

    def _build_rule_manager_plan(
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
        return self.router_runtime.validate_plan(
            plan,
            allowed_worker_ids=allowed_worker_ids,
            router_id=str(router_agent.id),
        )

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
        preflight_result: dict[str, Any] | None = None,
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
        result = self._persist_manager_plan_for_task(
            session,
            task=task,
            plan=plan,
            user_input=user_input,
            preflight_result=preflight_result,
        )
        self._record_manager_run_created(session, result)
        return result

    def _build_planner_or_fallback_plan(
        self,
        session: Session,
        *,
        task: AgentTask,
        router_agent: Agent,
        workers: list[Agent],
        user_input: dict[str, Any],
        account: Account | None,
    ) -> RouterPlan:
        allowed_worker_ids = {str(worker.id) for worker in workers}
        fallback_reason = ""
        if account is None:
            fallback_reason = "planner_account_context_missing"
        else:
            try:
                model = self.language_model_service.load_language_model(
                    self._router_model_config(session, router_agent),
                    session=session,
                    account=account,
                )
                planner_result = self.planner_agent.create_plan(
                    model=model,
                    planner_input=self._build_planner_input(
                        session=session,
                        task=task,
                        router_agent=router_agent,
                        workers=workers,
                    ),
                )
                if planner_result.raw_output:
                    self.trace_service.record(
                        session,
                        tenant_id=task.tenant_id,
                        event_type="planner.generated",
                        task=task,
                        payload={
                            "model": f"{model.provider}/{model.model}",
                            "usage": planner_result.usage,
                            "latency_ms": planner_result.latency_ms,
                            "raw_output": self._truncate(planner_result.raw_output, 4000),
                        },
                        token_count=int(planner_result.usage.get("total_tokens") or 0),
                        latency=float((planner_result.latency_ms or 0) / 1000),
                    )
                if planner_result.plan is None:
                    fallback_reason = planner_result.error or "planner_returned_empty_plan"
                else:
                    plan = self.router_runtime.validate_plan(
                        planner_result.plan,
                        allowed_worker_ids=allowed_worker_ids,
                        router_id=str(router_agent.id),
                        max_steps=5,
                        allow_async=False,
                        allow_required_approval=False,
                    )
                    self.trace_service.record(
                        session,
                        tenant_id=task.tenant_id,
                        event_type="planner.validated",
                        task=task,
                        payload={
                            "step_count": len(plan.steps),
                            "worker_ids": [step.worker_id for step in plan.steps],
                            "risk_level": plan.risk_assessment.get("risk_level") or "low",
                            "source": plan.risk_assessment.get("source") or "llm_planner_v1",
                        },
                    )
                    return plan
            except Exception as exc:  # noqa: BLE001
                fallback_reason = str(exc)

        self.trace_service.record(
            session,
            tenant_id=task.tenant_id,
            event_type="planner.failed",
            task=task,
            payload={"error_message": self._truncate(fallback_reason, 1000)},
        )
        fallback_plan = self._build_rule_manager_plan(
            router_agent=router_agent,
            workers=workers,
            user_input=user_input,
        )
        self.trace_service.record(
            session,
            tenant_id=task.tenant_id,
            event_type="planner.fallback",
            task=task,
            payload={
                "reason": self._truncate(fallback_reason, 1000),
                "source": "manager_rule_v1",
                "selected_worker_ids": [step.worker_id for step in fallback_plan.steps],
            },
        )
        return fallback_plan

    def _build_planner_input(
        self,
        *,
        session: Session,
        task: AgentTask,
        router_agent: Agent,
        workers: list[Agent],
    ) -> PlannerInput:
        user_input = task.user_input or {}
        query = str(user_input.get("query") or user_input.get("input") or user_input.get("message") or "")
        context = user_input.get("context") if isinstance(user_input.get("context"), dict) else {}
        conversation = user_input.get("conversation") if isinstance(user_input.get("conversation"), dict) else {}
        recent_history = self._recent_history_from_user_input(user_input)
        if not recent_history and task.conversation_id:
            recent_history = self._conversation_recent_history(session, task.conversation_id, 10)
        return PlannerInput(
            router_id=str(router_agent.id),
            query=query,
            conversation_id=str(task.conversation_id or context.get("conversation_id") or conversation.get("id") or ""),
            message_id=str(
                user_input.get("message_id") or context.get("message_id") or conversation.get("message_id") or ""
            ),
            input_files=[],
            recent_history=recent_history,
            workers=[self._planner_worker_descriptor(session=session, worker=worker) for worker in workers],
            constraints={
                "allow_parallel": False,
                "allow_replan": False,
                "allow_required_approval": False,
                "execution_mode": "sync",
                "max_steps": 5,
            },
        )

    def _debug_recent_history(self, session: Session, app: App, conversation_id: uuid.UUID) -> list[dict[str, str]]:
        dialog_round = 10
        try:
            config = self.app_service._config_to_dict(self.app_service.get_or_create_draft_config(session, app))
            dialog_round = int(config.get("dialog_round") or 0)
        except Exception:  # noqa: BLE001
            dialog_round = 10
        return self._conversation_recent_history(session, conversation_id, dialog_round)

    def _conversation_recent_history(
        self,
        session: Session,
        conversation_id: uuid.UUID,
        dialog_round: int,
    ) -> list[dict[str, str]]:
        if dialog_round <= 0:
            return []
        try:
            return self._recent_history_from_items(
                TokenBufferMemory(session, conversation_id).get_history_messages(dialog_round)
            )
        except Exception:  # noqa: BLE001
            return []

    @classmethod
    def _recent_history_from_user_input(cls, user_input: dict[str, Any]) -> list[dict[str, str]]:
        raw_history = user_input.get("recent_history") if isinstance(user_input, dict) else []
        return cls._recent_history_from_items(raw_history)

    @classmethod
    def _recent_history_from_items(cls, raw_history: Any) -> list[dict[str, str]]:
        if not isinstance(raw_history, list):
            return []
        history: list[dict[str, str]] = []
        for item in raw_history[-20:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            history.append({"role": role, "content": cls._truncate(content, 2000)})
        return history

    def _planner_worker_descriptor(self, *, session: Session, worker: Agent) -> PlannerWorkerDescriptor:
        version = None
        if worker.published_version_id or worker.draft_version_id:
            version = session.get(AgentVersion, worker.published_version_id or worker.draft_version_id)
        capability_bindings = version.capability_bindings if version is not None else []
        worker_config = version.worker_config if version is not None else {}
        capability_summary = (
            worker_config.get("capability_summary")
            if isinstance(worker_config, dict) and isinstance(worker_config.get("capability_summary"), dict)
            else self.capability_service.ensure_worker_capability_summary(session, worker)
        )
        return PlannerWorkerDescriptor(
            worker_id=str(worker.id),
            name=worker.name,
            description=worker.description or "",
            runtime_type=worker.runtime_type,
            product_category=worker.product_category,
            target_ref_type=worker.target_ref_type,
            target_ref_id=worker.target_ref_id,
            capabilities=capability_bindings if isinstance(capability_bindings, list) else [],
            config_summary={
                "worker_config": worker_config if isinstance(worker_config, dict) else {},
                "capability_summary": capability_summary,
            },
        )

    def _router_model_config(self, session: Session, router_agent: Agent) -> dict[str, Any]:
        version_id = router_agent.draft_version_id or router_agent.published_version_id
        if version_id is None:
            return {}
        version = session.get(AgentVersion, version_id)
        return version.model_config if version is not None else {}

    def _persist_manager_plan_for_task(
        self,
        session: Session,
        *,
        task: AgentTask,
        plan: RouterPlan,
        user_input: dict[str, Any],
        preflight_result: dict[str, Any] | None = None,
    ) -> RouterManagerRunResult:
        plan_json = plan.model_dump(mode="json")
        if preflight_result is not None:
            plan_json["preflight"] = preflight_result
        preflight_by_step = self._preflight_by_step(preflight_result)
        persisted_plan = self.task_engine.create_plan(
            session,
            task=task,
            plan_json=plan_json,
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
                input_json={
                    "task": step.task,
                    "user_input": user_input,
                    "preflight": preflight_by_step.get(step.step_id),
                },
                execution_mode=step.execution_mode,
            )
            for step in plan.steps
        ]
        if any(step.required_approval for step in plan.steps):
            self.task_engine.wait_for_approval(session, task)
        result = RouterManagerRunResult(task=task, plan=persisted_plan, steps=steps)
        return result

    def _record_manager_run_created(self, session: Session, result: RouterManagerRunResult) -> None:
        self.trace_service.record(
            session,
            tenant_id=result.task.tenant_id,
            event_type="router.manager_run.created",
            task=result.task,
            plan=result.plan,
            payload={
                "router_agent_id": str(result.task.router_agent_id),
                "step_count": len(result.steps),
                "risk_level": result.plan.risk_level,
                "plan_source": (result.plan.plan_json or {}).get("risk_assessment", {}).get("source", ""),
                "status": result.task.status,
            },
        )

    def execute_manager_run_steps(
        self,
        session: Session,
        *,
        run: RouterManagerRunResult,
        account: Account,
    ) -> RouterManagerRunResult:
        if run.task.status in {TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}:
            return run
        try:
            input_files = self._input_file_refs(session, account, run.task.user_input)
        except Exception as exc:
            self.task_engine.fail_task(
                session,
                run.task,
                error_code="input_files_invalid",
                error_message=str(exc),
                final_result={"error": str(exc)},
            )
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="router.input_files.failed",
                task=run.task,
                plan=run.plan,
                payload={"error": str(exc)},
            )
            return run

        step_outputs = []
        accumulated_artifacts: list[dict[str, Any]] = []
        for step in run.steps:
            self.task_engine.start_step(session, step)
            if self._step_preflight_failed(step):
                error_code, user_message = self._step_preflight_error(step)
                self.task_engine.fail_step(session, step, error_code=error_code, error_message=user_message)
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code=error_code,
                    error_message=user_message,
                    final_result={"step_key": step.step_key, "preflight": step.input_json.get("preflight")},
                )
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="router.capability_preflight.failed",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    payload=step.input_json.get("preflight") or {},
                )
                return run
            worker = self.get_worker_agent(session, run.task.tenant_id, step.worker_agent_id)
            invocation = self._build_worker_invocation(
                run=run,
                step=step,
                worker=worker,
                account=account,
                input_files=input_files,
                artifacts=accumulated_artifacts,
            )
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
                worker_result = self._with_registered_artifacts(
                    session,
                    account=account,
                    run=run,
                    step=step,
                    worker=worker,
                    worker_result=worker_result,
                )
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
            step_artifacts = list(output.get("artifacts") or [])
            accumulated_artifacts.extend(step_artifacts)
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
                    "artifact_count": len(step_artifacts),
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

        self.task_engine.succeed_task(
            session,
            run.task,
            final_result={"steps": step_outputs, "artifacts": accumulated_artifacts},
        )
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
        account: Account | None = None,
    ) -> RouterManagerRunResult:
        router = self.get_router_agent(session, tenant_id, router_agent_id)
        workers = self.list_bound_workers(session, tenant_id=tenant_id, router_agent_id=router_agent_id)
        selected_workers = self._select_workers(workers, requested_worker_ids)
        if not selected_workers:
            raise FailException("Router agent has no available worker bindings")

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
        self.trace_service.record(
            session,
            tenant_id=tenant_id,
            event_type="planner.started",
            task=task,
            payload={
                "router_agent_id": str(router_agent_id),
                "worker_count": len(selected_workers),
                "max_steps": 5,
                "has_input_files": any(self._iter_input_file_ids(user_input)),
            },
        )
        plan = self._build_planner_or_fallback_plan(
            session,
            task=task,
            router_agent=router,
            workers=selected_workers,
            user_input=user_input,
            account=account,
        )
        preflight_result = self._preflight_plan(
            session,
            task=task,
            router_agent=router,
            workers=selected_workers,
            plan=plan,
            user_input=user_input,
            account=account,
        )
        result = self._persist_manager_plan_for_task(
            session,
            task=task,
            plan=plan,
            user_input=user_input,
            preflight_result=preflight_result,
        )
        self._record_manager_run_created(session, result)
        if preflight_result.get("status") == "failed":
            error_code, user_message = self._first_preflight_error(preflight_result)
            self._fail_run_for_preflight(session, run=result, error_code=error_code, user_message=user_message)
        return result

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

    def get_app_worker_capability_summary(
        self,
        session: Session,
        *,
        app_id: uuid.UUID,
        account: Account,
    ) -> dict[str, Any]:
        app = self.app_service.get_app(session, app_id, account)
        if (getattr(app, "agent_type", "worker") or "worker") != "worker":
            raise FailException("Only WorkerAgent apps have capability summaries")
        existing = self._find_app_worker_agent(session, account.id, app_id)
        if existing is not None:
            version = self._active_version(session, existing)
            summary = self.capability_service.ensure_worker_capability_summary(session, existing, account=account)
            return {
                "app_id": str(app_id),
                "agent_id": str(existing.id),
                "version_id": str(version.id) if version is not None else "",
                "capability_summary": summary,
                "warnings": [],
            }

        descriptor = self.app_service.app_to_worker_agent_descriptor(session, app_id, account)
        version_payload = self.capability_service.attach_summary_to_version_payload(
            agent_payload=descriptor.to_agent_payload(),
            version_payload=descriptor.to_version_payload(),
            session=session,
            account=account,
        )
        return {
            "app_id": str(app_id),
            "agent_id": "",
            "version_id": "",
            "capability_summary": version_payload["worker_config"]["capability_summary"],
            "warnings": [],
        }

    def refresh_app_worker_capability_summary(
        self,
        session: Session,
        *,
        app_id: uuid.UUID,
        account: Account,
        preserve_manual_overrides: bool = True,
    ) -> dict[str, Any]:
        worker_agent, _ = self.create_worker_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=app_id,
            account=account,
            status="published",
        )
        return self.capability_service.refresh_agent_capability_summary(
            session,
            worker_agent.id,
            account,
            preserve_manual_overrides=preserve_manual_overrides,
        )

    def patch_app_worker_capability_summary(
        self,
        session: Session,
        *,
        app_id: uuid.UUID,
        account: Account,
        manual_overrides: dict[str, Any],
    ) -> dict[str, Any]:
        worker_agent, _ = self.create_worker_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=app_id,
            account=account,
            status="published",
        )
        return self.capability_service.patch_agent_capability_summary(
            session,
            worker_agent.id,
            account,
            manual_overrides=manual_overrides,
        )

    def get_planner_routing_policy(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        account: Account,
    ) -> dict[str, Any]:
        planner_agent, version = self.create_planner_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=planner_app_id,
            account=account,
        )
        routing_policy = self._routing_policy_for_version(version)
        return {
            "app_id": str(planner_app_id),
            "agent_id": str(planner_agent.id),
            "version_id": str(version.id),
            "routing_policy": routing_policy,
        }

    def save_planner_routing_policy(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        account: Account,
        routing_policy: dict[str, Any],
    ) -> dict[str, Any]:
        validation = self.capability_service.validate_routing_policy(routing_policy)
        if not validation["valid"]:
            raise FailException("routing_policy_invalid")
        planner_agent, version = self.create_planner_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=planner_app_id,
            account=account,
        )
        router_config = dict(version.router_config or {})
        router_config["routing_policy"] = validation["routing_policy"]
        self.update(session, version, router_config=router_config)
        return {
            "app_id": str(planner_app_id),
            "agent_id": str(planner_agent.id),
            "version_id": str(version.id),
            "routing_policy": validation["routing_policy"],
        }

    def validate_planner_routing_policy(self, routing_policy: dict[str, Any]) -> dict[str, Any]:
        return self.capability_service.validate_routing_policy(routing_policy)

    def preflight_planner_workers(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        account: Account,
        message: str,
        input_modalities: list[str] | None = None,
        candidate_worker_ids: list[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        planner_agent, _ = self.create_planner_agent_from_app(
            session,
            tenant_id=account.id,
            app_id=planner_app_id,
            account=account,
        )
        workers = self.list_bound_workers(session, tenant_id=account.id, router_agent_id=planner_agent.id)
        workers = self._select_workers(workers, candidate_worker_ids)
        worker_capabilities = self._worker_capability_map(session, workers, account=account)
        routing_policy = self._routing_policy_for_agent(session, planner_agent)
        user_input = {"query": message, "input_modalities": input_modalities or []}
        results = []
        for worker in workers:
            plan = RouterPlan(
                router_id=str(planner_agent.id),
                user_intent=message,
                steps=[RouterPlanStep(step_id="diagnostic", worker_id=str(worker.id), task=message)],
            )
            preflight = self.router_runtime.preflight_plan(
                plan,
                worker_capabilities=worker_capabilities,
                user_input=user_input,
                routing_policy=routing_policy,
            )
            result = preflight["results"][0] if preflight.get("results") else {}
            first_failed_check = next(
                (check for check in result.get("checks", []) if not check.get("passed")),
                {},
            )
            results.append(
                {
                    "worker_id": str(worker.id),
                    "worker_name": worker.name,
                    "passed": bool(result.get("passed", True)),
                    "error_code": first_failed_check.get("error_code"),
                    "user_message": first_failed_check.get("user_message") or "",
                    "checks": result.get("checks", []),
                    "capability_snapshot": result.get("capability_snapshot", {}),
                }
            )
        suggested_worker_ids = [result["worker_id"] for result in results if result["passed"]]
        return {
            "status": "succeeded" if suggested_worker_ids else "failed",
            "results": results,
            "suggested_worker_ids": suggested_worker_ids,
        }

    def _get_planner_binding(
        self,
        session: Session,
        tenant_id: uuid.UUID,
        router_agent_id: uuid.UUID,
        binding_id: uuid.UUID,
    ) -> AgentBinding:
        binding = (
            session.query(AgentBinding)
            .filter(
                AgentBinding.id == binding_id,
                AgentBinding.tenant_id == tenant_id,
                AgentBinding.router_agent_id == router_agent_id,
            )
            .one_or_none()
        )
        if binding is None:
            raise NotFoundException("Planner worker binding not found")
        return binding

    def _requested_worker_agent_ids(
        self,
        session: Session,
        *,
        planner_agent_id: uuid.UUID,
        account: Account,
        requested_worker_app_ids: list[uuid.UUID],
    ) -> list[uuid.UUID] | None:
        if not requested_worker_app_ids:
            return None
        requested_app_ids = {str(app_id) for app_id in requested_worker_app_ids}
        rows = (
            session.query(AgentBinding, Agent)
            .join(Agent, AgentBinding.worker_agent_id == Agent.id)
            .filter(
                AgentBinding.tenant_id == account.id,
                AgentBinding.router_agent_id == planner_agent_id,
                AgentBinding.enabled.is_(True),
                Agent.tenant_id == account.id,
                Agent.runtime_type == "worker",
                Agent.target_ref_type == "app",
            )
            .all()
        )
        worker_agent_ids = [
            worker.id
            for _, worker in rows
            if str(worker.target_ref_id) in requested_app_ids
        ]
        if len(worker_agent_ids) != len(requested_app_ids):
            raise FailException("Requested worker apps must be enabled planner bindings")
        return worker_agent_ids

    @staticmethod
    def _task_answer(task: AgentTask) -> str:
        final_result = task.final_result or {}
        for key in ("answer", "summary", "result", "error"):
            value = final_result.get(key)
            if value:
                return str(value)
        steps = final_result.get("steps")
        if isinstance(steps, list):
            answers = []
            for step in steps:
                if not isinstance(step, dict):
                    continue
                output = step.get("output") if isinstance(step.get("output"), dict) else {}
                answer = output.get("answer") or output.get("summary") or output.get("data", {}).get("answer")
                if answer:
                    answers.append(str(answer))
            if answers:
                return "\n\n".join(answers)
        return task.error_message or ""

    @staticmethod
    def _planner_plan_observation(plan: RouterPlan, workers: list[Agent]) -> str:
        worker_names = {str(worker.id): worker.name for worker in workers}
        lines = []
        source = plan.risk_assessment.get("source") or "planner"
        for index, step in enumerate(plan.steps, start=1):
            worker_name = worker_names.get(str(step.worker_id), step.worker_id)
            lines.append(f"{index}. {worker_name}: {step.task}")
        return f"计划来源: {source}\n" + "\n".join(lines)

    @staticmethod
    def _worker_app_map(session: Session, workers: list[Agent], account_id: uuid.UUID) -> dict[str, App]:
        app_ids = []
        for worker in workers:
            if worker.target_ref_type != "app":
                continue
            try:
                app_ids.append(uuid.UUID(str(worker.target_ref_id)))
            except (TypeError, ValueError):
                continue
        if not app_ids:
            return {}
        apps = session.query(App).filter(App.id.in_(app_ids), App.account_id == account_id).all()
        return {str(app.id): app for app in apps}

    @staticmethod
    def _agent_payload(agent: Agent) -> dict[str, Any]:
        return {
            "id": str(agent.id),
            "name": agent.name,
            "icon": agent.icon,
            "description": agent.description,
            "runtime_type": agent.runtime_type,
            "product_category": agent.product_category,
            "status": agent.status,
            "target_ref_type": agent.target_ref_type,
            "target_ref_id": agent.target_ref_id,
        }

    @staticmethod
    def _app_payload(app: App | None) -> dict[str, Any] | None:
        if app is None:
            return None
        return {
            "id": str(app.id),
            "name": app.name,
            "icon": app.icon,
            "description": app.description,
            "agent_type": getattr(app, "agent_type", "worker") or "worker",
            "status": app.status,
        }

    @staticmethod
    def _timestamp(value) -> int:
        return int(value.timestamp()) if value else 0

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        text = str(value or "")
        return text if len(text) <= limit else f"{text[:limit]}..."

    @staticmethod
    def _select_workers(workers: list[Agent], requested_worker_ids: list[uuid.UUID] | None) -> list[Agent]:
        if not requested_worker_ids:
            return workers
        requested = {str(worker_id) for worker_id in requested_worker_ids}
        return [worker for worker in workers if str(worker.id) in requested]

    def _preflight_plan(
        self,
        session: Session,
        *,
        task: AgentTask,
        router_agent: Agent,
        workers: list[Agent],
        plan: RouterPlan,
        user_input: dict[str, Any],
        account: Account | None,
    ) -> dict[str, Any]:
        self.trace_service.record(
            session,
            tenant_id=task.tenant_id,
            event_type="router.capability_preflight.started",
            task=task,
            payload={
                "router_agent_id": str(router_agent.id),
                "worker_ids": [str(worker.id) for worker in workers],
                "step_count": len(plan.steps),
            },
        )
        result = self.router_runtime.preflight_plan(
            plan,
            worker_capabilities=self._worker_capability_map(session, workers, account=account),
            user_input=user_input,
            routing_policy=self._routing_policy_for_agent(session, router_agent),
        )
        self.trace_service.record(
            session,
            tenant_id=task.tenant_id,
            event_type=f"router.capability_preflight.{result.get('status')}",
            task=task,
            payload=result,
        )
        return result

    def _worker_capability_map(
        self,
        session: Session,
        workers: list[Agent],
        *,
        account: Account | None,
    ) -> dict[str, dict[str, Any]]:
        return {
            str(worker.id): self.capability_service.ensure_worker_capability_summary(session, worker, account=account)
            for worker in workers
        }

    def _routing_policy_for_agent(self, session: Session, agent: Agent | None) -> dict[str, Any]:
        if agent is None:
            return self.capability_service.validate_routing_policy({})["routing_policy"]
        return self._routing_policy_for_version(self._active_version(session, agent))

    def _routing_policy_for_version(self, version: AgentVersion | None) -> dict[str, Any]:
        router_config = version.router_config if version is not None and isinstance(version.router_config, dict) else {}
        policy = router_config.get("routing_policy") if isinstance(router_config.get("routing_policy"), dict) else {}
        return self.capability_service.validate_routing_policy(policy)["routing_policy"]

    def _capability_summary_for_agent(self, session: Session, agent: Agent | None) -> dict[str, Any]:
        if agent is None:
            return {}
        version = self._active_version(session, agent)
        if version is None or not isinstance(version.worker_config, dict):
            return {}
        summary = version.worker_config.get("capability_summary")
        return summary if isinstance(summary, dict) else {}

    @staticmethod
    def _active_version(session: Session, agent: Agent) -> AgentVersion | None:
        version_id = agent.published_version_id or agent.draft_version_id
        if version_id is None:
            return None
        return session.get(AgentVersion, version_id)

    @staticmethod
    def _preflight_by_step(preflight_result: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not isinstance(preflight_result, dict):
            return {}
        results = preflight_result.get("results")
        if not isinstance(results, list):
            return {}
        return {
            str(result.get("step_id") or ""): result
            for result in results
            if isinstance(result, dict) and str(result.get("step_id") or "")
        }

    @staticmethod
    def _step_preflight_failed(step: AgentStep) -> bool:
        input_json = step.input_json if isinstance(step.input_json, dict) else {}
        preflight = input_json.get("preflight") if isinstance(input_json.get("preflight"), dict) else {}
        return preflight.get("status") == "failed" or preflight.get("passed") is False

    @staticmethod
    def _step_preflight_error(step: AgentStep) -> tuple[str, str]:
        input_json = step.input_json if isinstance(step.input_json, dict) else {}
        preflight = input_json.get("preflight") if isinstance(input_json.get("preflight"), dict) else {}
        for check in preflight.get("checks", []) if isinstance(preflight.get("checks"), list) else []:
            if isinstance(check, dict) and not check.get("passed"):
                return str(check.get("error_code") or "capability_summary_invalid"), str(
                    check.get("user_message") or "Worker 能力校验未通过。"
                )
        return "capability_summary_invalid", "Worker 能力校验未通过。"

    @staticmethod
    def _first_preflight_error(preflight_result: dict[str, Any]) -> tuple[str, str]:
        for result in preflight_result.get("results", []) if isinstance(preflight_result.get("results"), list) else []:
            if not isinstance(result, dict):
                continue
            for check in result.get("checks", []) if isinstance(result.get("checks"), list) else []:
                if isinstance(check, dict) and not check.get("passed"):
                    return str(check.get("error_code") or "capability_summary_invalid"), str(
                        check.get("user_message") or "Worker 能力校验未通过。"
                    )
        return "capability_summary_invalid", "Worker 能力校验未通过。"

    def _fail_run_for_preflight(
        self,
        session: Session,
        *,
        run: RouterManagerRunResult,
        error_code: str,
        user_message: str,
    ) -> None:
        for step in run.steps:
            if self._step_preflight_failed(step):
                self.task_engine.fail_step(session, step, error_code=error_code, error_message=user_message)
        self.task_engine.fail_task(
            session,
            run.task,
            error_code=error_code,
            error_message=user_message,
            final_result={"preflight": (run.plan.plan_json or {}).get("preflight", {})},
        )
        self.trace_service.record(
            session,
            tenant_id=run.task.tenant_id,
            event_type="router.capability_preflight.failed",
            task=run.task,
            plan=run.plan,
            payload={"error_code": error_code, "user_message": user_message},
        )

    def _find_app_worker_agent(self, session: Session, tenant_id: uuid.UUID, app_id: uuid.UUID) -> Agent | None:
        return (
            session.query(Agent)
            .filter(
                Agent.tenant_id == tenant_id,
                Agent.runtime_type == "worker",
                Agent.target_ref_type == "app",
                Agent.target_ref_id == str(app_id),
            )
            .one_or_none()
        )

    def _build_worker_invocation(
        self,
        *,
        run: RouterManagerRunResult,
        step: AgentStep,
        worker: Agent,
        account: Account,
        input_files: list[dict[str, Any]] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> WorkerInvocation:
        user_input = step.input_json.get("user_input") if isinstance(step.input_json, dict) else {}
        image_urls = user_input.get("image_urls") if isinstance(user_input, dict) else []
        recent_history = self._recent_history_from_user_input(user_input)
        preflight = step.input_json.get("preflight") if isinstance(step.input_json, dict) else None
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
                "input_files": input_files or [],
                "image_urls": image_urls if isinstance(image_urls, list) else [],
                "artifacts": artifacts or [],
                "recent_history": recent_history,
                "preflight": preflight if isinstance(preflight, dict) else {},
            },
            execution_policy={
                "execution_agent_type": self._worker_execution_agent_type(worker),
                "target_ref_type": worker.target_ref_type,
                "target_ref_id": worker.target_ref_id,
                "capability_snapshot": preflight.get("capability_snapshot", {}) if isinstance(preflight, dict) else {},
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

    def _input_file_refs(self, session: Session, account: Account, user_input: dict[str, Any]) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        seen: set[uuid.UUID] = set()
        for raw_file_id in self._iter_input_file_ids(user_input):
            file_id = self._parse_uuid(raw_file_id, "input_file_ids")
            if file_id in seen:
                continue
            seen.add(file_id)
            refs.append(self._json_ready(self.file_service.to_agent_input_ref(session, account, file_id)))
        return refs

    def _with_registered_artifacts(
        self,
        session: Session,
        *,
        account: Account,
        run: RouterManagerRunResult,
        step: AgentStep,
        worker: Agent,
        worker_result: WorkerResult,
    ) -> WorkerResult:
        if not worker_result.artifacts:
            return worker_result
        artifacts = [
            ArtifactRef(**artifact)
            for artifact in self._register_artifacts(
                session,
                account=account,
                run=run,
                step=step,
                worker=worker,
                artifacts=worker_result.artifacts,
            )
        ]
        return worker_result.model_copy(update={"artifacts": artifacts})

    def _register_artifacts(
        self,
        session: Session,
        *,
        account: Account,
        run: RouterManagerRunResult,
        step: AgentStep,
        worker: Agent,
        artifacts: list[ArtifactRef],
    ) -> list[dict[str, Any]]:
        registered: list[dict[str, Any]] = []
        for artifact in artifacts:
            data = artifact.model_dump(mode="json")
            metadata = dict(data.get("metadata") or {})
            metadata.setdefault("step_key", step.step_key)
            data.update(
                {
                    "task_id": data.get("task_id") or str(run.task.id),
                    "step_id": data.get("step_id") or str(step.id),
                    "worker_id": data.get("worker_id") or str(worker.id),
                    "metadata": metadata,
                }
            )

            content = self._pop_artifact_content(metadata)
            if data.get("file_id"):
                file_id = self._parse_uuid(data["file_id"], "artifact.file_id")
                file = self.file_service.get_file(session, account, file_id)
                if file.type != "file":
                    raise FailException("Artifact file_id must reference a file")
                registered.append(self._merge_file_artifact(data, self.file_service.to_response(session, file)))
                continue

            if content is not None:
                artifact_file = self.file_service.create_agent_artifact(
                    session,
                    account,
                    name=str(data.get("name") or f"{step.step_key}-artifact.txt"),
                    content=content if isinstance(content, str | bytes) else str(content),
                    mime_type=str(metadata.get("mime_type") or "text/plain; charset=utf-8"),
                    extension=self._artifact_extension(data, metadata),
                    metadata=metadata,
                )
                data["file_id"] = str(artifact_file.id)
                data["source"] = "agent"
                registered.append(
                    self._merge_file_artifact(data, self.file_service.to_response(session, artifact_file))
                )
                continue

            registered.append(data)
        return registered

    @classmethod
    def _iter_input_file_ids(cls, user_input: dict[str, Any]):
        for key in ("input_file_ids", "file_ids", "input_files", "files"):
            value = user_input.get(key)
            if value is None:
                continue
            yield from cls._iter_file_id_values(value)

    @classmethod
    def _iter_file_id_values(cls, value: Any):
        if isinstance(value, str | uuid.UUID):
            yield value
            return
        if isinstance(value, dict):
            file_id = value.get("file_id") or value.get("id")
            if file_id:
                yield file_id
            return
        if isinstance(value, list | tuple):
            for item in value:
                yield from cls._iter_file_id_values(item)

    @staticmethod
    def _parse_uuid(value: Any, field_name: str) -> uuid.UUID:
        try:
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise FailException(f"{field_name} is invalid") from exc

    @staticmethod
    def _pop_artifact_content(metadata: dict[str, Any]) -> Any | None:
        for key in ("content", "text"):
            if key in metadata:
                return metadata.pop(key)
        return None

    @classmethod
    def _merge_file_artifact(cls, artifact: dict[str, Any], file_data: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(artifact.get("metadata") or {})
        metadata["file"] = {
            "id": str(file_data.get("id") or file_data.get("file_id") or ""),
            "mime_type": file_data.get("mime_type") or "",
            "extension": file_data.get("extension") or "",
            "size": file_data.get("size") or 0,
            "storage_provider": file_data.get("storage_provider") or "",
            "file_path": file_data.get("file_path") or "",
            "download_url": file_data.get("download_url") or "",
            "preview_url": file_data.get("preview_url") or "",
        }
        return {
            **artifact,
            "file_id": str(file_data.get("id") or artifact.get("file_id") or ""),
            "name": artifact.get("name") or str(file_data.get("name") or ""),
            "type": "file",
            "source": artifact.get("source") or str(file_data.get("source") or "agent"),
            "metadata": cls._json_ready(metadata),
        }

    @staticmethod
    def _artifact_extension(artifact: dict[str, Any], metadata: dict[str, Any]) -> str:
        explicit = str(metadata.get("extension") or "").lstrip(".")
        if explicit:
            return explicit
        name = str(artifact.get("name") or "")
        if "." in name:
            return name.rsplit(".", 1)[-1].lower()
        return "txt"

    @classmethod
    def _json_ready(cls, value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, dict):
            return {key: cls._json_ready(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._json_ready(item) for item in value]
        return value

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

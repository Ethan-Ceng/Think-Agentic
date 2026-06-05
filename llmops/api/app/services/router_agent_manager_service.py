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
from app.domain.agent_runtime.planner import (
    PlannerInput,
    PlannerPlanFeedbackInput,
    PlannerReplanInput,
    PlannerWorkerDescriptor,
    RouterPlannerAgent,
)
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
from app.services.task_engine_service import TASK_WAITING_STATUSES, TaskEngineService, TaskStatus
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


@dataclass(frozen=True)
class ReplanAttemptResult:
    run: RouterManagerRunResult | None
    error_code: str = ""
    user_message: str = ""

    @property
    def applied(self) -> bool:
        return self.run is not None


@dataclass(frozen=True)
class PlanUpdateAttemptResult:
    run: RouterManagerRunResult | None
    completed_enough: bool = False
    error_code: str = ""
    user_message: str = ""

    @property
    def applied(self) -> bool:
        return self.run is not None


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

    def bind_worker_agent_to_planner(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        worker_agent_id: uuid.UUID,
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
        worker_agent = self.get_worker_agent(session, account.id, worker_agent_id)
        if worker_agent.status not in {"published", "active"}:
            raise FailException("Worker agent must be published or active before binding")
        return self.bind_worker(
            session,
            tenant_id=account.id,
            router_agent_id=planner_agent.id,
            worker_agent_id=worker_agent.id,
            priority=priority,
            conditions=conditions,
            enabled=enabled,
        )

    def bind_worker_to_planner(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        account: Account,
        worker_app_id: uuid.UUID | None = None,
        worker_agent_id: uuid.UUID | None = None,
        priority: int = 0,
        conditions: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> AgentBinding:
        if bool(worker_app_id) == bool(worker_agent_id):
            raise FailException("Exactly one of worker_app_id or worker_agent_id is required")
        if worker_agent_id is not None:
            return self.bind_worker_agent_to_planner(
                session,
                planner_app_id=planner_app_id,
                worker_agent_id=worker_agent_id,
                account=account,
                priority=priority,
                conditions=conditions,
                enabled=enabled,
            )
        return self.bind_worker_app_to_planner(
            session,
            planner_app_id=planner_app_id,
            worker_app_id=worker_app_id,
            account=account,
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
        requested_worker_ids: list[uuid.UUID] | None = None,
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
            requested_worker_ids=requested_worker_ids or [],
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
        requested_worker_ids: list[uuid.UUID] | None = None,
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
            requested_worker_ids=requested_worker_ids or [],
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
                "workers": self._worker_summary_payload(selected_workers),
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
                workers=selected_workers,
            )
            self._record_manager_run_created(session, run, workers=selected_workers)
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
            replan = self._maybe_replan(
                session,
                run=run,
                router_agent=planner_agent,
                workers=selected_workers,
                account=account,
                trigger="capability_preflight_failed",
                failed_step=self._first_failed_preflight_step(run),
                error_code=error_code,
                user_message=user_message,
                failure_payload={"preflight": preflight_result},
            )
            if replan.applied and replan.run is not None:
                run = replan.run
                plan = RouterPlan.model_validate(run.plan.plan_json)
                yield emit(
                    QueueEvent.AGENT_ACTION,
                    observation="PlannerAgent replanned execution after preflight failure.",
                    tool="planner.replan",
                    tool_input=(run.plan.plan_json or {}).get("replan", {}),
                )
            else:
                self._fail_run_for_preflight(
                    session,
                    run=run,
                    error_code=replan.error_code or error_code,
                    user_message=replan.user_message or user_message,
                )
                yield emit(
                    QueueEvent.ERROR,
                    observation=replan.user_message or user_message,
                    tool="router.capability_preflight",
                )
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
        if self._is_waiting_task_status(run.task.status):
            yield emit(
                QueueEvent.AGENT_ACTION,
                observation=run.task.error_message or "任务已暂停，等待处理",
                tool="planner.wait",
                tool_input={"status": run.task.status, "error_code": run.task.error_code},
            )
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

        def execute_replanned_run(next_run: RouterManagerRunResult) -> RouterManagerRunResult:
            return self.execute_manager_run_steps(
                session,
                run=next_run,
                account=account,
                _step_outputs=step_outputs,
                _accumulated_artifacts=accumulated_artifacts,
            )

        for step in run.steps:
            if stopped():
                yield cancel_task()
                return

            if step.status == TaskStatus.SUCCEEDED.value:
                self._append_step_output(step_outputs, step, worker_agent_id=str(step.worker_agent_id))
                accumulated_artifacts.extend(list((step.output_json or {}).get("artifacts") or []))
                continue
            if step.status == TaskStatus.WAITING_USER.value:
                if self._is_waiting_task_status(run.task.status):
                    yield emit(QueueEvent.AGENT_ACTION, observation="等待用户补充信息", tool="planner.wait_user")
                    return
                self.task_engine.resume_step(session, step)
            if step.status == TaskStatus.CREATED.value:
                self.task_engine.start_step(session, step)
            if self._step_preflight_failed(step):
                error_code, user_message = self._step_preflight_error(step)
                self.task_engine.fail_step(session, step, error_code=error_code, error_message=user_message)
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="router.capability_preflight.failed",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    payload=step.input_json.get("preflight") or {},
                )
                replan = self._maybe_replan(
                    session,
                    run=run,
                    router_agent=planner_agent,
                    workers=selected_workers,
                    account=account,
                    trigger="capability_preflight_failed",
                    failed_step=step,
                    error_code=error_code,
                    user_message=user_message,
                    failure_payload={"preflight": step.input_json.get("preflight") or {}},
                    completed_steps=step_outputs,
                )
                if replan.applied and replan.run is not None:
                    yield emit(
                        QueueEvent.AGENT_ACTION,
                        observation="PlannerAgent replanned execution after preflight failure.",
                        tool="planner.replan",
                        tool_input=(replan.run.plan.plan_json or {}).get("replan", {}),
                    )
                    run = execute_replanned_run(replan.run)
                    answer = self._task_answer(run.task)
                    if run.task.status == TaskStatus.SUCCEEDED.value:
                        yield emit(
                            QueueEvent.AGENT_MESSAGE,
                            thought=answer,
                            answer=answer,
                            total_token_count=max(1, len(answer) // 4) if answer else 0,
                        )
                        yield emit(QueueEvent.AGENT_END)
                    else:
                        yield emit(QueueEvent.ERROR, observation=run.task.error_message, tool="planner.replan")
                    return
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code=replan.error_code or error_code,
                    error_message=replan.user_message or user_message,
                    final_result={"step_key": step.step_key, "preflight": step.input_json.get("preflight")},
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
                payload=self._worker_trace_payload(worker, step),
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
                payload=self._worker_trace_payload(
                    worker,
                    step,
                    execution_agent_type=invocation.execution_policy.get("execution_agent_type"),
                    executor_type=invocation.execution_policy.get("executor_type"),
                ),
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
                error_message = str(exc)
                self.task_engine.complete_worker_call(
                    session,
                    worker_call,
                    status=TaskStatus.FAILED,
                    result_json={"error": error_message},
                )
                self.task_engine.fail_step(
                    session,
                    step,
                    error_code="worker_execution_failed",
                    error_message=error_message,
                )
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="worker.call.failed",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    worker_call=worker_call,
                    payload=self._worker_trace_payload(worker, step, error=error_message),
                )
                replan = self._maybe_replan(
                    session,
                    run=run,
                    router_agent=planner_agent,
                    workers=selected_workers,
                    account=account,
                    trigger="worker_failed",
                    failed_step=step,
                    error_code="worker_execution_failed",
                    user_message=error_message,
                    failure_payload={"exception": error_message},
                    completed_steps=step_outputs,
                )
                if replan.applied and replan.run is not None:
                    yield emit(
                        QueueEvent.AGENT_ACTION,
                        observation="PlannerAgent replanned execution after worker failure.",
                        tool="planner.replan",
                        tool_input=(replan.run.plan.plan_json or {}).get("replan", {}),
                    )
                    run = execute_replanned_run(replan.run)
                    answer = self._task_answer(run.task)
                    if run.task.status == TaskStatus.SUCCEEDED.value:
                        yield emit(
                            QueueEvent.AGENT_MESSAGE,
                            thought=answer,
                            answer=answer,
                            total_token_count=max(1, len(answer) // 4) if answer else 0,
                        )
                        yield emit(QueueEvent.AGENT_END)
                    else:
                        yield emit(QueueEvent.ERROR, observation=run.task.error_message, tool="planner.replan")
                    return
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code=replan.error_code or "worker_execution_failed",
                    error_message=replan.user_message or error_message,
                    final_result={"step_key": step.step_key},
                )
                yield emit(QueueEvent.ERROR, observation=replan.user_message or error_message, tool=worker.name)
                return

            output = self._worker_result_to_output(worker_result)
            self._record_agent_events(session, run=run, step=step, worker_call=worker_call, worker_result=worker_result)
            if worker_result.status == TaskStatus.WAITING_USER.value:
                plan_feedback = self._worker_plan_feedback(worker_result)
                self.task_engine.wait_worker_call_for_user(session, worker_call, result_json=output)
                self.task_engine.wait_step_for_user(session, step, output_json=output)
                self.task_engine.wait_for_user(
                    session,
                    run.task,
                    final_result={
                        "step_key": step.step_key,
                        "worker_result": output,
                        "completed_steps": step_outputs,
                        "artifacts": accumulated_artifacts,
                    },
                    error_message=worker_result.summary or "Worker is waiting for user input",
                )
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="wait.user.requested",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    worker_call=worker_call,
                    payload=self._worker_trace_payload(
                        worker,
                        step,
                        status=TaskStatus.WAITING.value,
                        worker_result_status=worker_result.status,
                        wait_type="user_input",
                        reason_code=plan_feedback.get("reason_code") or "missing_info",
                        resume_policy="resume_same_step",
                        summary=worker_result.summary,
                        missing_info=plan_feedback.get("missing_info", []),
                        plan_feedback=plan_feedback,
                    ),
                )
                yield emit(
                    QueueEvent.AGENT_ACTION,
                    observation=worker_result.summary or "等待用户补充信息",
                    tool=worker.name,
                    tool_input={"step_key": step.step_key, "status": worker_result.status},
                )
                return
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

                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="worker.call.failed",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    worker_call=worker_call,
                    payload=self._worker_trace_payload(
                        worker,
                        step,
                        status=worker_result.status,
                        error_code=worker_result.error_code,
                        summary=worker_result.summary,
                        replan_signal=self._worker_replan_signal(worker_result),
                    ),
                )
                replan = self._maybe_replan(
                    session,
                    run=run,
                    router_agent=planner_agent,
                    workers=selected_workers,
                    account=account,
                    trigger="worker_failed",
                    failed_step=step,
                    error_code=worker_result.error_code or "worker_execution_failed",
                    user_message=worker_result.summary or "Worker execution failed",
                    failure_payload={"worker_result": output},
                    completed_steps=step_outputs,
                )
                if replan.applied and replan.run is not None:
                    yield emit(
                        QueueEvent.AGENT_ACTION,
                        observation="PlannerAgent replanned execution after worker failure.",
                        tool="planner.replan",
                        tool_input=(replan.run.plan.plan_json or {}).get("replan", {}),
                    )
                    run = execute_replanned_run(replan.run)
                    answer = self._task_answer(run.task)
                    if run.task.status == TaskStatus.SUCCEEDED.value:
                        yield emit(
                            QueueEvent.AGENT_MESSAGE,
                            thought=answer,
                            answer=answer,
                            total_token_count=max(1, len(answer) // 4) if answer else 0,
                        )
                        yield emit(QueueEvent.AGENT_END)
                    else:
                        yield emit(QueueEvent.ERROR, observation=run.task.error_message, tool="planner.replan")
                    return
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code=replan.error_code or worker_result.error_code or "worker_execution_failed",
                    error_message=replan.user_message or worker_result.summary or "Worker execution failed",
                    final_result={"step_key": step.step_key, "worker_result": output},
                )
                yield emit(
                    QueueEvent.ERROR,
                    observation=replan.user_message or worker_result.summary or "Worker execution failed",
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
                payload=self._worker_trace_payload(
                    worker,
                    step,
                    answer_length=len(str(output.get("answer") or "")),
                    worker_result_status=worker_result.status,
                    artifact_count=len(step_artifacts),
                ),
            )
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="router.step.succeeded",
                task=run.task,
                plan=run.plan,
                step=step,
                payload=self._worker_trace_payload(worker, step),
            )
            yield emit(
                QueueEvent.AGENT_ACTION,
                observation=self._truncate(str(output.get("answer") or worker_result.summary or "执行完成"), 1000),
                tool=worker.name,
                tool_input={"step_key": step.step_key, "status": worker_result.status},
            )
            plan_update = self._maybe_update_plan_from_feedback(
                session,
                run=run,
                step=step,
                worker_result=worker_result,
                completed_steps=step_outputs,
                accumulated_artifacts=accumulated_artifacts,
                account=account,
            )
            if plan_update.completed_enough:
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
                    payload={"step_count": len(step_outputs), "completed_enough": True},
                )
                answer = self._task_answer(run.task)
                yield emit(
                    QueueEvent.AGENT_MESSAGE,
                    thought=answer,
                    answer=answer,
                    total_token_count=max(1, len(answer) // 4) if answer else 0,
                )
                yield emit(QueueEvent.AGENT_END)
                return
            if plan_update.applied and plan_update.run is not None:
                yield emit(
                    QueueEvent.AGENT_ACTION,
                    observation="PlannerAgent updated the remaining plan from worker feedback.",
                    tool="planner.plan_update",
                    tool_input=(plan_update.run.plan.plan_json or {}).get("plan_update", {}),
                )
                run = execute_replanned_run(plan_update.run)
                answer = self._task_answer(run.task)
                if run.task.status == TaskStatus.SUCCEEDED.value:
                    yield emit(
                        QueueEvent.AGENT_MESSAGE,
                        thought=answer,
                        answer=answer,
                        total_token_count=max(1, len(answer) // 4) if answer else 0,
                    )
                    yield emit(QueueEvent.AGENT_END)
                else:
                    yield emit(QueueEvent.ERROR, observation=run.task.error_message, tool="planner.plan_update")
                return

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
                    selection_reason=self._rule_selection_reason(worker, source="manager_rule_v1"),
                    selection_signals=self._worker_selection_signals(worker),
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
            workers=None,
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
                            "planned_steps": self._plan_step_payload(plan, workers),
                            "plan_snapshot": self._plan_snapshot_payload(plan, workers),
                            "planning_reason": str(plan.risk_assessment.get("planning_reason") or ""),
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
                "selected_workers": self._worker_summary_payload(workers),
                "planned_steps": self._plan_step_payload(fallback_plan, workers),
                "plan_snapshot": self._plan_snapshot_payload(fallback_plan, workers),
                "planning_reason": str(fallback_plan.risk_assessment.get("planning_reason") or ""),
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
        replan_metadata: dict[str, Any] | None = None,
        plan_update_metadata: dict[str, Any] | None = None,
        workers: list[Agent] | None = None,
    ) -> RouterManagerRunResult:
        plan_json = plan.model_dump(mode="json")
        if preflight_result is not None:
            plan_json["preflight"] = preflight_result
        if replan_metadata is not None:
            plan_json["replan"] = self._json_ready(replan_metadata)
        if plan_update_metadata is not None:
            plan_json["plan_update"] = self._json_ready(plan_update_metadata)
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
                    "expected_output": step.expected_output,
                    "success_criteria": list(step.success_criteria or []),
                    "required_artifacts": list(step.required_artifacts or []),
                    "handoff_context": step.handoff_context,
                    "user_input": user_input,
                    "planner_selection": self._step_selection_payload(step, plan, workers or []),
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

    def _record_manager_run_created(
        self,
        session: Session,
        result: RouterManagerRunResult,
        *,
        workers: list[Agent] | None = None,
    ) -> None:
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
                "plan_snapshot": self._plan_json_snapshot_payload(result.plan.plan_json or {}, workers or []),
                "status": result.task.status,
                "steps": [
                    {
                        "step_id": str(step.id),
                        "step_key": step.step_key,
                        "worker_agent_id": str(step.worker_agent_id),
                        "task": self._step_task_text(step),
                        "selection_reason": self._planner_selection_from_step(step).get("reason", ""),
                        "selection_signals": self._planner_selection_from_step(step).get("signals", []),
                    }
                    for step in result.steps
                ],
            },
        )

    def _maybe_replan(
        self,
        session: Session,
        *,
        run: RouterManagerRunResult,
        router_agent: Agent,
        workers: list[Agent],
        account: Account | None,
        trigger: str,
        failed_step: AgentStep | None,
        error_code: str,
        user_message: str,
        failure_payload: dict[str, Any] | None = None,
        completed_steps: list[dict[str, Any]] | None = None,
    ) -> ReplanAttemptResult:
        if not self._replan_error_retryable(error_code):
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.replan.fallback",
                task=run.task,
                plan=run.plan,
                step=failed_step,
                payload={
                    "reason": "replan_error_not_retryable",
                    "trigger": trigger,
                    "error_code": error_code,
                },
            )
            return ReplanAttemptResult(run=None, error_code=error_code, user_message=user_message)

        routing_policy = self._routing_policy_for_agent(session, router_agent)
        if not self._replan_policy_allows(routing_policy, trigger):
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.replan.fallback",
                task=run.task,
                plan=run.plan,
                step=failed_step,
                payload={
                    "reason": "replan_disabled_by_policy",
                    "trigger": trigger,
                    "error_code": error_code,
                },
            )
            return ReplanAttemptResult(run=None, error_code=error_code, user_message=user_message)

        attempt = self._next_replan_attempt(run.plan)
        max_attempts = self._max_replan_attempts(routing_policy)
        if attempt > max_attempts:
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.replan.limit_exceeded",
                task=run.task,
                plan=run.plan,
                step=failed_step,
                payload={
                    "trigger": trigger,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_code": error_code,
                },
            )
            return ReplanAttemptResult(
                run=None,
                error_code="replan_limit_exceeded",
                user_message=user_message,
            )

        failure_payload = failure_payload or {}
        candidate_workers = self._select_replan_workers(
            workers,
            trigger=trigger,
            failed_step=failed_step,
            failure_payload=failure_payload,
        )
        if not candidate_workers:
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.replan.fallback",
                task=run.task,
                plan=run.plan,
                step=failed_step,
                payload={
                    "reason": "replan_candidate_workers_missing",
                    "trigger": trigger,
                    "attempt": attempt,
                    "error_code": error_code,
                },
            )
            return ReplanAttemptResult(run=None, error_code=error_code, user_message=user_message)

        failure = {
            "trigger": trigger,
            "error_code": error_code,
            "user_message": user_message,
            **failure_payload,
        }
        completed_steps = completed_steps or self._completed_step_payloads(run.steps)
        self.trace_service.record(
            session,
            tenant_id=run.task.tenant_id,
            event_type="planner.replan.requested",
            task=run.task,
            plan=run.plan,
            step=failed_step,
            payload={
                "trigger": trigger,
                "attempt": attempt,
                "current_plan_id": str(run.plan.id),
                "current_plan_snapshot": self._plan_json_snapshot_payload(run.plan.plan_json or {}, workers),
                "failed_step_id": str(failed_step.id) if failed_step else "",
                "failed_step_key": failed_step.step_key if failed_step else "",
                "failed_step_task": self._step_task_text(failed_step),
                "candidate_worker_ids": [str(worker.id) for worker in candidate_workers],
                "candidate_workers": self._worker_summary_payload(candidate_workers),
                "error_code": error_code,
            },
        )

        try:
            replan = self._build_replan_or_fallback_plan(
                session,
                task=run.task,
                router_agent=router_agent,
                current_plan=run.plan,
                failed_step=failed_step,
                failure=failure,
                completed_steps=completed_steps,
                workers=candidate_workers,
                account=account,
                attempt=attempt,
            )
            preflight_result = self._preflight_plan(
                session,
                task=run.task,
                router_agent=router_agent,
                workers=candidate_workers,
                plan=replan,
                user_input=run.task.user_input or {},
                account=account,
                event_type_prefix="planner.replan.preflight",
            )
        except Exception as exc:  # noqa: BLE001
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.replan.fallback",
                task=run.task,
                plan=run.plan,
                step=failed_step,
                payload={
                    "reason": "replan_generation_failed",
                    "trigger": trigger,
                    "attempt": attempt,
                    "error": self._truncate(str(exc), 1000),
                },
            )
            return ReplanAttemptResult(run=None, error_code=error_code, user_message=user_message)

        if preflight_result.get("status") == "failed":
            next_error_code, next_user_message = self._first_preflight_error(preflight_result)
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.replan.fallback",
                task=run.task,
                plan=run.plan,
                step=failed_step,
                payload={
                    "reason": "replan_preflight_failed",
                    "trigger": trigger,
                    "attempt": attempt,
                    "error_code": next_error_code,
                    "user_message": next_user_message,
                },
            )
            return ReplanAttemptResult(run=None, error_code=next_error_code, user_message=next_user_message)

        previous_plan_snapshot = self._plan_json_snapshot_payload(run.plan.plan_json or {}, workers)
        new_plan_snapshot = self._plan_snapshot_payload(replan, candidate_workers)
        plan_diff = self._plan_diff_payload(previous_plan_snapshot, new_plan_snapshot)
        new_run = self._persist_manager_plan_for_task(
            session,
            task=run.task,
            plan=replan,
            user_input=run.task.user_input or {},
            preflight_result=preflight_result,
            workers=candidate_workers,
            replan_metadata={
                "schema_version": "router_replan_v1",
                "attempt": attempt,
                "trigger": trigger,
                "parent_plan_id": str(run.plan.id),
                "failed_step_id": str(failed_step.id) if failed_step else "",
                "failed_step_key": failed_step.step_key if failed_step else "",
                "failed_worker_agent_id": str(failed_step.worker_agent_id) if failed_step else "",
                "failure": failure,
                "completed_steps": completed_steps,
                "candidate_worker_ids": [str(worker.id) for worker in candidate_workers],
                "preflight": preflight_result,
                "previous_plan": previous_plan_snapshot,
                "new_plan": new_plan_snapshot,
                "plan_diff": plan_diff,
            },
        )
        self._mark_replanned_step_failed(
            session,
            step=failed_step,
            error_code=error_code,
            user_message=user_message,
        )
        self._mark_plan_superseded(session, run.plan, superseded_by_plan_id=new_run.plan.id)
        self._record_manager_run_created(session, new_run, workers=candidate_workers)
        self.trace_service.record(
            session,
            tenant_id=run.task.tenant_id,
            event_type="planner.replan.applied",
            task=run.task,
            plan=new_run.plan,
            step=failed_step,
            payload={
                "attempt": attempt,
                "trigger": trigger,
                "parent_plan_id": str(run.plan.id),
                "new_plan_id": str(new_run.plan.id),
                "new_step_ids": [str(step.id) for step in new_run.steps],
                "planned_steps": self._plan_step_payload(replan, candidate_workers),
                "previous_plan": previous_plan_snapshot,
                "new_plan": new_plan_snapshot,
                "plan_diff": plan_diff,
            },
        )
        return ReplanAttemptResult(run=new_run)

    def _maybe_update_plan_from_feedback(
        self,
        session: Session,
        *,
        run: RouterManagerRunResult,
        step: AgentStep,
        worker_result: WorkerResult,
        completed_steps: list[dict[str, Any]],
        accumulated_artifacts: list[dict[str, Any]],
        account: Account | None,
    ) -> PlanUpdateAttemptResult:
        feedback = self._worker_plan_feedback(worker_result)
        if not feedback:
            return PlanUpdateAttemptResult(run=None)

        completed_enough = bool(feedback.get("completed_enough"))
        needs_plan_update = bool(feedback.get("needs_plan_update"))
        if not completed_enough and not needs_plan_update:
            return PlanUpdateAttemptResult(run=None)

        router_agent = self.get_router_agent(session, run.task.tenant_id, run.task.router_agent_id)
        workers = self.list_bound_workers(
            session,
            tenant_id=run.task.tenant_id,
            router_agent_id=run.task.router_agent_id,
        )
        routing_policy = self._routing_policy_for_agent(session, router_agent)
        if not self._plan_update_policy_allows(routing_policy):
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.plan_update.fallback",
                task=run.task,
                plan=run.plan,
                step=step,
                payload={
                    "reason": "plan_update_disabled_by_policy",
                    "feedback": self._json_ready(feedback),
                },
            )
            return PlanUpdateAttemptResult(run=None)

        remaining_step_count = self._remaining_step_count(run.steps)
        if completed_enough:
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.plan_update.completed_enough",
                task=run.task,
                plan=run.plan,
                step=step,
                payload={
                    "feedback": self._json_ready(feedback),
                    "remaining_step_count": remaining_step_count,
                },
            )
            return PlanUpdateAttemptResult(run=None, completed_enough=True)

        if remaining_step_count <= 0:
            return PlanUpdateAttemptResult(run=None)

        attempt = self._next_plan_update_attempt(run.plan)
        max_attempts = self._max_plan_update_attempts(routing_policy)
        if attempt > max_attempts:
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.plan_update.limit_exceeded",
                task=run.task,
                plan=run.plan,
                step=step,
                payload={
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "feedback": self._json_ready(feedback),
                },
            )
            return PlanUpdateAttemptResult(
                run=None,
                error_code="plan_update_limit_exceeded",
                user_message="Plan update limit exceeded",
            )

        candidate_workers = self._select_plan_update_workers(workers, feedback=feedback)
        if not candidate_workers:
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.plan_update.fallback",
                task=run.task,
                plan=run.plan,
                step=step,
                payload={
                    "reason": "plan_update_candidate_workers_missing",
                    "attempt": attempt,
                    "feedback": self._json_ready(feedback),
                },
            )
            return PlanUpdateAttemptResult(run=None)

        self.trace_service.record(
            session,
            tenant_id=run.task.tenant_id,
            event_type="planner.plan_update.requested",
            task=run.task,
            plan=run.plan,
            step=step,
            payload={
                "attempt": attempt,
                "current_plan_id": str(run.plan.id),
                "current_plan_snapshot": self._plan_json_snapshot_payload(run.plan.plan_json or {}, workers),
                "latest_step_id": str(step.id),
                "latest_step_key": step.step_key,
                "latest_step_task": self._step_task_text(step),
                "candidate_worker_ids": [str(worker.id) for worker in candidate_workers],
                "candidate_workers": self._worker_summary_payload(candidate_workers),
                "feedback": self._json_ready(feedback),
            },
        )

        try:
            updated_plan = self._build_plan_update_from_feedback(
                session,
                task=run.task,
                router_agent=router_agent,
                current_plan=run.plan,
                latest_step=step,
                worker_result=worker_result,
                plan_feedback=feedback,
                completed_steps=completed_steps,
                workers=candidate_workers,
                account=account,
                attempt=attempt,
            )
            preflight_result = self._preflight_plan(
                session,
                task=run.task,
                router_agent=router_agent,
                workers=candidate_workers,
                plan=updated_plan,
                user_input=run.task.user_input or {},
                account=account,
                event_type_prefix="planner.plan_update.preflight",
            )
        except Exception as exc:  # noqa: BLE001
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.plan_update.fallback",
                task=run.task,
                plan=run.plan,
                step=step,
                payload={
                    "reason": "plan_update_generation_failed",
                    "attempt": attempt,
                    "error": self._truncate(str(exc), 1000),
                },
            )
            return PlanUpdateAttemptResult(run=None)

        if preflight_result.get("status") == "failed":
            error_code, user_message = self._first_preflight_error(preflight_result)
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="planner.plan_update.fallback",
                task=run.task,
                plan=run.plan,
                step=step,
                payload={
                    "reason": "plan_update_preflight_failed",
                    "attempt": attempt,
                    "error_code": error_code,
                    "user_message": user_message,
                },
            )
            return PlanUpdateAttemptResult(run=None, error_code=error_code, user_message=user_message)

        previous_plan_snapshot = self._plan_json_snapshot_payload(run.plan.plan_json or {}, workers)
        new_plan_snapshot = self._plan_snapshot_payload(updated_plan, candidate_workers)
        plan_diff = self._plan_diff_payload(previous_plan_snapshot, new_plan_snapshot)
        new_run = self._persist_manager_plan_for_task(
            session,
            task=run.task,
            plan=updated_plan,
            user_input=run.task.user_input or {},
            preflight_result=preflight_result,
            workers=candidate_workers,
            plan_update_metadata={
                "schema_version": "router_plan_update_v1",
                "attempt": attempt,
                "trigger": "worker_plan_feedback",
                "parent_plan_id": str(run.plan.id),
                "latest_step_id": str(step.id),
                "latest_step_key": step.step_key,
                "latest_worker_agent_id": str(step.worker_agent_id),
                "plan_feedback": self._json_ready(feedback),
                "completed_steps": self._json_ready(completed_steps),
                "candidate_worker_ids": [str(worker.id) for worker in candidate_workers],
                "preflight": preflight_result,
                "previous_plan": previous_plan_snapshot,
                "new_plan": new_plan_snapshot,
                "plan_diff": plan_diff,
                "artifacts": self._json_ready(accumulated_artifacts),
            },
        )
        self._mark_plan_superseded(session, run.plan, superseded_by_plan_id=new_run.plan.id)
        self._record_manager_run_created(session, new_run, workers=candidate_workers)
        self.trace_service.record(
            session,
            tenant_id=run.task.tenant_id,
            event_type="planner.plan_update.applied",
            task=run.task,
            plan=new_run.plan,
            step=step,
            payload={
                "attempt": attempt,
                "trigger": "worker_plan_feedback",
                "parent_plan_id": str(run.plan.id),
                "new_plan_id": str(new_run.plan.id),
                "new_step_ids": [str(step.id) for step in new_run.steps],
                "planned_steps": self._plan_step_payload(updated_plan, candidate_workers),
                "previous_plan": previous_plan_snapshot,
                "new_plan": new_plan_snapshot,
                "plan_diff": plan_diff,
                "feedback": self._json_ready(feedback),
            },
        )
        return PlanUpdateAttemptResult(run=new_run)

    def _build_plan_update_from_feedback(
        self,
        session: Session,
        *,
        task: AgentTask,
        router_agent: Agent,
        current_plan: AgentPlan,
        latest_step: AgentStep,
        worker_result: WorkerResult,
        plan_feedback: dict[str, Any],
        completed_steps: list[dict[str, Any]],
        workers: list[Agent],
        account: Account | None,
        attempt: int,
    ) -> RouterPlan:
        if account is None:
            raise FailException("planner_account_context_missing")
        model = self.language_model_service.load_language_model(
            self._router_model_config(session, router_agent),
            session=session,
            account=account,
        )
        update_result = self.planner_agent.update_plan_from_feedback(
            model=model,
            feedback_input=self._build_plan_feedback_input(
                session=session,
                task=task,
                router_agent=router_agent,
                current_plan=current_plan,
                latest_step=latest_step,
                worker_result=worker_result,
                plan_feedback=plan_feedback,
                completed_steps=completed_steps,
                workers=workers,
                attempt=attempt,
            ),
        )
        if update_result.raw_output:
            self.trace_service.record(
                session,
                tenant_id=task.tenant_id,
                event_type="planner.plan_update.generated",
                task=task,
                plan=current_plan,
                step=latest_step,
                payload={
                    "model": f"{model.provider}/{model.model}",
                    "usage": update_result.usage,
                    "latency_ms": update_result.latency_ms,
                    "raw_output": self._truncate(update_result.raw_output, 4000),
                },
                token_count=int(update_result.usage.get("total_tokens") or 0),
                latency=float((update_result.latency_ms or 0) / 1000),
            )
        if update_result.plan is None:
            raise FailException(update_result.error or "planner_plan_feedback_returned_empty_plan")
        plan = self.router_runtime.validate_plan(
            update_result.plan,
            allowed_worker_ids={str(worker.id) for worker in workers},
            router_id=str(router_agent.id),
            max_steps=5,
            allow_async=False,
            allow_required_approval=False,
        )
        self.trace_service.record(
            session,
            tenant_id=task.tenant_id,
            event_type="planner.plan_update.validated",
            task=task,
            plan=current_plan,
            step=latest_step,
            payload={
                "attempt": attempt,
                "step_count": len(plan.steps),
                "worker_ids": [step.worker_id for step in plan.steps],
                "planned_steps": self._plan_step_payload(plan, workers),
                "plan_snapshot": self._plan_snapshot_payload(plan, workers),
                "planning_reason": str(plan.risk_assessment.get("planning_reason") or ""),
                "risk_level": plan.risk_assessment.get("risk_level") or "low",
                "source": plan.risk_assessment.get("source") or "llm_plan_feedback_v1",
            },
        )
        return plan

    def _build_plan_feedback_input(
        self,
        *,
        session: Session,
        task: AgentTask,
        router_agent: Agent,
        current_plan: AgentPlan,
        latest_step: AgentStep,
        worker_result: WorkerResult,
        plan_feedback: dict[str, Any],
        completed_steps: list[dict[str, Any]],
        workers: list[Agent],
        attempt: int,
    ) -> PlannerPlanFeedbackInput:
        user_input = task.user_input or {}
        return PlannerPlanFeedbackInput(
            router_id=str(router_agent.id),
            original_query=self._user_query(user_input),
            current_plan=current_plan.plan_json or {},
            completed_steps=self._json_ready(completed_steps),
            latest_step=self._step_output_descriptor(latest_step),
            worker_result=self._json_ready(self._worker_result_to_output(worker_result)),
            plan_feedback=self._json_ready(plan_feedback),
            workers=[self._planner_worker_descriptor(session=session, worker=worker) for worker in workers],
            input_files=[],
            recent_history=self._recent_history_from_user_input(user_input),
            constraints={
                "allow_parallel": False,
                "allow_plan_update": True,
                "allow_required_approval": False,
                "execution_mode": "sync",
                "max_steps": 5,
            },
            attempt=attempt,
        )

    def _build_replan_or_fallback_plan(
        self,
        session: Session,
        *,
        task: AgentTask,
        router_agent: Agent,
        current_plan: AgentPlan,
        failed_step: AgentStep | None,
        failure: dict[str, Any],
        completed_steps: list[dict[str, Any]],
        workers: list[Agent],
        account: Account | None,
        attempt: int,
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
                replan_result = self.planner_agent.update_plan(
                    model=model,
                    replan_input=self._build_replan_input(
                        session=session,
                        task=task,
                        router_agent=router_agent,
                        current_plan=current_plan,
                        failed_step=failed_step,
                        failure=failure,
                        completed_steps=completed_steps,
                        workers=workers,
                        attempt=attempt,
                    ),
                )
                if replan_result.raw_output:
                    self.trace_service.record(
                        session,
                        tenant_id=task.tenant_id,
                        event_type="planner.replan.generated",
                        task=task,
                        plan=current_plan,
                        step=failed_step,
                        payload={
                            "model": f"{model.provider}/{model.model}",
                            "usage": replan_result.usage,
                            "latency_ms": replan_result.latency_ms,
                            "raw_output": self._truncate(replan_result.raw_output, 4000),
                        },
                        token_count=int(replan_result.usage.get("total_tokens") or 0),
                        latency=float((replan_result.latency_ms or 0) / 1000),
                    )
                if replan_result.plan is None:
                    fallback_reason = replan_result.error or "planner_replan_returned_empty_plan"
                else:
                    plan = self.router_runtime.validate_plan(
                        replan_result.plan,
                        allowed_worker_ids=allowed_worker_ids,
                        router_id=str(router_agent.id),
                        max_steps=5,
                        allow_async=False,
                        allow_required_approval=False,
                    )
                    self.trace_service.record(
                        session,
                        tenant_id=task.tenant_id,
                        event_type="planner.replan.validated",
                        task=task,
                        plan=current_plan,
                        step=failed_step,
                        payload={
                            "attempt": attempt,
                            "step_count": len(plan.steps),
                            "worker_ids": [step.worker_id for step in plan.steps],
                            "planned_steps": self._plan_step_payload(plan, workers),
                            "plan_snapshot": self._plan_snapshot_payload(plan, workers),
                            "planning_reason": str(plan.risk_assessment.get("planning_reason") or ""),
                            "risk_level": plan.risk_assessment.get("risk_level") or "low",
                            "source": plan.risk_assessment.get("source") or "llm_replan_v1",
                        },
                    )
                    return plan
            except Exception as exc:  # noqa: BLE001
                fallback_reason = str(exc)

        fallback_plan = self._build_rule_replan_plan(
            router_agent=router_agent,
            workers=workers,
            user_input=task.user_input or {},
            failed_step=failed_step,
            attempt=attempt,
        )
        self.trace_service.record(
            session,
            tenant_id=task.tenant_id,
            event_type="planner.replan.fallback",
            task=task,
            plan=current_plan,
            step=failed_step,
            payload={
                "reason": self._truncate(fallback_reason, 1000),
                "attempt": attempt,
                "source": "manager_replan_rule_v1",
                "selected_worker_ids": [str(worker.id) for worker in workers[:1]],
                "selected_workers": self._worker_summary_payload(workers[:1]),
                "planned_steps": self._plan_step_payload(fallback_plan, workers),
                "plan_snapshot": self._plan_snapshot_payload(fallback_plan, workers),
                "planning_reason": str(fallback_plan.risk_assessment.get("planning_reason") or ""),
            },
        )
        return self.router_runtime.validate_plan(
            fallback_plan,
            allowed_worker_ids=allowed_worker_ids,
            router_id=str(router_agent.id),
            max_steps=5,
            allow_async=False,
            allow_required_approval=False,
        )

    def _build_replan_input(
        self,
        *,
        session: Session,
        task: AgentTask,
        router_agent: Agent,
        current_plan: AgentPlan,
        failed_step: AgentStep | None,
        failure: dict[str, Any],
        completed_steps: list[dict[str, Any]],
        workers: list[Agent],
        attempt: int,
    ) -> PlannerReplanInput:
        user_input = task.user_input or {}
        return PlannerReplanInput(
            router_id=str(router_agent.id),
            original_query=self._user_query(user_input),
            current_plan=current_plan.plan_json or {},
            failed_step=self._step_failure_descriptor(failed_step),
            failure=self._json_ready(failure),
            completed_steps=self._json_ready(completed_steps),
            workers=[self._planner_worker_descriptor(session=session, worker=worker) for worker in workers],
            input_files=[],
            recent_history=self._recent_history_from_user_input(user_input),
            constraints={
                "allow_parallel": False,
                "allow_replan": True,
                "allow_required_approval": False,
                "execution_mode": "sync",
                "max_steps": 5,
            },
            attempt=attempt,
        )

    def _build_rule_replan_plan(
        self,
        *,
        router_agent: Agent,
        workers: list[Agent],
        user_input: dict[str, Any],
        failed_step: AgentStep | None,
        attempt: int,
    ) -> RouterPlan:
        if not workers:
            raise FailException("Router agent has no available worker bindings for replan")
        task_text = ""
        if failed_step is not None and isinstance(failed_step.input_json, dict):
            task_text = str(failed_step.input_json.get("task") or "")
        task_text = task_text or self._user_query(user_input) or "Complete the remaining user request"
        worker = workers[0]
        return RouterPlan(
            router_id=str(router_agent.id),
            user_intent=self._user_query(user_input),
            risk_assessment={"risk_level": "low", "source": "manager_replan_rule_v1"},
            steps=[
                RouterPlanStep(
                    step_id=f"replan_{attempt}_step_1",
                    worker_id=str(worker.id),
                    task=task_text,
                    dependencies=[],
                    execution_mode="sync",
                    required_approval=False,
                    selection_reason=self._rule_selection_reason(worker, source="manager_replan_rule_v1"),
                    selection_signals=self._worker_selection_signals(worker),
                )
            ],
            final_response_policy={"mode": "summarize_worker_results"},
        )

    def execute_manager_run_steps(
        self,
        session: Session,
        *,
        run: RouterManagerRunResult,
        account: Account,
        _step_outputs: list[dict[str, Any]] | None = None,
        _accumulated_artifacts: list[dict[str, Any]] | None = None,
    ) -> RouterManagerRunResult:
        if run.task.status in {TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}:
            return run
        if self._is_waiting_task_status(run.task.status):
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

        step_outputs = list(_step_outputs or [])
        accumulated_artifacts: list[dict[str, Any]] = list(_accumulated_artifacts or [])
        for step in run.steps:
            if step.status == TaskStatus.SUCCEEDED.value:
                self._append_step_output(step_outputs, step, worker_agent_id=str(step.worker_agent_id))
                accumulated_artifacts.extend(list((step.output_json or {}).get("artifacts") or []))
                continue
            if step.status == TaskStatus.WAITING_USER.value:
                if self._is_waiting_task_status(run.task.status):
                    return run
                self.task_engine.resume_step(session, step)
            if step.status == TaskStatus.CREATED.value:
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
                router_agent = self.get_router_agent(session, run.task.tenant_id, run.task.router_agent_id)
                workers = self.list_bound_workers(
                    session,
                    tenant_id=run.task.tenant_id,
                    router_agent_id=run.task.router_agent_id,
                )
                replan = self._maybe_replan(
                    session,
                    run=run,
                    router_agent=router_agent,
                    workers=workers,
                    account=account,
                    trigger="capability_preflight_failed",
                    failed_step=step,
                    error_code=error_code,
                    user_message=user_message,
                    failure_payload={"preflight": step.input_json.get("preflight") or {}},
                    completed_steps=step_outputs,
                )
                if replan.applied and replan.run is not None:
                    return self.execute_manager_run_steps(
                        session,
                        run=replan.run,
                        account=account,
                        _step_outputs=step_outputs,
                        _accumulated_artifacts=accumulated_artifacts,
                    )
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code=replan.error_code or error_code,
                    error_message=replan.user_message or user_message,
                    final_result={"step_key": step.step_key, "preflight": step.input_json.get("preflight")},
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
                payload=self._worker_trace_payload(worker, step),
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
                payload=self._worker_trace_payload(
                    worker,
                    step,
                    execution_agent_type=invocation.execution_policy.get("execution_agent_type"),
                    executor_type=invocation.execution_policy.get("executor_type"),
                ),
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
                error_message = str(exc)
                self.task_engine.complete_worker_call(
                    session,
                    worker_call,
                    status=TaskStatus.FAILED,
                    result_json={"error": error_message},
                )
                self.task_engine.fail_step(
                    session,
                    step,
                    error_code="worker_execution_failed",
                    error_message=error_message,
                )
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="worker.call.failed",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    worker_call=worker_call,
                    payload=self._worker_trace_payload(worker, step, error=error_message),
                )
                router_agent = self.get_router_agent(session, run.task.tenant_id, run.task.router_agent_id)
                workers = self.list_bound_workers(
                    session,
                    tenant_id=run.task.tenant_id,
                    router_agent_id=run.task.router_agent_id,
                )
                replan = self._maybe_replan(
                    session,
                    run=run,
                    router_agent=router_agent,
                    workers=workers,
                    account=account,
                    trigger="worker_failed",
                    failed_step=step,
                    error_code="worker_execution_failed",
                    user_message=error_message,
                    failure_payload={"exception": error_message},
                    completed_steps=step_outputs,
                )
                if replan.applied and replan.run is not None:
                    return self.execute_manager_run_steps(
                        session,
                        run=replan.run,
                        account=account,
                        _step_outputs=step_outputs,
                        _accumulated_artifacts=accumulated_artifacts,
                    )
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code=replan.error_code or "worker_execution_failed",
                    error_message=replan.user_message or error_message,
                    final_result={"step_key": step.step_key},
                )
                return run

            output = self._worker_result_to_output(worker_result)
            self._record_agent_events(session, run=run, step=step, worker_call=worker_call, worker_result=worker_result)
            if worker_result.status == TaskStatus.WAITING_USER.value:
                plan_feedback = self._worker_plan_feedback(worker_result)
                self.task_engine.wait_worker_call_for_user(session, worker_call, result_json=output)
                self.task_engine.wait_step_for_user(session, step, output_json=output)
                self.task_engine.wait_for_user(
                    session,
                    run.task,
                    final_result={
                        "step_key": step.step_key,
                        "worker_result": output,
                        "completed_steps": step_outputs,
                        "artifacts": accumulated_artifacts,
                    },
                    error_message=worker_result.summary or "Worker is waiting for user input",
                )
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="wait.user.requested",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    worker_call=worker_call,
                    payload=self._worker_trace_payload(
                        worker,
                        step,
                        status=TaskStatus.WAITING.value,
                        worker_result_status=worker_result.status,
                        wait_type="user_input",
                        reason_code=plan_feedback.get("reason_code") or "missing_info",
                        resume_policy="resume_same_step",
                        summary=worker_result.summary,
                        missing_info=plan_feedback.get("missing_info", []),
                        plan_feedback=plan_feedback,
                    ),
                )
                return run
            if worker_result.status != TaskStatus.SUCCEEDED.value:
                terminal_status = self._worker_terminal_status(worker_result)
                self.task_engine.complete_worker_call(
                    session,
                    worker_call,
                    status=terminal_status,
                    result_json=output,
                )
                self.task_engine.fail_step(
                    session,
                    step,
                    error_code=worker_result.error_code or "worker_execution_failed",
                    error_message=worker_result.summary or "Worker execution failed",
                )
                self.trace_service.record(
                    session,
                    tenant_id=run.task.tenant_id,
                    event_type="worker.call.failed",
                    task=run.task,
                    plan=run.plan,
                    step=step,
                    worker_call=worker_call,
                    payload=self._worker_trace_payload(
                        worker,
                        step,
                        status=worker_result.status,
                        error_code=worker_result.error_code,
                        summary=worker_result.summary,
                        replan_signal=self._worker_replan_signal(worker_result),
                    ),
                )
                if terminal_status != TaskStatus.CANCELLED:
                    router_agent = self.get_router_agent(session, run.task.tenant_id, run.task.router_agent_id)
                    workers = self.list_bound_workers(
                        session,
                        tenant_id=run.task.tenant_id,
                        router_agent_id=run.task.router_agent_id,
                    )
                    replan = self._maybe_replan(
                        session,
                        run=run,
                        router_agent=router_agent,
                        workers=workers,
                        account=account,
                        trigger="worker_failed",
                        failed_step=step,
                        error_code=worker_result.error_code or "worker_execution_failed",
                        user_message=worker_result.summary or "Worker execution failed",
                        failure_payload={"worker_result": output},
                        completed_steps=step_outputs,
                    )
                    if replan.applied and replan.run is not None:
                        return self.execute_manager_run_steps(
                            session,
                            run=replan.run,
                            account=account,
                            _step_outputs=step_outputs,
                            _accumulated_artifacts=accumulated_artifacts,
                        )
                    error_code = replan.error_code or worker_result.error_code or "worker_execution_failed"
                    error_message = replan.user_message or worker_result.summary or "Worker execution failed"
                else:
                    error_code = worker_result.error_code or "worker_execution_failed"
                    error_message = worker_result.summary or "Worker execution failed"
                self.task_engine.fail_task(
                    session,
                    run.task,
                    error_code=error_code,
                    error_message=error_message,
                    final_result={"step_key": step.step_key, "worker_result": output},
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
                payload=self._worker_trace_payload(
                    worker,
                    step,
                    answer_length=len(str(output.get("answer") or "")),
                    worker_result_status=worker_result.status,
                    artifact_count=len(step_artifacts),
                ),
            )
            self.trace_service.record(
                session,
                tenant_id=run.task.tenant_id,
                event_type="router.step.succeeded",
                task=run.task,
                plan=run.plan,
                step=step,
                payload=self._worker_trace_payload(worker, step),
            )
            plan_update = self._maybe_update_plan_from_feedback(
                session,
                run=run,
                step=step,
                worker_result=worker_result,
                completed_steps=step_outputs,
                accumulated_artifacts=accumulated_artifacts,
                account=account,
            )
            if plan_update.completed_enough:
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
                    payload={"step_count": len(step_outputs), "completed_enough": True},
                )
                return run
            if plan_update.applied and plan_update.run is not None:
                return self.execute_manager_run_steps(
                    session,
                    run=plan_update.run,
                    account=account,
                    _step_outputs=step_outputs,
                    _accumulated_artifacts=accumulated_artifacts,
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
                "workers": self._worker_summary_payload(selected_workers),
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
            workers=selected_workers,
        )
        self._record_manager_run_created(session, result, workers=selected_workers)
        if preflight_result.get("status") == "failed":
            error_code, user_message = self._first_preflight_error(preflight_result)
            replan = self._maybe_replan(
                session,
                run=result,
                router_agent=router,
                workers=selected_workers,
                account=account,
                trigger="capability_preflight_failed",
                failed_step=self._first_failed_preflight_step(result),
                error_code=error_code,
                user_message=user_message,
                failure_payload={"preflight": preflight_result},
            )
            if replan.applied:
                return replan.run
            self._fail_run_for_preflight(
                session,
                run=result,
                error_code=replan.error_code or error_code,
                user_message=replan.user_message or user_message,
            )
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
        self._ensure_worker_app_for_capability(session, app_id=app_id, account=account)
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
        self._ensure_worker_app_for_capability(session, app_id=app_id, account=account)
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
        self._ensure_worker_app_for_capability(session, app_id=app_id, account=account)
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

    def _ensure_worker_app_for_capability(
        self,
        session: Session,
        *,
        app_id: uuid.UUID,
        account: Account,
    ) -> App:
        app = self.app_service.get_app(session, app_id, account)
        if (getattr(app, "agent_type", "worker") or "worker") != "worker":
            raise FailException(
                "PlannerAgent 不直接维护能力摘要，"
                "请在 Planner 编排的 WorkerAgent 绑定列表中查看每个 Worker 的能力摘要"
            )
        return app

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

    def dry_run_planner(
        self,
        session: Session,
        *,
        planner_app_id: uuid.UUID,
        account: Account,
        query: str,
        image_urls: list[str] | None = None,
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
        selected_workers = self._select_workers(workers, candidate_worker_ids)
        if not selected_workers:
            raise FailException("Router agent has no available worker bindings")

        user_input = {
            "query": query,
            "image_urls": image_urls or [],
            "input_modalities": input_modalities or [],
            "invoke_from": "planner_dry_run",
        }
        allowed_worker_ids = {str(worker.id) for worker in selected_workers}
        fallback_reason = ""
        raw_output = ""
        usage: dict[str, Any] = {}
        latency_ms = 0
        try:
            model = self.language_model_service.load_language_model(
                self._router_model_config(session, planner_agent),
                session=session,
                account=account,
            )
            planner_result = self.planner_agent.create_plan(
                model=model,
                planner_input=PlannerInput(
                    router_id=str(planner_agent.id),
                    query=query,
                    workers=[
                        self._planner_worker_descriptor(session=session, worker=worker)
                        for worker in selected_workers
                    ],
                    constraints={
                        "allow_parallel": False,
                        "allow_replan": False,
                        "allow_required_approval": False,
                        "execution_mode": "sync",
                        "max_steps": 5,
                        "dry_run": True,
                    },
                ),
            )
            raw_output = planner_result.raw_output
            usage = planner_result.usage
            latency_ms = int(planner_result.latency_ms or 0)
            if planner_result.plan is None:
                fallback_reason = planner_result.error or "planner_returned_empty_plan"
                plan = self._build_rule_manager_plan(
                    router_agent=planner_agent,
                    workers=selected_workers,
                    user_input=user_input,
                )
            else:
                plan = self.router_runtime.validate_plan(
                    planner_result.plan,
                    allowed_worker_ids=allowed_worker_ids,
                    router_id=str(planner_agent.id),
                    max_steps=5,
                    allow_async=False,
                    allow_required_approval=False,
                )
        except Exception as exc:  # noqa: BLE001
            fallback_reason = str(exc)
            plan = self._build_rule_manager_plan(
                router_agent=planner_agent,
                workers=selected_workers,
                user_input=user_input,
            )

        preflight = self.router_runtime.preflight_plan(
            plan,
            worker_capabilities=self._worker_capability_map(session, selected_workers, account=account),
            user_input=user_input,
            routing_policy=self._routing_policy_for_agent(session, planner_agent),
        )
        plan_snapshot = self._plan_snapshot_payload(plan, selected_workers)
        return {
            "dry_run": True,
            "status": "ready" if preflight.get("status") == "succeeded" else "blocked",
            "query": query,
            "router_agent": self._agent_payload(planner_agent),
            "workers": self._worker_summary_payload(selected_workers),
            "plan": plan_snapshot,
            "planned_steps": plan_snapshot["steps"],
            "preflight": preflight,
            "source": plan.risk_assessment.get("source") or "",
            "risk_level": plan.risk_assessment.get("risk_level") or "low",
            "fallback_reason": self._truncate(fallback_reason, 1000),
            "raw_output": self._truncate(raw_output, 4000),
            "usage": usage,
            "latency_ms": latency_ms,
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
        requested_worker_ids: list[uuid.UUID] | None = None,
    ) -> list[uuid.UUID] | None:
        if not requested_worker_app_ids and not requested_worker_ids:
            return None
        requested_app_ids = {str(app_id) for app_id in requested_worker_app_ids}
        requested_agent_ids = {str(agent_id) for agent_id in requested_worker_ids or []}
        rows = (
            session.query(AgentBinding, Agent)
            .join(Agent, AgentBinding.worker_agent_id == Agent.id)
            .filter(
                AgentBinding.tenant_id == account.id,
                AgentBinding.router_agent_id == planner_agent_id,
                AgentBinding.enabled.is_(True),
                Agent.tenant_id == account.id,
                Agent.runtime_type == "worker",
            )
            .all()
        )
        worker_agent_ids = []
        matched_app_ids: set[str] = set()
        matched_agent_ids: set[str] = set()
        for _, worker in rows:
            worker_id = str(worker.id)
            app_id = str(worker.target_ref_id) if worker.target_ref_type == "app" else ""
            if worker_id in requested_agent_ids:
                worker_agent_ids.append(worker.id)
                matched_agent_ids.add(worker_id)
            if app_id in requested_app_ids:
                worker_agent_ids.append(worker.id)
                matched_app_ids.add(app_id)
        if len(matched_app_ids) != len(requested_app_ids):
            raise FailException("Requested worker apps must be enabled planner bindings")
        if len(matched_agent_ids) != len(requested_agent_ids):
            raise FailException("Requested worker agents must be enabled planner bindings")
        worker_agent_ids = list(dict.fromkeys(worker_agent_ids))
        return worker_agent_ids

    @staticmethod
    def _user_query(user_input: dict[str, Any]) -> str:
        return str(user_input.get("query") or user_input.get("input") or user_input.get("message") or "")

    @staticmethod
    def _replan_policy_allows(routing_policy: dict[str, Any], trigger: str) -> bool:
        fallback_policy = (
            routing_policy.get("fallback_policy") if isinstance(routing_policy.get("fallback_policy"), dict) else {}
        )
        if trigger == "worker_failed":
            return fallback_policy.get("on_worker_failed") == "replan_once"
        if trigger == "capability_preflight_failed":
            return fallback_policy.get("on_preflight_failed") == "replan_once"
        return False

    @staticmethod
    def _plan_update_policy_allows(routing_policy: dict[str, Any]) -> bool:
        fallback_policy = (
            routing_policy.get("fallback_policy") if isinstance(routing_policy.get("fallback_policy"), dict) else {}
        )
        return fallback_policy.get("on_plan_feedback") == "update_once"

    @staticmethod
    def _replan_error_retryable(error_code: str) -> bool:
        non_retryable = {
            "external_agent_auth_required",
            "replan_limit_exceeded",
        }
        return error_code not in non_retryable

    @staticmethod
    def _max_replan_attempts(routing_policy: dict[str, Any]) -> int:
        fallback_policy = (
            routing_policy.get("fallback_policy") if isinstance(routing_policy.get("fallback_policy"), dict) else {}
        )
        raw_value = fallback_policy.get("max_replan_attempts", fallback_policy.get("max_replans", 1))
        try:
            return max(0, int(raw_value))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _max_plan_update_attempts(routing_policy: dict[str, Any]) -> int:
        fallback_policy = (
            routing_policy.get("fallback_policy") if isinstance(routing_policy.get("fallback_policy"), dict) else {}
        )
        raw_value = fallback_policy.get("max_plan_update_attempts", fallback_policy.get("max_plan_updates", 1))
        try:
            return max(0, int(raw_value))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _next_replan_attempt(plan: AgentPlan) -> int:
        plan_json = plan.plan_json if isinstance(plan.plan_json, dict) else {}
        replan = plan_json.get("replan") if isinstance(plan_json.get("replan"), dict) else {}
        try:
            return int(replan.get("attempt") or 0) + 1
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _plan_attempt(plan: AgentPlan) -> int:
        plan_json = plan.plan_json if isinstance(plan.plan_json, dict) else {}
        replan = plan_json.get("replan") if isinstance(plan_json.get("replan"), dict) else {}
        plan_update = plan_json.get("plan_update") if isinstance(plan_json.get("plan_update"), dict) else {}
        try:
            return int(replan.get("attempt") or plan_update.get("attempt") or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _next_plan_update_attempt(plan: AgentPlan) -> int:
        plan_json = plan.plan_json if isinstance(plan.plan_json, dict) else {}
        plan_update = plan_json.get("plan_update") if isinstance(plan_json.get("plan_update"), dict) else {}
        try:
            return int(plan_update.get("attempt") or 0) + 1
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _select_replan_workers(
        workers: list[Agent],
        *,
        trigger: str,
        failed_step: AgentStep | None,
        failure_payload: dict[str, Any],
    ) -> list[Agent]:
        preflight = failure_payload.get("preflight") if isinstance(failure_payload.get("preflight"), dict) else {}
        suggested_worker_ids = preflight.get("suggested_worker_ids") or failure_payload.get("suggested_worker_ids")
        if isinstance(suggested_worker_ids, list) and suggested_worker_ids:
            suggested = {str(worker_id) for worker_id in suggested_worker_ids}
            return [worker for worker in workers if str(worker.id) in suggested]
        if trigger == "worker_failed" and failed_step is not None:
            return [worker for worker in workers if str(worker.id) != str(failed_step.worker_agent_id)]
        return workers

    @staticmethod
    def _select_plan_update_workers(
        workers: list[Agent],
        *,
        feedback: dict[str, Any],
    ) -> list[Agent]:
        suggested_worker_ids = feedback.get("suggested_worker_ids")
        if isinstance(suggested_worker_ids, list) and suggested_worker_ids:
            suggested = {str(worker_id) for worker_id in suggested_worker_ids}
            return [worker for worker in workers if str(worker.id) in suggested]
        return workers

    @staticmethod
    def _remaining_step_count(steps: list[AgentStep]) -> int:
        return sum(1 for step in steps if step.status == TaskStatus.CREATED.value)

    @staticmethod
    def _completed_step_payloads(steps: list[AgentStep]) -> list[dict[str, Any]]:
        payloads = []
        for step in steps:
            if step.status != TaskStatus.SUCCEEDED.value:
                continue
            payloads.append(
                {
                    "step_id": str(step.id),
                    "step_key": step.step_key,
                    "worker_agent_id": str(step.worker_agent_id),
                    "output": step.output_json or {},
                }
            )
        return payloads

    @staticmethod
    def _append_step_output(
        step_outputs: list[dict[str, Any]],
        step: AgentStep,
        *,
        worker_agent_id: str,
    ) -> None:
        if any(str(item.get("step_key") or "") == step.step_key for item in step_outputs):
            return
        step_outputs.append(
            {
                "step_key": step.step_key,
                "worker_agent_id": worker_agent_id,
                "output": step.output_json or {},
            }
        )

    @staticmethod
    def _step_failure_descriptor(step: AgentStep | None) -> dict[str, Any]:
        if step is None:
            return {}
        input_json = step.input_json if isinstance(step.input_json, dict) else {}
        return {
            "step_id": str(step.id),
            "step_key": step.step_key,
            "worker_agent_id": str(step.worker_agent_id),
            "status": step.status,
            "task": input_json.get("task") or "",
            "preflight": input_json.get("preflight") if isinstance(input_json.get("preflight"), dict) else {},
        }

    @staticmethod
    def _step_output_descriptor(step: AgentStep | None) -> dict[str, Any]:
        if step is None:
            return {}
        input_json = step.input_json if isinstance(step.input_json, dict) else {}
        success_criteria = input_json.get("success_criteria")
        required_artifacts = input_json.get("required_artifacts")
        return {
            "step_id": str(step.id),
            "step_key": step.step_key,
            "worker_agent_id": str(step.worker_agent_id),
            "status": step.status,
            "task": input_json.get("task") or "",
            "expected_output": input_json.get("expected_output") or "",
            "success_criteria": success_criteria if isinstance(success_criteria, list) else [],
            "required_artifacts": required_artifacts if isinstance(required_artifacts, list) else [],
            "handoff_context": input_json.get("handoff_context") or "",
            "output": step.output_json or {},
        }

    def _mark_replanned_step_failed(
        self,
        session: Session,
        *,
        step: AgentStep | None,
        error_code: str,
        user_message: str,
    ) -> None:
        if step is None or step.status in {
            TaskStatus.SUCCEEDED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }:
            return
        self.task_engine.fail_step(session, step, error_code=error_code, error_message=user_message)

    def _mark_plan_superseded(
        self,
        session: Session,
        plan: AgentPlan,
        *,
        superseded_by_plan_id: uuid.UUID,
    ) -> None:
        plan_json = dict(plan.plan_json or {})
        existing_replan = plan_json.get("replan")
        replan = dict(existing_replan) if isinstance(existing_replan, dict) else {}
        replan["superseded_by_plan_id"] = str(superseded_by_plan_id)
        plan_json["replan"] = replan
        self.update(session, plan, status="superseded", plan_json=plan_json)

    def _first_failed_preflight_step(self, run: RouterManagerRunResult) -> AgentStep | None:
        for step in run.steps:
            if self._step_preflight_failed(step):
                return step
        return None

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

    @classmethod
    def _plan_snapshot_payload(cls, plan: RouterPlan, workers: list[Agent]) -> dict[str, Any]:
        return {
            "schema_version": plan.schema_version,
            "router_id": plan.router_id,
            "user_intent": plan.user_intent,
            "risk_assessment": cls._json_ready(plan.risk_assessment),
            "final_response_policy": cls._json_ready(plan.final_response_policy),
            "steps": cls._plan_step_payload(plan, workers),
        }

    @classmethod
    def _plan_json_snapshot_payload(cls, plan_json: dict[str, Any] | None, workers: list[Agent]) -> dict[str, Any]:
        data = plan_json if isinstance(plan_json, dict) else {}
        worker_map = {str(worker.id): worker for worker in workers}
        risk_assessment = data.get("risk_assessment") if isinstance(data.get("risk_assessment"), dict) else {}
        source = str(risk_assessment.get("source") or "planner")
        steps = []
        for raw_step in data.get("steps", []) if isinstance(data.get("steps"), list) else []:
            if not isinstance(raw_step, dict):
                continue
            worker_id = str(raw_step.get("worker_id") or "")
            worker = worker_map.get(worker_id)
            signals = cls._unique_strings(
                [
                    *(raw_step.get("selection_signals") if isinstance(raw_step.get("selection_signals"), list) else []),
                    *cls._worker_selection_signals(worker),
                ]
            )
            steps.append(
                {
                    "step_id": str(raw_step.get("step_id") or ""),
                    "worker_id": worker_id,
                    "worker_name": worker.name if worker else str(raw_step.get("worker_name") or ""),
                    "task": str(raw_step.get("task") or ""),
                    "dependencies": list(raw_step.get("dependencies") or []),
                    "execution_mode": str(raw_step.get("execution_mode") or "sync"),
                    "required_approval": bool(raw_step.get("required_approval")),
                    "expected_output": str(raw_step.get("expected_output") or ""),
                    "success_criteria": [
                        str(item)
                        for item in raw_step.get("success_criteria", [])
                        if str(item).strip()
                    ]
                    if isinstance(raw_step.get("success_criteria"), list)
                    else [],
                    "required_artifacts": [
                        str(item)
                        for item in raw_step.get("required_artifacts", [])
                        if str(item).strip()
                    ]
                    if isinstance(raw_step.get("required_artifacts"), list)
                    else [],
                    "handoff_context": str(raw_step.get("handoff_context") or ""),
                    "selection_reason": str(
                        raw_step.get("selection_reason")
                        or cls._default_selection_reason(source=source, worker=worker)
                    ),
                    "selection_signals": signals,
                }
            )
        return {
            "schema_version": str(data.get("schema_version") or "router_plan_v1"),
            "router_id": str(data.get("router_id") or ""),
            "user_intent": str(data.get("user_intent") or ""),
            "risk_assessment": cls._json_ready(risk_assessment),
            "final_response_policy": cls._json_ready(data.get("final_response_policy") or {}),
            "steps": steps,
        }

    @classmethod
    def _plan_diff_payload(cls, previous_plan: dict[str, Any], next_plan: dict[str, Any]) -> dict[str, Any]:
        previous_steps = [step for step in previous_plan.get("steps", []) if isinstance(step, dict)]
        next_steps = [step for step in next_plan.get("steps", []) if isinstance(step, dict)]
        previous_by_key = {str(step.get("step_id") or ""): step for step in previous_steps}
        next_by_key = {str(step.get("step_id") or ""): step for step in next_steps}
        previous_keys = {key for key in previous_by_key if key}
        next_keys = {key for key in next_by_key if key}
        added = [next_by_key[key] for key in sorted(next_keys - previous_keys)]
        removed = [previous_by_key[key] for key in sorted(previous_keys - next_keys)]
        changed = []
        for key in sorted(previous_keys & next_keys):
            previous = previous_by_key[key]
            current = next_by_key[key]
            changes = {}
            if str(previous.get("worker_id") or "") != str(current.get("worker_id") or ""):
                changes["worker"] = {
                    "from": {
                        "id": str(previous.get("worker_id") or ""),
                        "name": str(previous.get("worker_name") or ""),
                    },
                    "to": {
                        "id": str(current.get("worker_id") or ""),
                        "name": str(current.get("worker_name") or ""),
                    },
                }
            if str(previous.get("task") or "") != str(current.get("task") or ""):
                changes["task"] = {
                    "from": str(previous.get("task") or ""),
                    "to": str(current.get("task") or ""),
                }
            for field in ("expected_output", "handoff_context"):
                if str(previous.get(field) or "") != str(current.get(field) or ""):
                    changes[field] = {
                        "from": str(previous.get(field) or ""),
                        "to": str(current.get(field) or ""),
                    }
            for field in ("success_criteria", "required_artifacts"):
                previous_values = list(previous.get(field) or [])
                current_values = list(current.get(field) or [])
                if previous_values != current_values:
                    changes[field] = {"from": previous_values, "to": current_values}
            if changes:
                changed.append({"step_id": key, "changes": changes})
        return {
            "added_steps": added,
            "removed_steps": removed,
            "changed_steps": changed,
            "summary": {
                "added": len(added),
                "removed": len(removed),
                "changed": len(changed),
            },
        }

    @classmethod
    def _plan_step_payload(cls, plan: RouterPlan, workers: list[Agent]) -> list[dict[str, Any]]:
        worker_map = {str(worker.id): worker for worker in workers}
        steps = []
        for step in plan.steps:
            worker = worker_map.get(str(step.worker_id))
            selection = cls._step_selection_payload(step, plan, workers)
            steps.append(
                {
                    "step_id": step.step_id,
                    "worker_id": str(step.worker_id),
                    "worker_name": worker.name if worker else "",
                    "target_ref_type": worker.target_ref_type if worker else "",
                    "target_ref_id": worker.target_ref_id if worker else "",
                    "product_category": worker.product_category if worker else "",
                    "task": step.task,
                    "dependencies": list(step.dependencies or []),
                    "execution_mode": step.execution_mode,
                    "required_approval": bool(step.required_approval),
                    "expected_output": step.expected_output,
                    "success_criteria": list(step.success_criteria or []),
                    "required_artifacts": list(step.required_artifacts or []),
                    "handoff_context": step.handoff_context,
                    "selection_reason": selection["reason"],
                    "selection_signals": selection["signals"],
                }
            )
        return steps

    @staticmethod
    def _worker_summary_payload(workers: list[Agent]) -> list[dict[str, Any]]:
        return [
            {
                "id": str(worker.id),
                "name": worker.name,
                "description": worker.description or "",
                "runtime_type": worker.runtime_type,
                "product_category": worker.product_category,
                "target_ref_type": worker.target_ref_type,
                "target_ref_id": worker.target_ref_id,
                "selection_signals": RouterAgentManagerService._worker_selection_signals(worker),
            }
            for worker in workers
        ]

    @classmethod
    def _worker_trace_payload(cls, worker: Agent, step: AgentStep, **extra: Any) -> dict[str, Any]:
        selection = cls._planner_selection_from_step(step)
        input_json = step.input_json if isinstance(step.input_json, dict) else {}
        success_criteria = input_json.get("success_criteria")
        required_artifacts = input_json.get("required_artifacts")
        payload = {
            "step_key": step.step_key,
            "task": cls._step_task_text(step),
            "worker_agent_id": str(worker.id),
            "worker_name": worker.name,
            "target_ref_type": worker.target_ref_type,
            "target_ref_id": worker.target_ref_id,
            "selection_reason": selection.get("reason", ""),
            "selection_signals": selection.get("signals", []),
            "expected_output": str(input_json.get("expected_output") or ""),
            "success_criteria": list(success_criteria or []) if isinstance(success_criteria, list) else [],
            "required_artifacts": list(required_artifacts or []) if isinstance(required_artifacts, list) else [],
            "handoff_context": str(input_json.get("handoff_context") or ""),
        }
        payload.update(extra)
        return payload

    @staticmethod
    def _step_task_text(step: AgentStep | None) -> str:
        if step is None or not isinstance(step.input_json, dict):
            return ""
        return str(step.input_json.get("task") or "")

    @classmethod
    def _step_selection_payload(cls, step: RouterPlanStep, plan: RouterPlan, workers: list[Agent]) -> dict[str, Any]:
        worker = {str(worker.id): worker for worker in workers}.get(str(step.worker_id))
        source = str(plan.risk_assessment.get("source") or "planner")
        reason = str(step.selection_reason or cls._default_selection_reason(source=source, worker=worker))
        signals = cls._unique_strings([*step.selection_signals, *cls._worker_selection_signals(worker)])
        return {
            "reason": reason,
            "signals": signals,
            "source": source,
        }

    @staticmethod
    def _planner_selection_from_step(step: AgentStep | None) -> dict[str, Any]:
        input_json = step.input_json if step is not None and isinstance(step.input_json, dict) else {}
        selection = input_json.get("planner_selection")
        if isinstance(selection, dict):
            return {
                "reason": str(selection.get("reason") or selection.get("selection_reason") or ""),
                "signals": [
                    str(item)
                    for item in selection.get("signals", selection.get("selection_signals", []))
                    if str(item).strip()
                ]
                if isinstance(selection.get("signals", selection.get("selection_signals", [])), list)
                else [],
                "source": str(selection.get("source") or ""),
            }
        return {"reason": "", "signals": [], "source": ""}

    @classmethod
    def _worker_selection_signals(cls, worker: Agent | None) -> list[str]:
        if worker is None:
            return []
        values = [
            f"name:{worker.name}",
            f"runtime:{worker.runtime_type}",
            f"category:{worker.product_category}",
            f"target:{worker.target_ref_type}",
        ]
        if worker.description:
            values.append(f"description:{cls._truncate(worker.description, 160)}")
        return cls._unique_strings(values)

    @classmethod
    def _rule_selection_reason(cls, worker: Agent, *, source: str) -> str:
        return cls._default_selection_reason(source=source, worker=worker)

    @staticmethod
    def _default_selection_reason(*, source: str, worker: Agent | None) -> str:
        worker_name = worker.name if worker is not None else "the selected worker"
        if "replan" in source:
            return f"Replan selected {worker_name} to recover the failed or remaining work."
        if "rule" in source:
            return f"Rule fallback selected {worker_name} from the bound WorkerAgent list."
        return f"Planner selected {worker_name} for this step based on worker metadata and routing constraints."

    @staticmethod
    def _unique_strings(values: list[Any]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

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
        event_type_prefix: str = "router.capability_preflight",
    ) -> dict[str, Any]:
        self.trace_service.record(
            session,
            tenant_id=task.tenant_id,
            event_type=f"{event_type_prefix}.started",
            task=task,
            payload={
                "router_agent_id": str(router_agent.id),
                "worker_ids": [str(worker.id) for worker in workers],
                "workers": self._worker_summary_payload(workers),
                "planned_steps": self._plan_step_payload(plan, workers),
                "plan_snapshot": self._plan_snapshot_payload(plan, workers),
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
            event_type=f"{event_type_prefix}.{result.get('status')}",
            task=task,
            payload={
                **result,
                "workers": self._worker_summary_payload(workers),
                "planned_steps": self._plan_step_payload(plan, workers),
                "plan_snapshot": self._plan_snapshot_payload(plan, workers),
            },
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
                "executor_type": self._worker_executor_type(worker),
                "plan_attempt": self._plan_attempt(run.plan),
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
                event_type=self._trace_event_type_for_agent_event(event.event_type),
                task=run.task,
                plan=run.plan,
                step=step,
                worker_call=worker_call,
                payload=event.model_dump(mode="json"),
            )

    @staticmethod
    def _trace_event_type_for_agent_event(event_type: str) -> str:
        if event_type.startswith(("worker.", "tool.", "artifact.", "wait.", "approval.", "task.", "error.")):
            return event_type
        return f"worker.event.{event_type}"

    @staticmethod
    def _worker_execution_agent_type(worker: Agent) -> str:
        if worker.target_ref_type == "a2a_agent":
            return "a2a_worker"
        if worker.target_ref_type == "app":
            return "react_worker"
        return "unsupported_worker"

    @staticmethod
    def _worker_executor_type(worker: Agent) -> str:
        if worker.target_ref_type == "a2a_agent":
            return "a2a"
        if worker.target_ref_type == "app":
            return "app"
        return str(worker.target_ref_type or "unknown")

    @staticmethod
    def _worker_result_to_output(worker_result: WorkerResult) -> dict[str, Any]:
        output = worker_result.model_dump(mode="json")
        output["answer"] = str(worker_result.data.get("answer") or worker_result.summary or "")
        return output

    @staticmethod
    def _worker_replan_signal(worker_result: WorkerResult) -> dict[str, Any]:
        signal = worker_result.data.get("replan_signal") if isinstance(worker_result.data, dict) else {}
        return signal if isinstance(signal, dict) else {}

    @staticmethod
    def _worker_plan_feedback(worker_result: WorkerResult) -> dict[str, Any]:
        feedback = worker_result.data.get("plan_feedback") if isinstance(worker_result.data, dict) else {}
        return feedback if isinstance(feedback, dict) else {}

    @staticmethod
    def _worker_terminal_status(worker_result: WorkerResult) -> TaskStatus:
        try:
            status = TaskStatus(worker_result.status)
        except ValueError:
            return TaskStatus.FAILED
        terminal_statuses = {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        return status if status in terminal_statuses else TaskStatus.FAILED

    @staticmethod
    def _is_waiting_task_status(status: str) -> bool:
        return str(status or "") in {item.value for item in TASK_WAITING_STATUSES}

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

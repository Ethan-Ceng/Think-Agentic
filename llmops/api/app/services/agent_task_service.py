import math
from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import String, cast, desc, false, func, or_
from sqlalchemy.orm import Session

from app.core.conversation import MessageStatus
from app.core.exceptions import NotFoundException
from app.models.account import Account
from app.models.agent import Agent
from app.models.conversation import Message, MessageAgentThought
from app.models.task import AgentPlan, AgentStep, AgentTask, CapabilityCall, WorkerCall
from app.models.trace import TraceEvent
from app.services.app_service import AppService
from app.services.base_service import BaseService


class AgentTaskService(BaseService):
    """Read-only task aggregation for Agent execution UI."""

    def __init__(self, *, app_service: AppService | None = None) -> None:
        self.app_service = app_service or AppService()

    def list_app_tasks_with_page(
        self,
        session: Session,
        *,
        app_id: UUID,
        account: Account,
        page: int = 1,
        page_size: int = 20,
        status: str = "all",
        search_word: str = "",
    ) -> tuple[list[dict[str, Any]], int, int]:
        self.app_service.get_app(session, app_id, account)
        app_agent_ids = self._app_agent_ids(session, app_id, account, validate_app=False)
        query = self._app_task_query(session, app_agent_ids)
        message_query = self._app_message_query(session, app_id)
        cleaned_status = (status or "all").strip().lower()
        if cleaned_status and cleaned_status != "all":
            query = query.filter(AgentTask.status == cleaned_status)
            message_query = self._filter_message_query_by_task_status(message_query, cleaned_status)
        cleaned_search = (search_word or "").strip()
        if cleaned_search:
            query = query.filter(cast(AgentTask.user_input, String).ilike(f"%{cleaned_search}%"))
            message_query = message_query.filter(Message.query.ilike(f"%{cleaned_search}%"))

        total_record = query.count() + message_query.count()
        total_page = math.ceil(total_record / page_size) if total_record else 0
        tasks: list[AgentTask | Message] = (
            query.order_by(desc(AgentTask.created_at))
            .limit(page * page_size)
            .all()
        )
        tasks.extend(
            message_query.order_by(desc(Message.created_at))
            .limit(page * page_size)
            .all()
        )
        items = sorted(tasks, key=lambda item: item.created_at, reverse=True)
        page_items = items[(page - 1) * page_size : page * page_size]
        agent_tasks = [item for item in page_items if isinstance(item, AgentTask)]
        messages = [item for item in page_items if isinstance(item, Message)]
        summaries_by_id = {item["id"]: item for item in self._summaries(session, agent_tasks)}
        summaries_by_id.update({item["id"]: item for item in self._message_summaries(session, messages)})
        return [summaries_by_id[item.id] for item in page_items], total_record, total_page

    def get_app_task_detail(
        self,
        session: Session,
        *,
        app_id: UUID,
        task_id: UUID,
        account: Account,
    ) -> dict[str, Any]:
        self.app_service.get_app(session, app_id, account)
        app_agent_ids = self._app_agent_ids(session, app_id, account, validate_app=False)
        task = self._app_task_query(session, app_agent_ids).filter(AgentTask.id == task_id).one_or_none()
        if task is None:
            message = self._app_message_query(session, app_id).filter(Message.id == task_id).one_or_none()
            if message is None:
                raise NotFoundException("Agent task does not exist")
            return self._message_detail(session, message)

        plans = (
            session.query(AgentPlan)
            .filter(AgentPlan.task_id == task.id)
            .order_by(AgentPlan.created_at.asc())
            .all()
        )
        steps = (
            session.query(AgentStep)
            .filter(AgentStep.task_id == task.id)
            .order_by(AgentStep.created_at.asc())
            .all()
        )
        worker_calls = (
            session.query(WorkerCall)
            .filter(WorkerCall.task_id == task.id)
            .order_by(WorkerCall.created_at.asc())
            .all()
        )
        capability_calls = (
            session.query(CapabilityCall)
            .filter(CapabilityCall.task_id == task.id)
            .order_by(CapabilityCall.created_at.asc())
            .all()
        )
        trace_events = (
            session.query(TraceEvent)
            .filter(TraceEvent.task_id == task.id)
            .order_by(TraceEvent.created_at.asc())
            .all()
        )

        agent_ids = {task.router_agent_id}
        agent_ids.update(step.worker_agent_id for step in steps)
        agent_ids.update(call.worker_agent_id for call in worker_calls)
        agent_map = self._agent_map(session, agent_ids)

        artifacts = self._collect_artifacts(task, steps, worker_calls)
        input_files = self._collect_input_files(task, worker_calls)
        return {
            **self._task_base(task, agent_map),
            "summary": self._final_summary(task.final_result),
            "step_count": len(steps),
            "worker_call_count": len(worker_calls),
            "artifact_count": len(artifacts),
            "trace_count": len(trace_events),
            "plans": [self._plan_response(plan) for plan in plans],
            "plan": self._plan_response(plans[-1]) if plans else None,
            "steps": [self._step_response(step, agent_map) for step in steps],
            "worker_calls": [self._worker_call_response(call, agent_map) for call in worker_calls],
            "capability_calls": [self._capability_call_response(call) for call in capability_calls],
            "trace_events": [self._trace_event_response(event) for event in trace_events],
            "input_files": input_files,
            "artifacts": artifacts,
        }

    def _app_agent_ids(self, session: Session, app_id: UUID, account: Account, *, validate_app: bool = True) -> list[UUID]:
        if validate_app:
            self.app_service.get_app(session, app_id, account)
        agents = (
            session.query(Agent)
            .filter(
                Agent.target_ref_type == "app",
                Agent.target_ref_id == str(app_id),
            )
            .all()
        )
        return [agent.id for agent in agents]

    @staticmethod
    def _app_message_query(session: Session, app_id: UUID):
        return session.query(Message).filter(
            Message.app_id == app_id,
            Message.is_deleted.is_(False),
        )

    @staticmethod
    def _app_task_query(session: Session, app_agent_ids: list[UUID]):
        if not app_agent_ids:
            return session.query(AgentTask).filter(false())
        worker_task_ids = session.query(AgentStep.task_id).filter(AgentStep.worker_agent_id.in_(app_agent_ids))
        return session.query(AgentTask).filter(
            or_(
                AgentTask.router_agent_id.in_(app_agent_ids),
                AgentTask.id.in_(worker_task_ids),
            )
        )

    def _summaries(self, session: Session, tasks: list[AgentTask]) -> list[dict[str, Any]]:
        if not tasks:
            return []
        task_ids = [task.id for task in tasks]
        steps = session.query(AgentStep).filter(AgentStep.task_id.in_(task_ids)).all()
        worker_calls = session.query(WorkerCall).filter(WorkerCall.task_id.in_(task_ids)).all()
        trace_counts = dict(
            session.query(TraceEvent.task_id, func.count(TraceEvent.id))
            .filter(TraceEvent.task_id.in_(task_ids))
            .group_by(TraceEvent.task_id)
            .all()
        )

        steps_by_task: dict[UUID, list[AgentStep]] = defaultdict(list)
        calls_by_task: dict[UUID, list[WorkerCall]] = defaultdict(list)
        agent_ids: set[UUID] = set()
        for task in tasks:
            agent_ids.add(task.router_agent_id)
        for step in steps:
            steps_by_task[step.task_id].append(step)
            agent_ids.add(step.worker_agent_id)
        for call in worker_calls:
            calls_by_task[call.task_id].append(call)
            agent_ids.add(call.worker_agent_id)
        agent_map = self._agent_map(session, agent_ids)

        summaries = []
        for task in tasks:
            task_steps = steps_by_task.get(task.id, [])
            task_calls = calls_by_task.get(task.id, [])
            artifacts = self._collect_artifacts(task, task_steps, task_calls)
            summaries.append(
                {
                    **self._task_base(task, agent_map),
                    "summary": self._final_summary(task.final_result),
                    "user_input_preview": self._user_input_preview(task.user_input),
                    "step_count": len(task_steps),
                    "succeeded_step_count": sum(1 for step in task_steps if step.status == "succeeded"),
                    "failed_step_count": sum(1 for step in task_steps if step.status == "failed"),
                    "worker_call_count": len(task_calls),
                    "artifact_count": len(artifacts),
                    "trace_count": int(trace_counts.get(task.id) or 0),
                }
            )
        return summaries

    def _message_summaries(self, session: Session, messages: list[Message]) -> list[dict[str, Any]]:
        if not messages:
            return []
        message_ids = [message.id for message in messages]
        thought_counts = dict(
            session.query(MessageAgentThought.message_id, func.count(MessageAgentThought.id))
            .filter(MessageAgentThought.message_id.in_(message_ids))
            .group_by(MessageAgentThought.message_id)
            .all()
        )
        return [
            {
                **self._message_base(message),
                "summary": message.answer or message.error,
                "user_input_preview": message.query,
                "step_count": 0,
                "succeeded_step_count": 0,
                "failed_step_count": 0,
                "worker_call_count": 0,
                "artifact_count": 0,
                "trace_count": int(thought_counts.get(message.id) or 0),
            }
            for message in messages
        ]

    def _message_detail(self, session: Session, message: Message) -> dict[str, Any]:
        thoughts = (
            session.query(MessageAgentThought)
            .filter(MessageAgentThought.message_id == message.id)
            .order_by(MessageAgentThought.position.asc(), MessageAgentThought.created_at.asc())
            .all()
        )
        return {
            **self._message_base(message),
            "summary": message.answer or message.error,
            "user_input_preview": message.query,
            "step_count": 0,
            "succeeded_step_count": 0,
            "failed_step_count": 0,
            "worker_call_count": 0,
            "artifact_count": 0,
            "trace_count": len(thoughts),
            "plans": [],
            "plan": None,
            "steps": [],
            "worker_calls": [],
            "capability_calls": [],
            "trace_events": [self._message_trace_event_response(thought) for thought in thoughts],
            "input_files": self._message_input_files(message),
            "artifacts": [],
        }

    def _message_base(self, message: Message) -> dict[str, Any]:
        return {
            "id": message.id,
            "run_type": message.invoke_from or "chat",
            "entry_agent": None,
            "status": self._message_task_status(message),
            "user_input": {
                "query": message.query,
                "image_urls": message.image_urls or [],
                "conversation_id": str(message.conversation_id),
                "invoke_from": message.invoke_from,
            },
            "final_result": {
                "answer": message.answer,
                "error": message.error,
                "message": message.message or [],
                "total_token_count": message.total_token_count,
                "total_price": float(message.total_price or 0),
                "latency": float(message.latency or 0),
            },
            "error_code": "message_error" if message.status == MessageStatus.ERROR.value else "",
            "error_message": message.error or "",
            "version": 0,
            "started_at": self._ts(message.created_at),
            "finished_at": self._ts(message.updated_at or message.created_at),
            "created_at": self._ts(message.created_at),
            "updated_at": self._ts(message.updated_at),
        }

    def _message_trace_event_response(self, thought: MessageAgentThought) -> dict[str, Any]:
        return {
            "id": thought.id,
            "trace_id": str(thought.conversation_id),
            "task_id": thought.message_id,
            "plan_id": None,
            "step_id": None,
            "worker_call_id": None,
            "capability_call_id": None,
            "approval_id": None,
            "event_type": thought.event,
            "payload": {
                "message": thought.thought or thought.answer or thought.observation,
                "thought": thought.thought,
                "observation": thought.observation,
                "tool": thought.tool,
                "tool_input": thought.tool_input or {},
                "answer": thought.answer,
                "position": thought.position,
            },
            "token_count": thought.total_token_count,
            "cost": float(thought.total_price or 0),
            "latency": float(thought.latency or 0),
            "created_at": self._ts(thought.created_at),
            "updated_at": self._ts(thought.updated_at),
        }

    @staticmethod
    @staticmethod
    def _message_task_status(message: Message) -> str:
        if message.status in {MessageStatus.ERROR.value, MessageStatus.TIMEOUT.value}:
            return "failed"
        if message.status == MessageStatus.STOP.value:
            return "cancelled"
        if message.status == MessageStatus.NORMAL.value:
            return "succeeded" if message.answer else "running"
        return message.status or "succeeded"

    @staticmethod
    def _filter_message_query_by_task_status(query, status: str):
        if status == "succeeded":
            return query.filter(Message.status == MessageStatus.NORMAL.value, Message.answer != "")
        if status == "running":
            return query.filter(Message.status == MessageStatus.NORMAL.value, Message.answer == "")
        if status == "failed":
            return query.filter(Message.status.in_([MessageStatus.ERROR.value, MessageStatus.TIMEOUT.value]))
        if status == "cancelled":
            return query.filter(Message.status == MessageStatus.STOP.value)
        return query.filter(false())

    @staticmethod
    def _message_input_files(message: Message) -> list[dict[str, Any]]:
        return [
            {
                "id": url,
                "name": url.split("/")[-1] or "image",
                "preview_url": url,
                "download_url": url,
                "source": "message_image",
            }
            for url in message.image_urls or []
        ]

    @staticmethod
    def _agent_map(session: Session, agent_ids: set[UUID]) -> dict[UUID, Agent]:
        if not agent_ids:
            return {}
        return {agent.id: agent for agent in session.query(Agent).filter(Agent.id.in_(list(agent_ids))).all()}

    def _task_base(self, task: AgentTask, agent_map: dict[UUID, Agent]) -> dict[str, Any]:
        entry_agent = agent_map.get(task.router_agent_id)
        return {
            "id": task.id,
            "run_type": entry_agent.runtime_type if entry_agent else "router",
            "entry_agent": self._agent_response(entry_agent),
            "status": task.status,
            "user_input": task.user_input or {},
            "final_result": task.final_result or {},
            "error_code": task.error_code,
            "error_message": task.error_message,
            "version": task.version,
            "started_at": self._ts(task.started_at),
            "finished_at": self._ts(task.finished_at),
            "created_at": self._ts(task.created_at),
            "updated_at": self._ts(task.updated_at),
        }

    @staticmethod
    def _agent_response(agent: Agent | None) -> dict[str, Any] | None:
        if agent is None:
            return None
        return {
            "id": agent.id,
            "name": agent.name,
            "icon": agent.icon,
            "description": agent.description,
            "runtime_type": agent.runtime_type,
            "product_category": agent.product_category,
            "status": agent.status,
            "target_ref_type": agent.target_ref_type,
            "target_ref_id": agent.target_ref_id,
        }

    def _plan_response(self, plan: AgentPlan) -> dict[str, Any]:
        return {
            "id": plan.id,
            "schema_version": plan.schema_version,
            "plan_json": plan.plan_json or {},
            "risk_level": plan.risk_level,
            "status": plan.status,
            "created_at": self._ts(plan.created_at),
            "updated_at": self._ts(plan.updated_at),
        }

    def _step_response(self, step: AgentStep, agent_map: dict[UUID, Agent]) -> dict[str, Any]:
        return {
            "id": step.id,
            "plan_id": step.plan_id,
            "step_key": step.step_key,
            "worker_agent": self._agent_response(agent_map.get(step.worker_agent_id)),
            "dependencies": step.dependencies or [],
            "execution_mode": step.execution_mode,
            "status": step.status,
            "input_json": step.input_json or {},
            "output_json": step.output_json or {},
            "retry_count": step.retry_count,
            "timeout_seconds": step.timeout_seconds,
            "started_at": self._ts(step.started_at),
            "finished_at": self._ts(step.finished_at),
            "created_at": self._ts(step.created_at),
            "updated_at": self._ts(step.updated_at),
        }

    def _worker_call_response(self, call: WorkerCall, agent_map: dict[UUID, Agent]) -> dict[str, Any]:
        return {
            "id": call.id,
            "step_id": call.step_id,
            "worker_agent": self._agent_response(agent_map.get(call.worker_agent_id)),
            "invocation_json": call.invocation_json or {},
            "result_json": call.result_json or {},
            "status": call.status,
            "token_count": call.token_count,
            "cost": float(call.cost or 0),
            "latency": float(call.latency or 0),
            "created_at": self._ts(call.created_at),
            "updated_at": self._ts(call.updated_at),
        }

    def _capability_call_response(self, call: CapabilityCall) -> dict[str, Any]:
        return {
            "id": call.id,
            "step_id": call.step_id,
            "worker_call_id": call.worker_call_id,
            "capability_id": call.capability_id,
            "input_json": call.input_json or {},
            "output_json": call.output_json or {},
            "status": call.status,
            "risk_level": call.risk_level,
            "approval_id": call.approval_id,
            "idempotency_key": call.idempotency_key,
            "latency": float(call.latency or 0),
            "created_at": self._ts(call.created_at),
            "updated_at": self._ts(call.updated_at),
        }

    def _trace_event_response(self, event: TraceEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "trace_id": event.trace_id,
            "task_id": event.task_id,
            "plan_id": event.plan_id,
            "step_id": event.step_id,
            "worker_call_id": event.worker_call_id,
            "capability_call_id": event.capability_call_id,
            "approval_id": event.approval_id,
            "event_type": event.event_type,
            "payload": event.payload or {},
            "token_count": event.token_count,
            "cost": float(event.cost or 0),
            "latency": float(event.latency or 0),
            "created_at": self._ts(event.created_at),
            "updated_at": self._ts(event.updated_at),
        }

    @classmethod
    def _collect_input_files(cls, task: AgentTask, worker_calls: list[WorkerCall]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for call in worker_calls:
            context = (call.invocation_json or {}).get("context") or {}
            value = context.get("input_files") or []
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        if not items:
            for file_id in cls._iter_file_ids(task.user_input or {}):
                items.append({"file_id": str(file_id), "id": str(file_id)})
        return cls._dedupe_dicts(items, ("file_id", "id", "name"))

    @classmethod
    def _collect_artifacts(
        cls,
        task: AgentTask,
        steps: list[AgentStep],
        worker_calls: list[WorkerCall],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        final_result = task.final_result or {}
        value = final_result.get("artifacts")
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
        for step in steps:
            value = (step.output_json or {}).get("artifacts")
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        for call in worker_calls:
            value = (call.result_json or {}).get("artifacts")
            if isinstance(value, list):
                items.extend(item for item in value if isinstance(item, dict))
        return cls._dedupe_dicts(items, ("file_id", "artifact_id", "name"))

    @classmethod
    def _dedupe_dicts(cls, items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in items:
            key = next((str(item.get(field)) for field in keys if item.get(field)), str(item))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _iter_file_ids(user_input: dict[str, Any]):
        for key in ("input_file_ids", "file_ids", "input_files", "files"):
            value = user_input.get(key)
            if value is None:
                continue
            if isinstance(value, str | UUID):
                yield value
            elif isinstance(value, dict):
                file_id = value.get("file_id") or value.get("id")
                if file_id:
                    yield file_id
            elif isinstance(value, list | tuple):
                for item in value:
                    if isinstance(item, str | UUID):
                        yield item
                    elif isinstance(item, dict):
                        file_id = item.get("file_id") or item.get("id")
                        if file_id:
                            yield file_id

    @staticmethod
    def _final_summary(final_result: dict[str, Any] | None) -> str:
        data = final_result or {}
        for key in ("summary", "answer", "result"):
            value = data.get(key)
            if value:
                return str(value)
        steps = data.get("steps")
        if isinstance(steps, list) and steps:
            output = steps[-1].get("output") if isinstance(steps[-1], dict) else None
            if isinstance(output, dict):
                return str(output.get("answer") or output.get("summary") or "")
        return ""

    @staticmethod
    def _user_input_preview(user_input: dict[str, Any] | None) -> str:
        data = user_input or {}
        for key in ("query", "input", "message", "task"):
            value = data.get(key)
            if value:
                return str(value)
        return ""

    @staticmethod
    def _ts(value) -> int:
        return int(value.timestamp()) if value else 0

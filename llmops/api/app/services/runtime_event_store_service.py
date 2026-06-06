from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.conversation import Message
from app.models.task import AgentPlan, AgentStep, AgentTask, WorkerCall
from app.models.trace import TraceEvent


@dataclass(frozen=True)
class RuntimeEventRecords:
    tasks: list[AgentTask] = field(default_factory=list)
    plans_by_task: dict[UUID, list[AgentPlan]] = field(default_factory=dict)
    steps_by_task: dict[UUID, list[AgentStep]] = field(default_factory=dict)
    worker_calls_by_task: dict[UUID, list[WorkerCall]] = field(default_factory=dict)
    trace_events_by_task: dict[UUID, list[TraceEvent]] = field(default_factory=dict)
    agent_map: dict[UUID, Agent] = field(default_factory=dict)


class RuntimeEventStoreService:
    """Read runtime records from the current unified event storage boundary.

    TraceEvent is the source of truth for task runtime facts. MessageAgentThought
    remains a compatibility fallback for ordinary chat messages without tasks.
    """

    def records_for_message(
        self,
        session: Session,
        message: Message,
        *,
        account_id: UUID | None = None,
    ) -> RuntimeEventRecords:
        tasks = self.message_tasks(session, message, account_id=account_id)
        if not tasks:
            return RuntimeEventRecords()

        task_ids = [task.id for task in tasks]
        plans = (
            session.query(AgentPlan)
            .filter(AgentPlan.task_id.in_(task_ids))
            .order_by(AgentPlan.created_at.asc())
            .all()
        )
        steps = (
            session.query(AgentStep)
            .filter(AgentStep.task_id.in_(task_ids))
            .order_by(AgentStep.created_at.asc())
            .all()
        )
        worker_calls = (
            session.query(WorkerCall)
            .filter(WorkerCall.task_id.in_(task_ids))
            .order_by(WorkerCall.created_at.asc())
            .all()
        )
        trace_events = (
            session.query(TraceEvent)
            .filter(TraceEvent.task_id.in_(task_ids))
            .order_by(TraceEvent.created_at.asc())
            .all()
        )
        agent_ids = self._collect_agent_ids(tasks, steps, worker_calls)
        agents = session.query(Agent).filter(Agent.id.in_(agent_ids)).all() if agent_ids else []
        return RuntimeEventRecords(
            tasks=tasks,
            plans_by_task=self._group_by(plans, "task_id"),
            steps_by_task=self._group_by(steps, "task_id"),
            worker_calls_by_task=self._group_by(worker_calls, "task_id"),
            trace_events_by_task=self._group_by(trace_events, "task_id"),
            agent_map={agent.id: agent for agent in agents},
        )

    def message_tasks(
        self,
        session: Session,
        message: Message,
        *,
        account_id: UUID | None,
    ) -> list[AgentTask]:
        query = session.query(AgentTask).filter(AgentTask.conversation_id == message.conversation_id)
        if account_id is not None:
            query = query.filter(AgentTask.tenant_id == account_id)
        tasks = query.order_by(AgentTask.created_at.asc()).all()
        matched = [task for task in tasks if message.id in self._task_message_ids(task)]
        if matched:
            return matched

        message_query = (message.query or "").strip()
        query_matched = [
            task
            for task in tasks
            if message_query and self._user_input_preview(task.user_input).strip() == message_query
        ]
        if query_matched:
            return query_matched
        return tasks if len(tasks) == 1 else []

    @staticmethod
    def _task_message_ids(task: AgentTask) -> set[UUID]:
        user_input = task.user_input or {}
        candidates: list[Any] = [user_input.get("message_id")]
        message_ids = user_input.get("message_ids")
        if isinstance(message_ids, list):
            candidates.extend(message_ids)
        for key in ("context", "conversation"):
            value = user_input.get(key)
            if isinstance(value, dict):
                candidates.append(value.get("message_id"))

        parsed: set[UUID] = set()
        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed.add(candidate if isinstance(candidate, UUID) else UUID(str(candidate)))
            except (TypeError, ValueError):
                continue
        return parsed

    @staticmethod
    def _collect_agent_ids(
        tasks: list[AgentTask],
        steps: list[AgentStep],
        worker_calls: list[WorkerCall],
    ) -> set[UUID]:
        agent_ids: set[UUID] = {task.router_agent_id for task in tasks if task.router_agent_id}
        agent_ids.update(step.worker_agent_id for step in steps if step.worker_agent_id)
        agent_ids.update(call.worker_agent_id for call in worker_calls if call.worker_agent_id)
        return agent_ids

    @staticmethod
    def _group_by(items: list[Any], attr: str) -> dict[Any, list[Any]]:
        grouped: dict[Any, list[Any]] = defaultdict(list)
        for item in items:
            key = getattr(item, attr, None)
            if key is not None:
                grouped[key].append(item)
        return grouped

    @staticmethod
    def _user_input_preview(user_input: dict[str, Any] | None) -> str:
        data = user_input if isinstance(user_input, dict) else {}
        for key in ("query", "input", "message", "task"):
            value = data.get(key)
            if value:
                return str(value)
        return ""

import json
import math
from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import desc, false, func, or_
from sqlalchemy.orm import Session

from app.core.conversation import MessageStatus
from app.core.exceptions import NotFoundException
from app.models.account import Account
from app.models.agent import Agent
from app.models.conversation import Conversation, Message, MessageAgentThought
from app.models.end_user import EndUser
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
        user_id: str = "all",
        search_word: str = "",
    ) -> tuple[list[dict[str, Any]], int, int, list[dict[str, Any]]]:
        self.app_service.get_app(session, app_id, account)
        query = session.query(Conversation).filter(
            Conversation.app_id == app_id,
            Conversation.is_deleted.is_(False),
        )
        users = self._conversation_user_options(session, app_id)
        cleaned_user_id = (user_id or "all").strip()
        if cleaned_user_id and cleaned_user_id != "all":
            try:
                query = query.filter(Conversation.created_by == UUID(cleaned_user_id))
            except ValueError:
                query = query.filter(false())
        cleaned_search = (search_word or "").strip()
        if cleaned_search:
            matched_conversation_ids = (
                session.query(Message.conversation_id)
                .filter(
                    Message.app_id == app_id,
                    Message.is_deleted.is_(False),
                    or_(
                        Message.query.ilike(f"%{cleaned_search}%"),
                        Message.answer.ilike(f"%{cleaned_search}%"),
                    ),
                )
                .distinct()
            )
            query = query.filter(
                or_(
                    Conversation.name.ilike(f"%{cleaned_search}%"),
                    Conversation.summary.ilike(f"%{cleaned_search}%"),
                    Conversation.id.in_(matched_conversation_ids),
                )
            )

        conversations = (
            query.order_by(desc(Conversation.updated_at), desc(Conversation.created_at))
            .all()
        )
        app_agent_ids = self._app_agent_ids(session, app_id, account, validate_app=False)
        summaries = self._conversation_summaries(session, conversations, app_agent_ids)
        summaries.sort(key=lambda item: item["updated_at"] or item["created_at"], reverse=True)
        cleaned_status = (status or "all").strip().lower()
        if cleaned_status and cleaned_status != "all":
            summaries = [summary for summary in summaries if summary["status"] == cleaned_status]

        total_record = len(summaries)
        total_page = math.ceil(total_record / page_size) if total_record else 0
        return summaries[(page - 1) * page_size : page * page_size], total_record, total_page, users

    def get_app_conversation_detail(
        self,
        session: Session,
        *,
        app_id: UUID,
        conversation_id: UUID,
        account: Account,
    ) -> dict[str, Any]:
        self.app_service.get_app(session, app_id, account)
        conversation = (
            session.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.app_id == app_id,
                Conversation.is_deleted.is_(False),
            )
            .one_or_none()
        )
        if conversation is None:
            raise NotFoundException("Conversation execution record does not exist")
        app_agent_ids = self._app_agent_ids(session, app_id, account, validate_app=False)
        return self._conversation_detail(session, conversation, app_agent_ids)

    def get_app_task_detail(
        self,
        session: Session,
        *,
        app_id: UUID,
        task_id: UUID,
        account: Account,
    ) -> dict[str, Any]:
        try:
            return self.get_app_conversation_detail(
                session,
                app_id=app_id,
                conversation_id=task_id,
                account=account,
            )
        except NotFoundException:
            pass

        self.app_service.get_app(session, app_id, account)
        app_agent_ids = self._app_agent_ids(session, app_id, account, validate_app=False)
        task = self._app_task_query(session, app_agent_ids).filter(AgentTask.id == task_id).one_or_none()
        if task is None:
            raise NotFoundException("Agent task does not exist")
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
            "trace_events": [
                self._trace_event_response(
                    event,
                    agent_map=agent_map,
                    task_map={task.id: task},
                    step_map={step.id: step for step in steps},
                    worker_call_map={call.id: call for call in worker_calls},
                )
                for event in trace_events
            ],
            "input_files": input_files,
            "artifacts": artifacts,
        }

    def _app_agent_ids(
        self,
        session: Session,
        app_id: UUID,
        account: Account,
        *,
        validate_app: bool = True,
    ) -> list[UUID]:
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
        worker_task_ids = [
            task_id
            for (task_id,) in session.query(AgentStep.task_id)
            .filter(AgentStep.worker_agent_id.in_(app_agent_ids))
            .distinct()
            .all()
        ]
        return session.query(AgentTask).filter(
            or_(
                AgentTask.router_agent_id.in_(app_agent_ids),
                AgentTask.id.in_(worker_task_ids),
            )
        )

    def _conversation_summaries(
        self,
        session: Session,
        conversations: list[Conversation],
        app_agent_ids: list[UUID],
    ) -> list[dict[str, Any]]:
        if not conversations:
            return []
        conversation_ids = [conversation.id for conversation in conversations]
        messages = (
            session.query(Message)
            .filter(
                Message.conversation_id.in_(conversation_ids),
                Message.is_deleted.is_(False),
            )
            .order_by(Message.created_at.asc())
            .all()
        )
        tasks = self._agent_tasks_for_conversations(session, app_agent_ids, conversation_ids)
        thought_trace_counts = dict(
            session.query(MessageAgentThought.conversation_id, func.count(MessageAgentThought.id))
            .filter(MessageAgentThought.conversation_id.in_(conversation_ids))
            .group_by(MessageAgentThought.conversation_id)
            .all()
        )
        task_trace_counts = self._task_trace_counts(session, tasks)
        messages_by_conversation: dict[UUID, list[Message]] = defaultdict(list)
        tasks_by_conversation: dict[UUID, list[AgentTask]] = defaultdict(list)
        for message in messages:
            messages_by_conversation[message.conversation_id].append(message)
        for task in tasks:
            if task.conversation_id:
                tasks_by_conversation[task.conversation_id].append(task)
        return [
            self._conversation_summary(
                conversation,
                messages_by_conversation.get(conversation.id, []),
                tasks_by_conversation.get(conversation.id, []),
                int(thought_trace_counts.get(conversation.id) or 0) + self._conversation_task_trace_count(
                    tasks_by_conversation.get(conversation.id, []),
                    task_trace_counts,
                ),
            )
            for conversation in conversations
        ]

    def _conversation_user_options(self, session: Session, app_id: UUID) -> list[dict[str, Any]]:
        creator_ids = [
            creator_id
            for (creator_id,) in session.query(Conversation.created_by)
            .filter(
                Conversation.app_id == app_id,
                Conversation.is_deleted.is_(False),
                Conversation.created_by.isnot(None),
            )
            .distinct()
            .all()
            if creator_id
        ]
        if not creator_ids:
            return []

        account_map = {item.id: item for item in session.query(Account).filter(Account.id.in_(creator_ids)).all()}
        end_user_map = {item.id: item for item in session.query(EndUser).filter(EndUser.id.in_(creator_ids)).all()}
        options = []
        for creator_id in creator_ids:
            account = account_map.get(creator_id)
            if account:
                label = account.name or account.email or str(account.id)
                options.append({"id": str(account.id), "label": label, "type": "account"})
                continue
            end_user = end_user_map.get(creator_id)
            if end_user:
                options.append({"id": str(end_user.id), "label": f"访客 {str(end_user.id)[:8]}", "type": "end_user"})
                continue
            options.append({"id": str(creator_id), "label": f"用户 {str(creator_id)[:8]}", "type": "unknown"})
        return options

    def _conversation_detail(
        self,
        session: Session,
        conversation: Conversation,
        app_agent_ids: list[UUID],
    ) -> dict[str, Any]:
        messages = (
            session.query(Message)
            .filter(
                Message.conversation_id == conversation.id,
                Message.is_deleted.is_(False),
            )
            .order_by(Message.created_at.asc())
            .all()
        )
        thoughts = (
            session.query(MessageAgentThought)
            .filter(MessageAgentThought.conversation_id == conversation.id)
            .order_by(
                MessageAgentThought.message_id.asc(),
                MessageAgentThought.position.asc(),
                MessageAgentThought.created_at.asc(),
            )
            .all()
        )
        thoughts_by_message: dict[UUID, list[MessageAgentThought]] = defaultdict(list)
        for thought in thoughts:
            thoughts_by_message[thought.message_id].append(thought)
        tasks = self._agent_tasks_for_conversations(session, app_agent_ids, [conversation.id])
        task_details = self._task_execution_details(session, tasks)
        task_details_by_id = {detail["id"]: detail for detail in task_details}
        task_details_by_message = self._tasks_by_message(messages, tasks, task_details_by_id)
        task_summaries = self._summaries(session, tasks)
        task_trace_events = [event for detail in task_details for event in detail["trace_events"]]
        message_trace_events = [self._message_trace_event_response(thought) for thought in thoughts]
        trace_events = self._sort_trace_events([*message_trace_events, *task_trace_events])
        summary = self._conversation_summary(conversation, messages, tasks, len(trace_events))
        summary["step_count"] = sum(int(detail["step_count"]) for detail in task_details)
        summary["succeeded_step_count"] = sum(int(detail["succeeded_step_count"]) for detail in task_details)
        summary["failed_step_count"] = sum(int(detail["failed_step_count"]) for detail in task_details)
        summary["worker_call_count"] = sum(int(detail["worker_call_count"]) for detail in task_details)
        summary["artifact_count"] = sum(int(detail["artifact_count"]) for detail in task_details)
        task_input_files = [item for detail in task_details for item in detail["input_files"]]
        task_artifacts = [item for detail in task_details for item in detail["artifacts"]]
        return {
            **summary,
            "messages": [
                self._conversation_message_response(
                    message,
                    thoughts_by_message.get(message.id, []),
                    agent_tasks=task_details_by_message.get(message.id, []),
                )
                for message in messages
            ],
            "agent_tasks": task_summaries,
            "plans": [],
            "plan": None,
            "steps": [],
            "worker_calls": [],
            "capability_calls": [],
            "trace_events": trace_events,
            "input_files": self._dedupe_dicts(
                [*self._conversation_input_files(messages), *task_input_files],
                ("file_id", "id", "name"),
            ),
            "artifacts": self._dedupe_dicts(task_artifacts, ("file_id", "artifact_id", "name")),
        }

    def _conversation_summary(
        self,
        conversation: Conversation,
        messages: list[Message],
        tasks: list[AgentTask],
        trace_count: int,
    ) -> dict[str, Any]:
        latest_message = messages[-1] if messages else None
        latest_at = latest_message.updated_at if latest_message else conversation.updated_at
        if conversation.updated_at and latest_at:
            latest_at = max(conversation.updated_at, latest_at)
        return {
            "id": conversation.id,
            "record_type": "conversation",
            "conversation_id": conversation.id,
            "name": conversation.name,
            "run_type": conversation.invoke_from or (latest_message.invoke_from if latest_message else "conversation"),
            "entry_agent": None,
            "status": self._conversation_status(messages, tasks),
            "user_input": {
                "conversation_id": str(conversation.id),
                "invoke_from": conversation.invoke_from,
                "latest_query": latest_message.query if latest_message else "",
            },
            "user_input_preview": latest_message.query if latest_message else conversation.name,
            "final_result": {
                "answer": latest_message.answer if latest_message else "",
                "error": latest_message.error if latest_message else "",
            },
            "summary": conversation.summary or (latest_message.answer if latest_message else ""),
            "error_code": (
                "message_error"
                if latest_message and latest_message.status == MessageStatus.ERROR.value
                else ""
            ),
            "error_message": latest_message.error if latest_message else "",
            "version": 0,
            "message_count": len(messages),
            "task_count": len(tasks),
            "step_count": 0,
            "succeeded_step_count": 0,
            "failed_step_count": 0,
            "worker_call_count": 0,
            "artifact_count": 0,
            "trace_count": trace_count,
            "total_token_count": sum(int(message.total_token_count or 0) for message in messages),
            "total_price": float(sum(float(message.total_price or 0) for message in messages)),
            "latency": float(sum(float(message.latency or 0) for message in messages)),
            "started_at": self._ts(conversation.created_at),
            "finished_at": self._ts(latest_at or conversation.created_at),
            "created_at": self._ts(conversation.created_at),
            "updated_at": self._ts(latest_at or conversation.updated_at),
        }

    def _conversation_message_response(
        self,
        message: Message,
        thoughts: list[MessageAgentThought],
        *,
        agent_tasks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        task_trace_events = [event for task in agent_tasks or [] for event in task.get("trace_events", [])]
        return {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "invoke_from": message.invoke_from,
            "status": self._message_task_status(message),
            "query": message.query,
            "image_urls": message.image_urls or [],
            "answer": message.answer,
            "error": message.error,
            "message": message.message or [],
            "total_token_count": message.total_token_count,
            "total_price": float(message.total_price or 0),
            "latency": float(message.latency or 0),
            "created_at": self._ts(message.created_at),
            "updated_at": self._ts(message.updated_at),
            "agent_tasks": agent_tasks or [],
            "trace_events": self._sort_trace_events(
                [self._message_trace_event_response(thought) for thought in thoughts] + task_trace_events
            ),
        }

    def _agent_tasks_for_conversations(
        self,
        session: Session,
        app_agent_ids: list[UUID],
        conversation_ids: list[UUID],
    ) -> list[AgentTask]:
        if not conversation_ids or not app_agent_ids:
            return []
        return (
            self._app_task_query(session, app_agent_ids)
            .filter(AgentTask.conversation_id.in_(conversation_ids))
            .order_by(AgentTask.created_at.asc())
            .all()
        )

    def _task_execution_details(self, session: Session, tasks: list[AgentTask]) -> list[dict[str, Any]]:
        if not tasks:
            return []
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
        capability_calls = (
            session.query(CapabilityCall)
            .filter(CapabilityCall.task_id.in_(task_ids))
            .order_by(CapabilityCall.created_at.asc())
            .all()
        )
        trace_events = (
            session.query(TraceEvent)
            .filter(TraceEvent.task_id.in_(task_ids))
            .order_by(TraceEvent.created_at.asc())
            .all()
        )

        plans_by_task: dict[UUID, list[AgentPlan]] = defaultdict(list)
        steps_by_task: dict[UUID, list[AgentStep]] = defaultdict(list)
        calls_by_task: dict[UUID, list[WorkerCall]] = defaultdict(list)
        capability_calls_by_task: dict[UUID, list[CapabilityCall]] = defaultdict(list)
        trace_events_by_task: dict[UUID, list[TraceEvent]] = defaultdict(list)
        agent_ids: set[UUID] = set()
        for task in tasks:
            agent_ids.add(task.router_agent_id)
        for plan in plans:
            plans_by_task[plan.task_id].append(plan)
        for step in steps:
            steps_by_task[step.task_id].append(step)
            agent_ids.add(step.worker_agent_id)
        for call in worker_calls:
            calls_by_task[call.task_id].append(call)
            agent_ids.add(call.worker_agent_id)
        for call in capability_calls:
            capability_calls_by_task[call.task_id].append(call)
        for event in trace_events:
            if event.task_id:
                trace_events_by_task[event.task_id].append(event)

        agent_map = self._agent_map(session, agent_ids)
        details: list[dict[str, Any]] = []
        for task in tasks:
            task_plans = plans_by_task.get(task.id, [])
            task_steps = steps_by_task.get(task.id, [])
            task_calls = calls_by_task.get(task.id, [])
            task_capability_calls = capability_calls_by_task.get(task.id, [])
            task_trace_events = trace_events_by_task.get(task.id, [])
            artifacts = self._collect_artifacts(task, task_steps, task_calls)
            details.append(
                {
                    **self._task_base(task, agent_map),
                    "summary": self._final_summary(task.final_result),
                    "user_input_preview": self._user_input_preview(task.user_input),
                    "step_count": len(task_steps),
                    "succeeded_step_count": sum(1 for step in task_steps if step.status == "succeeded"),
                    "failed_step_count": sum(1 for step in task_steps if step.status == "failed"),
                    "worker_call_count": len(task_calls),
                    "artifact_count": len(artifacts),
                    "trace_count": len(task_trace_events),
                    "plans": [self._plan_response(plan) for plan in task_plans],
                    "plan": self._plan_response(task_plans[-1]) if task_plans else None,
                    "steps": [self._step_response(step, agent_map) for step in task_steps],
                    "worker_calls": [self._worker_call_response(call, agent_map) for call in task_calls],
                    "capability_calls": [self._capability_call_response(call) for call in task_capability_calls],
                    "trace_events": [
                        self._trace_event_response(
                            event,
                            agent_map=agent_map,
                            task_map={task.id: task},
                            step_map={step.id: step for step in task_steps},
                            worker_call_map={call.id: call for call in task_calls},
                        )
                        for event in task_trace_events
                    ],
                    "input_files": self._collect_input_files(task, task_calls),
                    "artifacts": artifacts,
                }
            )
        return details

    def _tasks_by_message(
        self,
        messages: list[Message],
        tasks: list[AgentTask],
        task_details_by_id: dict[UUID, dict[str, Any]],
    ) -> dict[UUID, list[dict[str, Any]]]:
        grouped: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        if not messages:
            return grouped
        message_ids = {message.id for message in messages}
        for task in tasks:
            detail = task_details_by_id.get(task.id)
            if detail is None:
                continue
            message_id = self._task_message_id(task)
            if message_id not in message_ids:
                message_id = self._infer_message_id_for_task(messages, task)
            if message_id:
                grouped[message_id].append(detail)
        return grouped

    def _infer_message_id_for_task(self, messages: list[Message], task: AgentTask) -> UUID | None:
        preview = self._user_input_preview(task.user_input).strip()
        if preview:
            for message in reversed(messages):
                query = (message.query or "").strip()
                if query and (query == preview or query in preview or preview in query):
                    return message.id
        if task.created_at:
            for message in reversed(messages):
                if message.created_at and message.created_at <= task.created_at:
                    return message.id
        return messages[-1].id if messages else None

    @staticmethod
    def _task_message_id(task: AgentTask) -> UUID | None:
        user_input = task.user_input or {}
        context = user_input.get("context")
        conversation = user_input.get("conversation")
        candidates = [user_input.get("message_id")]
        if isinstance(context, dict):
            candidates.append(context.get("message_id"))
        if isinstance(conversation, dict):
            candidates.append(conversation.get("message_id"))
        for value in candidates:
            if not value:
                continue
            try:
                return UUID(str(value))
            except (TypeError, ValueError):
                continue
        return None

    def _task_trace_counts(self, session: Session, tasks: list[AgentTask]) -> dict[UUID, int]:
        if not tasks:
            return {}
        task_ids = [task.id for task in tasks]
        return {
            task_id: int(count)
            for task_id, count in session.query(TraceEvent.task_id, func.count(TraceEvent.id))
            .filter(TraceEvent.task_id.in_(task_ids))
            .group_by(TraceEvent.task_id)
            .all()
            if task_id
        }

    @staticmethod
    def _conversation_task_trace_count(tasks: list[AgentTask], task_trace_counts: dict[UUID, int]) -> int:
        return sum(int(task_trace_counts.get(task.id) or 0) for task in tasks)

    def _conversation_status(self, messages: list[Message], tasks: list[AgentTask]) -> str:
        if any(task.status in {"created", "running", "waiting_approval"} for task in tasks):
            return "running"
        if any(task.status == "failed" for task in tasks):
            return "failed"
        if any(task.status == "cancelled" for task in tasks):
            return "cancelled"
        if messages:
            return self._message_task_status(messages[-1])
        return "succeeded"

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
            "agent": None,
            "step": None,
            "worker_call": None,
            "token_count": thought.total_token_count,
            "cost": float(thought.total_price or 0),
            "latency": float(thought.latency or 0),
            "created_at": self._ts(thought.created_at),
            "updated_at": self._ts(thought.updated_at),
        }

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
    def _conversation_input_files(messages: list[Message]) -> list[dict[str, Any]]:
        files = []
        for message in messages:
            for url in message.image_urls or []:
                files.append(
                    {
                        "id": url,
                        "name": url.split("/")[-1] or "image",
                        "preview_url": url,
                        "download_url": url,
                        "source": "message_image",
                    }
                )
        return AgentTaskService._dedupe_dicts(files, ("id", "name"))

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
        input_json = step.input_json or {}
        output_json = step.output_json or {}
        selection = self._planner_selection(input_json)
        return {
            "id": step.id,
            "plan_id": step.plan_id,
            "step_key": step.step_key,
            "worker_agent": self._agent_response(agent_map.get(step.worker_agent_id)),
            "dependencies": step.dependencies or [],
            "execution_mode": step.execution_mode,
            "status": step.status,
            "task": str(input_json.get("task") or ""),
            "selection_reason": selection["reason"],
            "selection_signals": selection["signals"],
            "input_preview": self._preview_json(input_json),
            "output_preview": self._preview_json(output_json),
            "input_json": input_json,
            "output_json": output_json,
            "retry_count": step.retry_count,
            "timeout_seconds": step.timeout_seconds,
            "started_at": self._ts(step.started_at),
            "finished_at": self._ts(step.finished_at),
            "created_at": self._ts(step.created_at),
            "updated_at": self._ts(step.updated_at),
        }

    def _worker_call_response(self, call: WorkerCall, agent_map: dict[UUID, Agent]) -> dict[str, Any]:
        invocation_json = call.invocation_json or {}
        result_json = call.result_json or {}
        return {
            "id": call.id,
            "step_id": call.step_id,
            "worker_agent": self._agent_response(agent_map.get(call.worker_agent_id)),
            "invocation_preview": self._preview_json(invocation_json),
            "result_preview": self._preview_json(result_json),
            "invocation_json": invocation_json,
            "result_json": result_json,
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

    def _trace_event_response(
        self,
        event: TraceEvent,
        *,
        agent_map: dict[UUID, Agent] | None = None,
        task_map: dict[UUID, AgentTask] | None = None,
        step_map: dict[UUID, AgentStep] | None = None,
        worker_call_map: dict[UUID, WorkerCall] | None = None,
    ) -> dict[str, Any]:
        payload = event.payload or {}
        step = step_map.get(event.step_id) if event.step_id and step_map else None
        worker_call = worker_call_map.get(event.worker_call_id) if event.worker_call_id and worker_call_map else None
        agent = self._trace_agent(
            event,
            payload=payload,
            agent_map=agent_map or {},
            task_map=task_map or {},
            step=step,
            worker_call=worker_call,
        )
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
            "payload": payload,
            "agent": self._agent_response(agent),
            "step": self._trace_step_response(step, agent_map or {}),
            "worker_call": self._trace_worker_call_response(worker_call, agent_map or {}),
            "token_count": event.token_count,
            "cost": float(event.cost or 0),
            "latency": float(event.latency or 0),
            "created_at": self._ts(event.created_at),
            "updated_at": self._ts(event.updated_at),
        }

    @classmethod
    def _trace_agent(
        cls,
        event: TraceEvent,
        *,
        payload: dict[str, Any],
        agent_map: dict[UUID, Agent],
        task_map: dict[UUID, AgentTask],
        step: AgentStep | None,
        worker_call: WorkerCall | None,
    ) -> Agent | None:
        if worker_call is not None:
            return agent_map.get(worker_call.worker_agent_id)
        if step is not None:
            return agent_map.get(step.worker_agent_id)
        for key in ("worker_agent_id", "worker_id", "router_agent_id", "router_id"):
            agent = cls._agent_from_map(agent_map, payload.get(key))
            if agent is not None:
                return agent
        task = task_map.get(event.task_id) if event.task_id else None
        return agent_map.get(task.router_agent_id) if task is not None else None

    @staticmethod
    def _agent_from_map(agent_map: dict[UUID, Agent], raw_id: Any) -> Agent | None:
        if not raw_id:
            return None
        try:
            return agent_map.get(UUID(str(raw_id)))
        except (TypeError, ValueError):
            return None

    def _trace_step_response(self, step: AgentStep | None, agent_map: dict[UUID, Agent]) -> dict[str, Any] | None:
        if step is None:
            return None
        input_json = step.input_json if isinstance(step.input_json, dict) else {}
        output_json = step.output_json if isinstance(step.output_json, dict) else {}
        selection = self._planner_selection(input_json)
        return {
            "id": step.id,
            "plan_id": step.plan_id,
            "step_key": step.step_key,
            "task": str(input_json.get("task") or ""),
            "status": step.status,
            "worker_agent": self._agent_response(agent_map.get(step.worker_agent_id)),
            "selection_reason": selection["reason"],
            "selection_signals": selection["signals"],
            "input_preview": self._preview_json(input_json),
            "output_preview": self._preview_json(output_json),
        }

    def _trace_worker_call_response(
        self,
        worker_call: WorkerCall | None,
        agent_map: dict[UUID, Agent],
    ) -> dict[str, Any] | None:
        if worker_call is None:
            return None
        invocation_json = worker_call.invocation_json if isinstance(worker_call.invocation_json, dict) else {}
        result_json = worker_call.result_json if isinstance(worker_call.result_json, dict) else {}
        return {
            "id": worker_call.id,
            "status": worker_call.status,
            "worker_agent": self._agent_response(agent_map.get(worker_call.worker_agent_id)),
            "invocation_preview": self._preview_json(invocation_json),
            "result_preview": self._preview_json(result_json),
            "token_count": worker_call.token_count,
            "latency": float(worker_call.latency or 0),
        }

    @staticmethod
    def _planner_selection(input_json: dict[str, Any]) -> dict[str, Any]:
        selection = input_json.get("planner_selection") if isinstance(input_json, dict) else {}
        if not isinstance(selection, dict):
            return {"reason": "", "signals": []}
        raw_signals = selection.get("signals", selection.get("selection_signals", []))
        signals = [str(item) for item in raw_signals if str(item).strip()] if isinstance(raw_signals, list) else []
        return {
            "reason": str(selection.get("reason") or selection.get("selection_reason") or ""),
            "signals": signals,
        }

    @staticmethod
    def _preview_json(value: Any, limit: int = 260) -> str:
        if value in (None, {}, []):
            return ""
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
        return text if len(text) <= limit else f"{text[:limit]}..."

    @staticmethod
    def _sort_trace_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(events, key=lambda item: (int(item.get("created_at") or 0), str(item.get("id") or "")))

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

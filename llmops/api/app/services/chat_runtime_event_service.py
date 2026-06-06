import json
import time
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.agent import AgentThought, QueueEvent
from app.models.agent import Agent
from app.models.conversation import Message, MessageAgentThought
from app.models.task import AgentPlan, AgentStep, AgentTask, WorkerCall
from app.models.trace import TraceEvent

RUNTIME_EVENT_SSE_NAME = "runtime_event"
WAITING_STATUS_VALUES = {"waiting", "waiting_user", "waiting_approval"}


class ChatRuntimeEventService:
    """Adapt persisted router-agent runtime records into chat-friendly events."""

    def events_from_agent_thought(
        self,
        thought: AgentThought,
        *,
        conversation_id: UUID,
        message_id: UUID,
    ) -> list[dict[str, Any]]:
        event = self._queue_event_value(thought.event)
        if event == QueueEvent.PING.value:
            return []

        created_at = int(time.time())
        base = {
            "source": "agent_thought",
            "task_id": str(thought.task_id),
            "conversation_id": str(conversation_id),
            "message_id": str(message_id),
            "created_at": created_at,
        }
        if event == QueueEvent.AGENT_ACTION.value:
            return self._events_from_action(thought, base=base)
        if event == QueueEvent.AGENT_MESSAGE.value:
            return [
                self._event(
                    event_id=f"thought:{thought.id}:message",
                    event_type="message",
                    status="completed",
                    title="智能体消息",
                    summary=thought.thought or thought.answer,
                    payload={"answer": thought.answer, "thought": thought.thought},
                    **base,
                )
            ]
        if event == QueueEvent.AGENT_END.value:
            return [
                self._event(
                    event_id=f"thought:{thought.id}:done",
                    event_type="done",
                    status="completed",
                    title="任务完成",
                    summary="PlannerAgent 执行完成",
                    payload={},
                    **base,
                )
            ]
        if event in {QueueEvent.ERROR.value, QueueEvent.TIMEOUT.value, QueueEvent.STOP.value}:
            status = "cancelled" if event == QueueEvent.STOP.value else "failed"
            title = "任务已停止" if status == "cancelled" else "任务失败"
            return [
                self._event(
                    event_id=f"thought:{thought.id}:error",
                    event_type="error",
                    status=status,
                    title=title,
                    summary=thought.observation or thought.thought,
                    payload={
                        "queue_event": event,
                        "tool_name": thought.tool,
                        "retryable": event != QueueEvent.STOP.value,
                    },
                    **base,
                )
            ]
        return []

    def runtime_events_for_message(
        self,
        session: Session,
        message: Message,
        *,
        account_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        tasks = self._message_tasks(session, message, account_id=account_id)
        if not tasks:
            return self.runtime_events_from_message_thoughts(message)

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
        agent_map = {agent.id: agent for agent in agents}
        plans_by_task = self._group_by(plans, "task_id")
        steps_by_task = self._group_by(steps, "task_id")
        calls_by_task = self._group_by(worker_calls, "task_id")
        trace_by_task = self._group_by(trace_events, "task_id")

        events: list[dict[str, Any]] = []
        for task in tasks:
            task_plans = plans_by_task.get(task.id, [])
            task_steps = steps_by_task.get(task.id, [])
            task_calls = calls_by_task.get(task.id, [])
            task_traces = trace_by_task.get(task.id, [])
            events.extend(
                self._history_events_for_task(
                    task,
                    message=message,
                    plans=task_plans,
                    steps=task_steps,
                    worker_calls=task_calls,
                    trace_events=task_traces,
                    agent_map=agent_map,
                )
            )

        return sorted(events, key=lambda item: (int(item.get("created_at") or 0), str(item.get("id") or "")))

    def runtime_events_from_message_thoughts(self, message: Message) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        thoughts = sorted(
            message.agent_thoughts or [],
            key=lambda item: (item.position or 0, self._ts(item.created_at)),
        )
        for thought in thoughts:
            events.extend(self.events_from_message_agent_thought(thought, message=message))
        return events

    def events_from_message_agent_thought(
        self,
        thought: MessageAgentThought,
        *,
        message: Message,
    ) -> list[dict[str, Any]]:
        event = str(thought.event or "")
        if event == QueueEvent.PING.value:
            return []

        base = {
            "source": "message_agent_thought",
            "task_id": "",
            "conversation_id": str(message.conversation_id),
            "message_id": str(message.id),
            "created_at": self._ts(thought.created_at),
        }
        if event == QueueEvent.AGENT_ACTION.value:
            return self._events_from_action(thought, base=base)
        if event == QueueEvent.AGENT_MESSAGE.value:
            return [
                self._event(
                    event_id=f"message_thought:{thought.id}:message",
                    event_type="message",
                    status="completed",
                    title="智能体消息",
                    summary=thought.thought or thought.answer,
                    payload={"answer": thought.answer, "thought": thought.thought},
                    **base,
                )
            ]
        if event == QueueEvent.AGENT_END.value:
            return [
                self._event(
                    event_id=f"message_thought:{thought.id}:done",
                    event_type="done",
                    status="completed",
                    title="任务完成",
                    summary="执行完成",
                    payload={},
                    **base,
                )
            ]
        if event in {QueueEvent.ERROR.value, QueueEvent.TIMEOUT.value, QueueEvent.STOP.value}:
            status = "cancelled" if event == QueueEvent.STOP.value else "failed"
            title = "任务已停止" if status == "cancelled" else "任务失败"
            return [
                self._event(
                    event_id=f"message_thought:{thought.id}:error",
                    event_type="error",
                    status=status,
                    title=title,
                    summary=thought.observation or thought.thought,
                    payload={
                        "queue_event": event,
                        "tool_name": thought.tool,
                        "retryable": event != QueueEvent.STOP.value,
                    },
                    **base,
                )
            ]
        return []

    def _events_from_action(self, thought: AgentThought, *, base: dict[str, Any]) -> list[dict[str, Any]]:
        tool_input = thought.tool_input if isinstance(thought.tool_input, dict) else {}
        tool = thought.tool or ""
        if tool == "planner.plan":
            return [
                self._plan_event_from_tool_input(
                    event_id=f"thought:{thought.id}:plan",
                    status="created",
                    title="计划生成完成",
                    summary=thought.observation,
                    tool_input=tool_input,
                    **base,
                )
            ]
        if tool in {"planner.plan_update", "planner.replan"}:
            return [
                self._plan_event_from_tool_input(
                    event_id=f"thought:{thought.id}:plan",
                    status="updated",
                    title="计划已更新",
                    summary=thought.observation,
                    tool_input=tool_input,
                    **base,
                )
            ]

        if self._is_step_action(tool_input):
            step_event = self._step_event_from_tool_input(
                event_id=f"thought:{thought.id}:step",
                summary=thought.observation,
                tool_name=tool,
                tool_input=tool_input,
                **base,
            )
            if step_event["status"] == "waiting":
                return [
                    step_event,
                    self._wait_event_from_tool_input(
                        event_id=f"thought:{thought.id}:wait",
                        summary=thought.observation,
                        tool_name=tool,
                        tool_input=tool_input,
                        **base,
                    ),
                ]
            return [step_event]

        if tool in {"planner.wait", "planner.wait_user"}:
            return [
                self._wait_event_from_tool_input(
                    event_id=f"thought:{thought.id}:wait",
                    summary=thought.observation,
                    tool_name=tool,
                    tool_input=tool_input,
                    **base,
                )
            ]

        if tool:
            status = "running" if tool == "planner.generate_plan" else "completed"
            return [
                self._event(
                    event_id=f"thought:{thought.id}:tool",
                    event_type="tool",
                    status=status,
                    title=self._tool_title(tool, status),
                    summary=thought.observation,
                    tool_name=tool,
                    payload={
                        "tool_name": tool,
                        "function_name": tool,
                        "function_args": tool_input,
                        "input_summary": self._preview(tool_input),
                        "output_summary": thought.observation or "",
                    },
                    **base,
                )
            ]
        return []

    def _history_events_for_task(
        self,
        task: AgentTask,
        *,
        message: Message,
        plans: list[AgentPlan],
        steps: list[AgentStep],
        worker_calls: list[WorkerCall],
        trace_events: list[TraceEvent],
        agent_map: dict[UUID, Agent],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        latest_plan_id = plans[-1].id if plans else None
        steps_by_plan = self._group_by(steps, "plan_id")
        for index, plan in enumerate(plans):
            status = "created" if index == 0 else "updated"
            if plan.id == latest_plan_id and self._chat_status(task.status) == "completed":
                status = "completed"
            events.append(
                self._plan_event_from_plan(
                    task,
                    plan,
                    message=message,
                    steps=steps_by_plan.get(plan.id, []),
                    agent_map=agent_map,
                    status=status,
                )
            )

        for step in steps:
            events.append(self._step_event_from_step(task, step, message=message, agent_map=agent_map))

        for call in worker_calls:
            events.append(self._tool_event_from_worker_call(task, call, message=message, agent_map=agent_map))

        step_map = {step.id: step for step in steps}
        for trace in trace_events:
            if trace.event_type == "wait.user.requested":
                events.append(
                    self._wait_event_from_trace(task, trace, message=message, step=step_map.get(trace.step_id))
                )

        task_status = self._chat_status(task.status)
        if task_status == "completed":
            events.append(
                self._event(
                    event_id=f"task:{task.id}:done",
                    event_type="done",
                    status="completed",
                    title="任务完成",
                    summary=self._final_summary(task.final_result),
                    task_id=str(task.id),
                    conversation_id=str(message.conversation_id),
                    message_id=str(message.id),
                    created_at=self._ts(task.finished_at or task.updated_at or task.created_at),
                    payload={"final_result": task.final_result or {}},
                )
            )
        elif task_status in {"failed", "cancelled"}:
            events.append(
                self._event(
                    event_id=f"task:{task.id}:error",
                    event_type="error",
                    status=task_status,
                    title="任务已停止" if task_status == "cancelled" else "任务失败",
                    summary=task.error_message or "",
                    task_id=str(task.id),
                    conversation_id=str(message.conversation_id),
                    message_id=str(message.id),
                    created_at=self._ts(task.finished_at or task.updated_at or task.created_at),
                    payload={"error_code": task.error_code, "retryable": task_status != "cancelled"},
                )
            )
        return events

    def _plan_event_from_tool_input(
        self,
        *,
        event_id: str,
        status: str,
        title: str,
        summary: str,
        tool_input: dict[str, Any],
        source: str,
        task_id: str,
        conversation_id: str,
        message_id: str,
        created_at: int,
    ) -> dict[str, Any]:
        steps = self._steps_from_plan_payload(tool_input)
        return self._event(
            event_id=event_id,
            event_type="plan",
            status=status,
            title=title,
            summary=summary,
            task_id=task_id,
            conversation_id=conversation_id,
            message_id=message_id,
            created_at=created_at,
            goal=str(tool_input.get("goal") or tool_input.get("user_intent") or ""),
            language=str(tool_input.get("language") or "zh-CN"),
            steps=steps,
            payload={"source": source, **tool_input},
        )

    def _plan_event_from_plan(
        self,
        task: AgentTask,
        plan: AgentPlan,
        *,
        message: Message,
        steps: list[AgentStep],
        agent_map: dict[UUID, Agent],
        status: str,
    ) -> dict[str, Any]:
        plan_json = plan.plan_json if isinstance(plan.plan_json, dict) else {}
        title = "计划生成完成" if status == "created" else ("计划完成" if status == "completed" else "计划已更新")
        return self._event(
            event_id=f"plan:{plan.id}",
            event_type="plan",
            status=status,
            title=title,
            summary=self._plan_summary(plan_json, steps),
            task_id=str(task.id),
            conversation_id=str(message.conversation_id),
            message_id=str(message.id),
            created_at=self._ts(plan.created_at),
            plan_id=str(plan.id),
            goal=str(plan_json.get("user_intent") or self._user_input_preview(task.user_input)),
            language=str(plan_json.get("language") or "zh-CN"),
            steps=self._steps_from_plan(plan_json, steps, agent_map),
            payload={
                "schema_version": plan.schema_version,
                "risk_level": plan.risk_level,
                "plan_json": plan_json,
            },
        )

    def _step_event_from_tool_input(
        self,
        *,
        event_id: str,
        summary: str,
        tool_name: str,
        tool_input: dict[str, Any],
        source: str,
        task_id: str,
        conversation_id: str,
        message_id: str,
        created_at: int,
    ) -> dict[str, Any]:
        status = self._chat_status(tool_input.get("status") or "running")
        step_key = str(tool_input.get("step_key") or tool_input.get("step_id") or "")
        title = self._step_title(step_key, status)
        return self._event(
            event_id=event_id,
            event_type="step",
            status=status,
            title=title,
            summary=summary,
            task_id=task_id,
            conversation_id=conversation_id,
            message_id=message_id,
            created_at=created_at,
            step_id=step_key,
            step_key=step_key,
            worker_name=str(tool_input.get("worker_name") or tool_name),
            worker_agent_id=str(tool_input.get("worker_agent_id") or ""),
            payload={"source": source, **tool_input},
        )

    def _step_event_from_step(
        self,
        task: AgentTask,
        step: AgentStep,
        *,
        message: Message,
        agent_map: dict[UUID, Agent],
    ) -> dict[str, Any]:
        worker = agent_map.get(step.worker_agent_id)
        input_json = step.input_json if isinstance(step.input_json, dict) else {}
        output_json = step.output_json if isinstance(step.output_json, dict) else {}
        status = self._chat_status(step.status)
        return self._event(
            event_id=f"step:{step.id}",
            event_type="step",
            status=status,
            title=self._step_title(step.step_key, status),
            summary=self._step_summary(input_json, output_json, status),
            task_id=str(task.id),
            conversation_id=str(message.conversation_id),
            message_id=str(message.id),
            created_at=self._ts(step.started_at or step.updated_at or step.created_at),
            plan_id=str(step.plan_id),
            step_id=str(step.id),
            step_key=step.step_key,
            worker_name=worker.name if worker else "",
            worker_agent_id=str(step.worker_agent_id),
            payload={
                "description": str(input_json.get("task") or ""),
                "result": self._final_summary(output_json),
                "error": str(output_json.get("error") or ""),
                "attachments": list(output_json.get("artifacts") or [])
                if isinstance(output_json.get("artifacts"), list)
                else [],
                "input_summary": self._preview(input_json),
                "output_summary": self._preview(output_json),
            },
        )

    def _tool_event_from_worker_call(
        self,
        task: AgentTask,
        call: WorkerCall,
        *,
        message: Message,
        agent_map: dict[UUID, Agent],
    ) -> dict[str, Any]:
        worker = agent_map.get(call.worker_agent_id)
        tool_name = worker.name if worker else "WorkerAgent"
        invocation_json = call.invocation_json if isinstance(call.invocation_json, dict) else {}
        result_json = call.result_json if isinstance(call.result_json, dict) else {}
        status = self._chat_status(call.status)
        return self._event(
            event_id=f"tool:{call.id}",
            event_type="tool",
            status=status,
            title=self._tool_title(tool_name, status),
            summary=self._final_summary(result_json) or self._preview(result_json),
            task_id=str(task.id),
            conversation_id=str(message.conversation_id),
            message_id=str(message.id),
            created_at=self._ts(call.updated_at or call.created_at),
            step_id=str(call.step_id),
            tool_name=tool_name,
            worker_agent_id=str(call.worker_agent_id),
            payload={
                "tool_call_id": str(call.id),
                "tool_name": tool_name,
                "function_name": tool_name,
                "function_args": invocation_json,
                "function_result": result_json,
                "input_summary": self._preview(invocation_json),
                "output_summary": self._preview(result_json),
                "token_count": call.token_count,
                "latency": float(call.latency or 0),
            },
        )

    def _wait_event_from_tool_input(
        self,
        *,
        event_id: str,
        summary: str,
        tool_name: str,
        tool_input: dict[str, Any],
        source: str,
        task_id: str,
        conversation_id: str,
        message_id: str,
        created_at: int,
    ) -> dict[str, Any]:
        plan_feedback = tool_input.get("plan_feedback") if isinstance(tool_input.get("plan_feedback"), dict) else {}
        missing_info = tool_input.get("missing_info")
        if not isinstance(missing_info, list):
            feedback_missing_info = plan_feedback.get("missing_info")
            missing_info = feedback_missing_info if isinstance(feedback_missing_info, list) else []
        step_key = str(tool_input.get("step_key") or tool_input.get("step_id") or "")
        return self._event(
            event_id=event_id,
            event_type="wait",
            status="waiting",
            title="等待用户补充信息",
            summary=summary,
            task_id=task_id,
            conversation_id=conversation_id,
            message_id=message_id,
            created_at=created_at,
            step_id=step_key,
            step_key=step_key,
            worker_name=str(tool_input.get("worker_name") or tool_name),
            payload={
                "source": source,
                "reason": summary,
                "reason_code": tool_input.get("reason_code") or plan_feedback.get("reason_code") or "missing_info",
                "missing_info": missing_info,
                "missing_fields": missing_info,
                "resume_policy": tool_input.get("resume_policy") or "resume_same_step",
                "resume_operation": "补充信息后继续执行当前 Step",
                **tool_input,
            },
        )

    def _wait_event_from_trace(
        self,
        task: AgentTask,
        trace: TraceEvent,
        *,
        message: Message,
        step: AgentStep | None,
    ) -> dict[str, Any]:
        payload = trace.payload if isinstance(trace.payload, dict) else {}
        missing_info = payload.get("missing_info") if isinstance(payload.get("missing_info"), list) else []
        return self._event(
            event_id=f"wait:{trace.id}",
            event_type="wait",
            status="waiting",
            title="等待用户补充信息",
            summary=str(payload.get("summary") or task.error_message or ""),
            task_id=str(task.id),
            conversation_id=str(message.conversation_id),
            message_id=str(message.id),
            created_at=self._ts(trace.created_at),
            plan_id=str(trace.plan_id) if trace.plan_id else "",
            step_id=str(trace.step_id) if trace.step_id else "",
            step_key=step.step_key if step else str(payload.get("step_key") or ""),
            payload={
                "reason": str(payload.get("summary") or task.error_message or ""),
                "reason_code": payload.get("reason_code") or "missing_info",
                "missing_info": missing_info,
                "missing_fields": missing_info,
                "resume_policy": payload.get("resume_policy") or "resume_same_step",
                "resume_operation": "补充信息后继续执行当前 Step",
                **payload,
            },
        )

    @staticmethod
    def _event(
        *,
        event_id: str,
        event_type: str,
        status: str,
        title: str,
        summary: str,
        task_id: str,
        conversation_id: str,
        message_id: str,
        created_at: int,
        payload: dict[str, Any],
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "id": event_id,
            "type": event_type,
            "status": status,
            "title": title,
            "summary": summary or "",
            "task_id": task_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "created_at": created_at,
            "payload": payload or {},
            **extra,
        }

    def _message_tasks(
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
        matched = [task for task in tasks if self._task_message_id(task) == message.id]
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
    def _task_message_id(task: AgentTask) -> UUID | None:
        user_input = task.user_input or {}
        candidates = [user_input.get("message_id")]
        for key in ("context", "conversation"):
            value = user_input.get(key)
            if isinstance(value, dict):
                candidates.append(value.get("message_id"))
        for candidate in candidates:
            if not candidate:
                continue
            try:
                return UUID(str(candidate))
            except (TypeError, ValueError):
                continue
        return None

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

    def _steps_from_plan(
        self,
        plan_json: dict[str, Any],
        steps: list[AgentStep],
        agent_map: dict[UUID, Agent],
    ) -> list[dict[str, Any]]:
        if steps:
            return [self._step_snapshot(step, agent_map=agent_map) for step in steps]
        return self._steps_from_plan_payload(plan_json)

    def _steps_from_plan_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            raw_steps = payload.get("planned_steps") if isinstance(payload.get("planned_steps"), list) else []
        steps: list[dict[str, Any]] = []
        for index, raw_step in enumerate(raw_steps, start=1):
            if not isinstance(raw_step, dict):
                continue
            step_id = str(raw_step.get("step_id") or raw_step.get("step_key") or raw_step.get("id") or f"step_{index}")
            steps.append(
                {
                    "id": step_id,
                    "key": step_id,
                    "description": str(raw_step.get("task") or raw_step.get("description") or ""),
                    "status": self._chat_status(raw_step.get("status") or "created"),
                    "worker_name": str(raw_step.get("worker_name") or ""),
                    "worker_agent_id": str(raw_step.get("worker_agent_id") or raw_step.get("worker_id") or ""),
                    "result": str(raw_step.get("result") or raw_step.get("summary") or ""),
                    "error": str(raw_step.get("error") or ""),
                    "attachments": raw_step.get("attachments") if isinstance(raw_step.get("attachments"), list) else [],
                    "dependencies": raw_step.get("dependencies")
                    if isinstance(raw_step.get("dependencies"), list)
                    else [],
                }
            )
        return steps

    def _step_snapshot(self, step: AgentStep, *, agent_map: dict[UUID, Agent]) -> dict[str, Any]:
        worker = agent_map.get(step.worker_agent_id)
        input_json = step.input_json if isinstance(step.input_json, dict) else {}
        output_json = step.output_json if isinstance(step.output_json, dict) else {}
        artifacts = output_json.get("artifacts")
        return {
            "id": str(step.id),
            "key": step.step_key,
            "description": str(input_json.get("task") or ""),
            "status": self._chat_status(step.status),
            "worker_name": worker.name if worker else "",
            "worker_agent_id": str(step.worker_agent_id),
            "result": self._final_summary(output_json),
            "error": str(output_json.get("error") or ""),
            "attachments": artifacts if isinstance(artifacts, list) else [],
            "dependencies": step.dependencies or [],
        }

    @staticmethod
    def _queue_event_value(event: QueueEvent | str) -> str:
        return event.value if isinstance(event, QueueEvent) else str(event)

    @staticmethod
    def _is_step_action(tool_input: dict[str, Any]) -> bool:
        return bool(tool_input.get("step_key") or tool_input.get("step_id"))

    @classmethod
    def _chat_status(cls, status: Any) -> str:
        raw = str(status or "").strip().lower()
        if raw in WAITING_STATUS_VALUES:
            return "waiting"
        if raw == "created":
            return "pending"
        if raw == "running":
            return "running"
        if raw == "succeeded":
            return "completed"
        if raw in {"failed", "cancelled", "completed", "pending", "waiting"}:
            return raw
        return raw or "pending"

    @staticmethod
    def _ts(value: datetime | None) -> int:
        return int(value.timestamp()) if value is not None else 0

    @staticmethod
    def _preview(value: Any, limit: int = 300) -> str:
        if value in (None, "", {}, []):
            return ""
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
        return text if len(text) <= limit else f"{text[:limit]}..."

    @staticmethod
    def _user_input_preview(user_input: dict[str, Any] | None) -> str:
        data = user_input if isinstance(user_input, dict) else {}
        for key in ("query", "input", "message", "task"):
            value = data.get(key)
            if value:
                return str(value)
        return ""

    @staticmethod
    def _final_summary(value: dict[str, Any] | None) -> str:
        data = value if isinstance(value, dict) else {}
        for key in ("summary", "answer", "result"):
            if data.get(key):
                return str(data.get(key))
        steps = data.get("steps")
        if isinstance(steps, list) and steps:
            latest = steps[-1]
            if isinstance(latest, dict):
                output = latest.get("output")
                if isinstance(output, dict):
                    return str(output.get("answer") or output.get("summary") or "")
        return ""

    def _plan_summary(self, plan_json: dict[str, Any], steps: list[AgentStep]) -> str:
        step_count = len(steps) or len(plan_json.get("steps") or [])
        source = ""
        risk = plan_json.get("risk_assessment")
        if isinstance(risk, dict):
            source = str(risk.get("source") or "")
        suffix = f"，来源：{source}" if source else ""
        return f"共 {step_count} 个步骤{suffix}"

    def _step_summary(self, input_json: dict[str, Any], output_json: dict[str, Any], status: str) -> str:
        if status == "completed":
            return self._final_summary(output_json) or "执行完成"
        if status == "failed":
            return str(output_json.get("error") or "执行失败")
        if status == "waiting":
            return str(output_json.get("summary") or "等待用户补充信息")
        return str(input_json.get("task") or "")

    @staticmethod
    def _step_title(step_key: str, status: str) -> str:
        label = step_key or "Step"
        status_labels = {
            "pending": "待执行",
            "running": "正在执行",
            "completed": "已完成",
            "failed": "失败",
            "waiting": "等待中",
            "cancelled": "已停止",
        }
        return f"{label} {status_labels.get(status, status)}"

    @staticmethod
    def _tool_title(tool_name: str, status: str) -> str:
        if status == "running":
            return f"正在调用 {tool_name}"
        if status == "failed":
            return f"{tool_name} 调用失败"
        return f"{tool_name} 调用完成"

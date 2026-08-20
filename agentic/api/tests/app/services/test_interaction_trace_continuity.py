#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

from app.core.agent.agent_task_runner import AgentTaskRunner
from app.core.entities.event import (
    DoneEvent,
    InteractionDecision,
    InteractionEvent,
    InteractionResolution,
    InteractionType,
    MessageEvent,
    WaitEvent,
)
from app.schemas.run_execution import ExecutionNodeKind, ExecutionNodeStatus
from app.services.execution_view import ExecutionViewAssembler
from app.services.trace_service import TraceService


class FakeTraceRepository:
    def __init__(self) -> None:
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.events: list[Dict[str, Any]] = []

    async def create_run(self, data: Dict[str, Any]) -> None:
        self.runs[data["id"]] = data

    async def update_run(self, run_id: str, data: Dict[str, Any]) -> None:
        self.runs[run_id].update(data)

    async def append_event(self, data: Dict[str, Any]) -> int:
        stored = {**data, "ingest_seq": len(self.events) + 1}
        self.events.append(stored)
        return stored["ingest_seq"]

    async def get_run(self, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        run = self.runs.get(run_id)
        return run if run and run["user_id"] == user_id else None

    async def get_waiting_run_for_interaction(
        self,
        user_id: str,
        session_id: str,
        action_id: str,
    ) -> Optional[Dict[str, Any]]:
        for event in reversed(self.events):
            if (
                event["event_type"] == "interaction.pending"
                and event["payload"].get("action_id") == action_id
            ):
                run = self.runs.get(event["run_id"])
                if (
                    run
                    and run["user_id"] == user_id
                    and run["session_id"] == session_id
                    and run["status"] == "waiting"
                ):
                    return run
        return None

    async def get_step(self, run_id: str, step_id: str) -> Optional[Dict[str, Any]]:
        return None


class FakeUow:
    def __init__(self, trace: FakeTraceRepository) -> None:
        self.trace = trace

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


def _resolution() -> InteractionResolution:
    return InteractionResolution(
        action_id="action-1",
        interaction_type=InteractionType.ASK_USER,
        decision=InteractionDecision.ANSWER,
        tool_call_id="call-1",
        tool_name="message",
        function_name="message_ask_user",
        answer="long term",
        lead_replan_count=2,
    )


def test_trace_service_resumes_original_waiting_run_for_interaction() -> None:
    repo = FakeTraceRepository()
    original = TraceService(uow_factory=lambda: FakeUow(repo))

    async def run() -> None:
        run_id = await original.start_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-before-wait",
            input_event=MessageEvent(id="input-1", role="user", message="need advice"),
        )
        pending = InteractionEvent(
            action_id="action-1",
            interaction_type=InteractionType.ASK_USER,
            tool_call_id="call-1",
            tool_name="message",
            function_name="message_ask_user",
            prompt="请选择",
            lead_replan_count=2,
        )
        await original.project_event(pending)
        await original.project_event(WaitEvent(id="wait-1"))
        assert repo.runs[run_id]["status"] == "waiting"

        continuation = TraceService(uow_factory=lambda: FakeUow(repo))
        resumed_run_id = await continuation.resume_interaction_run(
            user_id="user-1",
            session_id="session-1",
            task_id="task-after-wait",
            resolution=_resolution(),
        )
        await continuation.project_interaction_resolution(_resolution())
        await continuation.project_event(DoneEvent(id="done-1"))

        assert resumed_run_id == run_id
        assert continuation.run_id == run_id
        assert len(repo.runs) == 1
        assert repo.runs[run_id]["task_id"] == "task-after-wait"
        assert repo.runs[run_id]["status"] == "completed"
        assert [
            event["run_id"]
            for event in repo.events
            if event["event_type"].startswith("interaction.")
        ] == [run_id, run_id]

    asyncio.run(run())


def test_agent_task_runner_prefers_resume_for_interaction_input() -> None:
    runner = object.__new__(AgentTaskRunner)
    runner._user_id = "user-1"
    runner._session_id = "session-1"
    runner._flow = type(
        "Flow",
        (),
        {"set_skill_runtime_context": lambda self, context: None},
    )()
    runner._trace_service = type(
        "Trace",
        (),
        {
            "resume_interaction_run": AsyncMock(return_value="run-original"),
            "start_run": AsyncMock(return_value="run-new"),
        },
    )()
    runner._skill_runtime_service = None
    event = MessageEvent(
        role="user",
        message="Resolve interaction action-1",
        visible=False,
        interaction_response=_resolution(),
    )
    task = type("Task", (), {"id": "task-after-wait"})()

    asyncio.run(runner._prepare_skill_runtime(task, event))

    runner._trace_service.resume_interaction_run.assert_awaited_once_with(
        user_id="user-1",
        session_id="session-1",
        task_id="task-after-wait",
        resolution=event.interaction_response,
    )
    runner._trace_service.start_run.assert_not_awaited()


def test_execution_view_does_not_duplicate_structured_wait_node() -> None:
    now = datetime(2026, 8, 20, 8, 0, 0)
    run = {
        "id": "run-1",
        "session_id": "session-1",
        "input_event_id": "input-1",
        "status": "completed",
        "started_at": now,
        "finished_at": now + timedelta(seconds=3),
    }

    def event(cursor: int, event_type: str, node_id: str, payload: Dict[str, Any]):
        return {
            "ingest_seq": cursor,
            "schema_version": 2,
            "event_type": event_type,
            "node_id": node_id,
            "parent_node_id": "run:run-1",
            "summary": event_type,
            "payload": payload,
            "created_at": now + timedelta(milliseconds=cursor),
        }

    view = ExecutionViewAssembler().assemble(
        run=run,
        events=[
            event(
                1,
                "interaction.pending",
                "interaction:action-1",
                {"action_id": "action-1", "status": "pending"},
            ),
            event(2, "wait.created", "event:wait-1", {"status": "waiting"}),
            event(
                3,
                "interaction.resolved",
                "interaction:action-1",
                {"action_id": "action-1", "status": "resolved"},
            ),
        ],
        next_cursor=3,
        has_more=False,
    )

    interactions = [
        node for node in view.nodes if node.kind == ExecutionNodeKind.INTERACTION
    ]
    assert len(interactions) == 1
    assert interactions[0].status == ExecutionNodeStatus.SUCCEEDED

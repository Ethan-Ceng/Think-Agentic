#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import TypeAdapter

from app.core.agent.agent_task_runner import AgentTaskRunner
from app.core.entities.event import (
    DoneEvent,
    ErrorEvent,
    Event,
    ExecutionUpdateEvent,
    MessageDeltaEvent,
    MessageEvent,
    TitleEvent,
    WaitEvent,
)
from app.core.entities.session import NextMessage, NextMessageState, SessionStatus
from app.core.task.base import RunCancellationContext, RunCancellationReason
from app.core.llm.failure import ModelFailureCode, ModelRuntimeError, model_failure


class FakeSessionRepository:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self.status_updates: list[SessionStatus] = []
        self.next_messages: list[NextMessage] = []
        self.consumed_next_messages: list[str] = []
        self.generated_titles: list[str] = []
        self.finish_calls = 0

    async def add_event(self, session_id: str, event: Event) -> None:
        assert session_id == "session-1"
        self.events.append(event)

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        assert session_id == "session-1"
        self.status_updates.append(status)

    async def update_latest_message(self, session_id: str, message: str, timestamp) -> None:
        assert session_id == "session-1"

    async def increment_unread_message_count(self, session_id: str) -> None:
        assert session_id == "session-1"

    async def update_generated_title(self, session_id: str, title: str) -> bool:
        assert session_id == "session-1"
        self.generated_titles.append(title)
        return True

    async def finish_or_claim_next_message(self, session_id: str, task_id: str):
        assert session_id == "session-1"
        self.finish_calls += 1
        if self.next_messages:
            claimed = self.next_messages.pop(0).model_copy(
                update={"state": NextMessageState.PROCESSING, "task_id": task_id}
            )
            return claimed
        self.status_updates.append(SessionStatus.COMPLETED)
        return None

    async def consume_next_message(
        self,
        session_id: str,
        message_id: str,
        task_id: str,
        event: Event,
    ) -> None:
        assert session_id == "session-1"
        assert task_id == "task-1"
        self.consumed_next_messages.append(message_id)
        self.events.append(event)

    async def reset_processing_next_message(self, session_id: str):
        assert session_id == "session-1"
        return None


class FakeUow:
    def __init__(self, session: FakeSessionRepository) -> None:
        self.session = session
        self.file = type("FileRepository", (), {"get_by_id_for_user": AsyncMock(return_value=None)})()

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class FakeInputStream:
    def __init__(self, event: MessageEvent | list[MessageEvent]) -> None:
        events = event if isinstance(event, list) else [event]
        self._items = [
            (f"input-{index}", item.model_dump_json())
            for index, item in enumerate(events, start=1)
        ]

    async def is_empty(self) -> bool:
        return not self._items

    async def pop(self) -> tuple[str | None, str | None]:
        if not self._items:
            return None, None
        return self._items.pop(0)


class FakeOutputStream:
    def __init__(self) -> None:
        self.payloads: list[str] = []
        self.status_source: list[SessionStatus] | None = None
        self.status_snapshots: list[list[SessionStatus]] = []

    async def put(self, payload: str) -> str:
        if self.status_source is not None:
            self.status_snapshots.append(list(self.status_source))
        self.payloads.append(payload)
        return f"output-{len(self.payloads)}"


class FakeTask:
    id = "task-1"

    def __init__(self, event: MessageEvent | list[MessageEvent]) -> None:
        self.input_stream = FakeInputStream(event)
        self.output_stream = FakeOutputStream()
        self.cancellation_context: RunCancellationContext | None = None


def make_runner() -> tuple[AgentTaskRunner, FakeSessionRepository]:
    session_repo = FakeSessionRepository()
    uow = FakeUow(session_repo)
    runner = object.__new__(AgentTaskRunner)
    runner._session_id = "session-1"
    runner._user_id = "user-1"
    runner._uow = uow
    runner._sandbox_runtime = type(
        "Runtime",
        (),
        {"set_attachment_manifest": lambda self, attachments: []},
    )()
    runner._sandbox = type("Sandbox", (), {"ensure_sandbox": AsyncMock()})()
    runner._mcp_config = object()
    runner._mcp_tool = type("MCP", (), {"initialize": AsyncMock()})()
    runner._a2a_config = object()
    runner._a2a_tool = type("A2A", (), {"initialize": AsyncMock()})()
    runner._trace_service = type("Trace", (), {"project_event": AsyncMock()})()
    runner._last_execution_cursor = None
    runner._execution_poll_at = 0.0
    runner._sync_message_attachments_to_sandbox = AsyncMock()
    runner._prepare_skill_runtime = AsyncMock()
    runner._cleanup_tools = AsyncMock()
    return runner, session_repo


def parse_output_events(task: FakeTask) -> list[Event]:
    return [TypeAdapter(Event).validate_json(payload) for payload in task.output_stream.payloads]


def test_destroy_cleans_tools_when_sandbox_destroy_fails() -> None:
    runner, _ = make_runner()
    runner._sandbox.destroy = AsyncMock(side_effect=RuntimeError("sandbox failed"))

    with pytest.raises(RuntimeError, match="sandbox failed"):
        asyncio.run(runner.destroy())

    runner._cleanup_tools.assert_awaited_once()


def test_normal_completion_updates_status_then_emits_done_event() -> None:
    runner, session_repo = make_runner()

    async def empty_flow(_message):
        if False:
            yield None

    runner._run_flow = empty_flow
    task = FakeTask(MessageEvent(role="user", message="hello"))

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert session_repo.status_updates == [SessionStatus.COMPLETED]
    assert len(output_events) == 1
    assert isinstance(output_events[0], DoneEvent)
    assert len(session_repo.events) == 1
    assert isinstance(session_repo.events[0], DoneEvent)


def test_title_events_use_generated_title_guard() -> None:
    runner, session_repo = make_runner()

    async def title_flow(_message):
        yield TitleEvent(title="Generated title")

    runner._run_flow = title_flow
    task = FakeTask(MessageEvent(role="user", message="hello"))

    asyncio.run(runner.invoke(task))

    assert session_repo.generated_titles == ["Generated title"]


def test_normal_flow_done_event_is_not_duplicated_by_completion_fallback() -> None:
    runner, session_repo = make_runner()

    async def completed_flow(_message):
        yield DoneEvent()

    runner._run_flow = completed_flow
    task = FakeTask(MessageEvent(role="user", message="hello"))
    task.output_stream.status_source = session_repo.status_updates

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert session_repo.status_updates == [SessionStatus.COMPLETED]
    assert len(output_events) == 1
    assert isinstance(output_events[0], DoneEvent)
    assert task.output_stream.status_snapshots == [[SessionStatus.COMPLETED]]


def test_waiting_run_emits_wait_without_done() -> None:
    runner, session_repo = make_runner()
    session_repo.next_messages.append(NextMessage(message="wait behind interaction"))

    async def wait_flow(_message):
        yield WaitEvent()

    runner._run_flow = wait_flow
    task = FakeTask(MessageEvent(role="user", message="hello"))

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert session_repo.status_updates == [SessionStatus.WAITING]
    assert len(output_events) == 1
    assert isinstance(output_events[0], WaitEvent)
    assert len(session_repo.next_messages) == 1
    assert session_repo.finish_calls == 0


def test_failed_run_updates_status_then_emits_error() -> None:
    runner, session_repo = make_runner()
    session_repo.next_messages.append(NextMessage(message="keep after error"))

    async def failed_flow(_message):
        raise RuntimeError("broken flow")
        if False:
            yield None

    runner._run_flow = failed_flow
    task = FakeTask(MessageEvent(role="user", message="hello"))

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert session_repo.status_updates == [SessionStatus.COMPLETED]
    assert len(output_events) == 1
    assert isinstance(output_events[0], ErrorEvent)
    assert output_events[0].failure is not None
    assert output_events[0].failure.code == "RUN_INTERNAL_ERROR"
    assert "broken flow" not in output_events[0].error
    assert len(session_repo.next_messages) == 1
    assert session_repo.finish_calls == 0


def test_model_failure_keeps_its_typed_error_at_run_boundary() -> None:
    runner, session_repo = make_runner()
    failure = model_failure(ModelFailureCode.AUTHENTICATION_FAILED)

    async def failed_flow(_message):
        raise ModelRuntimeError(failure)
        if False:
            yield None

    runner._run_flow = failed_flow
    task = FakeTask(MessageEvent(role="user", message="hello"))

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert session_repo.status_updates == [SessionStatus.COMPLETED]
    assert len(output_events) == 1
    assert isinstance(output_events[0], ErrorEvent)
    assert output_events[0].failure is not None
    assert output_events[0].failure.code == ModelFailureCode.AUTHENTICATION_FAILED.value
    assert output_events[0].failure.debug_id == failure.debug_id


def test_unattributed_cancel_becomes_internal_error_instead_of_user_stop() -> None:
    runner, session_repo = make_runner()
    session_repo.next_messages.append(NextMessage(message="keep after stop"))

    async def cancelled_flow(_message):
        raise asyncio.CancelledError
        if False:
            yield None

    runner._run_flow = cancelled_flow
    task = FakeTask(MessageEvent(role="user", message="hello"))

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert session_repo.status_updates == [SessionStatus.COMPLETED]
    assert len(output_events) == 1
    assert isinstance(output_events[0], ErrorEvent)
    assert output_events[0].failure is not None
    assert output_events[0].failure.code == "RUN_INTERNAL_ERROR"
    assert len(session_repo.next_messages) == 1
    assert session_repo.finish_calls == 0


def test_next_message_runs_after_current_flow_and_only_final_done_is_emitted() -> None:
    runner, session_repo = make_runner()
    session_repo.next_messages.append(NextMessage(message="follow up"))
    received: list[str] = []

    async def completed_flow(message):
        received.append(message.message)
        yield DoneEvent()

    runner._run_flow = completed_flow
    task = FakeTask(MessageEvent(role="user", message="current"))

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert received == ["current", "follow up"]
    assert [type(event) for event in output_events] == [MessageEvent, DoneEvent]
    assert output_events[0].message == "follow up"
    assert len(session_repo.consumed_next_messages) == 1
    assert session_repo.status_updates == [SessionStatus.COMPLETED]


def test_empty_recovery_task_starts_from_persisted_next_message() -> None:
    runner, session_repo = make_runner()
    session_repo.next_messages.append(NextMessage(message="recover me"))
    received: list[str] = []

    async def completed_flow(message):
        received.append(message.message)
        yield DoneEvent()

    runner._run_flow = completed_flow
    task = FakeTask([])

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert received == ["recover me"]
    assert [type(event) for event in output_events] == [MessageEvent, DoneEvent]
    assert session_repo.status_updates == [SessionStatus.COMPLETED]


def test_existing_redis_input_waits_for_current_flow_to_finish() -> None:
    runner, _ = make_runner()
    received: list[str] = []
    first_turn_events: list[str] = []

    async def multi_event_flow(message):
        received.append(message.message)
        if message.message == "current":
            first_turn_events.append("first")
            yield MessageEvent(role="assistant", message="part one")
            first_turn_events.append("second")
            yield MessageEvent(role="assistant", message="part two")
        yield DoneEvent()

    runner._run_flow = multi_event_flow
    task = FakeTask(
        [
            MessageEvent(role="user", message="current"),
            MessageEvent(role="user", message="legacy queued"),
        ]
    )

    asyncio.run(runner.invoke(task))

    assert first_turn_events == ["first", "second"]
    assert received == ["current", "legacy queued"]


def test_message_delta_is_transient_but_final_message_remains_persisted() -> None:
    runner, session_repo = make_runner()

    async def streaming_flow(_message):
        yield MessageDeltaEvent(
            stream_id="stream-1",
            sequence=0,
            delta="Hel",
        )
        yield MessageEvent(
            role="assistant",
            message="Hello",
            stream_id="stream-1",
        )
        yield DoneEvent()

    runner._run_flow = streaming_flow
    task = FakeTask(MessageEvent(role="user", message="hello"))

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert [event.type for event in output_events] == [
        "message_delta",
        "message",
        "done",
    ]
    assert [event.type for event in session_repo.events] == ["message", "done"]
    projected = runner._trace_service.project_event.await_args_list
    assert [call.args[0].type for call in projected] == ["message", "done"]


def test_execution_update_is_transient_incremental_and_not_session_history() -> None:
    runner, session_repo = make_runner()

    class TraceWithExecution:
        run_id = "run-1"

        def __init__(self) -> None:
            self.after_values = []

        async def get_execution_view(self, user_id, run_id, *, after, limit, detail):
            self.after_values.append(after)
            cursor = 1 if after is None else 2
            return {
                "schema_version": 1,
                "run": {"input_event_id": "input-1"},
                "nodes": [
                    {
                        "node_id": "run:run-1",
                        "parent_node_id": None,
                        "kind": "run",
                        "phase": "decide",
                        "status": "running",
                        "title": "开始处理请求",
                        "summary": "开始处理请求",
                        "cursor": cursor,
                        "metrics": {},
                    }
                ],
                "next_cursor": cursor,
                "trace_complete": True,
            }

    trace = TraceWithExecution()
    runner._trace_service = trace
    task = FakeTask([])

    async def emit_twice() -> None:
        await runner._emit_execution_update(task, force=True)
        await runner._emit_execution_update(task, force=True)

    asyncio.run(emit_twice())

    output_events = parse_output_events(task)
    assert all(isinstance(event, ExecutionUpdateEvent) for event in output_events)
    assert [event.next_cursor for event in output_events] == [1, 2]
    assert trace.after_values == [None, 1]
    assert session_repo.events == []


def test_flow_error_aborts_an_unfinished_transient_draft() -> None:
    runner, session_repo = make_runner()

    async def failed_stream(_message):
        yield MessageDeltaEvent(
            stream_id="stream-1",
            sequence=0,
            delta="partial",
        )
        raise RuntimeError("stream failed")

    runner._run_flow = failed_stream
    task = FakeTask(MessageEvent(role="user", message="hello"))

    asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert [event.type for event in output_events] == [
        "message_delta",
        "message_delta",
        "error",
    ]
    assert output_events[1].operation == "abort"
    assert output_events[1].sequence == 1
    assert [event.type for event in session_repo.events] == ["error"]


def test_cancellation_aborts_an_unfinished_transient_draft() -> None:
    runner, session_repo = make_runner()

    async def cancelled_stream(_message):
        yield MessageDeltaEvent(
            stream_id="stream-1",
            sequence=0,
            delta="partial",
        )
        raise asyncio.CancelledError

    runner._run_flow = cancelled_stream
    task = FakeTask(MessageEvent(role="user", message="hello"))
    task.cancellation_context = RunCancellationContext(
        reason=RunCancellationReason.USER,
        requested_by="user-1",
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runner.invoke(task))

    output_events = parse_output_events(task)
    assert [event.type for event in output_events] == [
        "message_delta",
        "message_delta",
        "done",
    ]
    assert output_events[1].operation == "abort"
    assert [event.type for event in session_repo.events] == ["done"]

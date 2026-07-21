#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.entities.event import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    InteractionDecision,
    InteractionResolution,
    InteractionType,
    MessageEvent,
)
from app.core.entities.session import Session, SessionStatus
from app.schemas.event import MessageSSEEvent
from app.services.agent_service import AgentService


class FakeSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.events: List[BaseEvent] = []
        self.status_updates: List[SessionStatus] = []
        self.latest_messages: List[str] = []

    async def get_by_id_for_user(self, session_id: str, user_id: str) -> Optional[Session]:
        if session_id == self.session.id and user_id == self.session.user_id:
            return self.session
        return None

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        assert session_id == self.session.id
        self.session.status = status
        self.status_updates.append(status)

    async def add_event(self, session_id: str, event: BaseEvent) -> None:
        assert session_id == self.session.id
        self.events.append(event)

    async def reset_processing_next_message(self, session_id: str):
        assert session_id == self.session.id
        return self.session.next_message

    async def update_latest_message(self, session_id: str, message: str, timestamp: datetime) -> None:
        assert session_id == self.session.id
        self.latest_messages.append(message)

    async def update_unread_message_count(self, session_id: str, count: int) -> None:
        assert session_id == self.session.id


class FakeTraceRepository:
    def __init__(self) -> None:
        self.interruptions: List[Dict[str, Any]] = []

    async def finalize_interrupted_run(
        self,
        session_id: str,
        error: str,
        finished_at: datetime,
    ) -> Optional[str]:
        self.interruptions.append(
            {
                "session_id": session_id,
                "error": error,
                "finished_at": finished_at,
            }
        )
        return "run-1"


class FakeFileRepository:
    async def get_by_id_for_user(self, file_id: str, user_id: str) -> None:
        return None


class FakeUow:
    def __init__(self, session: FakeSessionRepository, trace: FakeTraceRepository) -> None:
        self.session = session
        self.trace = trace
        self.file = FakeFileRepository()

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class MissingTask:
    @classmethod
    def get(cls, task_id: str) -> None:
        return None


class FakeInputStream:
    def __init__(self) -> None:
        self.payloads: List[str] = []

    async def put(self, payload: str) -> str:
        self.payloads.append(payload)
        return "event-1"


class TailOutputStreamWithoutEvent:
    async def get(self, start_id=None, block_ms=None):
        return None, None


class CompletedTask:
    def __init__(self) -> None:
        self.input_stream = FakeInputStream()
        self.output_stream = TailOutputStreamWithoutEvent()
        self.done = False

    async def invoke(self) -> None:
        self.done = True


class TailOutputStream:
    def __init__(self, event: BaseEvent) -> None:
        self.event = event
        self.reads = 0

    async def get(self, start_id=None, block_ms=None):
        self.reads += 1
        if self.reads == 1:
            return "output-1", self.event.model_dump_json()
        return None, None


class FinishedTaskWithTail:
    done = True

    def __init__(self, event: BaseEvent) -> None:
        self.output_stream = TailOutputStream(event)


class TimeoutThenTailOutputStream:
    def __init__(self, event: BaseEvent) -> None:
        self.event = event
        self.start_ids: List[Optional[str]] = []

    async def get(self, start_id=None, block_ms=None):
        self.start_ids.append(start_id)
        if len(self.start_ids) == 1:
            return None, None
        return "output-2", self.event.model_dump_json()


class RunningTaskWithTemporaryTimeout:
    done = False

    def __init__(self, event: BaseEvent) -> None:
        self.output_stream = TimeoutThenTailOutputStream(event)


def make_service(session: Session) -> tuple[AgentService, FakeSessionRepository, FakeTraceRepository]:
    session_repo = FakeSessionRepository(session)
    trace_repo = FakeTraceRepository()
    uow = FakeUow(session_repo, trace_repo)
    service = AgentService(
        uow_factory=lambda: uow,
        user_config_service=object(),
        llm_factory=lambda *_: object(),
        sandbox_cls=object(),
        task_cls=MissingTask,
        json_parser=object(),
        search_engine=object(),
        file_storage=object(),
    )
    return service, session_repo, trace_repo


def test_chat_finalizes_running_session_when_task_registry_was_lost() -> None:
    session = Session(
        id="session-1",
        user_id="user-1",
        task_id="missing-task",
        status=SessionStatus.RUNNING,
    )
    service, session_repo, trace_repo = make_service(session)

    async def run() -> List[ErrorEvent]:
        events = [
            event
            async for event in service.chat(
                session_id=session.id,
                user_id=session.user_id,
            )
        ]
        await asyncio.sleep(0)
        return events

    events = asyncio.run(run())

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert "运行上下文已丢失" in events[0].error
    assert session_repo.status_updates == [SessionStatus.COMPLETED]
    assert session_repo.events == events
    assert trace_repo.interruptions[0]["session_id"] == session.id
    assert "运行上下文已丢失" in trace_repo.interruptions[0]["error"]


def test_recovery_messages_distinguish_continue_from_restart() -> None:
    continue_message = AgentService.get_recovery_message("continue")
    restart_message = AgentService.get_recovery_message("restart")

    assert "从未完成处继续" in continue_message
    assert "避免重复" in continue_message
    assert "从头重新执行" in restart_message
    assert continue_message != restart_message


def test_resume_starts_a_new_run_in_the_same_session() -> None:
    session = Session(id="session-1", user_id="user-1", status=SessionStatus.COMPLETED)
    service, _, _ = make_service(session)
    captured: Dict[str, Any] = {}

    async def fake_chat(**kwargs):
        captured.update(kwargs)
        yield ErrorEvent(error="stream-marker")

    service.chat = fake_chat  # type: ignore[method-assign]

    async def run() -> List[ErrorEvent]:
        return [
            event
            async for event in service.resume(
                session_id=session.id,
                user_id=session.user_id,
                mode="continue",
            )
        ]

    events = asyncio.run(run())

    assert events[0].error == "stream-marker"
    assert captured["session_id"] == session.id
    assert captured["user_id"] == session.user_id
    assert captured["message"] == AgentService.get_recovery_message("continue")
    assert captured["visible"] is False


def test_internal_message_stays_in_agent_input_without_updating_conversation_summary() -> None:
    session = Session(id="session-1", user_id="user-1", status=SessionStatus.COMPLETED)
    service, session_repo, _ = make_service(session)
    task = CompletedTask()

    async def fake_get_task(_session: Session) -> None:
        return None

    async def fake_create_task(_session: Session) -> CompletedTask:
        return task

    service._get_task = fake_get_task  # type: ignore[method-assign]
    service._create_task = fake_create_task  # type: ignore[method-assign]

    async def run() -> List[BaseEvent]:
        events = [
            event
            async for event in service.chat(
                session_id=session.id,
                user_id=session.user_id,
                message="internal recovery instruction",
                visible=False,
            )
        ]
        await asyncio.sleep(0)
        return events

    events = asyncio.run(run())

    message_event = events[0]
    assert isinstance(message_event, MessageEvent)
    assert message_event.visible is False
    assert session_repo.latest_messages == []
    assert session_repo.events == [message_event]
    assert MessageSSEEvent.from_event(message_event).data.visible is False


def test_stop_finalizes_orphaned_run_instead_of_leaving_trace_running() -> None:
    session = Session(
        id="session-1",
        user_id="user-1",
        task_id="missing-task",
        status=SessionStatus.RUNNING,
    )
    service, session_repo, trace_repo = make_service(session)

    asyncio.run(service.stop_session(session.id, session.user_id))

    assert session_repo.status_updates == [SessionStatus.COMPLETED]
    assert len(trace_repo.interruptions) == 1
    assert trace_repo.interruptions[0]["session_id"] == session.id


def test_chat_drains_terminal_event_after_task_has_already_finished() -> None:
    session = Session(
        id="session-1",
        user_id="user-1",
        task_id="finished-task",
        status=SessionStatus.RUNNING,
    )
    service, _, _ = make_service(session)
    task = FinishedTaskWithTail(DoneEvent())

    async def fake_get_task(_session: Session) -> FinishedTaskWithTail:
        return task

    service._get_task = fake_get_task  # type: ignore[method-assign]

    async def run() -> List[BaseEvent]:
        events = [
            event
            async for event in service.chat(
                session_id=session.id,
                user_id=session.user_id,
            )
        ]
        await asyncio.sleep(0)
        return events

    events = asyncio.run(run())

    assert len(events) == 1
    assert isinstance(events[0], DoneEvent)
    assert task.output_stream.reads == 1


def test_chat_keeps_output_cursor_after_a_temporary_read_timeout() -> None:
    session = Session(
        id="session-1",
        user_id="user-1",
        task_id="running-task",
        status=SessionStatus.RUNNING,
    )
    service, _, _ = make_service(session)
    task = RunningTaskWithTemporaryTimeout(DoneEvent())

    async def fake_get_task(_session: Session) -> RunningTaskWithTemporaryTimeout:
        return task

    service._get_task = fake_get_task  # type: ignore[method-assign]

    async def run() -> List[BaseEvent]:
        events = [
            event
            async for event in service.chat(
                session_id=session.id,
                user_id=session.user_id,
                latest_event_id="output-1",
            )
        ]
        await asyncio.sleep(0)
        return events

    events = asyncio.run(run())

    assert len(events) == 1
    assert isinstance(events[0], DoneEvent)
    assert task.output_stream.start_ids == ["output-1", "output-1"]


def test_interaction_resolution_stays_in_task_input_but_not_session_history() -> None:
    session = Session(id="session-1", user_id="user-1", status=SessionStatus.WAITING)
    service, session_repo, _ = make_service(session)
    task = CompletedTask()

    async def fake_get_task(_session: Session) -> None:
        return None

    async def fake_create_task(_session: Session) -> CompletedTask:
        return task

    service._get_task = fake_get_task  # type: ignore[method-assign]
    service._create_task = fake_create_task  # type: ignore[method-assign]
    resolution = InteractionResolution(
        action_id="action-1",
        interaction_type=InteractionType.TOOL_APPROVAL,
        decision=InteractionDecision.APPROVE,
        tool_call_id="call-1",
        function_name="dangerous_write",
        function_args={"api_key": "must-not-persist"},
    )

    async def run() -> List[BaseEvent]:
        return [
            event
            async for event in service.chat(
                session_id=session.id,
                user_id=session.user_id,
                message="internal interaction resolution",
                visible=False,
                interaction_response=resolution,
            )
        ]

    events = asyncio.run(run())
    queued = MessageEvent.model_validate_json(task.input_stream.payloads[0])

    assert queued.interaction_response == resolution
    assert events[0].interaction_response is None
    assert session_repo.events[0].interaction_response is None
    assert "must-not-persist" not in session_repo.events[0].model_dump_json()

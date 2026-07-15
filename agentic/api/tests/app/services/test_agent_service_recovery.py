#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.entities.event import ErrorEvent
from app.core.entities.session import Session, SessionStatus
from app.services.agent_service import AgentService


class FakeSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.events: List[ErrorEvent] = []
        self.status_updates: List[SessionStatus] = []

    async def get_by_id_for_user(self, session_id: str, user_id: str) -> Optional[Session]:
        if session_id == self.session.id and user_id == self.session.user_id:
            return self.session
        return None

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        assert session_id == self.session.id
        self.session.status = status
        self.status_updates.append(status)

    async def add_event(self, session_id: str, event: ErrorEvent) -> None:
        assert session_id == self.session.id
        self.events.append(event)

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

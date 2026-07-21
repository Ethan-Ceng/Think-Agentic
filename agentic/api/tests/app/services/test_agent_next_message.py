import asyncio
from datetime import datetime
from typing import Optional

import pytest

from app.core.entities.event import ErrorEvent
from app.core.entities.session import (
    NextMessage,
    NextMessageConflictError,
    NextMessageNotFoundError,
    NextMessageState,
    Session,
    SessionStatus,
)
from app.schemas.exceptions import ConflictError, NotFoundError
from app.services.agent_service import AgentService
from app.services.session_service import SessionService


class _SessionRepository:
    def __init__(self, session: Optional[Session]) -> None:
        self.session = session
        self.reset_calls = 0

    async def get_by_id_for_user(self, session_id: str, user_id: str):
        if self.session and self.session.id == session_id and self.session.user_id == user_id:
            return self.session
        return None

    async def put_next_message(self, session_id: str, user_id: str, message: NextMessage):
        if self.session is None:
            raise NextMessageNotFoundError()
        if self.session.status != SessionStatus.RUNNING:
            raise NextMessageConflictError("not running")
        self.session.next_message = message
        return message

    async def cancel_next_message(self, session_id: str, user_id: str):
        if self.session is None:
            raise NextMessageNotFoundError()
        self.session.next_message = None

    async def start_next_message_run(self, session_id: str, user_id: str):
        if self.session is None:
            raise NextMessageNotFoundError()
        if self.session.status != SessionStatus.COMPLETED or self.session.next_message is None:
            raise NextMessageConflictError("not ready")
        self.session.status = SessionStatus.RUNNING
        return self.session

    async def reset_processing_next_message(self, session_id: str):
        self.reset_calls += 1
        if self.session and self.session.next_message:
            self.session.next_message = self.session.next_message.model_copy(
                update={
                    "state": NextMessageState.QUEUED,
                    "task_id": None,
                    "claimed_at": None,
                }
            )
        return self.session.next_message if self.session else None

    async def update_status(self, session_id: str, status: SessionStatus):
        assert self.session is not None
        self.session.status = status

    async def add_event(self, session_id: str, event):
        assert self.session is not None
        self.session.events.append(event)

    async def save(self, session: Session):
        self.session = session


class _TraceRepository:
    async def finalize_interrupted_run(self, **kwargs):
        return "run-1"


class _Uow:
    def __init__(self, repository: _SessionRepository) -> None:
        self.session = repository
        self.trace = _TraceRepository()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


class _MissingTask:
    @classmethod
    def get(cls, task_id: str):
        return None


class _StartedTask:
    def __init__(self) -> None:
        self.invoked = False

    async def invoke(self):
        self.invoked = True


def _agent_service(repository: _SessionRepository) -> AgentService:
    uow = _Uow(repository)
    return AgentService(
        uow_factory=lambda: uow,
        user_config_service=object(),
        llm_factory=lambda *_: object(),
        sandbox_cls=object(),
        task_cls=_MissingTask,
        json_parser=object(),
        search_engine=object(),
        file_storage=object(),
    )


def test_session_service_queues_and_maps_repository_errors():
    running = Session(id="session-1", user_id="user-1", status=SessionStatus.RUNNING)
    repository = _SessionRepository(running)
    service = SessionService(lambda: _Uow(repository), sandbox_cls=object())

    saved = asyncio.run(
        service.queue_next_message(
            running.id,
            running.user_id,
            message="follow up",
            attachments=["file-1"],
            skills=[],
        )
    )
    assert saved.message == "follow up"
    assert running.next_message == saved

    running.status = SessionStatus.COMPLETED
    with pytest.raises(ConflictError):
        asyncio.run(
            service.queue_next_message(
                running.id,
                running.user_id,
                message="too late",
                attachments=[],
                skills=[],
            )
        )

    missing = SessionService(
        lambda: _Uow(_SessionRepository(None)), sandbox_cls=object()
    )
    with pytest.raises(NotFoundError):
        asyncio.run(missing.cancel_next_message("missing", "user-1"))


def test_orphan_finalization_requeues_processing_message():
    processing = NextMessage(
        message="survive restart",
        state=NextMessageState.PROCESSING,
        task_id="dead-task",
        claimed_at=datetime.now(),
    )
    session = Session(
        id="session-1",
        user_id="user-1",
        task_id="dead-task",
        status=SessionStatus.RUNNING,
        next_message=processing,
    )
    repository = _SessionRepository(session)
    service = _agent_service(repository)

    asyncio.run(service._finalize_orphaned_run(session))

    assert repository.reset_calls == 1
    assert session.next_message is not None
    assert session.next_message.state == NextMessageState.QUEUED
    assert session.status == SessionStatus.COMPLETED


def test_run_next_message_atomically_starts_task_and_reuses_chat_stream():
    session = Session(
        id="session-1",
        user_id="user-1",
        status=SessionStatus.COMPLETED,
        next_message=NextMessage(message="follow up"),
    )
    repository = _SessionRepository(session)
    service = _agent_service(repository)
    task = _StartedTask()
    captured = {}

    async def create_task(started_session: Session):
        captured["status"] = started_session.status
        return task

    async def chat(**kwargs):
        captured.update(kwargs)
        yield ErrorEvent(error="marker")

    service._create_task = create_task  # type: ignore[method-assign]
    service.chat = chat  # type: ignore[method-assign]

    async def run():
        return [
            event
            async for event in service.run_next_message(session.id, session.user_id)
        ]

    events = asyncio.run(run())

    assert task.invoked is True
    assert captured["status"] == SessionStatus.RUNNING
    assert captured["message"] is None
    assert events[0].error == "marker"


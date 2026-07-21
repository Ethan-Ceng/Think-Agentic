import asyncio
from datetime import datetime

import pytest

from app.core.entities.event import MessageEvent
from app.core.entities.session import (
    NextMessage,
    NextMessageConflictError,
    NextMessageState,
    SessionStatus,
)
from app.models.session import SessionModel
from app.repositories.db_session_repository import DBSessionRepository


class _ScalarResult:
    def __init__(self, record):
        self._record = record

    def scalar_one_or_none(self):
        return self._record


class _FakeDBSession:
    def __init__(self, record):
        self.record = record
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _ScalarResult(self.record)


def _record(*, status: str = "running", next_message=None) -> SessionModel:
    return SessionModel(
        id="session-1",
        user_id="user-1",
        task_id="task-1",
        title="",
        unread_message_count=0,
        latest_message="",
        events=[],
        files=[],
        memories={},
        status=status,
        next_message=next_message,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _next(message: str = "follow up") -> NextMessage:
    return NextMessage(message=message, attachment_ids=["file-1"])


def test_put_replaces_a_queued_message_for_the_session_owner():
    async def scenario():
        old = _next("old").model_dump(mode="json")
        record = _record(next_message=old)
        repository = DBSessionRepository(_FakeDBSession(record))

        saved = await repository.put_next_message("session-1", "user-1", _next("new"))

        assert saved.message == "new"
        assert NextMessage.model_validate(record.next_message).message == "new"

    asyncio.run(scenario())


def test_put_rejects_completed_sessions_and_processing_messages():
    async def completed_scenario():
        repository = DBSessionRepository(_FakeDBSession(_record(status="completed")))
        with pytest.raises(NextMessageConflictError):
            await repository.put_next_message("session-1", "user-1", _next())

    async def processing_scenario():
        processing = _next().model_copy(
            update={"state": NextMessageState.PROCESSING, "task_id": "task-1"}
        )
        repository = DBSessionRepository(
            _FakeDBSession(_record(next_message=processing.model_dump(mode="json")))
        )
        with pytest.raises(NextMessageConflictError):
            await repository.put_next_message("session-1", "user-1", _next("replacement"))

    asyncio.run(completed_scenario())
    asyncio.run(processing_scenario())


def test_cancel_is_idempotent_but_rejects_processing_message():
    async def queued_scenario():
        record = _record(next_message=_next().model_dump(mode="json"))
        repository = DBSessionRepository(_FakeDBSession(record))
        await repository.cancel_next_message("session-1", "user-1")
        await repository.cancel_next_message("session-1", "user-1")
        assert record.next_message is None

    async def processing_scenario():
        processing = _next().model_copy(
            update={"state": NextMessageState.PROCESSING, "task_id": "task-1"}
        )
        repository = DBSessionRepository(
            _FakeDBSession(_record(next_message=processing.model_dump(mode="json")))
        )
        with pytest.raises(NextMessageConflictError):
            await repository.cancel_next_message("session-1", "user-1")

    asyncio.run(queued_scenario())
    asyncio.run(processing_scenario())


def test_finish_or_claim_atomically_claims_queue_or_completes_session():
    async def claim_scenario():
        record = _record(next_message=_next().model_dump(mode="json"))
        repository = DBSessionRepository(_FakeDBSession(record))
        claimed = await repository.finish_or_claim_next_message("session-1", "task-1")

        assert claimed is not None
        assert claimed.state == NextMessageState.PROCESSING
        assert claimed.task_id == "task-1"
        assert claimed.claimed_at is not None
        assert record.status == SessionStatus.RUNNING.value

    async def complete_scenario():
        record = _record()
        repository = DBSessionRepository(_FakeDBSession(record))
        claimed = await repository.finish_or_claim_next_message("session-1", "task-1")

        assert claimed is None
        assert record.status == SessionStatus.COMPLETED.value

    asyncio.run(claim_scenario())
    asyncio.run(complete_scenario())


def test_finish_or_claim_rejects_a_stale_task():
    async def scenario():
        record = _record(next_message=_next().model_dump(mode="json"))
        repository = DBSessionRepository(_FakeDBSession(record))

        with pytest.raises(NextMessageConflictError):
            await repository.finish_or_claim_next_message("session-1", "stale-task")

        assert NextMessage.model_validate(record.next_message).state == NextMessageState.QUEUED
        assert record.status == SessionStatus.RUNNING.value

    asyncio.run(scenario())


def test_consume_persists_user_event_and_clears_matching_processing_slot():
    async def scenario():
        processing = _next().model_copy(
            update={"state": NextMessageState.PROCESSING, "task_id": "task-1"}
        )
        record = _record(next_message=processing.model_dump(mode="json"))
        repository = DBSessionRepository(_FakeDBSession(record))
        event = MessageEvent(role="user", message=processing.message)

        await repository.consume_next_message(
            "session-1",
            processing.id,
            "task-1",
            event,
        )

        assert record.next_message is None
        assert record.events[-1]["id"] == event.id
        assert record.events[-1]["message"] == "follow up"

    asyncio.run(scenario())


def test_reset_processing_message_makes_it_recoverable_after_orphaning():
    async def scenario():
        processing = _next().model_copy(
            update={
                "state": NextMessageState.PROCESSING,
                "task_id": "dead-task",
                "claimed_at": datetime.now(),
            }
        )
        record = _record(next_message=processing.model_dump(mode="json"))
        repository = DBSessionRepository(_FakeDBSession(record))

        reset = await repository.reset_processing_next_message("session-1")

        assert reset is not None
        assert reset.state == NextMessageState.QUEUED
        assert reset.task_id is None
        assert reset.claimed_at is None

    asyncio.run(scenario())

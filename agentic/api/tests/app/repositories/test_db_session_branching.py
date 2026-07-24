import asyncio
from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.entities.event import MessageEvent
from app.core.entities.file import File
from app.core.entities.session import (
    BranchOperation,
    NextMessage,
    SessionBranchConflictError,
    SessionBranchNotFoundError,
    SessionStatus,
)
from app.core.entities.skill import SkillRef, SkillSource
from app.models.file import FileModel
from app.models.session import SessionModel
from app.repositories.db_session_repository import DBSessionRepository


class _Result:
    def __init__(self, *, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = list(scalars or [])

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._scalars


class _FakeDBSession:
    def __init__(self, *results, flush_error=None):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.flush_error = flush_error

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)

    def add(self, record):
        self.added.append(record)

    def begin_nested(self):
        return _NestedTransaction()

    async def flush(self):
        if self.flush_error is not None:
            error = self.flush_error
            self.flush_error = None
            raise error


class _NestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def _file(file_id: str = "file-1", *, user_id: str = "user-1") -> File:
    return File(
        id=file_id,
        user_id=user_id,
        filename="brief.txt",
        filepath=f"/uploads/{file_id}",
        key=f"uploads/{file_id}",
        extension=".txt",
        mime_type="text/plain",
        size=12,
    )


def _source_record(
    *,
    status: str = SessionStatus.COMPLETED.value,
    next_message=None,
) -> tuple[SessionModel, dict[str, MessageEvent]]:
    selected_skill = SkillRef(source=SkillSource.BUNDLED, name="browser")
    file = _file()
    messages = {
        "user-1": MessageEvent(id="user-1", role="user", message="first question"),
        "assistant-1": MessageEvent(
            id="assistant-1", role="assistant", message="first answer"
        ),
        "hidden": MessageEvent(
            id="hidden", role="assistant", message="private state", visible=False
        ),
        "user-2": MessageEvent(
            id="user-2",
            role="user",
            message="second question",
            attachments=[file],
            skills=[selected_skill],
        ),
        "assistant-2": MessageEvent(
            id="assistant-2", role="assistant", message="second answer"
        ),
    }
    events = [
        messages["user-1"].model_dump(mode="json"),
        messages["assistant-1"].model_dump(mode="json"),
        {
            "id": "tool-1",
            "type": "tool",
            "created_at": datetime.now().isoformat(),
            "function_name": "shell_execute",
        },
        messages["hidden"].model_dump(mode="json"),
        messages["user-2"].model_dump(mode="json"),
        messages["assistant-2"].model_dump(mode="json"),
    ]
    return (
        SessionModel(
            id="source-1",
            user_id="user-1",
            task_id="old-task",
            sandbox_id="old-sandbox",
            title="Original conversation",
            unread_message_count=0,
            latest_message="second answer",
            latest_message_at=datetime.now(),
            events=events,
            files=[file.model_dump(mode="json")],
            memories={"planner": {"messages": [{"role": "tool", "content": "secret"}]}},
            status=status,
            next_message=next_message,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
        messages,
    )


def _repository(source, *, existing=None, files=()):
    return DBSessionRepository(
        _FakeDBSession(
            _Result(scalar=source),
            _Result(scalar=existing),
            *([_Result(scalars=files)] if files else []),
        )
    )


def test_fork_copies_only_visible_messages_through_target_without_mutating_source():
    async def scenario():
        source, messages = _source_record()
        original = deepcopy(source.events)
        file_record = FileModel.from_domain(_file())
        repository = _repository(source, files=[file_record])

        branch = await repository.create_branch(
            source_session_id=source.id,
            user_id=source.user_id,
            target_event_id="assistant-2",
            operation=BranchOperation.FORK,
            request_id="request-1",
        )

        assert source.events == original
        assert [event.message for event in branch.events] == [
            "first question",
            "first answer",
            "second question",
            "second answer",
        ]
        assert all(isinstance(event, MessageEvent) for event in branch.events)
        assert {event.id for event in branch.events}.isdisjoint(messages)
        assert branch.next_message is None
        assert branch.status == SessionStatus.COMPLETED
        assert branch.sandbox_id is None
        assert branch.task_id is None
        assert branch.memories == {}
        assert branch.source_session_id == source.id
        assert branch.forked_from_event_id == "assistant-2"
        assert branch.branch_operation == BranchOperation.FORK
        assert branch.branch_request_id == "request-1"
        assert [item.content for item in branch.context_seed] == [
            "first question",
            "first answer",
            "second question",
            "second answer",
        ]
        assert branch.context_seed[2].attachment_names == ["brief.txt"]

    asyncio.run(scenario())


def test_edit_queues_replacement_with_original_attachments_and_skills():
    async def scenario():
        source, messages = _source_record()
        repository = _repository(source, files=[FileModel.from_domain(_file())])

        branch = await repository.create_branch(
            source_session_id=source.id,
            user_id=source.user_id,
            target_event_id="user-2",
            operation=BranchOperation.EDIT,
            request_id="request-edit",
            message="revised second question",
        )

        assert [event.message for event in branch.events] == [
            "first question",
            "first answer",
        ]
        queued = NextMessage.model_validate(branch.next_message)
        assert queued.message == "revised second question"
        assert queued.attachment_ids == ["file-1"]
        assert queued.skills == messages["user-2"].skills
        assert branch.latest_message == "revised second question"
        assert branch.status == SessionStatus.COMPLETED

    asyncio.run(scenario())


def test_regenerate_replays_nearest_previous_user_turn():
    async def scenario():
        source, messages = _source_record()
        repository = _repository(source, files=[FileModel.from_domain(_file())])

        branch = await repository.create_branch(
            source_session_id=source.id,
            user_id=source.user_id,
            target_event_id="assistant-2",
            operation=BranchOperation.REGENERATE,
            request_id="request-regenerate",
        )

        assert [event.message for event in branch.events] == [
            "first question",
            "first answer",
        ]
        queued = NextMessage.model_validate(branch.next_message)
        assert queued.message == messages["user-2"].message
        assert queued.attachment_ids == ["file-1"]
        assert queued.skills == messages["user-2"].skills

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("operation", "target", "message"),
    [
        (BranchOperation.EDIT, "assistant-2", "invalid role"),
        (BranchOperation.REGENERATE, "user-2", None),
    ],
)
def test_branch_rejects_invalid_target_boundaries(operation, target, message):
    async def scenario():
        source, _ = _source_record()
        repository = _repository(source)

        with pytest.raises(SessionBranchConflictError):
            await repository.create_branch(
                source_session_id=source.id,
                user_id=source.user_id,
                target_event_id=target,
                operation=operation,
                request_id=f"request-{target}",
                message=message,
            )

    asyncio.run(scenario())


def test_branch_hides_missing_or_invisible_targets_as_not_found():
    async def scenario():
        source, _ = _source_record()
        repository = _repository(source)

        with pytest.raises(SessionBranchNotFoundError):
            await repository.create_branch(
                source_session_id=source.id,
                user_id=source.user_id,
                target_event_id="missing",
                operation=BranchOperation.FORK,
                request_id="request-missing-target",
            )

    asyncio.run(scenario())


def test_branch_rejects_non_completed_or_queued_sources():
    async def scenario(source):
        repository = _repository(source)
        with pytest.raises(SessionBranchConflictError):
            await repository.create_branch(
                source_session_id=source.id,
                user_id=source.user_id,
                target_event_id="assistant-2",
                operation=BranchOperation.FORK,
                request_id="request-conflict",
            )

    running, _ = _source_record(status=SessionStatus.RUNNING.value)
    queued, _ = _source_record(next_message=NextMessage(message="queued").model_dump(mode="json"))
    asyncio.run(scenario(running))
    asyncio.run(scenario(queued))


def test_branch_hides_not_found_and_rejects_inaccessible_attachments():
    async def not_found_scenario():
        repository = _repository(None)
        with pytest.raises(SessionBranchNotFoundError):
            await repository.create_branch(
                source_session_id="missing",
                user_id="user-1",
                target_event_id="assistant-2",
                operation=BranchOperation.FORK,
                request_id="request-missing",
            )

    async def attachment_scenario():
        source, _ = _source_record()
        repository = DBSessionRepository(
            _FakeDBSession(
                _Result(scalar=source),
                _Result(scalar=None),
                _Result(scalars=[]),
            )
        )
        with pytest.raises(SessionBranchConflictError):
            await repository.create_branch(
                source_session_id=source.id,
                user_id=source.user_id,
                target_event_id="assistant-2",
                operation=BranchOperation.FORK,
                request_id="request-attachment",
            )

    asyncio.run(not_found_scenario())
    asyncio.run(attachment_scenario())


def test_repeated_request_returns_same_branch_and_mismatched_request_conflicts():
    async def replay_scenario():
        source, _ = _source_record()
        existing = SessionModel(
            id="branch-1",
            user_id=source.user_id,
            title="Existing branch",
            unread_message_count=0,
            latest_message="second answer",
            events=[],
            files=[],
            memories={},
            context_seed=[],
            status=SessionStatus.COMPLETED.value,
            source_session_id=source.id,
            forked_from_event_id="assistant-2",
            branch_operation=BranchOperation.FORK.value,
            branch_request_id="same-request",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        fake = _FakeDBSession(_Result(scalar=source), _Result(scalar=existing))
        repository = DBSessionRepository(fake)

        branch = await repository.create_branch(
            source_session_id=source.id,
            user_id=source.user_id,
            target_event_id="assistant-2",
            operation=BranchOperation.FORK,
            request_id="same-request",
        )

        assert branch.id == existing.id
        assert fake.added == []

    async def conflict_scenario():
        source, _ = _source_record()
        existing = SessionModel(
            id="branch-2",
            user_id=source.user_id,
            title="Mismatched branch",
            unread_message_count=0,
            latest_message="",
            events=[],
            files=[],
            memories={},
            context_seed=[],
            status=SessionStatus.COMPLETED.value,
            source_session_id=source.id,
            forked_from_event_id="user-1",
            branch_operation=BranchOperation.FORK.value,
            branch_request_id="same-request",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        repository = DBSessionRepository(
            _FakeDBSession(_Result(scalar=source), _Result(scalar=existing))
        )

        with pytest.raises(SessionBranchConflictError):
            await repository.create_branch(
                source_session_id=source.id,
                user_id=source.user_id,
                target_event_id="assistant-2",
                operation=BranchOperation.FORK,
                request_id="same-request",
            )

    asyncio.run(replay_scenario())
    asyncio.run(conflict_scenario())


def test_unique_request_race_rereads_the_winning_branch():
    async def scenario():
        source, _ = _source_record()
        winner = SessionModel(
            id="branch-winner",
            user_id=source.user_id,
            title="Winning branch",
            unread_message_count=0,
            latest_message="second answer",
            events=[],
            files=[],
            memories={},
            context_seed=[],
            status=SessionStatus.COMPLETED.value,
            source_session_id=source.id,
            forked_from_event_id="assistant-2",
            branch_operation=BranchOperation.FORK.value,
            branch_request_id="racing-request",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        fake = _FakeDBSession(
            _Result(scalar=source),
            _Result(scalar=None),
            _Result(scalars=[FileModel.from_domain(_file())]),
            _Result(scalar=winner),
            flush_error=IntegrityError("insert", {}, RuntimeError("unique")),
        )
        repository = DBSessionRepository(fake)

        branch = await repository.create_branch(
            source_session_id=source.id,
            user_id=source.user_id,
            target_event_id="assistant-2",
            operation=BranchOperation.FORK,
            request_id="racing-request",
        )

        assert branch.id == winner.id

    asyncio.run(scenario())

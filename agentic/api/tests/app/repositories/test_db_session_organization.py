import asyncio
import json
from datetime import datetime

import pytest

from app.core.entities.event import (
    InteractionDecision,
    InteractionEvent,
    InteractionStatus,
    InteractionType,
    MessageEvent,
)
from app.core.entities.session import (
    InteractionConflictError,
    InteractionValidationError,
    NextMessage,
    Session,
    SessionOrganizationConflictError,
    SessionOrganizationNotFoundError,
    SessionStatus,
)
from app.models.session import SessionModel
from app.repositories.db_session_repository import DBSessionRepository


class _Result:
    def __init__(self, *, scalar=None, scalars=None, rowcount=0):
        self._scalar = scalar
        self._scalars = list(scalars or [])
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._scalars


class _FakeDBSession:
    def __init__(self, *results):
        self.results = list(results)
        self.statements = []
        self.flush_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)

    async def flush(self):
        self.flush_count += 1


def _record(
    *,
    session_id: str = "session-1",
    user_id: str = "user-1",
    status: str = SessionStatus.COMPLETED.value,
    next_message=None,
    title: str = "Generated title",
    title_is_manual: bool = False,
    is_pinned: bool = False,
    project_id: str | None = None,
    archived_at: datetime | None = None,
    latest_message_at: datetime | None = None,
    events=None,
    memories=None,
) -> SessionModel:
    now = datetime.now()
    return SessionModel(
        id=session_id,
        user_id=user_id,
        project_id=project_id,
        title=title,
        title_is_manual=title_is_manual,
        is_pinned=is_pinned,
        archived_at=archived_at,
        unread_message_count=0,
        latest_message="latest",
        latest_message_at=latest_message_at or now,
        events=events or [],
        files=[],
        memories=memories or {},
        context_seed=[],
        status=status,
        next_message=next_message,
        created_at=now,
        updated_at=now,
    )


def test_session_model_round_trips_organization_metadata():
    archived_at = datetime.now()
    session = Session(
        user_id="user-1",
        title="Manual title",
        project_id="project-1",
        title_is_manual=True,
        is_pinned=True,
        archived_at=archived_at,
    )

    record = SessionModel.from_domain(session)
    record.created_at = session.created_at
    record.updated_at = session.updated_at
    restored = record.to_domain()

    assert restored.title_is_manual is True
    assert restored.project_id == "project-1"
    assert restored.is_pinned is True
    assert restored.archived_at == archived_at


def test_active_and_archived_lists_use_distinct_filters_and_stable_ordering():
    async def scenario():
        active = _record(session_id="active", is_pinned=True)
        archived = _record(session_id="archived", archived_at=datetime.now())
        fake = _FakeDBSession(
            _Result(scalars=[active]),
            _Result(scalars=[archived]),
        )
        repository = DBSessionRepository(fake)

        active_result = await repository.get_all_by_user("user-1")
        archived_result = await repository.get_all_by_user("user-1", archived=True)

        active_sql = str(fake.statements[0].compile(compile_kwargs={"literal_binds": True}))
        archived_sql = str(fake.statements[1].compile(compile_kwargs={"literal_binds": True}))
        assert [session.id for session in active_result] == ["active"]
        assert [session.id for session in archived_result] == ["archived"]
        assert "sessions.archived_at IS NULL" in active_sql
        assert "sessions.is_pinned DESC" in active_sql
        assert "sessions.latest_message_at DESC NULLS LAST" in active_sql
        assert "sessions.created_at DESC" in active_sql
        assert "sessions.archived_at IS NOT NULL" in archived_sql
        assert "sessions.archived_at DESC" in archived_sql

    asyncio.run(scenario())


def test_manual_title_is_persisted_and_generated_updates_respect_the_lock():
    async def scenario():
        record = _record()
        fake = _FakeDBSession(
            _Result(scalar=record),
            _Result(rowcount=1),
            _Result(rowcount=0),
        )
        repository = DBSessionRepository(fake)

        updated = await repository.update_organization(
            "session-1",
            "user-1",
            title="My durable title",
        )
        generated_changed = await repository.update_generated_title(
            "session-1",
            "Agent replacement",
        )

        generated_sql = str(
            fake.statements[2].compile(compile_kwargs={"literal_binds": True})
        )
        assert updated.title == "My durable title"
        assert updated.title_is_manual is True
        assert generated_changed is False
        assert "sessions.title_is_manual IS false" in generated_sql

    asyncio.run(scenario())


def test_archive_clears_pin_and_repeated_archive_keeps_original_timestamp():
    async def scenario():
        record = _record(is_pinned=True)
        repository = DBSessionRepository(
            _FakeDBSession(
                _Result(scalar=record),
                _Result(rowcount=1),
                _Result(scalar=record),
                _Result(rowcount=1),
            )
        )

        archived = await repository.update_organization(
            "session-1",
            "user-1",
            archived=True,
        )
        first_archived_at = archived.archived_at
        replay = await repository.update_organization(
            "session-1",
            "user-1",
            archived=True,
        )

        assert first_archived_at is not None
        assert replay.archived_at == first_archived_at
        assert replay.is_pinned is False

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "next_message"),
    [
        (SessionStatus.RUNNING.value, None),
        (SessionStatus.WAITING.value, None),
        (
            SessionStatus.COMPLETED.value,
            NextMessage(message="queued").model_dump(mode="json"),
        ),
    ],
)
def test_archive_rejects_active_or_queued_sessions(status, next_message):
    async def scenario():
        record = _record(status=status, next_message=next_message)
        repository = DBSessionRepository(_FakeDBSession(_Result(scalar=record)))

        with pytest.raises(SessionOrganizationConflictError):
            await repository.update_organization(
                "session-1",
                "user-1",
                archived=True,
            )
        assert record.archived_at is None

    asyncio.run(scenario())


def test_archived_session_cannot_be_pinned_but_restore_is_idempotent():
    async def scenario():
        record = _record(archived_at=datetime.now())
        repository = DBSessionRepository(
            _FakeDBSession(
                _Result(scalar=record),
                _Result(scalar=record),
                _Result(rowcount=1),
                _Result(scalar=record),
                _Result(rowcount=1),
            )
        )

        with pytest.raises(SessionOrganizationConflictError):
            await repository.update_organization(
                "session-1",
                "user-1",
                pinned=True,
            )
        restored = await repository.update_organization(
            "session-1",
            "user-1",
            archived=False,
        )
        replay = await repository.update_organization(
            "session-1",
            "user-1",
            archived=False,
        )

        assert restored.archived_at is None
        assert replay.archived_at is None

    asyncio.run(scenario())


def test_organization_update_hides_missing_or_cross_user_sessions():
    async def scenario():
        repository = DBSessionRepository(_FakeDBSession(_Result(scalar=None)))

        with pytest.raises(SessionOrganizationNotFoundError):
            await repository.update_organization(
                "session-1",
                "other-user",
                pinned=True,
            )

    asyncio.run(scenario())


def test_execution_claim_serializes_new_runs_with_archiving():
    async def scenario():
        record = _record(status=SessionStatus.COMPLETED.value)
        repository = DBSessionRepository(
            _FakeDBSession(
                _Result(scalar=record),
                _Result(scalar=record),
            )
        )

        claimed, previous_status = await repository.claim_execution(
            "session-1",
            "user-1",
        )

        assert previous_status == SessionStatus.COMPLETED
        assert claimed.status == SessionStatus.RUNNING
        with pytest.raises(SessionOrganizationConflictError):
            await repository.update_organization(
                "session-1",
                "user-1",
                archived=True,
            )

    asyncio.run(scenario())


def test_execution_claim_retires_legacy_approval_and_repairs_memory():
    async def scenario():
        pending = InteractionEvent(
            action_id="legacy-action",
            interaction_type=InteractionType.TOOL_APPROVAL,
            status=InteractionStatus.PENDING,
            tool_call_id="call-1",
            tool_name="shell",
            function_name="shell_execute",
            function_args={"command": "private command"},
            prompt="legacy approval",
        )
        record = _record(
            status=SessionStatus.WAITING.value,
            events=[pending.model_dump(mode="json")],
            memories={
                "react": {
                    "messages": [
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "shell_execute",
                                        "arguments": '{"command":"private command"}',
                                    },
                                }
                            ],
                        }
                    ]
                }
            },
        )
        fake = _FakeDBSession(_Result(scalar=record), _Result(scalar=record))
        repository = DBSessionRepository(fake)

        claimed, previous_status = await repository.claim_execution(
            "session-1",
            "user-1",
        )
        replay, replay_previous_status = await repository.claim_execution(
            "session-1",
            "user-1",
        )

        assert previous_status == SessionStatus.COMPLETED
        assert claimed.status == SessionStatus.RUNNING
        assert replay_previous_status is None
        assert replay.status == SessionStatus.RUNNING
        resolved = InteractionEvent.model_validate(record.events[-1])
        assert resolved.status == InteractionStatus.RESOLVED
        assert resolved.decision == InteractionDecision.REJECT
        tool_message = record.memories["react"]["messages"][-1]
        assert tool_message["role"] == "tool"
        assert tool_message["tool_call_id"] == "call-1"
        result = json.loads(tool_message["content"])
        assert result["success"] is False
        assert "private command" not in tool_message["content"]
        assert len(record.events) == 2
        assert len(record.memories["react"]["messages"]) == 2

    asyncio.run(scenario())


def test_user_input_claim_resolves_pending_text_question_atomically():
    async def scenario():
        pending = InteractionEvent(
            action_id="ask-action",
            interaction_type=InteractionType.ASK_USER,
            status=InteractionStatus.PENDING,
            tool_call_id="call-ask",
            tool_name="message",
            function_name="message_ask_user",
            function_args={"text": "Which city?", "allow_text": True},
            prompt="Which city?",
            allow_text=True,
        )
        record = _record(
            status=SessionStatus.WAITING.value,
            events=[pending.model_dump(mode="json")],
        )
        fake = _FakeDBSession(
            _Result(scalar=record),
            _Result(scalar=record),
            _Result(scalar=record),
        )
        repository = DBSessionRepository(fake)

        claimed, previous_status, resolved = (
            await repository.claim_execution_for_user_input(
                "session-1",
                "user-1",
                answer="Shanghai",
            )
        )
        with pytest.raises(InteractionConflictError, match="正在继续处理"):
            await repository.claim_execution_for_user_input(
                "session-1",
                "user-1",
                answer="Shanghai",
            )
        record.events.append(
            MessageEvent(
                role="user",
                message="Shanghai",
            ).model_dump(mode="json")
        )
        with pytest.raises(InteractionConflictError, match="正在继续处理"):
            await repository.claim_execution_for_user_input(
                "session-1",
                "user-1",
                answer="Shanghai",
            )

        assert previous_status == SessionStatus.WAITING
        assert claimed.status == SessionStatus.RUNNING
        assert resolved is not None
        assert resolved.action_id == pending.action_id
        assert resolved.status == InteractionStatus.RESOLVED
        assert resolved.decision == InteractionDecision.ANSWER
        assert resolved.answer == "Shanghai"
        assert InteractionEvent.model_validate(record.events[-2]) == resolved
        assert len(record.events) == 3
        assert fake.flush_count == 1

    asyncio.run(scenario())


def test_user_input_claim_rejects_text_for_options_only_question_without_mutation():
    async def scenario():
        pending = InteractionEvent(
            action_id="ask-action",
            interaction_type=InteractionType.ASK_USER,
            status=InteractionStatus.PENDING,
            tool_call_id="call-ask",
            tool_name="message",
            function_name="message_ask_user",
            function_args={"text": "Choose", "allow_text": False},
            prompt="Choose",
            allow_text=False,
        )
        record = _record(
            status=SessionStatus.WAITING.value,
            events=[pending.model_dump(mode="json")],
        )
        fake = _FakeDBSession(_Result(scalar=record))
        repository = DBSessionRepository(fake)

        with pytest.raises(InteractionValidationError):
            await repository.claim_execution_for_user_input(
                "session-1",
                "user-1",
                answer="typed answer",
            )

        assert record.status == SessionStatus.WAITING.value
        assert record.events == [pending.model_dump(mode="json")]
        assert fake.flush_count == 0

    asyncio.run(scenario())


def test_explicit_interaction_resolution_claims_continuation_atomically():
    async def scenario():
        pending = InteractionEvent(
            action_id="ask-action",
            interaction_type=InteractionType.ASK_USER,
            status=InteractionStatus.PENDING,
            tool_call_id="call-ask",
            tool_name="message",
            function_name="message_ask_user",
            function_args={"text": "Choose", "allow_text": False},
            prompt="Choose",
            options=[{"value": "staging", "label": "Staging"}],
            allow_text=False,
        )
        record = _record(
            status=SessionStatus.WAITING.value,
            events=[pending.model_dump(mode="json")],
        )
        repository = DBSessionRepository(_FakeDBSession(_Result(scalar=record)))

        resolved = await repository.resolve_interaction(
            "session-1",
            "user-1",
            action_id=pending.action_id,
            decision=InteractionDecision.ANSWER,
            selected_values=["staging"],
        )

        assert resolved.status == InteractionStatus.RESOLVED
        assert record.status == SessionStatus.RUNNING.value
        assert InteractionEvent.model_validate(record.events[-1]) == resolved

    asyncio.run(scenario())


def test_runtime_handle_patch_does_not_write_organization_metadata():
    async def scenario():
        fake = _FakeDBSession(_Result(rowcount=1))
        repository = DBSessionRepository(fake)

        await repository.update_runtime_handles(
            "session-1",
            sandbox_id="sandbox-1",
            task_id="task-1",
        )

        compiled = str(
            fake.statements[0].compile(compile_kwargs={"literal_binds": True})
        )
        assert "sandbox_id" in compiled
        assert "task_id" in compiled
        assert "title_is_manual" not in compiled
        assert "is_pinned" not in compiled
        assert "archived_at" not in compiled

    asyncio.run(scenario())


def test_organization_patch_explicitly_preserves_business_updated_at():
    async def scenario():
        record = _record()
        original_updated_at = record.updated_at
        fake = _FakeDBSession(
            _Result(scalar=record),
            _Result(rowcount=1),
        )
        repository = DBSessionRepository(fake)

        updated = await repository.update_organization(
            "session-1",
            "user-1",
            pinned=True,
        )

        statement = str(
            fake.statements[1].compile(compile_kwargs={"literal_binds": True})
        )
        assert statement.startswith("UPDATE sessions")
        assert "updated_at=" in statement
        assert updated.updated_at == original_updated_at

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "next_message", "archived"),
    [
        (SessionStatus.RUNNING.value, None, False),
        (SessionStatus.WAITING.value, None, False),
        (
            SessionStatus.COMPLETED.value,
            NextMessage(message="queued").model_dump(mode="json"),
            False,
        ),
        (SessionStatus.COMPLETED.value, None, True),
    ],
)
def test_project_move_preserves_runtime_content_and_archive_state(
    status,
    next_message,
    archived,
):
    async def scenario():
        archived_at = datetime.now() if archived else None
        record = _record(
            status=status,
            next_message=next_message,
            project_id="project-old",
            archived_at=archived_at,
            is_pinned=not archived,
        )
        record.unread_message_count = 3
        event = MessageEvent(
            id="event-1",
            role="user",
            message="keep me",
        )
        record.events = [event.model_dump(mode="json")]
        original = {
            "updated_at": record.updated_at,
            "latest_message": record.latest_message,
            "latest_message_at": record.latest_message_at,
            "status": record.status,
            "unread_message_count": record.unread_message_count,
            "is_pinned": record.is_pinned,
            "events": [event],
            "next_message": (
                NextMessage.model_validate(record.next_message)
                if record.next_message is not None
                else None
            ),
            "archived_at": record.archived_at,
        }
        fake = _FakeDBSession(
            _Result(scalar=record),
            _Result(rowcount=1),
        )
        repository = DBSessionRepository(fake)

        moved = await repository.update_organization(
            "session-1",
            "user-1",
            project_id="project-new",
            project_id_provided=True,
        )

        statement = str(
            fake.statements[1].compile(compile_kwargs={"literal_binds": True})
        )
        assert moved.project_id == "project-new"
        assert "project_id=" in statement
        for field_name, value in original.items():
            assert getattr(moved, field_name) == value

    asyncio.run(scenario())


def test_explicit_null_unassigns_project_but_omission_keeps_it():
    async def scenario():
        assigned = _record(project_id="project-1")
        fake = _FakeDBSession(
            _Result(scalar=assigned),
            _Result(rowcount=1),
            _Result(scalar=assigned),
        )
        repository = DBSessionRepository(fake)

        unassigned = await repository.update_organization(
            "session-1",
            "user-1",
            project_id=None,
            project_id_provided=True,
        )
        unchanged = await repository.update_organization(
            "session-1",
            "user-1",
        )

        assert unassigned.project_id is None
        assert unchanged.project_id is None
        assert len(fake.statements) == 3

    asyncio.run(scenario())

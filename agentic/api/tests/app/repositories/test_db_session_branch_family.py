import asyncio
from datetime import datetime, timedelta

import pytest

from app.core.entities.event import MessageEvent
from app.core.entities.session import (
    BranchOperation,
    SessionBranchConflictError,
    SessionBranchFamilyValidationError,
    SessionBranchNotFoundError,
    SessionStatus,
)
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
    def __init__(self, *results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)


_CREATED_AT = datetime(2026, 7, 25, 9, 0, 0)


def _messages():
    return [
        MessageEvent(id="user-1", role="user", message="question").model_dump(
            mode="json"
        ),
        MessageEvent(
            id="hidden-1",
            role="assistant",
            message="private",
            visible=False,
        ).model_dump(mode="json"),
        MessageEvent(
            id="assistant-1",
            role="assistant",
            message="answer",
        ).model_dump(mode="json"),
    ]


def _record(
    session_id: str,
    *,
    user_id: str = "user-1",
    source_session_id: str | None = None,
    target_event_id: str | None = None,
    operation: BranchOperation | None = None,
    created_at: datetime = _CREATED_AT,
    archived_at: datetime | None = None,
) -> SessionModel:
    return SessionModel(
        id=session_id,
        user_id=user_id,
        title=session_id,
        title_is_manual=False,
        is_pinned=False,
        unread_message_count=0,
        latest_message="answer",
        events=_messages(),
        files=[],
        memories={},
        context_seed=[],
        status=SessionStatus.COMPLETED.value,
        source_session_id=source_session_id,
        forked_from_event_id=target_event_id,
        branch_operation=operation.value if operation is not None else None,
        branch_request_id=(
            f"request-{session_id}" if source_session_id is not None else None
        ),
        archived_at=archived_at,
        created_at=created_at,
        updated_at=created_at,
    )


def test_source_entry_returns_source_then_stably_sorted_direct_children():
    async def scenario():
        source = _record("source")
        later = _record(
            "branch-z",
            source_session_id=source.id,
            target_event_id="assistant-1",
            operation=BranchOperation.REGENERATE,
            created_at=_CREATED_AT + timedelta(minutes=1),
        )
        same_time_b = _record(
            "branch-b",
            source_session_id=source.id,
            target_event_id="assistant-1",
            operation=BranchOperation.FORK,
        )
        same_time_a = _record(
            "branch-a",
            source_session_id=source.id,
            target_event_id="assistant-1",
            operation=BranchOperation.EDIT,
        )
        fake = _FakeDBSession(
            _Result(scalar=source),
            _Result(scalars=[later, same_time_b, same_time_a]),
        )

        family = await DBSessionRepository(fake).get_branch_family(
            session_id=source.id,
            user_id=source.user_id,
            target_event_id="assistant-1",
        )

        assert family.source_session is not None
        assert family.source_session.id == source.id
        assert family.current_session.id == source.id
        assert family.target_event_id == "assistant-1"
        assert [item.id for item in family.variants] == [
            "source",
            "branch-a",
            "branch-b",
            "branch-z",
        ]
        child_query = str(fake.statements[1])
        assert "sessions.user_id" in child_query
        assert "sessions.source_session_id" in child_query
        assert "sessions.forked_from_event_id" in child_query
        assert "sessions.created_at ASC" in child_query
        assert "sessions.id ASC" in child_query

    asyncio.run(scenario())


def test_child_entry_derives_family_and_includes_archived_siblings():
    async def scenario():
        source = _record("source")
        current = _record(
            "branch-current",
            source_session_id=source.id,
            target_event_id="user-1",
            operation=BranchOperation.EDIT,
        )
        archived = _record(
            "branch-archived",
            source_session_id=source.id,
            target_event_id="user-1",
            operation=BranchOperation.FORK,
            archived_at=_CREATED_AT + timedelta(days=1),
        )
        fake = _FakeDBSession(
            _Result(scalar=current),
            _Result(scalar=source),
            _Result(scalars=[current, archived]),
        )

        family = await DBSessionRepository(fake).get_branch_family(
            session_id=current.id,
            user_id=current.user_id,
        )

        assert family.source_session is not None
        assert family.source_session.id == source.id
        assert family.current_session.id == current.id
        assert family.target_event_id == "user-1"
        assert [item.id for item in family.variants] == [
            "source",
            "branch-archived",
            "branch-current",
        ]
        assert family.variants[1].archived_at is not None

    asyncio.run(scenario())


def test_child_entry_rejects_an_explicit_mismatched_anchor():
    async def scenario():
        current = _record(
            "branch-current",
            source_session_id="source",
            target_event_id="assistant-1",
            operation=BranchOperation.REGENERATE,
        )
        repository = DBSessionRepository(
            _FakeDBSession(_Result(scalar=current))
        )

        with pytest.raises(SessionBranchConflictError, match="锚点"):
            await repository.get_branch_family(
                session_id=current.id,
                user_id=current.user_id,
                target_event_id="other-anchor",
            )

    asyncio.run(scenario())


def test_branch_can_be_the_explicit_source_of_its_own_direct_family():
    async def scenario():
        current_source = _record(
            "branch-parent",
            source_session_id="root",
            target_event_id="root-event",
            operation=BranchOperation.FORK,
        )
        child = _record(
            "branch-child",
            source_session_id=current_source.id,
            target_event_id="assistant-1",
            operation=BranchOperation.REGENERATE,
        )
        fake = _FakeDBSession(
            _Result(scalar=current_source),
            _Result(scalars=[child]),
        )

        family = await DBSessionRepository(fake).get_branch_family(
            session_id=current_source.id,
            user_id=current_source.user_id,
            target_event_id="assistant-1",
        )

        assert family.source_session is not None
        assert family.source_session.id == current_source.id
        assert family.current_session.id == current_source.id
        assert family.target_event_id == "assistant-1"
        assert [item.id for item in family.variants] == [
            "branch-parent",
            "branch-child",
        ]

    asyncio.run(scenario())


def test_source_entry_requires_a_target_event_id():
    async def scenario():
        source = _record("source")
        repository = DBSessionRepository(
            _FakeDBSession(_Result(scalar=source))
        )

        with pytest.raises(SessionBranchFamilyValidationError, match="目标消息"):
            await repository.get_branch_family(
                session_id=source.id,
                user_id=source.user_id,
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("target_event_id", ["missing", "hidden-1"])
def test_source_entry_hides_missing_or_invisible_target_events(target_event_id):
    async def scenario():
        source = _record("source")
        repository = DBSessionRepository(
            _FakeDBSession(_Result(scalar=source))
        )

        with pytest.raises(SessionBranchNotFoundError, match="目标消息"):
            await repository.get_branch_family(
                session_id=source.id,
                user_id=source.user_id,
                target_event_id=target_event_id,
            )

    asyncio.run(scenario())


def test_deleted_or_inaccessible_source_does_not_block_owned_siblings():
    async def scenario():
        current = _record(
            "branch-current",
            source_session_id="deleted-source",
            target_event_id="assistant-1",
            operation=BranchOperation.REGENERATE,
        )
        sibling = _record(
            "branch-sibling",
            source_session_id="deleted-source",
            target_event_id="assistant-1",
            operation=BranchOperation.FORK,
            created_at=_CREATED_AT + timedelta(minutes=1),
        )
        fake = _FakeDBSession(
            _Result(scalar=current),
            _Result(scalar=None),
            _Result(scalars=[current, sibling]),
        )

        family = await DBSessionRepository(fake).get_branch_family(
            session_id=current.id,
            user_id=current.user_id,
        )

        assert family.source_session is None
        assert family.current_session.id == current.id
        assert [item.id for item in family.variants] == [
            "branch-current",
            "branch-sibling",
        ]
        source_query = str(fake.statements[1])
        child_query = str(fake.statements[2])
        assert "sessions.user_id" in source_query
        assert "sessions.user_id" in child_query
        assert "sessions.source_session_id" in child_query
        assert "sessions.forked_from_event_id" in child_query

    asyncio.run(scenario())


def test_nested_branch_uses_its_direct_source_instead_of_the_global_root():
    async def scenario():
        direct_source = _record(
            "branch-parent",
            source_session_id="root",
            target_event_id="user-1",
            operation=BranchOperation.EDIT,
        )
        current = _record(
            "branch-child",
            source_session_id=direct_source.id,
            target_event_id="assistant-1",
            operation=BranchOperation.REGENERATE,
        )
        fake = _FakeDBSession(
            _Result(scalar=current),
            _Result(scalar=direct_source),
            _Result(scalars=[current]),
        )

        family = await DBSessionRepository(fake).get_branch_family(
            session_id=current.id,
            user_id=current.user_id,
        )

        assert family.source_session is not None
        assert family.source_session.id == direct_source.id
        assert family.target_event_id == "assistant-1"
        assert [item.id for item in family.variants] == [
            "branch-parent",
            "branch-child",
        ]

    asyncio.run(scenario())


def test_current_session_must_remain_in_the_computed_family():
    async def scenario():
        current = _record(
            "branch-current",
            source_session_id="source",
            target_event_id="assistant-1",
            operation=BranchOperation.REGENERATE,
        )
        repository = DBSessionRepository(
            _FakeDBSession(
                _Result(scalar=current),
                _Result(scalar=None),
                _Result(scalars=[]),
            )
        )

        with pytest.raises(SessionBranchConflictError, match="当前会话"):
            await repository.get_branch_family(
                session_id=current.id,
                user_id=current.user_id,
            )

    asyncio.run(scenario())


def test_current_session_lookup_is_user_scoped():
    async def scenario():
        repository = DBSessionRepository(
            _FakeDBSession(_Result(scalar=None))
        )

        with pytest.raises(SessionBranchNotFoundError, match="无权"):
            await repository.get_branch_family(
                session_id="someone-elses-session",
                user_id="user-1",
                target_event_id="assistant-1",
            )

        current_query = str(repository.db_session.statements[0])
        assert "sessions.id" in current_query
        assert "sessions.user_id" in current_query

    asyncio.run(scenario())

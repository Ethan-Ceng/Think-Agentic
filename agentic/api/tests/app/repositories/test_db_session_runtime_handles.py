from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from app.core.entities.session import SessionStatus
from app.models.session import SessionModel
from app.repositories.db_session_repository import DBSessionRepository


class _Result:
    def __init__(self, *, scalar=None, rowcount=0):
        self._scalar = scalar
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDBSession:
    def __init__(self, *results: _Result) -> None:
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)


def _record(*, sandbox_id: str | None) -> SessionModel:
    now = datetime.now()
    return SessionModel(
        id="session-1",
        user_id="user-1",
        title="Session",
        title_is_manual=False,
        is_pinned=False,
        unread_message_count=0,
        latest_message="",
        events=[],
        files=[],
        memories={},
        context_seed=[],
        status=SessionStatus.RUNNING.value,
        sandbox_id=sandbox_id,
        created_at=now,
        updated_at=now,
    )


def test_claim_sandbox_id_atomically_sets_candidate_for_expected_handle() -> None:
    async def scenario() -> None:
        fake = _FakeDBSession(_Result(scalar="sandbox-new", rowcount=1))
        repository = DBSessionRepository(fake)

        winner = await repository.claim_sandbox_id(
            "session-1",
            "sandbox-new",
            expected_sandbox_id=None,
        )

        statement = str(
            fake.statements[0].compile(compile_kwargs={"literal_binds": True})
        )
        assert winner == "sandbox-new"
        assert statement.startswith("UPDATE sessions")
        assert "sessions.sandbox_id IS NULL" in statement
        assert "RETURNING sessions.sandbox_id" in statement

    asyncio.run(scenario())


def test_claim_sandbox_id_returns_concurrent_winner() -> None:
    async def scenario() -> None:
        fake = _FakeDBSession(
            _Result(scalar=None, rowcount=0),
            _Result(scalar=_record(sandbox_id="sandbox-winner")),
        )
        repository = DBSessionRepository(fake)

        winner = await repository.claim_sandbox_id(
            "session-1",
            "sandbox-loser",
            expected_sandbox_id=None,
        )

        assert winner == "sandbox-winner"
        assert len(fake.statements) == 2

    asyncio.run(scenario())


def test_claim_sandbox_id_fails_when_session_was_deleted() -> None:
    async def scenario() -> None:
        fake = _FakeDBSession(
            _Result(scalar=None, rowcount=0),
            _Result(scalar=None),
        )
        repository = DBSessionRepository(fake)

        with pytest.raises(ValueError, match="不存在"):
            await repository.claim_sandbox_id(
                "session-1",
                "sandbox-orphan",
                expected_sandbox_id=None,
            )

    asyncio.run(scenario())

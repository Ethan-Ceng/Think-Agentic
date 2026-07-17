import asyncio

import pytest

from app.repositories.db_uow import DBUnitOfWork


class FailingCommitSession:
    def __init__(self) -> None:
        self.rollback_called = False
        self.close_called = False

    async def commit(self) -> None:
        raise RuntimeError("commit failed")

    async def rollback(self) -> None:
        self.rollback_called = True

    async def close(self) -> None:
        self.close_called = True


def test_uow_propagates_commit_failure_after_rollback_and_close() -> None:
    session = FailingCommitSession()
    uow = DBUnitOfWork(session_factory=lambda: session)  # type: ignore[arg-type]

    async def run() -> None:
        await uow.__aenter__()
        with pytest.raises(RuntimeError, match="commit failed"):
            await uow.__aexit__(None, None, None)

    asyncio.run(run())
    assert session.rollback_called
    assert session.close_called

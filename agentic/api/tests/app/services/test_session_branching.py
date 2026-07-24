import asyncio

import pytest

from app.core.entities.session import (
    BranchOperation,
    Session,
    SessionBranchConflictError,
    SessionBranchNotFoundError,
    SessionStatus,
)
from app.schemas.exceptions import ConflictError, NotFoundError
from app.services.session_service import SessionService


class _SessionRepository:
    def __init__(self, *, result=None, error=None, source=None) -> None:
        self.result = result
        self.error = error
        self.source = source
        self.calls = []

    async def create_branch(self, **kwargs):
        self.calls.append(("create_branch", kwargs))
        if self.error is not None:
            raise self.error
        return self.result

    async def get_by_id_for_user(self, session_id: str, user_id: str):
        self.calls.append(("get_by_id_for_user", session_id, user_id))
        if (
            self.source is not None
            and self.source.id == session_id
            and self.source.user_id == user_id
        ):
            return self.source
        return None


class _Uow:
    def __init__(self, repository: _SessionRepository) -> None:
        self.session = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def _service(repository: _SessionRepository) -> SessionService:
    return SessionService(lambda: _Uow(repository), sandbox_cls=object())


def test_create_branch_passes_owned_request_and_returns_domain_result():
    branch = Session(
        id="branch-1",
        user_id="user-1",
        source_session_id="source-1",
        forked_from_event_id="event-1",
        branch_operation=BranchOperation.EDIT,
        status=SessionStatus.COMPLETED,
    )
    repository = _SessionRepository(result=branch)
    service = _service(repository)

    result = asyncio.run(
        service.create_branch(
            source_session_id="source-1",
            user_id="user-1",
            target_event_id="event-1",
            operation=BranchOperation.EDIT,
            request_id="request-1",
            message="revised",
        )
    )

    assert result is branch
    assert repository.calls == [
        (
            "create_branch",
            {
                "source_session_id": "source-1",
                "user_id": "user-1",
                "target_event_id": "event-1",
                "operation": BranchOperation.EDIT,
                "request_id": "request-1",
                "message": "revised",
            },
        )
    ]


@pytest.mark.parametrize(
    ("repository_error", "service_error"),
    [
        (SessionBranchNotFoundError("hidden"), NotFoundError),
        (SessionBranchConflictError("state changed"), ConflictError),
    ],
)
def test_create_branch_maps_repository_errors(repository_error, service_error):
    service = _service(_SessionRepository(error=repository_error))

    with pytest.raises(service_error):
        asyncio.run(
            service.create_branch(
                source_session_id="source-1",
                user_id="user-1",
                target_event_id="event-1",
                operation=BranchOperation.FORK,
                request_id="request-1",
            )
        )


def test_source_lineage_is_only_navigable_for_the_current_owner():
    owned_source = Session(id="source-1", user_id="user-1", title="Owned source")
    repository = _SessionRepository(source=owned_source)
    service = _service(repository)

    found = asyncio.run(
        service.get_branch_source("source-1", "user-1")
    )
    hidden = asyncio.run(
        service.get_branch_source("source-1", "user-2")
    )

    assert found is owned_source
    assert hidden is None

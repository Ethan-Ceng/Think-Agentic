import asyncio
from datetime import datetime

import pytest

from app.core.entities.session import (
    Session,
    SessionOrganizationConflictError,
    SessionOrganizationNotFoundError,
)
from app.schemas.exceptions import ConflictError, NotFoundError
from app.services.session_service import SessionService


class _SessionRepository:
    def __init__(self, *, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = []

    async def update_organization(self, *args, **kwargs):
        self.calls.append(("update_organization", args, kwargs))
        if self.error is not None:
            raise self.error
        return self.result

    async def get_by_id_for_user(self, *args):
        self.calls.append(("get_by_id_for_user", args, {}))
        return self.result


class _Uow:
    def __init__(self, repository: _SessionRepository) -> None:
        self.session = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def _service(repository: _SessionRepository) -> SessionService:
    return SessionService(lambda: _Uow(repository), sandbox_cls=object())


def test_update_organization_passes_owned_patch_and_returns_session():
    archived_at = datetime.now()
    result = Session(
        id="session-1",
        user_id="user-1",
        title="Manual",
        title_is_manual=True,
        archived_at=archived_at,
    )
    repository = _SessionRepository(result=result)

    updated = asyncio.run(
        _service(repository).update_organization(
            session_id="session-1",
            user_id="user-1",
            title="Manual",
            pinned=None,
            archived=True,
        )
    )

    assert updated is result
    assert repository.calls == [
        (
            "update_organization",
            ("session-1", "user-1"),
            {"title": "Manual", "pinned": None, "archived": True},
        )
    ]


@pytest.mark.parametrize(
    ("repository_error", "service_error"),
    [
        (SessionOrganizationNotFoundError("hidden"), NotFoundError),
        (SessionOrganizationConflictError("busy"), ConflictError),
    ],
)
def test_update_organization_maps_repository_errors(repository_error, service_error):
    service = _service(_SessionRepository(error=repository_error))

    with pytest.raises(service_error):
        asyncio.run(
            service.update_organization(
                session_id="session-1",
                user_id="user-1",
                pinned=True,
            )
        )


def test_ensure_session_active_rejects_missing_or_archived_sessions():
    missing = _service(_SessionRepository(result=None))
    with pytest.raises(NotFoundError):
        asyncio.run(missing.ensure_session_active("missing", "user-1"))

    archived = _service(
        _SessionRepository(
            result=Session(
                id="session-1",
                user_id="user-1",
                archived_at=datetime.now(),
            )
        )
    )
    with pytest.raises(ConflictError) as exc_info:
        asyncio.run(archived.ensure_session_active("session-1", "user-1"))
    assert "先恢复" in exc_info.value.msg

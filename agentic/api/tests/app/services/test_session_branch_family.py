import asyncio
import logging
from datetime import datetime, timedelta

import pytest

from app.core.entities.session import (
    BranchOperation,
    Session,
    SessionBranchConflictError,
    SessionBranchFamilyValidationError,
    SessionBranchNotFoundError,
    SessionStatus,
)
from app.repositories.session_repository import SessionBranchFamily
from app.schemas.exceptions import ConflictError, NotFoundError, ValidationError
from app.services.session_service import SessionService


_CREATED_AT = datetime(2026, 7, 25, 10, 0, 0)


class _SessionRepository:
    def __init__(self, *, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = []

    async def get_branch_family(self, **kwargs):
        self.calls.append(("get_branch_family", kwargs))
        if self.error is not None:
            raise self.error
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


def _session(
    session_id: str,
    *,
    source_session_id: str | None = None,
    operation: BranchOperation | None = None,
    archived_at: datetime | None = None,
    created_at: datetime = _CREATED_AT,
) -> Session:
    return Session(
        id=session_id,
        user_id="user-1",
        title=f"Title {session_id}",
        status=SessionStatus.COMPLETED,
        source_session_id=source_session_id,
        forked_from_event_id=(
            "event-1" if source_session_id is not None else None
        ),
        branch_operation=operation,
        archived_at=archived_at,
        created_at=created_at,
        updated_at=created_at,
    )


def test_branch_family_projects_only_lightweight_navigation_metadata(caplog):
    source = _session("source")
    current = _session(
        "branch-current",
        source_session_id=source.id,
        operation=BranchOperation.EDIT,
    )
    archived = _session(
        "branch-archived",
        source_session_id=source.id,
        operation=BranchOperation.REGENERATE,
        archived_at=_CREATED_AT + timedelta(days=1),
        created_at=_CREATED_AT + timedelta(minutes=1),
    )
    repository = _SessionRepository(
        result=SessionBranchFamily(
            source_session=source,
            target_event_id="event-1",
            current_session=current,
            variants=(source, current, archived),
        )
    )

    with caplog.at_level(logging.INFO, logger="app.services.session_service"):
        response = asyncio.run(
            _service(repository).get_branch_family(
                session_id=current.id,
                user_id="user-1",
                target_event_id=" event-1 ",
            )
        )

    assert response.source_session_id == source.id
    assert response.current_session_id == current.id
    assert response.target_event_id == "event-1"
    assert [item.operation for item in response.variants] == [
        "original",
        "edit",
        "regenerate",
    ]
    assert [item.is_current for item in response.variants] == [
        False,
        True,
        False,
    ]
    assert response.variants[2].archived_at is not None
    assert set(response.variants[0].model_dump()) == {
        "session_id",
        "title",
        "operation",
        "status",
        "archived_at",
        "created_at",
        "is_current",
    }
    assert repository.calls == [
        (
            "get_branch_family",
            {
                "session_id": current.id,
                "user_id": "user-1",
                "target_event_id": "event-1",
            },
        )
    ]
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "branch_family_loaded"
    )
    assert record.user_id == "user-1"
    assert record.current_session_id == current.id
    assert record.source_session_id == source.id
    assert record.target_event_id == "event-1"
    assert record.variant_count == 3
    assert not hasattr(record, "title")
    assert not hasattr(record, "message_body")


def test_branch_family_does_not_disclose_an_unavailable_source():
    current = _session(
        "branch-current",
        source_session_id="hidden-source",
        operation=BranchOperation.FORK,
    )
    sibling = _session(
        "branch-sibling",
        source_session_id="hidden-source",
        operation=BranchOperation.REGENERATE,
    )
    repository = _SessionRepository(
        result=SessionBranchFamily(
            source_session=None,
            target_event_id="event-1",
            current_session=current,
            variants=(current, sibling),
        )
    )

    response = asyncio.run(
        _service(repository).get_branch_family(
            session_id=current.id,
            user_id="user-1",
        )
    )

    assert response.source_session_id is None
    assert [item.session_id for item in response.variants] == [
        current.id,
        sibling.id,
    ]
    assert all(item.operation != "original" for item in response.variants)


@pytest.mark.parametrize(
    ("repository_error", "service_error", "message"),
    [
        (
            SessionBranchNotFoundError("hidden"),
            NotFoundError,
            "会话或目标消息不存在",
        ),
        (
            SessionBranchConflictError("anchor changed"),
            ConflictError,
            "anchor changed",
        ),
        (
            SessionBranchFamilyValidationError("target required"),
            ValidationError,
            "target required",
        ),
    ],
)
def test_branch_family_maps_repository_errors(
    repository_error,
    service_error,
    message,
):
    service = _service(_SessionRepository(error=repository_error))

    with pytest.raises(service_error) as raised:
        asyncio.run(
            service.get_branch_family(
                session_id="session-1",
                user_id="user-1",
            )
        )

    assert raised.value.msg == message


@pytest.mark.parametrize("target_event_id", ["", "   ", "x" * 256])
def test_branch_family_rejects_invalid_explicit_target_before_repository(
    target_event_id,
):
    repository = _SessionRepository()

    with pytest.raises(ValidationError):
        asyncio.run(
            _service(repository).get_branch_family(
                session_id="session-1",
                user_id="user-1",
                target_event_id=target_event_id,
            )
        )

    assert repository.calls == []


def test_branch_family_rejects_a_variant_without_an_operation():
    current = _session(
        "branch-current",
        source_session_id="hidden-source",
        operation=None,
    )
    repository = _SessionRepository(
        result=SessionBranchFamily(
            source_session=None,
            target_event_id="event-1",
            current_session=current,
            variants=(current,),
        )
    )

    with pytest.raises(ConflictError) as raised:
        asyncio.run(
            _service(repository).get_branch_family(
                session_id=current.id,
                user_id="user-1",
            )
        )

    assert raised.value.msg == "分支版本缺少 operation"

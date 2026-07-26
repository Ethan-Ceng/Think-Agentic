import asyncio
from datetime import datetime

import pytest

from app.core.entities.project import Project
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
        self.saved = []

    async def save(self, session: Session):
        self.calls.append(("save", session))
        self.saved.append(session)

    async def update_organization(self, *args, **kwargs):
        self.calls.append(("update_organization", args, kwargs))
        if self.error is not None:
            raise self.error
        return self.result

    async def get_by_id_for_user(self, *args):
        self.calls.append(("get_by_id_for_user", args, {}))
        return self.result


class _ProjectRepository:
    def __init__(self, result=None) -> None:
        self.result = result
        self.calls = []

    async def get_by_id_for_user(self, project_id: str, user_id: str):
        self.calls.append(("get_by_id_for_user", project_id, user_id))
        return self.result


class _Uow:
    def __init__(
        self,
        repository: _SessionRepository,
        project_repository: _ProjectRepository,
    ) -> None:
        self.session = repository
        self.project = project_repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def _service(
    repository: _SessionRepository,
    project_repository: _ProjectRepository | None = None,
) -> SessionService:
    projects = project_repository or _ProjectRepository()
    return SessionService(
        lambda: _Uow(repository, projects),
        sandbox_cls=object(),
    )


def test_create_session_supports_unassigned_and_owned_project_in_same_uow():
    unassigned_repository = _SessionRepository()
    unassigned_projects = _ProjectRepository()
    unassigned = asyncio.run(
        _service(
            unassigned_repository,
            unassigned_projects,
        ).create_session("user-1")
    )

    owned_project = Project(
        id="project-1",
        user_id="user-1",
        name="Alpha",
    )
    assigned_repository = _SessionRepository()
    assigned_projects = _ProjectRepository(result=owned_project)
    assigned = asyncio.run(
        _service(
            assigned_repository,
            assigned_projects,
        ).create_session("user-1", project_id="project-1")
    )

    assert unassigned.project_id is None
    assert unassigned_projects.calls == []
    assert unassigned_repository.saved == [unassigned]
    assert assigned.project_id == "project-1"
    assert assigned_projects.calls == [
        ("get_by_id_for_user", "project-1", "user-1"),
    ]
    assert assigned_repository.saved == [assigned]


def test_create_session_hides_missing_or_cross_user_project():
    repository = _SessionRepository()
    projects = _ProjectRepository(result=None)

    with pytest.raises(NotFoundError) as exc_info:
        asyncio.run(
            _service(repository, projects).create_session(
                "user-1",
                project_id="hidden-project",
            )
        )

    assert exc_info.value.msg == "项目不存在或无权访问"
    assert repository.saved == []
    assert projects.calls == [
        ("get_by_id_for_user", "hidden-project", "user-1"),
    ]


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


def test_project_move_validates_owner_and_explicit_null_skips_lookup():
    owned_project = Project(
        id="project-1",
        user_id="user-1",
        name="Alpha",
    )
    moved = Session(
        id="session-1",
        user_id="user-1",
        project_id="project-1",
    )
    repository = _SessionRepository(result=moved)
    projects = _ProjectRepository(result=owned_project)
    service = _service(repository, projects)

    result = asyncio.run(
        service.update_organization(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            project_id_provided=True,
        )
    )

    assert result is moved
    assert projects.calls == [
        ("get_by_id_for_user", "project-1", "user-1"),
    ]
    assert repository.calls == [
        (
            "update_organization",
            ("session-1", "user-1"),
            {
                "title": None,
                "pinned": None,
                "archived": None,
                "project_id": "project-1",
                "project_id_provided": True,
            },
        )
    ]

    projects.calls.clear()
    repository.calls.clear()
    asyncio.run(
        service.update_organization(
            session_id="session-1",
            user_id="user-1",
            project_id=None,
            project_id_provided=True,
        )
    )
    assert projects.calls == []
    assert repository.calls[0][2]["project_id"] is None


def test_project_move_hides_missing_or_cross_user_target_before_session_write():
    repository = _SessionRepository(result=Session(user_id="user-1"))
    projects = _ProjectRepository(result=None)

    with pytest.raises(NotFoundError) as exc_info:
        asyncio.run(
            _service(repository, projects).update_organization(
                session_id="session-1",
                user_id="user-1",
                project_id="hidden-project",
                project_id_provided=True,
            )
        )

    assert exc_info.value.msg == "项目不存在或无权访问"
    assert repository.calls == []


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

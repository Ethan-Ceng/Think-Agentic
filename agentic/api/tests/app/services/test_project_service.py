import asyncio

import pytest

from app.core.entities.project import (
    Project,
    ProjectNameConflictError,
    ProjectNotFoundError,
)
from app.schemas.exceptions import ConflictError, NotFoundError
from app.services.project_service import ProjectService


class _ProjectRepository:
    def __init__(self, *, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.calls = []

    async def list_by_user(self, user_id: str):
        self.calls.append(("list_by_user", user_id))
        return self.result

    async def create(self, project: Project):
        self.calls.append(("create", project))
        if self.error is not None:
            raise self.error
        return project

    async def rename(self, project_id: str, user_id: str, name: str):
        self.calls.append(("rename", project_id, user_id, name))
        if self.error is not None:
            raise self.error
        return self.result

    async def delete(self, project_id: str, user_id: str):
        self.calls.append(("delete", project_id, user_id))
        if self.error is not None:
            raise self.error


class _Uow:
    def __init__(self, repository: _ProjectRepository) -> None:
        self.project = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def _service(repository: _ProjectRepository) -> ProjectService:
    return ProjectService(lambda: _Uow(repository))


def test_list_projects_uses_authenticated_user_scope_and_preserves_repository_order():
    projects = [
        Project(id="newer", user_id="user-1", name="Newer"),
        Project(id="older", user_id="user-1", name="Older"),
    ]
    repository = _ProjectRepository(result=projects)

    result = asyncio.run(_service(repository).list_projects("user-1"))

    assert result == projects
    assert repository.calls == [("list_by_user", "user-1")]


def test_create_project_binds_owner_and_returns_created_project():
    repository = _ProjectRepository()

    created = asyncio.run(
        _service(repository).create_project(
            user_id="user-1",
            name="Alpha",
        )
    )

    assert created.user_id == "user-1"
    assert created.name == "Alpha"
    assert repository.calls == [("create", created)]


@pytest.mark.parametrize("operation", ["create", "rename"])
def test_name_conflicts_map_to_stable_public_409(operation):
    repository = _ProjectRepository(
        result=Project(user_id="user-1", name="Alpha"),
        error=ProjectNameConflictError("duplicate"),
    )
    service = _service(repository)

    with pytest.raises(ConflictError) as exc_info:
        if operation == "create":
            asyncio.run(service.create_project("user-1", "alpha"))
        else:
            asyncio.run(
                service.rename_project(
                    "project-1",
                    "user-1",
                    "alpha",
                )
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.msg == "已存在同名项目"


def test_rename_uses_owner_scope_and_allows_repository_self_rename():
    renamed = Project(id="project-1", user_id="user-1", name="Alpha")
    repository = _ProjectRepository(result=renamed)

    result = asyncio.run(
        _service(repository).rename_project(
            project_id="project-1",
            user_id="user-1",
            name="Alpha",
        )
    )

    assert result is renamed
    assert repository.calls == [
        ("rename", "project-1", "user-1", "Alpha"),
    ]


@pytest.mark.parametrize("operation", ["rename", "delete"])
def test_missing_or_cross_user_project_maps_to_stable_404(operation):
    repository = _ProjectRepository(
        error=ProjectNotFoundError("hidden"),
    )
    service = _service(repository)

    with pytest.raises(NotFoundError) as exc_info:
        if operation == "rename":
            asyncio.run(
                service.rename_project(
                    "project-1",
                    "other-user",
                    "Hidden",
                )
            )
        else:
            asyncio.run(service.delete_project("project-1", "other-user"))

    assert exc_info.value.status_code == 404
    assert exc_info.value.msg == "项目不存在或无权访问"


def test_delete_only_calls_project_repository():
    repository = _ProjectRepository()

    asyncio.run(_service(repository).delete_project("project-1", "user-1"))

    assert repository.calls == [("delete", "project-1", "user-1")]

from datetime import datetime, timedelta

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.entities.project import Project
from app.core.entities.user import User
from app.dependencies import get_current_user, get_project_service
from app.main import app
from app.schemas.exceptions import ConflictError, NotFoundError


class RecordingProjectService:
    def __init__(self, *, error=None) -> None:
        self.error = error
        self.calls = []
        now = datetime.now()
        self.projects = [
            Project(
                id="project-newer",
                user_id="user-auth",
                name="Newer",
                created_at=now,
                updated_at=now,
            ),
            Project(
                id="project-older",
                user_id="user-auth",
                name="Older",
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            ),
        ]

    async def list_projects(self, user_id: str):
        self.calls.append(("list", user_id))
        return self.projects

    async def create_project(self, user_id: str, name: str):
        self.calls.append(("create", user_id, name))
        if self.error is not None:
            raise self.error
        return Project(id="project-created", user_id=user_id, name=name)

    async def rename_project(self, project_id: str, user_id: str, name: str):
        self.calls.append(("rename", project_id, user_id, name))
        if self.error is not None:
            raise self.error
        return Project(id=project_id, user_id=user_id, name=name)

    async def delete_project(self, project_id: str, user_id: str):
        self.calls.append(("delete", project_id, user_id))
        if self.error is not None:
            raise self.error


def authenticated_user() -> User:
    now = datetime.now()
    return User(
        id="user-auth",
        email="auth@example.com",
        created_at=now,
        updated_at=now,
    )


def _client(service: RecordingProjectService) -> TestClient:
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_project_service] = lambda: service
    return TestClient(app)


def test_project_routes_are_registered_and_require_authentication():
    routes = [route for route in app.routes if isinstance(route, APIRoute)]
    project_routes = [
        route for route in routes if route.path.startswith("/api/projects")
    ]

    assert {(route.path, tuple(sorted(route.methods))) for route in project_routes} == {
        ("/api/projects", ("GET",)),
        ("/api/projects", ("POST",)),
        ("/api/projects/{project_id}", ("PATCH",)),
        ("/api/projects/{project_id}", ("DELETE",)),
    }
    assert all(
        any(item.call is get_current_user for item in route.dependant.dependencies)
        for route in project_routes
    )


def test_project_routes_reject_unauthenticated_requests():
    service = RecordingProjectService()
    app.dependency_overrides[get_project_service] = lambda: service
    try:
        with TestClient(app) as client:
            responses = [
                client.get("/api/projects"),
                client.post("/api/projects", json={"name": "Alpha"}),
                client.patch(
                    "/api/projects/project-1",
                    json={"name": "Renamed"},
                ),
                client.delete("/api/projects/project-1"),
            ]

        assert all(response.status_code == 401 for response in responses)
        assert service.calls == []
    finally:
        app.dependency_overrides.clear()


def test_list_returns_stable_public_contract_without_owner_id():
    service = RecordingProjectService()
    try:
        with _client(service) as client:
            response = client.get("/api/projects")

        assert response.status_code == 200
        assert response.json()["msg"] == "获取项目列表成功"
        assert [item["id"] for item in response.json()["data"]["projects"]] == [
            "project-newer",
            "project-older",
        ]
        assert "user_id" not in response.json()["data"]["projects"][0]
        assert service.calls == [("list", "user-auth")]
    finally:
        app.dependency_overrides.clear()


def test_create_rename_and_delete_bind_authenticated_user_and_trim_name():
    service = RecordingProjectService()
    try:
        with _client(service) as client:
            created = client.post(
                "/api/projects",
                json={"name": "  Alpha  "},
            )
            renamed = client.patch(
                "/api/projects/project-created",
                json={"name": "  Renamed  "},
            )
            deleted = client.delete("/api/projects/project-created")

        assert created.status_code == 200
        assert created.json()["data"]["name"] == "Alpha"
        assert renamed.status_code == 200
        assert renamed.json()["data"]["name"] == "Renamed"
        assert deleted.status_code == 200
        assert deleted.json() == {
            "code": 200,
            "msg": "删除项目成功",
            "data": {},
        }
        assert service.calls == [
            ("create", "user-auth", "Alpha"),
            ("rename", "project-created", "user-auth", "Renamed"),
            ("delete", "project-created", "user-auth"),
        ]
    finally:
        app.dependency_overrides.clear()


def test_request_contract_rejects_blank_null_long_and_extra_fields():
    invalid_payloads = [
        {"name": "  "},
        {"name": None},
        {"name": "x" * 101},
        {"name": "Alpha", "user_id": "other-user"},
        {"name": "Alpha", "parent_id": "parent"},
        {"name": "Alpha", "unexpected": True},
    ]
    service = RecordingProjectService()
    try:
        with _client(service) as client:
            responses = [
                client.post("/api/projects", json=payload)
                for payload in invalid_payloads
            ]
            responses.extend(
                client.patch("/api/projects/project-1", json=payload)
                for payload in invalid_payloads
            )

        assert all(response.status_code == 422 for response in responses)
        assert service.calls == []
    finally:
        app.dependency_overrides.clear()


def test_routes_expose_stable_conflict_and_hidden_project_errors():
    try:
        for error, method, expected_status, expected_message in (
            (
                ConflictError("已存在同名项目"),
                "post",
                409,
                "已存在同名项目",
            ),
            (
                NotFoundError("项目不存在或无权访问"),
                "patch",
                404,
                "项目不存在或无权访问",
            ),
            (
                NotFoundError("项目不存在或无权访问"),
                "delete",
                404,
                "项目不存在或无权访问",
            ),
        ):
            service = RecordingProjectService(error=error)
            with _client(service) as client:
                if method == "post":
                    response = client.post(
                        "/api/projects",
                        json={"name": "Alpha"},
                    )
                elif method == "patch":
                    response = client.patch(
                        "/api/projects/project-1",
                        json={"name": "Renamed"},
                    )
                else:
                    response = client.delete("/api/projects/project-1")

            assert response.status_code == expected_status
            assert response.json()["code"] == expected_status
            assert response.json()["msg"] == expected_message
    finally:
        app.dependency_overrides.clear()

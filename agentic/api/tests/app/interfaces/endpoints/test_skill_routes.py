from datetime import datetime

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.entities.skill import Skill, SkillScope, SkillVersion
from app.core.entities.user import User
from app.dependencies import get_current_user
from app.dependencies.services import get_skill_service
from app.main import app
from app.schemas.exceptions import NotFoundError
from app.services.skill_service import SkillDetail, SkillDraft


class RecordingSkillService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.skill = Skill(
            id="skill-1",
            owner_user_id="user-auth",
            name="report-writer",
            display_name="Report Writer",
            description="Create reports.",
            scope=SkillScope.PERSONAL,
            current_version_id="version-1",
        )
        self.version = SkillVersion(
            id="version-1",
            skill_id="skill-1",
            version=1,
            manifest={
                "name": "report-writer",
                "description": "Create reports.",
            },
            storage_provider="local",
            storage_key="personal/user-auth/skill-1/1.skill",
            package_sha256="a" * 64,
            package_size=100,
            file_count=1,
            created_by_user_id="user-auth",
        )

    async def create_draft(self, user_id: str, **kwargs):
        self.calls.append(("create_draft", user_id, kwargs))
        return SkillDraft(
            draft_id="draft-1",
            skill_name=kwargs["name"],
            revision="b" * 64,
        )

    async def list_skills(self, user_id: str):
        self.calls.append(("list_skills", user_id))
        return [self.skill]

    async def get_skill(self, user_id: str, skill_id: str):
        self.calls.append(("get_skill", user_id, skill_id))
        if user_id != self.skill.owner_user_id or skill_id != self.skill.id:
            raise NotFoundError("Skill not found")
        return SkillDetail(skill=self.skill, version=self.version)


def authenticated_user() -> User:
    now = datetime.now()
    return User(
        id="user-auth",
        email="auth@example.com",
        created_at=now,
        updated_at=now,
    )


def another_authenticated_user() -> User:
    now = datetime.now()
    return User(
        id="user-other",
        email="other@example.com",
        created_at=now,
        updated_at=now,
    )


def skill_routes() -> list[APIRoute]:
    return [
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and (
            route.path.startswith("/api/skills")
            or route.path.startswith("/api/skill-drafts")
        )
    ]


def test_all_skill_routes_require_authenticated_user() -> None:
    routes = skill_routes()
    assert routes
    assert all(
        any(dependency.call is get_current_user for dependency in route.dependant.dependencies)
        for route in routes
    )

    with TestClient(app) as client:
        response = client.get("/api/skills")
    assert response.status_code == 401


def test_static_skill_routes_are_not_shadowed_by_dynamic_skill_id() -> None:
    routes = skill_routes()
    paths = [route.path for route in routes]

    assert "/api/skills/import" in paths
    assert "/api/skills/{skill_id}" in paths
    assert paths.index("/api/skills/import") < paths.index("/api/skills/{skill_id}")
    assert "/api/skill-drafts/{draft_id}/files/{path:path}" in paths


def test_skill_routes_are_present_in_openapi_schema() -> None:
    paths = app.openapi()["paths"]

    assert "post" in paths["/api/skills/import"]
    assert "multipart/form-data" in paths["/api/skills/import"]["post"][
        "requestBody"
    ]["content"]
    assert "get" in paths["/api/skills/{skill_id}"]
    assert "post" in paths["/api/skill-drafts/{draft_id}/publish"]


def test_create_draft_uses_authenticated_owner_and_ignores_client_owner() -> None:
    service = RecordingSkillService()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_skill_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/skill-drafts",
                json={
                    "name": "report-writer",
                    "display_name": "Report Writer",
                    "description": "Create reports.",
                    "owner_user_id": "attacker-controlled-user",
                },
            )
        assert response.status_code == 200
        assert response.json()["data"] == {
            "draft_id": "draft-1",
            "skill_name": "report-writer",
            "revision": "b" * 64,
        }
        assert service.calls == [
            (
                "create_draft",
                "user-auth",
                {
                    "name": "report-writer",
                    "display_name": "Report Writer",
                    "description": "Create reports.",
                },
            )
        ]
    finally:
        app.dependency_overrides.clear()


def test_create_draft_rejects_non_standard_skill_name_before_service_call() -> None:
    service = RecordingSkillService()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_skill_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/skill-drafts",
                json={
                    "name": "../report-writer",
                    "display_name": "Report Writer",
                    "description": "Create reports.",
                },
            )
        assert response.status_code == 422
        assert service.calls == []
    finally:
        app.dependency_overrides.clear()


def test_cross_user_skill_access_returns_not_found() -> None:
    service = RecordingSkillService()
    app.dependency_overrides[get_current_user] = another_authenticated_user
    app.dependency_overrides[get_skill_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/skills/skill-1")
        assert response.status_code == 404
        assert service.calls == [("get_skill", "user-other", "skill-1")]
    finally:
        app.dependency_overrides.clear()


def test_skill_list_response_contains_no_storage_credentials() -> None:
    service = RecordingSkillService()
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_skill_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/skills")
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload[0]["id"] == "skill-1"
        assert "storage_config" not in str(payload)
        assert "secret" not in str(payload).lower()
    finally:
        app.dependency_overrides.clear()

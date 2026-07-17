from datetime import datetime

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.entities.user import User
from app.dependencies import get_current_user
from app.dependencies.services import get_marketplace_skill_service
from app.main import app


class MarketplaceService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def list_marketplace(self, user_id: str):
        self.calls.append(("list", user_id))
        return []

    async def get_marketplace(self, user_id: str, skill_id: str):
        self.calls.append(("detail", user_id, skill_id))
        raise AssertionError("not called in this test")

    async def install(self, user_id: str, skill_id: str, **kwargs):
        self.calls.append(("install", user_id, skill_id, kwargs))
        return marketplace_view()

    async def update(self, user_id: str, skill_id: str, **kwargs):
        self.calls.append(("update", user_id, skill_id, kwargs))
        return marketplace_view()

    async def uninstall(self, user_id: str, skill_id: str):
        self.calls.append(("uninstall", user_id, skill_id))

    async def set_enabled(self, user_id: str, skill_id: str, enabled: bool):
        self.calls.append(("enabled", user_id, skill_id, enabled))
        return marketplace_view()

    async def set_auto_invoke(self, user_id: str, skill_id: str, enabled: bool):
        self.calls.append(("auto", user_id, skill_id, enabled))
        return marketplace_view()

    async def fork(self, user_id: str, skill_id: str, **kwargs):
        self.calls.append(("fork", user_id, skill_id, kwargs))
        from app.services.skill_service import SkillDraft

        return SkillDraft(
            draft_id="personal-fork-draft",
            skill_name="market-research",
            revision="c" * 64,
        )


def marketplace_view():
    from app.core.entities.skill import Skill, SkillInstallation, SkillScope, SkillVersion
    from app.services.marketplace_skill_service import MarketplaceSkillView

    skill = Skill(
        id="market-1",
        name="market-research",
        display_name="Market Research",
        description="Research a market.",
        scope=SkillScope.MARKETPLACE,
        current_version_id="version-1",
    )
    version = SkillVersion(
        id="version-1",
        skill_id=skill.id,
        version=1,
        manifest={"name": skill.name, "description": skill.description},
        storage_provider="local",
        storage_key="marketplace/market-1/1.skill",
        package_sha256="a" * 64,
        package_size=10,
        file_count=1,
    )
    installation = SkillInstallation(
        user_id="user-auth", skill_id=skill.id, pinned_version_id=version.id
    )
    return MarketplaceSkillView(
        skill=skill,
        versions=(version,),
        latest_version=version,
        installation=installation,
    )


def user() -> User:
    now = datetime.now()
    return User(id="user-auth", email="market@example.com", created_at=now, updated_at=now)


def test_marketplace_contract_routes_precede_personal_dynamic_route() -> None:
    routes = [route for route in app.routes if isinstance(route, APIRoute)]
    paths = [route.path for route in routes]
    required = {
        "/api/skills/marketplace",
        "/api/skills/marketplace/{skill_id}",
        "/api/skills/marketplace/{skill_id}/install",
        "/api/skills/marketplace/{skill_id}/update",
        "/api/skills/marketplace/{skill_id}/fork",
    }
    assert required <= set(paths)
    assert paths.index("/api/skills/marketplace") < paths.index("/api/skills/{skill_id}")
    assert all(
        any(item.call is get_current_user for item in route.dependant.dependencies)
        for route in routes
        if route.path in required
    )


def test_install_update_flags_uninstall_and_fork_use_authenticated_user() -> None:
    service = MarketplaceService()
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_marketplace_skill_service] = lambda: service
    try:
        client = TestClient(app)
        assert client.post(
            "/api/skills/marketplace/market-1/install",
            json={"version_id": "version-1"},
        ).status_code == 200
        assert client.post(
            "/api/skills/marketplace/market-1/update", json={}
        ).status_code == 200
        assert client.post(
            "/api/skills/marketplace/market-1/disable"
        ).status_code == 200
        assert client.post(
            "/api/skills/marketplace/market-1/auto-invoke",
            json={"enabled": False},
        ).status_code == 200
        assert client.delete(
            "/api/skills/marketplace/market-1/install"
        ).status_code == 200
        assert client.post(
            "/api/skills/marketplace/market-1/fork",
            json={"version_id": "version-1"},
        ).status_code == 200
    finally:
        app.dependency_overrides.clear()

    assert service.calls == [
        ("install", "user-auth", "market-1", {"version_id": "version-1"}),
        ("update", "user-auth", "market-1", {"version_id": None}),
        ("enabled", "user-auth", "market-1", False),
        ("auto", "user-auth", "market-1", False),
        ("uninstall", "user-auth", "market-1"),
        (
            "fork",
            "user-auth",
            "market-1",
            {"version_id": "version-1", "display_name": None},
        ),
    ]

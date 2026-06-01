import uuid

from fastapi.testclient import TestClient

from app.api.deps import get_current_account
from app.app_factory import create_app
from app.core.config import Settings
from app.core.tools.builtin_tools.categories import BuiltinCategoryManager
from app.core.tools.builtin_tools.providers import BuiltinProviderManager
from app.models.account import Account
from app.services.builtin_tool_service import BuiltinToolService


def test_builtin_provider_manager_loads_yaml_metadata() -> None:
    manager = BuiltinProviderManager()

    provider = manager.get_provider("time")

    assert provider is not None
    assert provider.get_tool_entity("current_time") is not None
    assert provider.get_tool("current_time").run()


def test_builtin_tool_service_returns_categories() -> None:
    service = BuiltinToolService(BuiltinProviderManager(), BuiltinCategoryManager())

    categories = service.get_categories()

    assert any(category["category"] == "tool" for category in categories)
    assert all(category["icon"] for category in categories)


def test_builtin_tool_service_uses_fallback_inputs_for_known_tools() -> None:
    service = BuiltinToolService(BuiltinProviderManager(), BuiltinCategoryManager())

    tool = service.get_provider_tool("gaode", "gaode_weather")

    assert tool["inputs"] == [
        {
            "name": "city",
            "description": "City",
            "required": True,
            "type": "string",
        }
    ]


def test_builtin_tools_route_keeps_legacy_payload_shape() -> None:
    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )

    with TestClient(app) as client:
        response = client.get("/builtin-tools")

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert any(provider["name"] == "time" for provider in response.json()["data"])

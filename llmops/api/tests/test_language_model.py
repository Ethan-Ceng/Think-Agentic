import uuid

from fastapi.testclient import TestClient

from app.api.deps import get_current_account
from app.app_factory import create_app
from app.core.config import Settings
from app.core.language_model import LanguageModelManager
from app.models.account import Account
from app.services.language_model_service import LanguageModelService


def test_language_model_manager_loads_yaml_metadata() -> None:
    manager = LanguageModelManager()

    provider = manager.get_provider("openai")
    model = provider.get_model_entity("gpt-4o-mini")

    assert provider.provider_entity.label == "OpenAI"
    assert model.model_name == "gpt-4o-mini"
    assert model.parameters[0].name == "temperature"
    assert model.parameters[0].default == 1


def test_language_model_service_keeps_legacy_fields() -> None:
    service = LanguageModelService()

    providers = service.get_language_models()
    openai = next(provider for provider in providers if provider["name"] == "openai")

    assert "chat" in openai["support_model_types"]
    assert any(model["model_name"] == "gpt-4o-mini" for model in openai["models"])
    assert openai["models"][0]["context_windows"] == openai["models"][0]["context_window"]


def test_language_models_route_keeps_legacy_payload_shape() -> None:
    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )

    with TestClient(app) as client:
        response = client.get("/language-models")

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert any(provider["name"] == "openai" for provider in response.json()["data"])


def test_language_model_icon_route_is_not_shadowed_by_model_detail_route() -> None:
    app = create_app(Settings(app_env="test", debug=False))

    with TestClient(app) as client:
        response = client.get("/language-models/openai/icon")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")

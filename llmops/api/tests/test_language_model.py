import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_current_account
from app.app_factory import create_app
from app.core.config import Settings
from app.core.language_model import LanguageModelManager
from app.models.account import Account
from app.services.language_model_service import LanguageModelService
from app.services.llm_provider_service import LLMProviderService


def test_language_model_manager_loads_yaml_metadata() -> None:
    manager = LanguageModelManager()

    provider = manager.get_provider("openai")
    model = provider.get_model_entity("gpt-4o-mini")

    assert provider.provider_entity.label == "OpenAI"
    assert model.model_name == "gpt-4o-mini"
    assert model.parameters[0].name == "temperature"
    assert model.parameters[0].default == 1
    assert next(parameter for parameter in model.parameters if parameter.name == "top_p").default == 0.85


def test_language_model_service_keeps_legacy_fields() -> None:
    service = LanguageModelService()

    providers = service.get_language_models()
    openai = next(provider for provider in providers if provider["name"] == "openai")

    assert "chat" in openai["support_model_types"]
    assert any(model["model_name"] == "gpt-4o-mini" for model in openai["models"])
    assert openai["models"][0]["context_windows"] == openai["models"][0]["context_window"]


def test_llm_provider_service_builds_system_specs_from_yaml_and_env() -> None:
    service = LLMProviderService(
        settings=Settings(
            _env_file=None,
            openai_api_key="openai-key",
            openai_base_url="https://openai-compatible.example.test/v1",
            default_llm_provider="deepseek",
            default_llm_model="deepseek-v4-pro",
        )
    )

    providers = service.system_provider_specs()
    openai = next(provider for provider in providers if provider["provider"] == "openai")
    deepseek = next(provider for provider in providers if provider["provider"] == "deepseek")
    tongyi = next(provider for provider in providers if provider["provider"] == "tongyi")
    gpt_4o_mini = next(model for model in openai["models"] if model["model"] == "gpt-4o-mini")
    deepseek_v4_pro = next(model for model in deepseek["models"] if model["model"] == "deepseek-v4-pro")

    assert openai["name"] == "OpenAI"
    assert openai["base_url"] == "https://openai-compatible.example.test/v1"
    assert openai["api_key"] == "openai-key"
    assert gpt_4o_mini["context_window"] == 128000
    assert "tool_call" in gpt_4o_mini["features"]
    assert deepseek["is_default"] is True
    assert deepseek_v4_pro["is_default"] is True
    assert deepseek_v4_pro["context_window"] == 1048576
    assert deepseek_v4_pro["default_parameters"]["reasoning_effort"] == "high"
    assert [model["model"] for model in tongyi["models"]] == [
        "qwen3.7-plus",
        "qwen3.7-max",
        "qwen3.6-flash",
    ]


def test_llm_provider_service_ensures_system_yaml_even_with_custom_providers() -> None:
    class FakeQuery:
        def __init__(self, providers) -> None:  # noqa: ANN001
            self.providers = providers

        def filter(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return self

        def all(self):
            return self.providers

    class FakeSession:
        def __init__(self, providers) -> None:  # noqa: ANN001
            self.providers = providers

        def query(self, model):  # noqa: ANN001
            return FakeQuery(self.providers)

    class FakeService(LLMProviderService):
        def __init__(self) -> None:
            super().__init__()
            self.sync_calls = []

        def sync_system_providers(self, session, account_id, *, reset=False):  # noqa: ANN001
            self.sync_calls.append(reset)
            return []

    service = FakeService()

    service.ensure_system_providers(FakeSession([]), uuid.uuid4())
    assert service.sync_calls == [True]

    service.sync_calls.clear()
    service.ensure_system_providers(FakeSession([SimpleNamespace(config={})]), uuid.uuid4())
    assert service.sync_calls == [False]

    service.sync_calls.clear()
    service.ensure_system_providers(FakeSession([SimpleNamespace(config={"source": "system_yaml"})]), uuid.uuid4())
    assert service.sync_calls == []


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

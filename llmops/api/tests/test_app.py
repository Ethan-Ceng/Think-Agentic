import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_app_service, get_current_account, get_db_session
from app.app_factory import create_app
from app.core.app import DEFAULT_APP_CONFIG
from app.core.config import Settings
from app.models.account import Account
from app.schemas.app import AppPageResponse
from app.services.app_service import AppService


def test_app_config_normalization_keeps_defaults() -> None:
    config = AppService._normalize_config({"dialog_round": 5, "workflows": [uuid.uuid4()]})

    assert config["dialog_round"] == 5
    assert config["model_config"] == DEFAULT_APP_CONFIG["model_config"]
    assert isinstance(config["workflows"][0], str)


def test_app_config_normalization_repairs_invalid_top_p() -> None:
    config = AppService._normalize_config(
        {
            "model_config": {
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "parameters": {"top_p": 0, "temperature": 1},
            }
        }
    )

    assert config["model_config"]["parameters"]["top_p"] == 0.85
    assert config["model_config"]["parameters"]["temperature"] == 1


def test_app_config_tool_metadata_keeps_legacy_shape() -> None:
    tools = AppService()._tool_metadata(  # noqa: SLF001
        None,
        [{"type": "builtin_tool", "provider_id": "time", "tool_id": "current_time", "params": {}}],
    )

    assert tools[0]["type"] == "builtin_tool"
    assert tools[0]["provider"]["id"] == "time"
    assert tools[0]["tool"]["name"] == "current_time"


def test_app_runtime_capability_can_auto_create_app(monkeypatch) -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    service = AppService()
    capabilities = service._build_runtime_capabilities(  # noqa: SLF001
        None,
        {"runtime_capabilities": [{"type": "create_app"}]},
        account,
    )
    created = {}

    def fake_auto_create_app(session, name, description, account_id):  # noqa: ANN001
        created.update({"name": name, "description": description, "account_id": account_id})
        return SimpleNamespace(id=uuid.uuid4(), name=name, description=description)

    monkeypatch.setattr(service, "auto_create_app", fake_auto_create_app)
    observation = service._invoke_runtime_capability(  # noqa: SLF001
        None,
        capabilities[0],
        {"name": "Research Agent", "description": "Summarize docs"},
        account,
        "create one",
    )

    assert capabilities[0].name == "create_app"
    assert '"name": "Research Agent"' in observation
    assert created == {
        "name": "Research Agent",
        "description": "Summarize docs",
        "account_id": account.id,
    }


def test_app_page_response_keeps_legacy_fields() -> None:
    app = SimpleNamespace(
        id=uuid.uuid4(),
        name="Agent",
        icon="https://example.test/icon.png",
        description="desc",
        status="draft",
        updated_at=datetime(2024, 1, 1),
        created_at=datetime(2024, 1, 1),
    )
    config = SimpleNamespace(
        preset_prompt="prompt",
        model_config={"provider": "openai", "model": "gpt-4o-mini"},
    )

    response = AppPageResponse.from_app(app, config)

    assert response.preset_prompt == "prompt"
    assert response.model_cfg["provider"] == "openai"


def test_app_create_route_keeps_legacy_payload_shape() -> None:
    app_id = uuid.uuid4()

    class FakeAppService:
        def create_app(self, session, req, current_user):  # noqa: ANN001
            return SimpleNamespace(id=app_id)

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_app_service] = lambda: FakeAppService()

    with TestClient(app) as client:
        response = client.post(
            "/apps",
            json={
                "name": "Agent",
                "icon": "https://example.test/icon.png",
                "description": "desc",
            },
        )

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert response.json()["data"]["id"] == str(app_id)


def test_update_draft_app_config_accepts_post_for_ui_compatibility() -> None:
    app_id = uuid.uuid4()
    seen_payload = {}

    class FakeAppService:
        def update_draft_app_config(self, session, target_app_id, payload, current_user):  # noqa: ANN001
            assert target_app_id == app_id
            seen_payload.update(payload)

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_app_service] = lambda: FakeAppService()

    with TestClient(app) as client:
        response = client.post(f"/apps/{app_id}/draft-app-config", json={"preset_prompt": ""})

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert seen_payload == {"preset_prompt": ""}


def test_debug_conversation_messages_accepts_legacy_ui_path() -> None:
    app_id = uuid.uuid4()
    seen = {}

    class FakeAppService:
        def get_debug_conversation_messages_with_page(self, session, target_app_id, req, current_user):  # noqa: ANN001
            seen["app_id"] = target_app_id
            seen["page"] = req.page
            seen["page_size"] = req.page_size
            seen["created_at"] = req.created_at
            return [], 0, 0

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_app_service] = lambda: FakeAppService()

    with TestClient(app) as client:
        response = client.get(
            f"/apps/{app_id}/conversations/messages",
            params={"current_page": 1, "page_size": 5, "created_at": 0},
        )

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert response.json()["data"]["current_page"] == 1
    assert response.json()["data"]["page_size"] == 5
    assert seen == {"app_id": app_id, "page": 1, "page_size": 5, "created_at": 0}


def test_published_config_returns_web_app_status_for_draft_app(monkeypatch) -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    app_id = uuid.uuid4()
    service = AppService()
    draft_app = SimpleNamespace(
        id=app_id,
        account_id=account.id,
        app_config_id=None,
        token=None,
        status="draft",
    )

    monkeypatch.setattr(service, "get_app", lambda session, target_app_id, current_user: draft_app)

    response = service.get_published_config(SimpleNamespace(), app_id, account)

    assert response == {"web_app": {"token": "", "status": "draft"}}

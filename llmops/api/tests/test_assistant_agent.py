import uuid

from fastapi.testclient import TestClient

from app.api.deps import get_assistant_agent_service, get_current_account, get_db_session
from app.app_factory import create_app
from app.core.config import Settings
from app.models.account import Account
from app.schemas.assistant_agent import AssistantAgentChatRequest
from app.services.assistant_agent_service import AssistantAgentService


def test_assistant_agent_runtime_config_uses_default_model() -> None:
    config = AssistantAgentService._assistant_runtime_config()

    assert config["model_config"]["provider"] == "openai"
    assert config["dialog_round"] == 3
    assert config["long_term_memory"]["enable"] is True
    assert config["runtime_capabilities"] == [{"type": "create_app"}]


def test_assistant_agent_chat_request_validates_image_urls() -> None:
    try:
        AssistantAgentChatRequest(query="hi", image_urls=["file://image.png"])
    except ValueError as exc:
        assert "HTTP URLs" in str(exc)
    else:
        raise AssertionError("validation should fail")


def test_assistant_agent_chat_route_streams() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    class FakeAssistantAgentService:
        def chat(self, session, req, current_user):  # noqa: ANN001
            assert req.query == "hi"
            assert current_user.id == account.id
            yield "event: agent_message\ndata:{\"answer\":\"hello\"}\n\n"

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: account
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_assistant_agent_service] = lambda: FakeAssistantAgentService()

    with TestClient(app) as client:
        response = client.post("/assistant-agent/chat", json={"query": "hi", "image_urls": []})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: agent_message" in response.text

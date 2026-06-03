import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import (
    get_api_key_account,
    get_db_session,
    get_openapi_service,
    get_web_app_service,
)
from app.app_factory import create_app
from app.core.config import Settings
from app.models.account import Account
from app.schemas.openapi import OpenAPIChatRequest
from app.schemas.web_app import WebAppChatRequest, WebAppConversationResponse


def test_openapi_chat_requires_end_user_when_conversation_is_supplied() -> None:
    try:
        OpenAPIChatRequest(app_id=uuid.uuid4(), conversation_id=uuid.uuid4(), query="hi")
    except ValueError as exc:
        assert "end_user_id" in str(exc)
    else:
        raise AssertionError("validation should fail")


def test_web_app_chat_request_rejects_non_http_images() -> None:
    try:
        WebAppChatRequest(query="hi", image_urls=["ftp://example.test/image.png"])
    except ValueError as exc:
        assert "HTTP URLs" in str(exc)
    else:
        raise AssertionError("validation should fail")


def test_web_app_chat_request_treats_empty_conversation_id_as_new() -> None:
    req = WebAppChatRequest(query="hi", conversation_id="", image_urls=[])

    assert req.conversation_id is None


def test_openapi_chat_route_uses_api_key_account_and_streams() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    class FakeOpenAPIService:
        def chat(self, session, req, current_user):  # noqa: ANN001
            assert req.query == "hi"
            assert current_user.id == account.id
            yield "event: agent_message\ndata:{\"answer\":\"hello\"}\n\n"

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_api_key_account] = lambda: account
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_openapi_service] = lambda: FakeOpenAPIService()

    with TestClient(app) as client:
        response = client.post("/openapi/chat", json={"app_id": str(uuid.uuid4()), "query": "hi"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: agent_message" in response.text


def test_web_app_routes_allow_anonymous_access_and_cookie_user() -> None:
    end_user = SimpleNamespace(id=uuid.uuid4())
    seen = {}

    class FakeWebAppService:
        def get_web_app_info(self, session, token, end_user_id):  # noqa: ANN001
            assert token == "token"
            assert end_user_id is None
            return end_user, {"id": str(uuid.uuid4()), "name": "App"}

        def get_conversations(self, session, token, is_pinned, end_user_id):  # noqa: ANN001
            assert token == "token"
            assert is_pinned is False
            seen["conversation_end_user_id"] = end_user_id
            return end_user, [
                SimpleNamespace(
                    id=uuid.uuid4(),
                    name="New Conversation",
                    summary="",
                    created_at=None,
                )
            ]

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_web_app_service] = lambda: FakeWebAppService()

    with TestClient(app) as client:
        info_response = client.get("/web-apps/token")
        conversations_response = client.get("/web-apps/token/conversations")

    assert info_response.status_code == 200
    assert info_response.json()["data"]["name"] == "App"
    assert "llmops_web_app_end_user_token" in info_response.headers["set-cookie"]
    assert conversations_response.status_code == 200
    assert conversations_response.json()["data"][0]["name"] == "New Conversation"
    assert seen["conversation_end_user_id"] == end_user.id


def test_web_app_chat_route_allows_anonymous_access() -> None:
    end_user = SimpleNamespace(id=uuid.uuid4())

    class FakeWebAppService:
        def web_app_chat(self, session, token, req, end_user_id):  # noqa: ANN001
            assert token == "token"
            assert req.query == "hi"
            assert end_user_id is None
            return end_user, iter(['event: agent_message\ndata:{"answer":"hello"}\n\n'])

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_web_app_service] = lambda: FakeWebAppService()

    with TestClient(app) as client:
        response = client.post("/web-apps/token/chat", json={"query": "hi", "image_urls": []})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "llmops_web_app_end_user_token" in response.headers["set-cookie"]
    assert "event: agent_message" in response.text


def test_web_app_conversation_messages_route_uses_cookie_user() -> None:
    end_user = SimpleNamespace(id=uuid.uuid4())
    conversation_id = uuid.uuid4()
    seen = {}

    class FakeWebAppService:
        def get_conversation_messages_with_page(  # noqa: ANN001
            self,
            session,
            token,
            target_conversation_id,
            end_user_id,
            created_at,
            current_page,
            page_size,
        ):
            assert token == "token"
            assert target_conversation_id == conversation_id
            seen["end_user_id"] = end_user_id
            assert created_at == 0
            assert current_page == 1
            assert page_size == 5
            return end_user, [], 0, 0

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_web_app_service] = lambda: FakeWebAppService()

    with TestClient(app) as client:
        client.cookies.set("llmops_web_app_end_user_token", str(end_user.id))
        response = client.get(
            f"/web-apps/token/conversations/{conversation_id}/messages",
            params={"current_page": 1, "page_size": 5, "created_at": 0},
        )

    assert response.status_code == 200
    assert response.json()["data"]["paginator"]["page_size"] == 5
    assert seen["end_user_id"] == end_user.id


def test_web_app_suggested_questions_route_uses_cookie_user() -> None:
    end_user = SimpleNamespace(id=uuid.uuid4())
    message_id = uuid.uuid4()
    seen = {}

    class FakeWebAppService:
        def generate_suggested_questions(self, session, token, target_message_id, end_user_id):  # noqa: ANN001
            assert token == "token"
            assert target_message_id == message_id
            seen["end_user_id"] = end_user_id
            return end_user, ["What should I do next?"]

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_web_app_service] = lambda: FakeWebAppService()

    with TestClient(app) as client:
        client.cookies.set("llmops_web_app_end_user_token", str(end_user.id))
        response = client.post("/web-apps/token/suggested-questions", json={"message_id": str(message_id)})

    assert response.status_code == 200
    assert response.json()["data"] == ["What should I do next?"]
    assert seen["end_user_id"] == end_user.id


def test_web_app_conversation_response_serializes_timestamp() -> None:
    conversation = SimpleNamespace(id=uuid.uuid4(), name="c", summary="", created_at=None)

    response = WebAppConversationResponse.from_conversation(conversation)

    assert response.created_at == 0

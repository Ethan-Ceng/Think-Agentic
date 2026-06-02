import hashlib
import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import (
    get_ai_service,
    get_audio_service,
    get_current_account,
    get_db_session,
    get_platform_service,
    get_wechat_service,
)
from app.app_factory import create_app
from app.core.config import Settings
from app.core.platform import WechatConfigStatus
from app.models.account import Account
from app.services.platform_service import PlatformService
from app.services.wechat_service import WechatService


def _test_app(account: Account):
    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: account
    app.dependency_overrides[get_db_session] = lambda: None
    return app


def test_platform_wechat_config_routes_keep_legacy_payload_shape() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    app_id = uuid.uuid4()

    class FakePlatformService:
        def get_wechat_config(self, session, target_app_id, current_user):  # noqa: ANN001
            assert target_app_id == app_id
            assert current_user.id == account.id
            return SimpleNamespace(
                id=uuid.uuid4(),
                app_id=target_app_id,
                wechat_app_id="wx-app",
                wechat_app_secret="secret",
                wechat_token="token",
                status="configured",
                updated_at=datetime(2026, 5, 13),
                created_at=datetime(2026, 5, 13),
            )

        def update_wechat_config(  # noqa: ANN001
            self,
            session,
            target_app_id,
            current_user,
            wechat_app_id,
            wechat_app_secret,
            wechat_token,
        ):
            assert target_app_id == app_id
            assert current_user.id == account.id
            assert wechat_app_id == "wx-app"
            assert wechat_app_secret == "secret"
            assert wechat_token == "token"

    app = _test_app(account)
    app.dependency_overrides[get_platform_service] = lambda: FakePlatformService()

    with TestClient(app) as client:
        get_response = client.get(f"/apps/{app_id}/platforms/wechat")
        put_response = client.put(
            f"/apps/{app_id}/platforms/wechat",
            json={
                "wechat_app_id": "wx-app",
                "wechat_app_secret": "secret",
                "wechat_token": "token",
            },
        )

    assert get_response.status_code == 200
    data = get_response.json()["data"]
    assert data["status"] == "configured"
    assert data["ip"] == ""
    assert data["url"] == f"/wechat/{app_id}"
    assert put_response.status_code == 200
    assert put_response.json()["message"] == "Update app wechat config success"


def test_platform_service_creates_default_wechat_config_when_missing(monkeypatch) -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    app_id = uuid.uuid4()
    service = PlatformService()
    created = {}

    class FakeQuery:
        def filter(self, *args):  # noqa: ANN001
            return self

        def one_or_none(self):
            return None

    class FakeSession:
        def query(self, model):  # noqa: ANN001
            return FakeQuery()

    def fake_create(session, model, **kwargs):  # noqa: ANN001
        created.update(kwargs)
        return SimpleNamespace(
            id=uuid.uuid4(),
            app_id=kwargs["app_id"],
            wechat_app_id="",
            wechat_app_secret="",
            wechat_token="",
            status=kwargs["status"],
            updated_at=None,
            created_at=None,
        )

    monkeypatch.setattr(
        service.app_service,
        "get_app",
        lambda session, target_app_id, current_user: SimpleNamespace(id=target_app_id, account_id=current_user.id),
    )
    monkeypatch.setattr(service, "create", fake_create)

    config = service.get_wechat_config(FakeSession(), app_id, account)

    assert created == {"app_id": app_id, "status": WechatConfigStatus.UNCONFIGURED.value}
    assert config.status == WechatConfigStatus.UNCONFIGURED.value


def test_wechat_signature_and_route() -> None:
    token = "wechat-token"
    timestamp = "1710000000"
    nonce = "nonce"
    signature = hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode()).hexdigest()
    config = SimpleNamespace(wechat_token=token)

    assert (
        WechatService._verify_wechat_signature(
            config,
            {"signature": signature, "timestamp": timestamp, "nonce": nonce, "echostr": "ok"},
        )
        == "ok"
    )

    class FakeWechatService:
        def wechat(self, session, app_id, method, query_params, body):  # noqa: ANN001
            assert method == "GET"
            assert body == b""
            return query_params["echostr"]

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_wechat_service] = lambda: FakeWechatService()

    with TestClient(app) as client:
        response = client.get(f"/wechat/{uuid.uuid4()}?echostr=hello")

    assert response.status_code == 200
    assert response.text == "hello"


def test_ai_routes_stream_and_return_suggested_questions() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    class FakeAIService:
        def optimize_prompt(self, prompt):  # noqa: ANN001
            assert prompt == "draft prompt"
            yield 'event: optimize_prompt\ndata:{"prompt":"optimized"}\n\n'

        def generate_suggested_questions_from_message_id(self, session, message_id, current_user):  # noqa: ANN001
            assert current_user.id == account.id
            return ["Question 1?", "Question 2?"]

    app = _test_app(account)
    app.dependency_overrides[get_ai_service] = lambda: FakeAIService()

    with TestClient(app) as client:
        optimize_response = client.post("/ai/optimize-prompt", json={"prompt": "draft prompt"})
        questions_response = client.post("/ai/suggested-questions", json={"message_id": str(uuid.uuid4())})

    assert optimize_response.status_code == 200
    assert optimize_response.headers["content-type"].startswith("text/event-stream")
    assert "optimized" in optimize_response.text
    assert questions_response.status_code == 200
    assert questions_response.json()["data"] == ["Question 1?", "Question 2?"]


def test_audio_routes_accept_upload_and_stream_tts() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    message_id = uuid.uuid4()

    class FakeAudioService:
        def audio_to_text(self, filename, content, content_type):  # noqa: ANN001
            assert filename == "recording.wav"
            assert content == b"audio"
            assert content_type == "audio/wav"
            return "hello"

        def message_to_audio(self, session, target_message_id, current_user):  # noqa: ANN001
            assert target_message_id == message_id
            assert current_user.id == account.id
            yield 'event: tts_end\ndata:{"status":"ok"}\n\n'

    app = _test_app(account)
    app.dependency_overrides[get_audio_service] = lambda: FakeAudioService()

    with TestClient(app) as client:
        text_response = client.post(
            "/audio/to-text",
            files={"file": ("recording.wav", b"audio", "audio/wav")},
        )
        tts_response = client.post("/audio/message-to-audio", json={"message_id": str(message_id)})

    assert text_response.status_code == 200
    assert text_response.json()["data"]["text"] == "hello"
    assert tts_response.status_code == 200
    assert tts_response.headers["content-type"].startswith("text/event-stream")
    assert "tts_end" in tts_response.text

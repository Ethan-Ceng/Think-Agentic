from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.config import Settings


def test_oauth_redirect_route_uses_legacy_path_and_payload_shape() -> None:
    app = create_app(
        Settings(
            app_env="test",
            debug=False,
            github_client_id="client-id",
            github_client_secret="secret",
            github_redirect_uri="https://example.test/callback",
        )
    )

    with TestClient(app) as client:
        response = client.get("/oauth/github")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "success"
    assert body["data"]["redirect_url"].startswith("https://github.com/login/oauth/authorize?")


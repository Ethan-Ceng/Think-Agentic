from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.config import Settings


def test_healthz() -> None:
    app = create_app(Settings(app_env="test", debug=False))
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_legacy_ping() -> None:
    app = create_app(Settings(app_env="test", debug=False))
    with TestClient(app) as client:
        response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"code": "success", "message": "", "data": {"pong": "success"}}

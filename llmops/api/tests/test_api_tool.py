import json
import uuid

from fastapi.testclient import TestClient

from app.api.deps import get_current_account
from app.app_factory import create_app
from app.core.config import Settings
from app.models.account import Account
from app.services.api_tool_service import ApiToolService


def _openapi_schema() -> str:
    return json.dumps(
        {
            "server": "https://example.test",
            "description": "Example API",
            "paths": {
                "/weather": {
                    "get": {
                        "description": "Get weather",
                        "operationId": "get_weather",
                        "parameters": [
                            {
                                "name": "city",
                                "in": "query",
                                "description": "City",
                                "required": True,
                                "type": "str",
                            }
                        ],
                    }
                }
            },
        }
    )


def test_parse_openapi_schema_normalizes_paths() -> None:
    parsed = ApiToolService.parse_openapi_schema(_openapi_schema())

    assert parsed.server == "https://example.test"
    assert parsed.paths["/weather"]["get"]["operationId"] == "get_weather"


def test_api_tool_validate_route_keeps_legacy_payload_shape() -> None:
    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )

    with TestClient(app) as client:
        response = client.post("/api-tools/validate", json={"openapi_schema": _openapi_schema()})

    assert response.status_code == 200
    assert response.json()["code"] == "success"


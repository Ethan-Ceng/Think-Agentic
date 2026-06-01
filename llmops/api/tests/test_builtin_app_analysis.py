import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_analysis_service, get_builtin_app_service, get_current_account, get_db_session
from app.app_factory import create_app
from app.core.builtin_apps import BuiltinAppManager
from app.core.config import Settings
from app.models.account import Account
from app.services.analysis_service import AnalysisService


def test_builtin_app_manager_loads_yaml_metadata() -> None:
    manager = BuiltinAppManager()

    apps = manager.get_builtin_apps()

    assert apps
    assert manager.get_categories()
    assert any(app.language_model_config for app in apps)


def test_builtin_apps_route_keeps_legacy_payload_shape() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: account

    with TestClient(app) as client:
        response = client.get("/builtin-apps")

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert response.json()["data"][0]["model_config"]["provider"]


def test_analysis_overview_calculations() -> None:
    messages = [
        SimpleNamespace(
            created_by=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            total_token_count=10,
            latency=2.0,
            total_price=0.5,
            created_at=datetime(2026, 5, 12),
        )
    ]

    overview = AnalysisService.calculate_overview_indicators_by_messages(messages)

    assert overview["total_messages"] == 1
    assert overview["token_output_rate"] == 5
    assert overview["cost_consumption"] == 0.5


def test_analysis_route_uses_service() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    class FakeAnalysisService:
        def get_app_analysis(self, session, app_id, current_user):  # noqa: ANN001
            assert current_user.id == account.id
            return {
                "total_messages_trend": {"x_axis": [], "y_axis": []},
                "active_accounts_trend": {"x_axis": [], "y_axis": []},
                "avg_of_conversation_messages_trend": {"x_axis": [], "y_axis": []},
                "cost_consumption_trend": {"x_axis": [], "y_axis": []},
                "total_messages": {"data": 0, "pop": 0},
                "active_accounts": {"data": 0, "pop": 0},
                "avg_of_conversation_messages": {"data": 0, "pop": 0},
                "token_output_rate": {"data": 0, "pop": 0},
                "cost_consumption": {"data": 0, "pop": 0},
            }

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: account
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_analysis_service] = lambda: FakeAnalysisService()
    app.dependency_overrides[get_builtin_app_service] = lambda: None

    with TestClient(app) as client:
        response = client.get(f"/analysis/app/{uuid.uuid4()}")

    assert response.status_code == 200
    assert response.json()["data"]["total_messages"]["data"] == 0

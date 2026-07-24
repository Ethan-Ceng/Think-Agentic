from datetime import datetime

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.entities.session import Session, SessionStatus
from app.core.entities.user import User
from app.dependencies import get_agent_service, get_current_user, get_session_service
from app.main import app
from app.schemas.exceptions import ConflictError, NotFoundError
from app.schemas.session import UpdateSessionOrganizationRequest


class RecordingSessionService:
    def __init__(self, *, error=None, execution_error=None) -> None:
        self.error = error
        self.execution_error = execution_error
        self.calls = []
        self.session = Session(
            id="session-1",
            user_id="user-auth",
            title="Manual title",
            title_is_manual=True,
            is_pinned=True,
            latest_message="latest",
            latest_message_at=datetime.now(),
            status=SessionStatus.COMPLETED,
        )

    async def get_all_sessions(self, user_id: str, archived: bool = False):
        self.calls.append(("get_all_sessions", user_id, archived))
        return [self.session]

    async def update_organization(self, **kwargs):
        self.calls.append(("update_organization", kwargs))
        if self.error is not None:
            raise self.error
        return self.session

    async def ensure_session_active(self, session_id: str, user_id: str):
        self.calls.append(("ensure_session_active", session_id, user_id))
        if self.execution_error is not None:
            raise self.execution_error
        return self.session


def authenticated_user() -> User:
    now = datetime.now()
    return User(
        id="user-auth",
        email="auth@example.com",
        created_at=now,
        updated_at=now,
    )


def _client(service: RecordingSessionService):
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_agent_service] = lambda: object()
    return TestClient(app)


def test_update_request_contract_trims_title_and_rejects_empty_or_conflicting_patch():
    request = UpdateSessionOrganizationRequest(title="  Manual title  ")
    assert request.title == "Manual title"
    assert request.model_fields_set == {"title"}

    for payload in ({}, {"title": "  "}, {"archived": True, "pinned": True}):
        try:
            UpdateSessionOrganizationRequest(**payload)
        except ValidationError:
            continue
        raise AssertionError(f"payload should be rejected: {payload}")


def test_list_scope_defaults_active_and_can_request_archived():
    service = RecordingSessionService()
    try:
        with _client(service) as client:
            active = client.get("/api/sessions")
            archived = client.get("/api/sessions?scope=archived")
            invalid = client.get("/api/sessions?scope=all")

        assert active.status_code == 200
        assert archived.status_code == 200
        assert invalid.status_code == 422
        assert service.calls[:2] == [
            ("get_all_sessions", "user-auth", False),
            ("get_all_sessions", "user-auth", True),
        ]
        assert active.json()["data"]["sessions"][0]["is_pinned"] is True
        assert active.json()["data"]["sessions"][0]["archived_at"] is None
        assert active.json()["data"]["sessions"][0]["has_next_message"] is False
    finally:
        app.dependency_overrides.clear()


def test_patch_route_uses_authenticated_owner_and_returns_list_item_contract():
    service = RecordingSessionService()
    try:
        with _client(service) as client:
            response = client.patch(
                "/api/sessions/session-1",
                json={"title": "  Manual title  ", "pinned": True},
            )

        assert response.status_code == 200
        assert response.json()["data"]["title"] == "Manual title"
        assert response.json()["data"]["is_pinned"] is True
        assert service.calls == [
            (
                "update_organization",
                {
                    "session_id": "session-1",
                    "user_id": "user-auth",
                    "title": "Manual title",
                    "pinned": True,
                    "archived": None,
                },
            )
        ]
    finally:
        app.dependency_overrides.clear()


def test_patch_route_exposes_stable_404_and_409_errors():
    try:
        for error, expected in (
            (NotFoundError("not found"), 404),
            (ConflictError("busy"), 409),
        ):
            service = RecordingSessionService(error=error)
            with _client(service) as client:
                response = client.patch(
                    "/api/sessions/session-1",
                    json={"archived": True},
                )
            assert response.status_code == expected
    finally:
        app.dependency_overrides.clear()


def test_archived_session_cannot_open_a_new_chat_stream():
    service = RecordingSessionService(
        execution_error=ConflictError("任务已归档，请先恢复后再继续执行")
    )
    try:
        with _client(service) as client:
            response = client.post(
                "/api/sessions/session-1/chat",
                json={"message": "continue"},
            )

        assert response.status_code == 409
        assert response.json()["msg"] == "任务已归档，请先恢复后再继续执行"
        assert service.calls == [
            ("ensure_session_active", "session-1", "user-auth"),
        ]
    finally:
        app.dependency_overrides.clear()

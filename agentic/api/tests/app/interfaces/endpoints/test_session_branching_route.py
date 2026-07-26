from datetime import datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.entities.session import (
    BranchOperation,
    NextMessage,
    Session,
    SessionStatus,
)
from app.core.entities.user import User
from app.dependencies import get_current_user, get_session_service
from app.main import app
from app.schemas.exceptions import ConflictError, NotFoundError
from app.schemas.session import CreateSessionBranchRequest


class RecordingSessionService:
    def __init__(self, *, error=None, source_available=True) -> None:
        self.error = error
        self.source_available = source_available
        self.calls = []
        self.branch = Session(
            id="branch-1",
            user_id="user-auth",
            project_id="project-1",
            title="Source · 分支",
            source_session_id="source-1",
            forked_from_event_id="event-1",
            branch_operation=BranchOperation.EDIT,
            next_message=NextMessage(message="revised"),
            status=SessionStatus.COMPLETED,
        )
        self.source = Session(
            id="source-1",
            user_id="user-auth",
            project_id="project-1",
            title="Source",
            status=SessionStatus.COMPLETED,
        )

    async def create_branch(self, **kwargs):
        self.calls.append(("create_branch", kwargs))
        if self.error is not None:
            raise self.error
        return self.branch

    async def get_session(self, session_id: str, user_id: str):
        self.calls.append(("get_session", session_id, user_id))
        return self.branch if session_id == self.branch.id else None

    async def get_branch_source(self, session_id: str, user_id: str):
        self.calls.append(("get_branch_source", session_id, user_id))
        return self.source if self.source_available else None


def authenticated_user() -> User:
    now = datetime.now()
    return User(
        id="user-auth",
        email="auth@example.com",
        created_at=now,
        updated_at=now,
    )


def _post(service: RecordingSessionService, payload: dict):
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_session_service] = lambda: service
    try:
        with TestClient(app) as client:
            return client.post("/api/sessions/source-1/branches", json=payload)
    finally:
        app.dependency_overrides.clear()


def test_branch_request_contract_trims_edit_and_forbids_message_elsewhere():
    request = CreateSessionBranchRequest(
        operation="edit",
        target_event_id="event-1",
        request_id="de305d54-75b4-431b-adb2-eb6b9e546014",
        message="  revised  ",
    )
    assert request.message == "revised"
    assert isinstance(request.request_id, UUID)

    service = RecordingSessionService()
    invalid = _post(
        service,
        {
            "operation": "fork",
            "target_event_id": "event-1",
            "request_id": "de305d54-75b4-431b-adb2-eb6b9e546014",
            "message": "not allowed",
        },
    )
    assert invalid.status_code == 422
    assert service.calls == []


def test_create_branch_route_uses_authenticated_owner_and_returns_contract():
    service = RecordingSessionService()
    response = _post(
        service,
        {
            "operation": "edit",
            "target_event_id": "event-1",
            "request_id": "de305d54-75b4-431b-adb2-eb6b9e546014",
            "message": "revised",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "session_id": "branch-1",
        "source_session_id": "source-1",
        "forked_from_event_id": "event-1",
        "operation": "edit",
        "queued": True,
    }
    assert service.calls[0][1]["user_id"] == "user-auth"
    assert service.calls[0][1]["request_id"] == "de305d54-75b4-431b-adb2-eb6b9e546014"


def test_create_branch_route_exposes_stable_404_and_409_errors():
    payload = {
        "operation": "fork",
        "target_event_id": "event-1",
        "request_id": "de305d54-75b4-431b-adb2-eb6b9e546014",
    }
    assert _post(
        RecordingSessionService(error=NotFoundError("not found")),
        payload,
    ).status_code == 404
    assert _post(
        RecordingSessionService(error=ConflictError("conflict")),
        payload,
    ).status_code == 409


def test_session_detail_only_returns_navigable_owned_source():
    service = RecordingSessionService(source_available=True)
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_session_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/sessions/branch-1")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["source_session_id"] == "source-1"
        assert data["source_session_title"] == "Source"
        assert data["forked_from_event_id"] == "event-1"
        assert data["branch_operation"] == "edit"
        assert data["project_id"] == "project-1"

        service.source_available = False
        with TestClient(app) as client:
            hidden = client.get("/api/sessions/branch-1")
        hidden_data = hidden.json()["data"]
        assert hidden_data["source_session_id"] is None
        assert hidden_data["source_session_title"] is None
        assert hidden_data["branch_operation"] == "edit"
    finally:
        app.dependency_overrides.clear()

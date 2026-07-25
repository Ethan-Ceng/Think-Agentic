from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.entities.user import User
from app.dependencies import get_current_user, get_session_service
from app.main import app
from app.schemas.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.session import BranchFamilyResponse, BranchFamilyVariantResponse


_CREATED_AT = datetime(2026, 7, 25, 10, 0, 0)


class RecordingSessionService:
    def __init__(self, *, error=None) -> None:
        self.error = error
        self.calls = []
        self.response = BranchFamilyResponse(
            source_session_id="source-1",
            target_event_id="event-1",
            current_session_id="branch-1",
            variants=[
                BranchFamilyVariantResponse(
                    session_id="source-1",
                    title="Source",
                    operation="original",
                    status="completed",
                    archived_at=None,
                    created_at=_CREATED_AT,
                    is_current=False,
                ),
                BranchFamilyVariantResponse(
                    session_id="branch-1",
                    title="Source · 分支",
                    operation="regenerate",
                    status="completed",
                    archived_at=_CREATED_AT + timedelta(days=1),
                    created_at=_CREATED_AT + timedelta(minutes=1),
                    is_current=True,
                ),
            ],
        )

    async def get_branch_family(self, **kwargs):
        self.calls.append(("get_branch_family", kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def authenticated_user() -> User:
    now = datetime.now()
    return User(
        id="user-auth",
        email="auth@example.com",
        created_at=now,
        updated_at=now,
    )


def _get(service: RecordingSessionService, query: str = ""):
    app.dependency_overrides[get_current_user] = authenticated_user
    app.dependency_overrides[get_session_service] = lambda: service
    try:
        with TestClient(app) as client:
            return client.get(
                f"/api/sessions/branch-1/branch-family{query}"
            )
    finally:
        app.dependency_overrides.clear()


def test_branch_family_route_uses_authenticated_owner_and_returns_contract():
    service = RecordingSessionService()

    response = _get(service, "?target_event_id=event-1")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source_session_id"] == "source-1"
    assert data["target_event_id"] == "event-1"
    assert data["current_session_id"] == "branch-1"
    assert data["variants"] == [
        {
            "session_id": "source-1",
            "title": "Source",
            "operation": "original",
            "status": "completed",
            "archived_at": None,
            "created_at": "2026-07-25T10:00:00",
            "is_current": False,
        },
        {
            "session_id": "branch-1",
            "title": "Source · 分支",
            "operation": "regenerate",
            "status": "completed",
            "archived_at": "2026-07-26T10:00:00",
            "created_at": "2026-07-25T10:01:00",
            "is_current": True,
        },
    ]
    assert service.calls == [
        (
            "get_branch_family",
            {
                "session_id": "branch-1",
                "user_id": "user-auth",
                "target_event_id": "event-1",
            },
        )
    ]


def test_branch_family_route_allows_child_lineage_inference():
    service = RecordingSessionService()

    response = _get(service)

    assert response.status_code == 200
    assert service.calls[0][1]["target_event_id"] is None


def test_branch_family_route_rejects_invalid_query_shape_before_service():
    service = RecordingSessionService()

    assert _get(service, "?target_event_id=").status_code == 422
    assert _get(service, f"?target_event_id={'x' * 256}").status_code == 422
    assert service.calls == []


def test_branch_family_route_exposes_stable_repository_error_contract():
    assert _get(
        RecordingSessionService(error=NotFoundError("not found"))
    ).status_code == 404
    assert _get(
        RecordingSessionService(error=ConflictError("conflict"))
    ).status_code == 409
    assert _get(
        RecordingSessionService(error=ValidationError("invalid"))
    ).status_code == 422

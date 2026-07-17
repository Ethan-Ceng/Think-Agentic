import asyncio

from app.controllers import runs
from app.core.entities.user import User
from app.main import app


class RecordingTraceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def list_run_skills(self, user_id: str, run_id: str):
        self.calls.append((user_id, run_id))
        return [{"id": "run-skill-1", "run_id": run_id, "name": "report-writer"}]


def test_run_skill_route_is_registered() -> None:
    matching = [
        route
        for route in app.routes
        if getattr(route, "path", "") == "/api/runs/{run_id}/skills"
    ]
    assert len(matching) == 1
    assert "GET" in matching[0].methods


def test_run_skill_endpoint_uses_authenticated_user() -> None:
    service = RecordingTraceService()
    response = asyncio.run(
        runs.list_run_skills(
            run_id="run-1",
            current_user=User(
                id="user-1",
                username="trace-user",
                email="trace@example.com",
            ),
            service=service,
        )
    )

    assert service.calls == [("user-1", "run-1")]
    assert response.data["skills"][0]["name"] == "report-writer"

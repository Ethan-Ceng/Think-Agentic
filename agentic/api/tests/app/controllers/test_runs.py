from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.controllers.runs import (
    list_run_events,
    list_run_model_calls,
    list_run_tool_calls,
)


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeTraceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, object, int]] = []

    async def list_events(self, user_id, run_id, *, after=None, limit=200):
        self.calls.append(("events", user_id, run_id, after, limit))
        return {"events": [{"ingest_seq": 8}], "next_cursor": 8, "has_more": False}

    async def list_tool_calls(self, user_id, run_id, *, after=None, limit=200):
        self.calls.append(("tools", user_id, run_id, after, limit))
        return {"tool_calls": [{"id": "tool-2"}], "next_cursor": "tool-2", "has_more": False}

    async def list_model_calls(self, user_id, run_id, *, after=None, limit=200):
        self.calls.append(("models", user_id, run_id, after, limit))
        return {"model_calls": [{"id": "model-2"}], "next_cursor": "model-2", "has_more": False}


async def test_trace_subresources_forward_independent_cursors_and_limits() -> None:
    service = FakeTraceService()
    user = SimpleNamespace(id="user-1")

    events = await list_run_events(
        run_id="run-1",
        after=7,
        limit=10,
        current_user=user,
        service=service,
    )
    tools = await list_run_tool_calls(
        run_id="run-1",
        after="tool-1",
        limit=11,
        current_user=user,
        service=service,
    )
    models = await list_run_model_calls(
        run_id="run-1",
        after="model-1",
        limit=12,
        current_user=user,
        service=service,
    )

    assert service.calls == [
        ("events", "user-1", "run-1", 7, 10),
        ("tools", "user-1", "run-1", "tool-1", 11),
        ("models", "user-1", "run-1", "model-1", 12),
    ]
    assert events.data["next_cursor"] == 8
    assert tools.data["next_cursor"] == "tool-2"
    assert models.data["next_cursor"] == "model-2"

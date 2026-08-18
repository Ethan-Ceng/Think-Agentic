from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.controllers.session import chat as chat_endpoint
from app.core.entities.event import DoneEvent, MessageDeltaEvent, MessageEvent
from app.schemas.session import ChatRequest


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeSessionService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def ensure_session_active(self, session_id: str, user_id: str) -> None:
        self.calls.append((session_id, user_id))


class FakeAgentService:
    def __init__(self) -> None:
        self.kwargs = None

    async def chat(self, **kwargs):
        self.kwargs = kwargs
        yield MessageDeltaEvent(
            stream_id="stream-1",
            sequence=0,
            delta="Hel",
        )
        yield MessageEvent(
            role="assistant",
            message="Hello",
            stream_id="stream-1",
        )
        yield DoneEvent()


async def test_chat_endpoint_serializes_message_delta_and_forwards_replay_cursor() -> None:
    agent_service = FakeAgentService()
    session_service = FakeSessionService()

    response = await chat_endpoint(
        session_id="session-1",
        request=ChatRequest(message="hello", event_id="output-8"),
        current_user=SimpleNamespace(id="user-1"),
        agent_service=agent_service,
        session_service=session_service,
    )
    events = [event async for event in response.body_iterator]

    assert [event.event for event in events] == [
        "message_delta",
        "message",
        "done",
    ]
    delta = json.loads(events[0].data)
    final = json.loads(events[1].data)
    assert delta["stream_id"] == final["stream_id"] == "stream-1"
    assert delta["delta"] == "Hel"
    assert agent_service.kwargs["latest_event_id"] == "output-8"
    assert session_service.calls == [("session-1", "user-1")]


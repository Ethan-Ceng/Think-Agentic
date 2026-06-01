import uuid
from datetime import datetime
from types import SimpleNamespace

from app.schemas.conversation import MessageResponse


def test_message_response_serializes_agent_thoughts() -> None:
    thought = SimpleNamespace(
        id=uuid.uuid4(),
        position=1,
        event="agent_message",
        thought="thinking",
        observation="",
        tool="",
        tool_input={"query": "hi"},
        latency=0.1,
        created_at=datetime(2024, 1, 1),
    )
    message = SimpleNamespace(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        query="hi",
        image_urls=[],
        answer="hello",
        total_token_count=2,
        latency=0.2,
        agent_thoughts=[thought],
        created_at=datetime(2024, 1, 1),
    )

    response = MessageResponse.from_message(message)

    assert response.answer == "hello"
    assert response.agent_thoughts[0]["tool_input"] == {"query": "hi"}


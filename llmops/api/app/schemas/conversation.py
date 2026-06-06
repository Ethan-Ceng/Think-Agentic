from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.conversation import Message


def datetime_to_timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    return int(value.timestamp())


class UpdateConversationNameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UpdateConversationIsPinnedRequest(BaseModel):
    is_pinned: bool = False


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    query: str = ""
    image_urls: list[str] = Field(default_factory=list)
    answer: str = ""
    total_token_count: int = 0
    latency: float = 0.0
    agent_thoughts: list[dict] = Field(default_factory=list)
    runtime_events: list[dict] = Field(default_factory=list)
    created_at: int = 0

    @classmethod
    def from_message(cls, message: Message) -> "MessageResponse":
        return cls(
            id=message.id,
            conversation_id=message.conversation_id,
            query=message.query or "",
            image_urls=message.image_urls or [],
            answer=message.answer or "",
            total_token_count=message.total_token_count or 0,
            latency=float(message.latency or 0),
            agent_thoughts=[
                {
                    "id": str(thought.id),
                    "position": thought.position,
                    "event": thought.event,
                    "thought": thought.thought or "",
                    "observation": thought.observation or "",
                    "tool": thought.tool or "",
                    "tool_input": thought.tool_input or {},
                    "latency": float(thought.latency or 0),
                    "created_at": datetime_to_timestamp(thought.created_at),
                }
                for thought in (message.agent_thoughts or [])
            ],
            created_at=datetime_to_timestamp(message.created_at),
        )


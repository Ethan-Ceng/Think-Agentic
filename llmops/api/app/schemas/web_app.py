from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.conversation import Conversation
from app.schemas.conversation import datetime_to_timestamp


class WebAppChatRequest(BaseModel):
    conversation_id: UUID | None = None
    query: str = Field(..., min_length=1)
    image_urls: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("image_urls")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        for image_url in value:
            if not image_url.startswith(("http://", "https://")):
                raise ValueError("image_urls must contain HTTP URLs")
        return value


class GetWebAppConversationsRequest(BaseModel):
    is_pinned: bool = False


class WebAppConversationResponse(BaseModel):
    id: UUID
    name: str
    summary: str
    created_at: int

    @classmethod
    def from_conversation(cls, conversation: Conversation) -> "WebAppConversationResponse":
        return cls(
            id=conversation.id,
            name=conversation.name,
            summary=conversation.summary,
            created_at=datetime_to_timestamp(conversation.created_at),
        )

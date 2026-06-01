from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.conversation import Message
from app.schemas.conversation import MessageResponse


class AssistantAgentChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    image_urls: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("image_urls")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        for image_url in value:
            if not image_url.startswith(("http://", "https://")):
                raise ValueError("image_urls must contain HTTP URLs")
        return value


class GetAssistantAgentMessagesWithPageRequest(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    created_at: int = Field(0, ge=0)


class AssistantAgentMessageResponse(MessageResponse):
    id: UUID

    @classmethod
    def from_message(cls, message: Message) -> "AssistantAgentMessageResponse":
        return cls(**MessageResponse.from_message(message).model_dump())

from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class OpenAPIChatRequest(BaseModel):
    app_id: UUID
    end_user_id: UUID | None = None
    conversation_id: UUID | None = None
    resume_task_id: UUID | None = None
    query: str = Field(..., min_length=1)
    image_urls: list[str] = Field(default_factory=list, max_length=5)
    stream: bool = True

    @model_validator(mode="after")
    def validate_conversation_owner(self) -> "OpenAPIChatRequest":
        if self.conversation_id and not self.end_user_id:
            raise ValueError("end_user_id is required when conversation_id is provided")
        return self

    @field_validator("image_urls")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        for image_url in value:
            if not image_url.startswith(("http://", "https://")):
                raise ValueError("image_urls must contain HTTP URLs")
        return value

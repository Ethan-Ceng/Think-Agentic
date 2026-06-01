from uuid import UUID

from pydantic import BaseModel, Field


class GenerateSuggestedQuestionsRequest(BaseModel):
    message_id: UUID


class OptimizePromptRequest(BaseModel):
    prompt: str = Field(..., max_length=2000)

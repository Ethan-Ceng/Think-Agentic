from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class LLMProviderCreateRequest(BaseModel):
    provider: str
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    enabled: bool = True
    is_default: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class LLMProviderUpdateRequest(BaseModel):
    provider: str | None = None
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    config: dict[str, Any] | None = None


class LLMSyncSystemProvidersRequest(BaseModel):
    reset: bool = False


class LLMModelCreateRequest(BaseModel):
    model: str
    display_name: str = ""
    model_type: str = "chat"
    features: list[str] = Field(default_factory=list)
    context_window: int = 0
    max_output_tokens: int = 0
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    is_default: bool = False


class LLMModelUpdateRequest(BaseModel):
    model: str | None = None
    display_name: str | None = None
    model_type: str | None = None
    features: list[str] | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    default_parameters: dict[str, Any] | None = None
    enabled: bool | None = None
    is_default: bool | None = None


class LLMModelResponse(BaseModel):
    id: UUID
    account_id: UUID
    provider_id: UUID
    model: str
    display_name: str
    model_type: str
    features: list[str]
    context_window: int
    max_output_tokens: int
    default_parameters: dict[str, Any]
    enabled: bool
    is_default: bool
    created_at: int = 0
    updated_at: int = 0

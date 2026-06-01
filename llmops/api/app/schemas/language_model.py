from typing import Any

from pydantic import BaseModel, Field


class LanguageModelParameterOption(BaseModel):
    label: str
    value: Any


class LanguageModelParameter(BaseModel):
    name: str
    label: str
    type: str
    help: str = ""
    required: bool = False
    default: Any | None = None
    min: float | None = None
    max: float | None = None
    precision: int = 2
    options: list[LanguageModelParameterOption] = Field(default_factory=list)


class LanguageModelDetail(BaseModel):
    model_name: str
    model: str
    label: str
    model_type: str
    features: list[str] = Field(default_factory=list)
    context_window: int = 0
    context_windows: int = 0
    max_output_tokens: int = 0
    attributes: dict[str, Any] = Field(default_factory=dict)
    parameters: list[LanguageModelParameter] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LanguageModelProvider(BaseModel):
    name: str
    position: int
    label: str
    icon: str
    description: str
    background: str
    support_model_types: list[str]
    models: list[LanguageModelDetail] = Field(default_factory=list)


class LanguageModelsResponse(BaseModel):
    data: list[LanguageModelProvider]


class LanguageModelResponse(BaseModel):
    data: LanguageModelDetail

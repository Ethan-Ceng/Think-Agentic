from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DefaultModelParameterName(StrEnum):
    TEMPERATURE = "temperature"
    TOP_P = "top_p"
    PRESENCE_PENALTY = "presence_penalty"
    FREQUENCY_PENALTY = "frequency_penalty"
    MAX_TOKENS = "max_tokens"


class ModelType(StrEnum):
    CHAT = "chat"
    COMPLETION = "completion"


class ModelParameterType(StrEnum):
    FLOAT = "float"
    INT = "int"
    STRING = "string"
    BOOLEAN = "boolean"


class ModelParameterOption(BaseModel):
    label: str
    value: Any


class ModelParameter(BaseModel):
    name: str = ""
    label: str = ""
    type: ModelParameterType = ModelParameterType.STRING
    help: str = ""
    required: bool = False
    default: Any | None = None
    min: float | None = None
    max: float | None = None
    precision: int = 2
    options: list[ModelParameterOption] = Field(default_factory=list)


class ModelFeature(StrEnum):
    TOOL_CALL = "tool_call"
    AGENT_THOUGHT = "agent_thought"
    IMAGE_INPUT = "image_input"


class ModelEntity(BaseModel):
    model_name: str = Field(default="", alias="model")
    label: str = ""
    model_type: ModelType = ModelType.CHAT
    features: list[ModelFeature] = Field(default_factory=list)
    context_window: int = 0
    max_output_tokens: int = 0
    attributes: dict[str, Any] = Field(default_factory=dict)
    parameters: list[ModelParameter] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)

    def to_legacy_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["model"] = self.model_name
        data["context_windows"] = self.context_window
        return data


class BaseLanguageModel(BaseModel):
    provider: str = ""
    model: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    features: list[ModelFeature] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_pricing(self) -> tuple[float, float, float]:
        pricing = self.metadata.get("pricing", {})
        return (
            float(pricing.get("input", 0.0) or 0.0),
            float(pricing.get("output", 0.0) or 0.0),
            float(pricing.get("unit", 0.0) or 0.0),
        )

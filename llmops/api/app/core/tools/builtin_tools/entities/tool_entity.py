from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolParamType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    SELECT = "select"


class ToolParam(BaseModel):
    name: str
    label: str
    type: ToolParamType
    required: bool = False
    default: Any | None = None
    min: float | None = None
    max: float | None = None
    options: list[dict[str, Any]] = Field(default_factory=list)


class ToolEntity(BaseModel):
    name: str
    label: str
    description: str
    params: list[ToolParam] = Field(default_factory=list)


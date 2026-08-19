from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from app.core.entities.plan import Step


class LeadMode(str, Enum):
    DIRECT = "direct"
    REACT = "react"
    PLAN = "plan"


class _DecisionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    language: str

    @field_validator("title", "language")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized


class DirectDecision(_DecisionBase):
    mode: Literal["direct"] = "direct"
    answer: str

    @field_validator("answer")
    @classmethod
    def require_answer(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("answer must not be empty")
        return normalized


class ReactDecision(_DecisionBase):
    mode: Literal["react"] = "react"
    goal: str
    capabilities: list[str] = Field(default_factory=list)
    provider_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)

    @field_validator("goal")
    @classmethod
    def require_goal(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("goal must not be empty")
        return normalized

    @field_validator("capabilities", "provider_ids", "tool_ids")
    @classmethod
    def normalize_scope_values(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            capability = str(value).strip()
            if capability and capability not in normalized:
                normalized.append(capability)
        return normalized


class PlanDecision(_DecisionBase):
    mode: Literal["plan"] = "plan"
    goal: str
    message: str = ""
    steps: list[Step] = Field(min_length=1)

    @field_validator("goal")
    @classmethod
    def require_goal(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("goal must not be empty")
        return normalized

    @field_validator("steps")
    @classmethod
    def require_step_descriptions(cls, steps: list[Step]) -> list[Step]:
        if any(not step.description.strip() for step in steps):
            raise ValueError("step descriptions must not be empty")
        return steps


LeadDecision = Annotated[
    Union[DirectDecision, ReactDecision, PlanDecision],
    Field(discriminator="mode"),
]

LEAD_DECISION_ADAPTER: TypeAdapter[LeadDecision] = TypeAdapter(LeadDecision)


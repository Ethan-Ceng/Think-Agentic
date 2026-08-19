"""Public request and result models for on-demand Provider diagnostics."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.entities.failure import FailureInfo


class ProviderType(str, Enum):
    LLM = "llm"
    MCP = "mcp"
    A2A = "a2a"
    API = "api"


class ProviderCheckKind(str, Enum):
    INFERENCE = "inference"
    DISCOVERY = "discovery"
    CONFIGURATION = "configuration"


class ProviderDiagnosticStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ProviderDiagnosticRequest(BaseModel):
    provider_type: ProviderType
    target_id: str | None = Field(default=None, max_length=160)

    model_config = ConfigDict(extra="forbid")
    @model_validator(mode="after")
    def validate_target(self) -> "ProviderDiagnosticRequest":
        if self.target_id is not None:
            self.target_id = self.target_id.strip()
        if self.provider_type is ProviderType.LLM:
            if self.target_id:
                raise ValueError("LLM diagnostics do not accept target_id")
            self.target_id = None
            return self
        if not self.target_id:
            raise ValueError(f"{self.provider_type.value} diagnostics require target_id")
        if any(not character.isprintable() for character in self.target_id):
            raise ValueError("target_id must contain printable characters only")
        return self


class ProviderDiagnosticResult(BaseModel):
    provider_type: ProviderType
    provider_id: str = Field(min_length=1, max_length=160)
    check_kind: ProviderCheckKind
    status: ProviderDiagnosticStatus
    message: str = Field(min_length=1, max_length=300)
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    latency_ms: int = Field(ge=0, le=3_600_000)
    capability_count: int | None = Field(default=None, ge=0)
    snapshot_state: Literal["fresh", "stale"] | None = None
    failure: FailureInfo | None = None

    model_config = ConfigDict(extra="forbid")

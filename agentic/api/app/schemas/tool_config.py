#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolBinding(BaseModel):
    enabled: bool = True
    risk_level: str = "low"
    execution_policy: Literal["allow", "deny"] = "allow"
    params: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_approval(cls, data):
        if not isinstance(data, dict) or "execution_policy" in data:
            return data
        migrated = dict(data)
        migrated["execution_policy"] = (
            "deny" if migrated.get("approval") == "deny" else "allow"
        )
        return migrated


class ToolBindingUpdate(BaseModel):
    """Terminal-user fields; platform execution policy is deliberately read-only."""

    enabled: bool = True
    risk_level: str = "low"
    params: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class RuntimeToolPolicy(BaseModel):
    allowed_executor_types: List[str] = Field(
        default_factory=lambda: ["builtin", "mcp", "a2a", "api"]
    )
    max_tool_iterations: int = Field(default=100, ge=1, le=1000)
    max_external_tool_schemas: int = Field(default=32, ge=1, le=256)
    max_external_schema_chars: int = Field(default=60000, ge=1000, le=500000)
    external_tool_search_top_k: int = Field(default=8, ge=1, le=32)

    model_config = ConfigDict(extra="ignore")


class RuntimeToolPolicyUpdate(BaseModel):
    allowed_executor_types: List[str] = Field(
        default_factory=lambda: ["builtin", "mcp", "a2a", "api"]
    )
    max_tool_iterations: int = Field(default=100, ge=1, le=1000)
    max_external_tool_schemas: int = Field(default=32, ge=1, le=256)
    max_external_schema_chars: int = Field(default=60000, ge=1000, le=500000)
    external_tool_search_top_k: int = Field(default=8, ge=1, le=32)

    model_config = ConfigDict(extra="forbid")


class ToolRegistration(BaseModel):
    registration_id: str
    provider_id: str
    provider_label: str
    source_type: str = "api"
    executor_type: str = "api"
    group: str = "custom"
    category: str = "自定义"
    description: str = ""
    enabled: bool = True
    builtin: bool = False
    editable: bool = True
    requires_sandbox: bool = False
    requires_browser: bool = False
    requires_credentials: bool = False
    config: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class ToolConfig(BaseModel):
    schema_version: str = "tool_config_v2"
    mode: str = "default_allow"
    bindings: Dict[str, ToolBinding] = Field(default_factory=dict)
    registrations: Dict[str, ToolRegistration] = Field(default_factory=dict)
    runtime_policy: RuntimeToolPolicy = Field(default_factory=RuntimeToolPolicy)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def migrate_schema_version(cls, data):
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        if migrated.get("schema_version") in {None, "tool_config_v1"}:
            migrated["schema_version"] = "tool_config_v2"
        return migrated


class ToolDescriptor(BaseModel):
    tool_id: str
    function_name: str
    provider_id: str
    provider_label: str
    group: str
    executor_type: str
    source_type: Literal["builtin", "api", "mcp", "a2a"] = "builtin"
    execution_backend: Literal[
        "in_process",
        "sandbox",
        "sandbox_browser",
        "remote_http",
        "external_provider",
        "delegation",
    ] = "in_process"
    resource_requirements: List[
        Literal["sandbox", "browser", "network", "credentials"]
    ] = Field(default_factory=list)
    execution_class: Literal[
        "sandbox_local",
        "external_read",
        "external_write",
        "delegation",
        "platform_forbidden",
    ] = "external_read"
    generality: Literal["specialized", "general_fallback"] = "specialized"
    cost_class: Literal["low", "medium", "high"] = "low"
    label: str
    description: str
    tool_schema: Dict[str, Any] = Field(alias="schema")
    category: str
    risk_level: str
    requires_sandbox: bool = False
    requires_browser: bool = False
    requires_credentials: bool = False
    enabled_by_default: bool = True
    enabled: bool = True

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_execution_metadata(cls, data):
        """Derive the new orthogonal metadata from legacy descriptor fields."""
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        provider_id = str(migrated.get("provider_id") or "")
        executor_type = str(migrated.get("executor_type") or "builtin")
        function_name = str(migrated.get("function_name") or "")
        requires_sandbox = bool(migrated.get("requires_sandbox"))
        requires_browser = bool(migrated.get("requires_browser"))
        requires_credentials = bool(migrated.get("requires_credentials"))

        if "source_type" not in migrated:
            source_type = executor_type if executor_type in {"api", "mcp", "a2a"} else "builtin"
            if provider_id.startswith("api."):
                source_type = "api"
            elif provider_id.startswith("mcp."):
                source_type = "mcp"
            elif provider_id.startswith("a2a."):
                source_type = "a2a"
            migrated["source_type"] = source_type

        if "execution_backend" not in migrated:
            if requires_browser:
                execution_backend = "sandbox_browser"
            elif requires_sandbox:
                execution_backend = "sandbox"
            elif migrated["source_type"] == "a2a":
                execution_backend = "delegation"
            elif migrated["source_type"] == "mcp":
                execution_backend = "external_provider"
            elif migrated["source_type"] == "api":
                execution_backend = "remote_http"
            else:
                execution_backend = "in_process"
            migrated["execution_backend"] = execution_backend

        if "resource_requirements" not in migrated:
            requirements = []
            if requires_sandbox or requires_browser:
                requirements.append("sandbox")
            if requires_browser:
                requirements.append("browser")
            if migrated["execution_backend"] in {
                "remote_http",
                "external_provider",
                "delegation",
            }:
                requirements.append("network")
            if requires_credentials:
                requirements.append("credentials")
            migrated["resource_requirements"] = requirements

        if "execution_class" not in migrated:
            backend = migrated["execution_backend"]
            if backend in {"sandbox", "sandbox_browser"}:
                execution_class = "sandbox_local"
            elif backend == "delegation":
                execution_class = "delegation"
            else:
                execution_class = "external_read"
            migrated["execution_class"] = execution_class

        if "generality" not in migrated and function_name in {
            "shell_execute",
            "browser_console_exec",
        }:
            migrated["generality"] = "general_fallback"

        if "cost_class" not in migrated:
            backend = migrated["execution_backend"]
            migrated["cost_class"] = (
                "high"
                if backend == "sandbox_browser"
                else "medium"
                if backend in {"sandbox", "remote_http", "external_provider", "delegation"}
                else "low"
            )
        return migrated


class ProviderDescriptor(BaseModel):
    """Safe Catalog metadata for one execution/delegation provider."""

    provider_id: str
    provider_type: Literal["builtin", "api", "mcp", "a2a"]
    label: str
    description: str = ""
    capability_groups: List[str] = Field(default_factory=list)
    semantic_tags: List[str] = Field(default_factory=list)
    metadata_trust: Literal[
        "platform_static",
        "untrusted_configuration",
    ] = "platform_static"
    enabled: bool = True
    credential_state: Literal["not_required", "configured", "missing"] = (
        "not_required"
    )
    snapshot_state: Literal["missing", "fresh", "stale"] = "missing"
    health_state: Literal[
        "unknown",
        "healthy",
        "degraded",
        "unhealthy",
    ] = "unknown"

    model_config = ConfigDict(extra="forbid")


class ToolListResponse(BaseModel):
    tools: List[ToolDescriptor]
    registrations: List[ToolRegistration] = Field(default_factory=list)
    runtime_policy: RuntimeToolPolicy


class ToolBindingsUpdate(BaseModel):
    bindings: Dict[str, ToolBindingUpdate] = Field(default_factory=dict)
    runtime_policy: RuntimeToolPolicyUpdate = Field(
        default_factory=RuntimeToolPolicyUpdate
    )

    model_config = ConfigDict(extra="forbid")


class ToolRegistrationCreate(BaseModel):
    provider_id: str
    provider_label: str
    source_type: str = "api"
    executor_type: str = "api"
    group: str = "custom"
    category: str = "自定义"
    description: str = ""
    enabled: bool = True
    requires_sandbox: bool = False
    requires_browser: bool = False
    requires_credentials: bool = False
    config: Dict[str, Any] = Field(default_factory=dict)


class ToolRegistrationUpdate(BaseModel):
    provider_label: str | None = None
    source_type: str | None = None
    executor_type: str | None = None
    group: str | None = None
    category: str | None = None
    description: str | None = None
    enabled: bool | None = None
    requires_sandbox: bool | None = None
    requires_browser: bool | None = None
    requires_credentials: bool | None = None
    config: Dict[str, Any] | None = None


class ToolRegistrationListResponse(BaseModel):
    registrations: List[ToolRegistration]


class ToolRegistrationTestRequest(BaseModel):
    function_name: str | None = None
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolRegistrationTestResponse(BaseModel):
    registration: ToolRegistration
    tools: List[ToolDescriptor] = Field(default_factory=list)
    selected_tool: ToolDescriptor | None = None
    result: Dict[str, Any] | None = None


class ToolPreflightRequest(BaseModel):
    message: str
    input_modalities: List[str] = Field(default_factory=lambda: ["text/plain"])


class ToolPreflightCheck(BaseModel):
    rule_id: str
    passed: bool
    error_code: str | None = None
    user_message: str


class ToolCapabilitySummary(BaseModel):
    schema_version: str = "tool_capability_v1"
    executor_types: List[str] = Field(default_factory=list)
    input_modalities: List[str] = Field(default_factory=lambda: ["text/plain"])
    output_modalities: List[str] = Field(default_factory=lambda: ["text/plain"])
    semantic_tags: List[str] = Field(default_factory=list)
    tool_names: List[str] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    generated_at: int


class ToolPreflightResponse(BaseModel):
    status: str
    checks: List[ToolPreflightCheck]
    capability_snapshot: ToolCapabilitySummary

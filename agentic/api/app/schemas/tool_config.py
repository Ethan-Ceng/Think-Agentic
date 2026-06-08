#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class ToolBinding(BaseModel):
    enabled: bool = True
    risk_level: str = "low"
    params: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class RuntimeToolPolicy(BaseModel):
    allowed_executor_types: List[str] = Field(
        default_factory=lambda: ["builtin", "mcp", "a2a", "api"]
    )
    max_tool_iterations: int = Field(default=100, ge=1, le=1000)

    model_config = ConfigDict(extra="ignore")


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
    schema_version: str = "tool_config_v1"
    mode: str = "default_allow"
    bindings: Dict[str, ToolBinding] = Field(default_factory=dict)
    registrations: Dict[str, ToolRegistration] = Field(default_factory=dict)
    runtime_policy: RuntimeToolPolicy = Field(default_factory=RuntimeToolPolicy)

    model_config = ConfigDict(extra="allow")


class ToolDescriptor(BaseModel):
    tool_id: str
    function_name: str
    provider_id: str
    provider_label: str
    group: str
    executor_type: str
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


class ToolListResponse(BaseModel):
    tools: List[ToolDescriptor]
    registrations: List[ToolRegistration] = Field(default_factory=list)
    runtime_policy: RuntimeToolPolicy


class ToolBindingsUpdate(BaseModel):
    bindings: Dict[str, ToolBinding] = Field(default_factory=dict)
    runtime_policy: RuntimeToolPolicy = Field(default_factory=RuntimeToolPolicy)


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

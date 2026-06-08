#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class ToolBinding(BaseModel):
    """单个工具的运行时绑定配置"""

    enabled: bool = True
    risk_level: str = "low"  # low | medium | high
    params: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class RuntimeToolPolicy(BaseModel):
    """工具运行时策略"""

    allowed_executor_types: List[str] = Field(
        default_factory=lambda: ["builtin", "mcp", "a2a", "api"]
    )
    max_tool_iterations: int = Field(default=100, ge=1, le=1000)

    model_config = ConfigDict(extra="ignore")


class ToolRegistration(BaseModel):
    """工具源注册配置"""

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
    """工具管理配置"""

    schema_version: str = "tool_config_v1"
    mode: str = "default_allow"
    bindings: Dict[str, ToolBinding] = Field(default_factory=dict)
    registrations: Dict[str, ToolRegistration] = Field(default_factory=dict)
    runtime_policy: RuntimeToolPolicy = Field(default_factory=RuntimeToolPolicy)

    model_config = ConfigDict(extra="allow")

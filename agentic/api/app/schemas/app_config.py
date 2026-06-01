#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
App Config Models - 应用配置的 Pydantic 模型
（从 domain/models/app_config.py 迁移，纯数据模型）
"""
import uuid
from enum import Enum
from typing import Dict, Optional, List, Any

from pydantic import BaseModel, Field, ConfigDict, model_validator


class LLMConfig(BaseModel):
    """LLM提供商配置"""
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    model_name: str = "deepseek-v4-pro"
    temperature: float = Field(0.7)
    max_tokens: int = Field(8192, ge=0)


class AgentConfig(BaseModel):
    """Agent通用配置"""
    max_iterations: int = Field(default=100, gt=0, lt=1000)
    max_retries: int = Field(default=3, gt=1, lt=10)
    max_search_results: int = Field(default=10, gt=1, lt=30)


class MCPTransport(str, Enum):
    """MCP传输类型枚举"""
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class MCPServerConfig(BaseModel):
    """MCP服务配置"""
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    enabled: bool = True
    description: Optional[str] = None
    env: Optional[Dict[str, Any]] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_mcp_server_config(self):
        if self.transport in [MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP]:
            if not self.url:
                raise ValueError("在sse或streamable_http模式下必须传递url")
        if self.transport == MCPTransport.STDIO:
            if not self.command:
                raise ValueError("在stdio模式下必须传递command")
        return self


class MCPConfig(BaseModel):
    """应用MCP配置"""
    mcpServers: Dict[str, MCPServerConfig] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class A2AServerConfig(BaseModel):
    """A2A服务配置"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    base_url: str
    enabled: bool = True


class A2AConfig(BaseModel):
    """A2A配置"""
    a2a_servers: List[A2AServerConfig] = Field(default_factory=list)


class AppConfig(BaseModel):
    """应用配置信息"""
    llm_config: LLMConfig = Field(default_factory=LLMConfig)
    agent_config: AgentConfig = Field(default_factory=AgentConfig)
    mcp_config: MCPConfig = Field(default_factory=MCPConfig)
    a2a_config: A2AConfig = Field(default_factory=A2AConfig)

    model_config = ConfigDict(extra="allow")

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
App Config Service - 基于YAML文件的配置管理
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

import yaml

from app.schemas.app_config import (
    AppConfig,
    LLMConfig,
    AgentConfig,
    MCPConfig,
    A2AConfig,
    A2AServerConfig,
)
from app.core.config import get_settings
from app.schemas.tool_config import ToolConfig

logger = logging.getLogger(__name__)


class AppConfigService:
    """应用配置服务 - 基于YAML文件"""

    def __init__(self):
        self._settings = get_settings()
        self._config_path = Path(self._settings.app_config_filepath)
        self._lock = asyncio.Lock()

    def _load(self) -> AppConfig:
        """从YAML文件加载配置"""
        if not self._config_path.exists():
            logger.warning(f"配置文件不存在: {self._config_path}，返回默认配置")
            return AppConfig()

        with self._config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return AppConfig.model_validate(data)

    def _save(self, config: AppConfig) -> None:
        """将配置保存到YAML文件"""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with self._config_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                config.model_dump(mode="json"),
                f,
                allow_unicode=True,
                sort_keys=False,
            )

    # ---------- LLM ----------
    async def get_llm_config(self) -> LLMConfig:
        async with self._lock:
            return self._load().llm_config

    async def update_llm_config(self, new_config: LLMConfig) -> LLMConfig:
        async with self._lock:
            cfg = self._load()
            # api_key 为空时保留原值
            merged = new_config.model_dump()
            if not merged.get("api_key"):
                merged["api_key"] = cfg.llm_config.api_key
            cfg.llm_config = LLMConfig.model_validate(merged)
            self._save(cfg)
            return cfg.llm_config

    # ---------- Agent ----------
    async def get_agent_config(self) -> AgentConfig:
        async with self._lock:
            return self._load().agent_config

    async def update_agent_config(self, new_config: AgentConfig) -> AgentConfig:
        async with self._lock:
            cfg = self._load()
            cfg.agent_config = new_config
            self._save(cfg)
            return cfg.agent_config

    # ---------- MCP ----------
    async def get_mcp_config(self) -> MCPConfig:
        async with self._lock:
            return self._load().mcp_config

    async def add_mcp_servers(self, new_mcp: MCPConfig) -> MCPConfig:
        async with self._lock:
            cfg = self._load()
            cfg.mcp_config.mcpServers.update(new_mcp.mcpServers)
            self._save(cfg)
            return cfg.mcp_config

    async def delete_mcp_server(self, server_name: str) -> None:
        async with self._lock:
            cfg = self._load()
            cfg.mcp_config.mcpServers.pop(server_name, None)
            self._save(cfg)

    async def update_mcp_enabled(self, server_name: str, enabled: bool) -> None:
        async with self._lock:
            cfg = self._load()
            if server_name in cfg.mcp_config.mcpServers:
                cfg.mcp_config.mcpServers[server_name].enabled = enabled
                self._save(cfg)

    # ---------- A2A ----------
    async def get_a2a_config(self) -> A2AConfig:
        async with self._lock:
            return self._load().a2a_config

    async def add_a2a_server(self, base_url: str) -> A2AServerConfig:
        async with self._lock:
            cfg = self._load()
            new_server = A2AServerConfig(base_url=base_url)
            cfg.a2a_config.a2a_servers.append(new_server)
            self._save(cfg)
            return new_server

    async def delete_a2a_server(self, a2a_id: str) -> None:
        async with self._lock:
            cfg = self._load()
            cfg.a2a_config.a2a_servers = [
                s for s in cfg.a2a_config.a2a_servers if s.id != a2a_id
            ]
            self._save(cfg)

    async def update_a2a_enabled(self, a2a_id: str, enabled: bool) -> None:
        async with self._lock:
            cfg = self._load()
            for s in cfg.a2a_config.a2a_servers:
                if s.id == a2a_id:
                    s.enabled = enabled
                    break
            self._save(cfg)

    # ---------- Tools ----------
    async def get_tool_config(self) -> ToolConfig:
        async with self._lock:
            return self._load().tool_config

    async def update_tool_config(self, new_config: ToolConfig) -> ToolConfig:
        async with self._lock:
            cfg = self._load()
            cfg.tool_config = new_config
            self._save(cfg)
            return cfg.tool_config


_app_config_service: Optional[AppConfigService] = None


def get_app_config_service() -> AppConfigService:
    """获取AppConfigService单例"""
    global _app_config_service
    if _app_config_service is None:
        _app_config_service = AppConfigService()
    return _app_config_service

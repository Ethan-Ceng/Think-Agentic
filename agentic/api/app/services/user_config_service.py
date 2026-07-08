#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""User-scoped configuration service."""
import copy
import logging
from pathlib import Path
from typing import Any, Callable, Dict

import yaml
from pydantic import ValidationError as PydanticValidationError

from app.core.config import API_ROOT, get_settings
from app.core.entities.app_config import (
    A2AConfig,
    A2AServerConfig,
    AgentConfig,
    AppConfig,
    LLMConfig,
    MCPConfig,
)
from app.core.entities.config import Config
from app.core.entities.tool_config import ToolConfig
from app.repositories.uow import IUnitOfWork
from app.schemas.exceptions import BadRequestError

logger = logging.getLogger(__name__)


CONFIG_TYPE_LLM = "llm"
CONFIG_TYPE_AGENT = "agent"
CONFIG_TYPE_MCP = "mcp"
CONFIG_TYPE_A2A = "a2a"
CONFIG_TYPE_TOOL = "tool"
CONFIG_TYPE_UI = "ui"
CONFIG_TYPE_STORAGE = "storage"

CONFIG_TYPES = {
    CONFIG_TYPE_LLM,
    CONFIG_TYPE_AGENT,
    CONFIG_TYPE_MCP,
    CONFIG_TYPE_A2A,
    CONFIG_TYPE_TOOL,
    CONFIG_TYPE_UI,
    CONFIG_TYPE_STORAGE,
}

REDACTED_VALUE = "******"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "secret_id",
    "secret_key",
    "password",
    "passwd",
    "credential",
)


class UserConfigService:
    """Read and write typed config documents for a single user."""

    def __init__(self, uow_factory: Callable[[], IUnitOfWork]) -> None:
        self._uow_factory = uow_factory
        self._settings = get_settings()
        self._default_app_config: AppConfig | None = None

    def _load_default_app_config(self) -> AppConfig:
        if self._default_app_config is not None:
            return self._default_app_config

        config_path = Path(self._settings.app_config_filepath)
        if not config_path.is_absolute():
            config_path = API_ROOT / config_path

        data: Dict[str, Any] = {}
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            logger.warning("默认配置文件不存在: %s，使用代码默认值", config_path)

        default_llm = {
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "model_name": "deepseek-v4-pro",
            "temperature": 0.7,
            "max_tokens": 8192,
        }
        default_data = {
            "llm_config": data.get("llm_config") or default_llm,
            "agent_config": data.get("agent_config") or AgentConfig().model_dump(mode="json"),
            "mcp_config": data.get("mcp_config") or MCPConfig().model_dump(mode="json"),
            "a2a_config": data.get("a2a_config") or A2AConfig().model_dump(mode="json"),
            "tool_config": data.get("tool_config") or ToolConfig().model_dump(mode="json"),
        }
        self._default_app_config = AppConfig.model_validate(default_data)
        return self._default_app_config

    def _default_config_data(self, config_type: str) -> Dict[str, Any]:
        app_config = self._load_default_app_config()
        if config_type == CONFIG_TYPE_LLM:
            return app_config.llm_config.model_dump(mode="json")
        if config_type == CONFIG_TYPE_AGENT:
            return app_config.agent_config.model_dump(mode="json")
        if config_type == CONFIG_TYPE_MCP:
            return app_config.mcp_config.model_dump(mode="json")
        if config_type == CONFIG_TYPE_A2A:
            return app_config.a2a_config.model_dump(mode="json")
        if config_type == CONFIG_TYPE_TOOL:
            return app_config.tool_config.model_dump(mode="json")
        if config_type in {CONFIG_TYPE_UI, CONFIG_TYPE_STORAGE}:
            return {}
        raise BadRequestError(f"不支持的配置类型: {config_type}")

    @staticmethod
    def _to_plain_data(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    @classmethod
    def _validate_config_data(cls, config_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        data = cls._to_plain_data(data)
        try:
            if config_type == CONFIG_TYPE_LLM:
                return LLMConfig.model_validate(data).model_dump(mode="json")
            if config_type == CONFIG_TYPE_AGENT:
                return AgentConfig.model_validate(data).model_dump(mode="json")
            if config_type == CONFIG_TYPE_MCP:
                return MCPConfig.model_validate(data).model_dump(mode="json")
            if config_type == CONFIG_TYPE_A2A:
                return A2AConfig.model_validate(data).model_dump(mode="json")
            if config_type == CONFIG_TYPE_TOOL:
                return ToolConfig.model_validate(data).model_dump(mode="json")
            if config_type in {CONFIG_TYPE_UI, CONFIG_TYPE_STORAGE}:
                if not isinstance(data, dict):
                    raise BadRequestError("配置内容必须是 JSON 对象")
                return data
        except PydanticValidationError as exc:
            raise BadRequestError(f"配置格式错误: {exc}") from exc

        raise BadRequestError(f"不支持的配置类型: {config_type}")

    async def _get_or_create_config(self, user_id: str, config_type: str) -> Config:
        if config_type not in CONFIG_TYPES:
            raise BadRequestError(f"不支持的配置类型: {config_type}")

        uow = self._uow_factory()
        async with uow:
            config = await uow.config.get_by_user_and_type(user_id, config_type)
            if config:
                return config

            config = Config(
                user_id=user_id,
                config_type=config_type,
                config=self._validate_config_data(config_type, self._default_config_data(config_type)),
            )
            await uow.config.save(config)
            return config

    async def get_raw_config(self, user_id: str, config_type: str) -> Dict[str, Any]:
        config = await self._get_or_create_config(user_id, config_type)
        return copy.deepcopy(config.config)

    async def upsert_raw_config(self, user_id: str, config_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        validated = self._validate_config_data(config_type, data)
        existing = await self._get_or_create_config(user_id, config_type)
        updated = existing.model_copy(update={"config": validated})

        uow = self._uow_factory()
        async with uow:
            await uow.config.save(updated)

        return copy.deepcopy(validated)

    async def get_llm_config(self, user_id: str) -> LLMConfig:
        return LLMConfig.model_validate(await self.get_raw_config(user_id, CONFIG_TYPE_LLM))

    async def update_llm_config(self, user_id: str, new_config: Any) -> LLMConfig:
        current = await self.get_llm_config(user_id)
        data = LLMConfig.model_validate(self._to_plain_data(new_config)).model_dump(mode="json")
        if not data.get("api_key") or data.get("api_key") == REDACTED_VALUE:
            data["api_key"] = current.api_key
        return LLMConfig.model_validate(await self.upsert_raw_config(user_id, CONFIG_TYPE_LLM, data))

    async def get_agent_config(self, user_id: str) -> AgentConfig:
        return AgentConfig.model_validate(await self.get_raw_config(user_id, CONFIG_TYPE_AGENT))

    async def update_agent_config(self, user_id: str, new_config: Any) -> AgentConfig:
        data = AgentConfig.model_validate(self._to_plain_data(new_config)).model_dump(mode="json")
        return AgentConfig.model_validate(await self.upsert_raw_config(user_id, CONFIG_TYPE_AGENT, data))

    async def get_mcp_config(self, user_id: str) -> MCPConfig:
        return MCPConfig.model_validate(await self.get_raw_config(user_id, CONFIG_TYPE_MCP))

    async def update_mcp_config(self, user_id: str, new_config: Any) -> MCPConfig:
        data = MCPConfig.model_validate(self._to_plain_data(new_config)).model_dump(mode="json")
        return MCPConfig.model_validate(await self.upsert_raw_config(user_id, CONFIG_TYPE_MCP, data))

    async def add_mcp_servers(self, user_id: str, new_mcp: Any) -> MCPConfig:
        current = await self.get_mcp_config(user_id)
        incoming = MCPConfig.model_validate(self._to_plain_data(new_mcp))
        current.mcpServers.update(incoming.mcpServers)
        return await self.update_mcp_config(user_id, current)

    async def delete_mcp_server(self, user_id: str, server_name: str) -> None:
        current = await self.get_mcp_config(user_id)
        current.mcpServers.pop(server_name, None)
        await self.update_mcp_config(user_id, current)

    async def update_mcp_enabled(self, user_id: str, server_name: str, enabled: bool) -> None:
        current = await self.get_mcp_config(user_id)
        if server_name in current.mcpServers:
            current.mcpServers[server_name].enabled = enabled
            await self.update_mcp_config(user_id, current)

    async def get_a2a_config(self, user_id: str) -> A2AConfig:
        return A2AConfig.model_validate(await self.get_raw_config(user_id, CONFIG_TYPE_A2A))

    async def update_a2a_config(self, user_id: str, new_config: Any) -> A2AConfig:
        data = A2AConfig.model_validate(self._to_plain_data(new_config)).model_dump(mode="json")
        return A2AConfig.model_validate(await self.upsert_raw_config(user_id, CONFIG_TYPE_A2A, data))

    async def add_a2a_server(self, user_id: str, base_url: str) -> A2AServerConfig:
        current = await self.get_a2a_config(user_id)
        new_server = A2AServerConfig(base_url=base_url)
        current.a2a_servers.append(new_server)
        await self.update_a2a_config(user_id, current)
        return new_server

    async def delete_a2a_server(self, user_id: str, a2a_id: str) -> None:
        current = await self.get_a2a_config(user_id)
        current.a2a_servers = [server for server in current.a2a_servers if server.id != a2a_id]
        await self.update_a2a_config(user_id, current)

    async def update_a2a_enabled(self, user_id: str, a2a_id: str, enabled: bool) -> None:
        current = await self.get_a2a_config(user_id)
        for server in current.a2a_servers:
            if server.id == a2a_id:
                server.enabled = enabled
                break
        await self.update_a2a_config(user_id, current)

    async def get_tool_config(self, user_id: str) -> ToolConfig:
        return ToolConfig.model_validate(await self.get_raw_config(user_id, CONFIG_TYPE_TOOL))

    async def update_tool_config(self, user_id: str, new_config: Any) -> ToolConfig:
        data = ToolConfig.model_validate(self._to_plain_data(new_config)).model_dump(mode="json")
        return ToolConfig.model_validate(await self.upsert_raw_config(user_id, CONFIG_TYPE_TOOL, data))

    async def get_app_config(self, user_id: str) -> AppConfig:
        return AppConfig(
            llm_config=await self.get_llm_config(user_id),
            agent_config=await self.get_agent_config(user_id),
            mcp_config=await self.get_mcp_config(user_id),
            a2a_config=await self.get_a2a_config(user_id),
            tool_config=await self.get_tool_config(user_id),
        )

    @classmethod
    def redact_sensitive_data(cls, value: Any) -> Any:
        if isinstance(value, dict):
            redacted: Dict[str, Any] = {}
            for key, item in value.items():
                lower_key = str(key).lower()
                if any(part in lower_key for part in SENSITIVE_KEY_PARTS):
                    redacted[key] = REDACTED_VALUE if item not in (None, "") else item
                else:
                    redacted[key] = cls.redact_sensitive_data(item)
            return redacted
        if isinstance(value, list):
            return [cls.redact_sensitive_data(item) for item in value]
        return value

    @classmethod
    def restore_redacted_data(cls, incoming: Any, existing: Any) -> Any:
        if incoming == REDACTED_VALUE:
            return existing
        if isinstance(incoming, dict) and isinstance(existing, dict):
            restored: Dict[str, Any] = {}
            for key, item in incoming.items():
                restored[key] = cls.restore_redacted_data(item, existing.get(key))
            return restored
        if isinstance(incoming, list) and isinstance(existing, list):
            return [
                cls.restore_redacted_data(item, existing[index] if index < len(existing) else None)
                for index, item in enumerate(incoming)
            ]
        return incoming

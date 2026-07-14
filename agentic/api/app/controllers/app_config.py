#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
App Config Controller - 应用配置管理端点
"""
import logging
from typing import Optional, Dict

from fastapi import APIRouter, Depends, Body

from app.core.entities.user import User
from app.dependencies import get_current_user, get_user_config_service
from app.schemas import Response
from app.schemas.app_config import (
    LLMConfig,
    AgentConfig,
    MCPConfig,
    A2AConfig,
)
from app.services.user_config_service import UserConfigService
from app.dependencies.infrastructure import get_file_storage
from app.schemas.file_management import StorageTestRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app-config", tags=["应用配置"])


@router.get("/storage", summary="获取存储配置")
async def get_storage_config(
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[dict]:
    config = await service.get_storage_config(current_user.id)
    return Response.success(data=config)


@router.post("/storage", summary="更新存储配置")
async def update_storage_config(
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[dict]:
    candidate = await service.prepare_storage_config(current_user.id, body)
    if candidate.default_provider != "local":
        await get_file_storage().test_provider(current_user.id, candidate.default_provider, candidate)
    updated = await service.update_storage_config(current_user.id, candidate)
    return Response.success(data=updated, msg="存储配置已保存")


@router.post("/storage/test", summary="测试存储连接")
async def test_storage_config(
    body: StorageTestRequest,
    current_user: User = Depends(get_current_user),
) -> Response[dict]:
    if body.provider not in {"local", "qcloud_cos", "aliyun_oss"}:
        return Response.fail(code=400, msg="不支持的存储 Provider")
    await get_file_storage().test_provider(current_user.id, body.provider)
    return Response.success(data={"provider": body.provider, "ok": True}, msg="存储连接测试成功")


# ==================== LLM ====================

@router.get("/llm", summary="获取LLM配置")
async def get_llm_config(
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[dict]:
    """获取LLM配置（脱敏 api_key，表示已填写但不暴露明文）"""
    config = await service.get_llm_config(current_user.id)
    return Response.success(data=service.redact_sensitive_data(config.model_dump(mode="json")))


@router.post("/llm", summary="更新LLM配置")
async def update_llm_config(
    new_config: LLMConfig,
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[dict]:
    """更新LLM配置（api_key为空表示不更新）"""
    updated = await service.update_llm_config(current_user.id, new_config)
    return Response.success(
        msg="更新LLM配置成功",
        data=service.redact_sensitive_data(updated.model_dump(mode="json")),
    )


# ==================== Agent ====================

@router.get("/agent", summary="获取Agent通用配置")
async def get_agent_config(
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[AgentConfig]:
    """获取Agent通用配置"""
    config = await service.get_agent_config(current_user.id)
    return Response.success(data=config.model_dump())


@router.post("/agent", summary="更新Agent通用配置")
async def update_agent_config(
    new_config: AgentConfig,
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[AgentConfig]:
    """更新Agent通用配置"""
    updated = await service.update_agent_config(current_user.id, new_config)
    return Response.success(msg="更新Agent配置成功", data=updated.model_dump())


# ==================== MCP ====================

@router.get("/mcp-servers", summary="获取MCP服务列表")
async def get_mcp_servers(
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[dict]:
    """获取MCP服务列表"""
    config = await service.get_mcp_config(current_user.id)
    return Response.success(
        data={
            "mcp_servers": [
                {
                    "server_name": server_name,
                    "enabled": server_config.enabled,
                    "transport": server_config.transport,
                    "tools": [],
                }
                for server_name, server_config in config.mcpServers.items()
            ]
        }
    )


@router.post("/mcp-servers", summary="新增MCP服务")
async def add_mcp_servers(
    new_mcp: MCPConfig,
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[Optional[Dict]]:
    """新增MCP服务"""
    await service.add_mcp_servers(current_user.id, new_mcp)
    return Response.success(msg="新增MCP服务成功")


@router.post("/mcp-servers/{server_name}/delete", summary="删除MCP服务")
async def delete_mcp_server(
    server_name: str,
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[Optional[Dict]]:
    """删除MCP服务"""
    await service.delete_mcp_server(current_user.id, server_name)
    return Response.success(msg="删除MCP服务成功")


@router.post("/mcp-servers/{server_name}/enabled", summary="更新MCP服务启用状态")
async def update_mcp_enabled(
    server_name: str,
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[Optional[Dict]]:
    """更新MCP服务启用状态"""
    await service.update_mcp_enabled(current_user.id, server_name, body.get("enabled", False))
    return Response.success(msg="更新MCP服务启用状态成功")


# ==================== A2A ====================

@router.get("/a2a-servers", summary="获取A2A服务列表")
async def get_a2a_servers(
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[A2AConfig]:
    """获取A2A服务列表"""
    config = await service.get_a2a_config(current_user.id)
    return Response.success(
        data={
            "a2a_servers": [
                {
                    "id": server.id,
                    "name": server.base_url,
                    "description": "",
                    "input_modes": [],
                    "output_modes": [],
                    "streaming": False,
                    "push_notifications": False,
                    "enabled": server.enabled,
                }
                for server in config.a2a_servers
            ]
        }
    )


@router.post("/a2a-servers", summary="新增A2A服务")
async def add_a2a_server(
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[Optional[Dict]]:
    """新增A2A服务"""
    base_url = body.get("base_url")
    if not base_url:
        return Response.fail(code=400, msg="缺少 base_url 参数")
    await service.add_a2a_server(current_user.id, base_url)
    return Response.success(msg="新增A2A服务成功")


@router.post("/a2a-servers/{a2a_id}/delete", summary="删除A2A服务")
async def delete_a2a_server(
    a2a_id: str,
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[Optional[Dict]]:
    """删除A2A服务"""
    await service.delete_a2a_server(current_user.id, a2a_id)
    return Response.success(msg="删除A2A服务成功")


@router.post("/a2a-servers/{a2a_id}/enabled", summary="更新A2A启用状态")
async def update_a2a_enabled(
    a2a_id: str,
    body: dict = Body(...),
    current_user: User = Depends(get_current_user),
    service: UserConfigService = Depends(get_user_config_service),
) -> Response[Optional[Dict]]:
    """更新A2A服务启用状态"""
    await service.update_a2a_enabled(current_user.id, a2a_id, body.get("enabled", False))
    return Response.success(msg="更新A2A启用状态成功")

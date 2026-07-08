#!/usr/bin/env python
# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends

from app.core.entities.user import User
from app.dependencies import get_current_user
from app.schemas import Response
from app.schemas.tool_config import (
    ToolBindingsUpdate,
    ToolListResponse,
    ToolPreflightRequest,
    ToolRegistrationCreate,
    ToolRegistrationListResponse,
    ToolRegistrationTestRequest,
    ToolRegistrationTestResponse,
    ToolRegistrationUpdate,
)
from app.services.tool_config_service import ToolConfigService, get_tool_config_service

router = APIRouter(prefix="/tools", tags=["工具管理"])


@router.get("", summary="获取工具列表")
async def list_tools(
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolListResponse]:
    return Response.success(data=await service.list_tools(current_user.id))


@router.post("/bindings", summary="更新工具绑定配置")
async def update_tool_bindings(
    update: ToolBindingsUpdate,
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolListResponse]:
    return Response.success(msg="更新工具配置成功", data=await service.update_bindings(current_user.id, update))


@router.get("/registrations", summary="获取工具源注册列表")
async def list_tool_registrations(
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationListResponse]:
    return Response.success(data=await service.list_registrations(current_user.id))


@router.post("/registrations", summary="新增工具源注册")
async def create_tool_registration(
    request: ToolRegistrationCreate,
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationListResponse]:
    return Response.success(msg="新增工具源成功", data=await service.create_registration(current_user.id, request))


@router.post("/registrations/{registration_id}", summary="更新工具源注册")
async def update_tool_registration(
    registration_id: str,
    request: ToolRegistrationUpdate,
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationListResponse]:
    return Response.success(
        msg="更新工具源成功",
        data=await service.update_registration(current_user.id, registration_id, request),
    )


@router.post("/registrations/{registration_id}/delete", summary="删除工具源注册")
async def delete_tool_registration(
    registration_id: str,
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationListResponse]:
    return Response.success(
        msg="删除工具源成功",
        data=await service.delete_registration(current_user.id, registration_id),
    )


@router.post("/registrations/{registration_id}/test", summary="测试工具源注册")
async def test_tool_registration(
    registration_id: str,
    request: ToolRegistrationTestRequest,
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationTestResponse]:
    return Response.success(
        msg="工具源测试完成",
        data=await service.test_registration(current_user.id, registration_id, request),
    )


@router.get("/capability-summary", summary="获取工具能力摘要")
async def get_capability_summary(
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[dict]:
    return Response.success(data=(await service.capability_summary(current_user.id)).model_dump())


@router.post("/capability-summary/refresh", summary="刷新工具能力摘要")
async def refresh_capability_summary(
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[dict]:
    return Response.success(data=(await service.capability_summary(current_user.id)).model_dump())


@router.post("/preflight", summary="工具能力预检")
async def preflight_tools(
    request: ToolPreflightRequest,
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[dict]:
    return Response.success(data=(await service.preflight(current_user.id, request.message)).model_dump())


@router.post("/reset-defaults", summary="重置工具默认配置")
async def reset_tool_defaults(
    current_user: User = Depends(get_current_user),
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolListResponse]:
    return Response.success(msg="已重置工具配置", data=await service.reset_defaults(current_user.id))

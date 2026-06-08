#!/usr/bin/env python
# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends

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
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolListResponse]:
    return Response.success(data=await service.list_tools())


@router.post("/bindings", summary="更新工具绑定配置")
async def update_tool_bindings(
    update: ToolBindingsUpdate,
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolListResponse]:
    return Response.success(msg="更新工具配置成功", data=await service.update_bindings(update))


@router.get("/registrations", summary="获取工具源注册列表")
async def list_tool_registrations(
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationListResponse]:
    return Response.success(data=await service.list_registrations())


@router.post("/registrations", summary="新增工具源注册")
async def create_tool_registration(
    request: ToolRegistrationCreate,
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationListResponse]:
    return Response.success(msg="新增工具源成功", data=await service.create_registration(request))


@router.post("/registrations/{registration_id}", summary="更新工具源注册")
async def update_tool_registration(
    registration_id: str,
    request: ToolRegistrationUpdate,
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationListResponse]:
    return Response.success(
        msg="更新工具源成功",
        data=await service.update_registration(registration_id, request),
    )


@router.post("/registrations/{registration_id}/delete", summary="删除工具源注册")
async def delete_tool_registration(
    registration_id: str,
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationListResponse]:
    return Response.success(
        msg="删除工具源成功",
        data=await service.delete_registration(registration_id),
    )


@router.post("/registrations/{registration_id}/test", summary="测试工具源注册")
async def test_tool_registration(
    registration_id: str,
    request: ToolRegistrationTestRequest,
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolRegistrationTestResponse]:
    return Response.success(
        msg="工具源测试完成",
        data=await service.test_registration(registration_id, request),
    )


@router.get("/capability-summary", summary="获取工具能力摘要")
async def get_capability_summary(
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[dict]:
    return Response.success(data=(await service.capability_summary()).model_dump())


@router.post("/capability-summary/refresh", summary="刷新工具能力摘要")
async def refresh_capability_summary(
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[dict]:
    return Response.success(data=(await service.capability_summary()).model_dump())


@router.post("/preflight", summary="工具能力预检")
async def preflight_tools(
    request: ToolPreflightRequest,
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[dict]:
    return Response.success(data=(await service.preflight(request.message)).model_dump())


@router.post("/reset-defaults", summary="重置工具默认配置")
async def reset_tool_defaults(
    service: ToolConfigService = Depends(get_tool_config_service),
) -> Response[ToolListResponse]:
    return Response.success(msg="已重置工具配置", data=await service.reset_defaults())

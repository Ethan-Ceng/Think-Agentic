#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run/trace query controller."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.entities.user import User
from app.dependencies import get_current_user, get_trace_service
from app.schemas import Response
from app.services.trace_service import TraceService

router = APIRouter(prefix="/runs", tags=["运行记录"])


@router.get("", summary="获取运行记录列表")
async def list_runs(
    session_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    service: TraceService = Depends(get_trace_service),
) -> Response[dict]:
    runs = await service.list_runs(
        user_id=current_user.id,
        session_id=session_id,
        limit=limit,
    )
    return Response.success(data={"runs": runs})


@router.get("/{run_id}", summary="获取运行记录详情")
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    service: TraceService = Depends(get_trace_service),
) -> Response[dict]:
    return Response.success(data=await service.get_run_detail(current_user.id, run_id))


@router.get("/{run_id}/events", summary="获取运行事件")
async def list_run_events(
    run_id: str,
    current_user: User = Depends(get_current_user),
    service: TraceService = Depends(get_trace_service),
) -> Response[dict]:
    return Response.success(data={"events": await service.list_events(current_user.id, run_id)})


@router.get("/{run_id}/tool-calls", summary="获取工具调用记录")
async def list_run_tool_calls(
    run_id: str,
    current_user: User = Depends(get_current_user),
    service: TraceService = Depends(get_trace_service),
) -> Response[dict]:
    return Response.success(data={"tool_calls": await service.list_tool_calls(current_user.id, run_id)})


@router.get("/{run_id}/model-calls", summary="获取模型调用记录")
async def list_run_model_calls(
    run_id: str,
    current_user: User = Depends(get_current_user),
    service: TraceService = Depends(get_trace_service),
) -> Response[dict]:
    return Response.success(data={"model_calls": await service.list_model_calls(current_user.id, run_id)})

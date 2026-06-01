#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Session Controller - 完整实现（接入真实 Agent 流程）
"""
import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional, Dict

import websockets
from fastapi import APIRouter, Depends
from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets import ConnectionClosed

from app.schemas import Response
from app.schemas.exceptions import NotFoundError
from app.schemas.event import EventMapper
from app.schemas.session import (
    CreateSessionResponse,
    ListSessionItem,
    ListSessionResponse,
    GetSessionResponse,
    ChatRequest,
    FileReadRequest,
    FileReadResponse,
    ShellReadRequest,
    ShellReadResponse,
    GetSessionFilesResponse,
)
from app.dependencies import (
    get_session_service,
    get_agent_service,
)
from app.services.session_service import SessionService
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["会话管理"])

SESSION_SLEEP_INTERVAL = 5


# ==================== 基础 CRUD ====================

@router.post("", summary="创建新会话")
async def create_session(
    session_service: SessionService = Depends(get_session_service),
) -> Response[CreateSessionResponse]:
    """创建新会话"""
    session = await session_service.create_session()
    return Response.success(
        msg="创建任务会话成功",
        data=CreateSessionResponse(session_id=session.id),
    )


@router.post("/stream", summary="SSE流式获取会话列表")
async def stream_sessions(
    session_service: SessionService = Depends(get_session_service),
) -> EventSourceResponse:
    """SSE流式推送会话列表"""

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        while True:
            sessions = await session_service.get_all_sessions()
            session_items = [
                ListSessionItem(
                    session_id=s.id,
                    title=s.title,
                    latest_message=s.latest_message,
                    latest_message_at=s.latest_message_at,
                    status=s.status,
                    unread_message_count=s.unread_message_count,
                )
                for s in sessions
            ]
            yield ServerSentEvent(
                event="sessions",
                data=ListSessionResponse(sessions=session_items).model_dump_json(),
            )
            await asyncio.sleep(SESSION_SLEEP_INTERVAL)

    return EventSourceResponse(event_generator())


@router.get("", summary="获取会话列表")
async def get_sessions(
    session_service: SessionService = Depends(get_session_service),
) -> Response[ListSessionResponse]:
    """获取会话列表"""
    sessions = await session_service.get_all_sessions()
    session_items = [
        ListSessionItem(
            session_id=s.id,
            title=s.title,
            latest_message=s.latest_message,
            latest_message_at=s.latest_message_at,
            status=s.status,
            unread_message_count=s.unread_message_count,
        )
        for s in sessions
    ]
    return Response.success(
        msg="获取任务会话列表成功",
        data=ListSessionResponse(sessions=session_items),
    )


@router.get("/{session_id}", summary="获取会话详情")
async def get_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
) -> Response[GetSessionResponse]:
    """获取会话详情"""
    try:
        session = await session_service.get_session(session_id)
        if not session:
            raise NotFoundError("该会话不存在，请核实后重试")

        return Response.success(
            msg="获取会话详情成功",
            data=GetSessionResponse(
                session_id=session.id,
                title=session.title,
                status=session.status,
                events=EventMapper.events_to_sse_events(session.events) if session.events else [],
            ),
        )
    except NotFoundError:
        raise  # 让 NotFoundError 正常抛出，返回 404
    except Exception as e:
        logger.error(f"获取会话详情失败: {e}", exc_info=True)
        return Response.fail(code=500, msg=f"获取会话详情失败: {str(e)}")


# ==================== 会话操作 ====================

@router.post("/{session_id}/clear-unread-message-count", summary="清除未读消息数")
async def clear_unread_message_count(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
) -> Response[Optional[Dict]]:
    """清除未读消息数"""
    await session_service.clear_unread_message_count(session_id)
    return Response.success(msg="清除未读消息数成功")


@router.post("/{session_id}/delete", summary="删除会话")
async def delete_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
) -> Response[Optional[Dict]]:
    """删除会话"""
    await session_service.delete_session(session_id)
    return Response.success(msg="删除任务会话成功")


@router.post("/{session_id}/stop", summary="停止会话")
async def stop_session(
    session_id: str,
    agent_service: AgentService = Depends(get_agent_service),
) -> Response[Optional[Dict]]:
    """停止会话"""
    await agent_service.stop_session(session_id)
    return Response.success(msg="停止任务会话成功")


# ==================== 聊天 ====================

@router.post("/{session_id}/chat", summary="聊天（SSE流式）")
async def chat(
    session_id: str,
    request: ChatRequest,
    agent_service: AgentService = Depends(get_agent_service),
) -> EventSourceResponse:
    """聊天（SSE流式响应） - 接入真实 Agent 流程"""

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        async for event in agent_service.chat(
            session_id=session_id,
            message=request.message,
            attachments=request.attachments,
            latest_event_id=request.event_id,
            timestamp=datetime.fromtimestamp(request.timestamp) if request.timestamp else None,
        ):
            sse_event = EventMapper.event_to_sse_event(event)
            if sse_event:
                yield ServerSentEvent(
                    event=sse_event.event,
                    data=sse_event.data.model_dump_json(),
                )

    return EventSourceResponse(event_generator())


# ==================== 文件/Shell ====================

@router.get("/{session_id}/files", summary="获取会话文件列表")
async def get_session_files(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
) -> Response[GetSessionFilesResponse]:
    """获取会话文件列表"""
    files = await session_service.get_session_files(session_id)
    return Response.success(
        msg="获取会话文件列表成功",
        data={"files": [f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in files]},
    )


@router.post("/{session_id}/file", summary="读取沙箱文件")
async def read_file(
    session_id: str,
    request: FileReadRequest,
    session_service: SessionService = Depends(get_session_service),
) -> Response[FileReadResponse]:
    """读取沙箱文件"""
    result = await session_service.read_file(session_id, request.target_path)
    return Response.success(msg="读取文件成功", data=result)


@router.post("/{session_id}/shell", summary="读取Shell输出")
async def read_shell(
    session_id: str,
    request: ShellReadRequest,
    session_service: SessionService = Depends(get_session_service),
) -> Response[ShellReadResponse]:
    """读取Shell输出"""
    result = await session_service.read_shell_output(session_id, request.target_session_id)
    return Response.success(msg="读取Shell输出成功", data=result)


# ==================== VNC WebSocket ====================

@router.websocket("/{session_id}/vnc")
async def vnc_proxy(
    websocket: WebSocket,
    session_id: str,
):
    """WebSocket VNC 代理 - 转发浏览器和沙箱之间的 VNC 流"""
    # 1. 协议协商
    protocols = websocket.headers.get("sec-websocket-protocol", "").split(",")
    protocols = [p.strip() for p in protocols if p.strip()]
    selected_protocol = "binary" if "binary" in protocols else None

    logger.info(f"为会话[{session_id}]开启WebSocket连接")
    await websocket.accept(subprotocol=selected_protocol)

    # 2. 获取 VNC URL（通过独立 service）
    session_service = get_session_service()
    try:
        sandbox_vnc_url = await session_service.get_vnc_url(session_id)
        logger.info(f"连接 VNC: {sandbox_vnc_url}")

        async with websockets.connect(sandbox_vnc_url, subprotocols=["binary"]) as sandbox_ws:
            async def forward_to_sandbox():
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await sandbox_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("Web->VNC 连接断开")
                except Exception as e:
                    logger.error(f"forward_to_sandbox 出错: {e}")

            async def forward_from_sandbox():
                try:
                    while True:
                        data = await sandbox_ws.recv()
                        await websocket.send_bytes(data)
                except ConnectionClosed:
                    logger.info("VNC->Web 连接关闭")
                except Exception as e:
                    logger.error(f"forward_from_sandbox 出错: {e}")

            t1 = asyncio.create_task(forward_to_sandbox())
            t2 = asyncio.create_task(forward_from_sandbox())
            done, pending = await asyncio.wait(
                [t1, t2],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except Exception as e:
        logger.error(f"VNC 连接失败: {e}")
        await websocket.close()

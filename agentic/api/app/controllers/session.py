#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Session Controller - 完整实现（接入真实 Agent 流程）
"""
import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional, Dict, Literal

import websockets
from fastapi import APIRouter, Body, Depends, Query
from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets import ConnectionClosed

from app.schemas import Response
from app.schemas.exceptions import NotFoundError
from app.schemas.event import EventMapper
from app.schemas.session import (
    CreateSessionResponse,
    CreateSessionRequest,
    ListSessionItem,
    ListSessionResponse,
    GetSessionResponse,
    CreateSessionBranchRequest,
    CreateSessionBranchResponse,
    BranchFamilyResponse,
    UpdateSessionOrganizationRequest,
    ChatRequest,
    NextMessageResponse,
    QueueNextMessageRequest,
    ResumeSessionRequest,
    ResolveInteractionRequest,
    FileReadRequest,
    FileReadResponse,
    ShellReadRequest,
    ShellReadResponse,
    GetSessionFilesResponse,
)
from app.dependencies import (
    get_current_user,
    get_session_service,
    get_agent_service,
)
from app.dependencies.auth import get_user_from_token
from app.core.entities.user import User
from app.core.entities.session import Session
from app.services.session_service import SessionService
from app.services.agent_service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["会话管理"])

SESSION_SLEEP_INTERVAL = 5


def _to_list_session_item(session: Session) -> ListSessionItem:
    return ListSessionItem(
        session_id=session.id,
        title=session.title,
        project_id=session.project_id,
        latest_message=session.latest_message,
        latest_message_at=session.latest_message_at,
        status=session.status,
        unread_message_count=session.unread_message_count,
        is_pinned=session.is_pinned,
        archived_at=session.archived_at,
        has_next_message=session.next_message is not None,
    )


# ==================== 基础 CRUD ====================

@router.post("", summary="创建新会话")
async def create_session(
    request: Optional[CreateSessionRequest] = Body(default=None),
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[CreateSessionResponse]:
    """创建新会话"""
    session = await session_service.create_session(
        current_user.id,
        project_id=request.project_id if request is not None else None,
    )
    return Response.success(
        msg="创建任务会话成功",
        data=CreateSessionResponse(session_id=session.id),
    )


@router.post("/stream", summary="SSE流式获取会话列表")
async def stream_sessions(
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> EventSourceResponse:
    """SSE流式推送会话列表"""

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        while True:
            sessions = await session_service.get_all_sessions(current_user.id)
            session_items = [_to_list_session_item(s) for s in sessions]
            yield ServerSentEvent(
                event="sessions",
                data=ListSessionResponse(sessions=session_items).model_dump_json(),
            )
            await asyncio.sleep(SESSION_SLEEP_INTERVAL)

    return EventSourceResponse(event_generator())


@router.get("", summary="获取会话列表")
async def get_sessions(
    scope: Literal["active", "archived"] = Query(default="active"),
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[ListSessionResponse]:
    """获取会话列表"""
    sessions = await session_service.get_all_sessions(
        current_user.id,
        archived=scope == "archived",
    )
    session_items = [_to_list_session_item(s) for s in sessions]
    return Response.success(
        msg="获取任务会话列表成功",
        data=ListSessionResponse(sessions=session_items),
    )


@router.get("/{session_id}", summary="获取会话详情")
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[GetSessionResponse]:
    """获取会话详情"""
    try:
        session = await session_service.get_session(session_id, current_user.id)
        if not session:
            raise NotFoundError("该会话不存在，请核实后重试")
        source_session = (
            await session_service.get_branch_source(
                session.source_session_id,
                current_user.id,
            )
            if session.source_session_id
            else None
        )

        return Response.success(
            msg="获取会话详情成功",
            data=GetSessionResponse(
                session_id=session.id,
                title=session.title,
                project_id=session.project_id,
                status=session.status,
                events=EventMapper.events_to_sse_events(session.events) if session.events else [],
                next_message=(
                    NextMessageResponse.model_validate(
                        session.next_message.model_dump(mode="python")
                    )
                    if session.next_message
                    else None
                ),
                source_session_id=source_session.id if source_session else None,
                source_session_title=source_session.title if source_session else None,
                forked_from_event_id=session.forked_from_event_id,
                branch_operation=session.branch_operation,
                is_pinned=session.is_pinned,
                archived_at=session.archived_at,
            ),
        )
    except NotFoundError:
        raise  # 让 NotFoundError 正常抛出，返回 404
    except Exception as e:
        logger.error(f"获取会话详情失败: {e}", exc_info=True)
        return Response.fail(code=500, msg=f"获取会话详情失败: {str(e)}")


# ==================== 会话操作 ====================

@router.patch("/{session_id}", summary="更新会话整理元数据")
async def update_session_organization(
    session_id: str,
    request: UpdateSessionOrganizationRequest,
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[ListSessionItem]:
    update_kwargs = {
        "session_id": session_id,
        "user_id": current_user.id,
        "title": request.title,
        "pinned": request.pinned,
        "archived": request.archived,
    }
    if "project_id" in request.model_fields_set:
        update_kwargs.update(
            project_id=request.project_id,
            project_id_provided=True,
        )
    session = await session_service.update_organization(
        **update_kwargs,
    )
    return Response.success(
        msg="更新任务会话成功",
        data=_to_list_session_item(session),
    )

@router.post("/{session_id}/branches", summary="从历史消息创建新会话分支")
async def create_session_branch(
    session_id: str,
    request: CreateSessionBranchRequest,
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[CreateSessionBranchResponse]:
    branch = await session_service.create_branch(
        source_session_id=session_id,
        user_id=current_user.id,
        target_event_id=request.target_event_id,
        operation=request.operation,
        request_id=str(request.request_id),
        message=request.message,
    )
    return Response.success(
        msg="会话分支创建成功",
        data=CreateSessionBranchResponse(
            session_id=branch.id,
            source_session_id=branch.source_session_id or session_id,
            forked_from_event_id=branch.forked_from_event_id or request.target_event_id,
            operation=branch.branch_operation or request.operation,
            queued=branch.next_message is not None,
        ),
    )


@router.get("/{session_id}/branch-family", summary="获取消息直接分支版本")
async def get_session_branch_family(
    session_id: str,
    target_event_id: Optional[str] = Query(
        default=None,
        min_length=1,
        max_length=255,
    ),
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[BranchFamilyResponse]:
    family = await session_service.get_branch_family(
        session_id=session_id,
        user_id=current_user.id,
        target_event_id=target_event_id,
    )
    return Response.success(
        msg="获取会话分支版本成功",
        data=family,
    )


@router.post("/{session_id}/clear-unread-message-count", summary="清除未读消息数")
async def clear_unread_message_count(
    session_id: str,
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[Optional[Dict]]:
    """清除未读消息数"""
    await session_service.clear_unread_message_count(session_id, current_user.id)
    return Response.success(msg="清除未读消息数成功")


@router.post("/{session_id}/delete", summary="删除会话")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[Optional[Dict]]:
    """删除会话"""
    await session_service.delete_session(session_id, current_user.id)
    return Response.success(msg="删除任务会话成功")


@router.post("/{session_id}/stop", summary="停止会话")
async def stop_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> Response[Optional[Dict]]:
    """停止会话"""
    await agent_service.stop_session(session_id, current_user.id)
    return Response.success(msg="停止任务会话成功")


# ==================== 聊天 ====================

@router.put("/{session_id}/next-message", summary="保存或替换下一条消息")
async def queue_next_message(
    session_id: str,
    request: QueueNextMessageRequest,
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[NextMessageResponse]:
    queued = await session_service.queue_next_message(
        session_id=session_id,
        user_id=current_user.id,
        message=request.message,
        attachments=request.attachments,
        skills=request.skills,
    )
    return Response.success(
        msg="下一条消息已保存",
        data=NextMessageResponse.model_validate(queued.model_dump(mode="python")),
    )


@router.delete("/{session_id}/next-message", summary="取消下一条消息")
async def cancel_next_message(
    session_id: str,
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[Optional[Dict]]:
    await session_service.cancel_next_message(session_id, current_user.id)
    return Response.success(msg="下一条消息已取消")


@router.post("/{session_id}/next-message/run", summary="恢复执行下一条消息（SSE）")
async def run_next_message(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    session_service: SessionService = Depends(get_session_service),
) -> EventSourceResponse:
    await session_service.ensure_session_active(session_id, current_user.id)

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        async for event in agent_service.run_next_message(
            session_id=session_id,
            user_id=current_user.id,
        ):
            sse_event = EventMapper.event_to_sse_event(event)
            if sse_event:
                yield ServerSentEvent(
                    event=sse_event.event,
                    data=sse_event.data.model_dump_json(),
                )

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/chat", summary="聊天（SSE流式）")
async def chat(
    session_id: str,
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    session_service: SessionService = Depends(get_session_service),
) -> EventSourceResponse:
    """聊天（SSE流式响应） - 接入真实 Agent 流程"""
    await session_service.ensure_session_active(session_id, current_user.id)

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        async for event in agent_service.chat(
            session_id=session_id,
            user_id=current_user.id,
            message=request.message,
            attachments=request.attachments,
            skills=request.skills,
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


# ==================== 任务恢复 ====================

@router.post("/{session_id}/resume", summary="恢复失败任务（SSE 流式）")
async def resume_session(
    session_id: str,
    request: ResumeSessionRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    session_service: SessionService = Depends(get_session_service),
) -> EventSourceResponse:
    """在保留当前对话上下文的前提下，由用户发起一个新的 Run。"""
    await session_service.ensure_session_active(session_id, current_user.id)

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        async for event in agent_service.resume(
            session_id=session_id,
            user_id=current_user.id,
            mode=request.mode,
        ):
            sse_event = EventMapper.event_to_sse_event(event)
            if sse_event:
                yield ServerSentEvent(
                    event=sse_event.event,
                    data=sse_event.data.model_dump_json(),
                )

    return EventSourceResponse(event_generator())


@router.post(
    "/{session_id}/interactions/{action_id}/resolve",
    summary="解决待处理交互（SSE 流式）",
)
async def resolve_interaction(
    session_id: str,
    action_id: str,
    request: ResolveInteractionRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> EventSourceResponse:
    """Answer a structured question or approve/reject one Tool Call."""
    resolved, resolution = await agent_service.resolve_interaction(
        session_id=session_id,
        user_id=current_user.id,
        action_id=action_id,
        decision=request.decision,
        answer=request.answer,
        selected_values=request.selected_values,
    )

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        resolved_sse = EventMapper.event_to_sse_event(resolved)
        if resolved_sse:
            yield ServerSentEvent(
                event=resolved_sse.event,
                data=resolved_sse.data.model_dump_json(),
            )
        async for event in agent_service.continue_interaction(
            session_id=session_id,
            user_id=current_user.id,
            resolution=resolution,
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
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[GetSessionFilesResponse]:
    """获取会话文件列表"""
    files = await session_service.get_session_files(session_id, current_user.id)
    return Response.success(
        msg="获取会话文件列表成功",
        data={"files": [f.model_dump(mode="json") if hasattr(f, "model_dump") else f for f in files]},
    )


@router.post("/{session_id}/file", summary="读取沙箱文件")
async def read_file(
    session_id: str,
    request: FileReadRequest,
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[FileReadResponse]:
    """读取沙箱文件"""
    result = await session_service.read_file(session_id, current_user.id, request.target_path)
    return Response.success(msg="读取文件成功", data=result)


@router.post("/{session_id}/shell", summary="读取Shell输出")
async def read_shell(
    session_id: str,
    request: ShellReadRequest,
    current_user: User = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> Response[ShellReadResponse]:
    """读取Shell输出"""
    result = await session_service.read_shell_output(session_id, current_user.id, request.target_session_id)
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
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return
    try:
        current_user = await get_user_from_token(token)
    except Exception:
        await websocket.close(code=1008)
        return

    await websocket.accept(subprotocol=selected_protocol)

    # 2. 获取 VNC URL（通过独立 service）
    session_service = get_session_service()
    try:
        sandbox_vnc_url = await session_service.get_vnc_url(session_id, current_user.id)
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

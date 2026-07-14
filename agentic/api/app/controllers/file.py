#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File Controller - 文件上传/下载端点
"""
import logging
import urllib.parse
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from starlette.responses import StreamingResponse

from app.dependencies import get_current_user, get_file_service
from app.core.entities.user import User
from app.services.file_service import FileService
from app.schemas import Response
from app.schemas.exceptions import AppException, BadRequestError, NotFoundError
from app.schemas.file_management import BatchDeleteRequest, BatchMoveRequest, CreateFolderRequest, UpdateFileRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["文件模块"])


def file_response_data(file_model) -> dict:
    """Build the file payload expected by the UI and the old API."""
    return {
        "id": file_model.id,
        "filename": file_model.filename,
        "name": file_model.filename,
        "filepath": file_model.filepath,
        "key": file_model.key,
        "extension": file_model.extension,
        "mime_type": file_model.mime_type,
        "content_type": file_model.mime_type,
        "size": file_model.size,
        "url": f"/api/files/{file_model.id}/download",
    }


@router.get("", summary="获取文件列表")
async def list_files(
    parent_id: Optional[str] = None,
    search_word: str = "",
    file_kind: str = "all",
    source_type: str = "all",
    current_page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    if file_kind not in {"all", "image", "video", "audio", "document", "other"}:
        raise BadRequestError("不支持的文件类型筛选")
    if source_type not in {"all", "user_upload", "agent_generated"}:
        raise BadRequestError("不支持的文件来源筛选")
    data = await service.list_files(
        current_user.id,
        parent_id=parent_id,
        search_word=search_word,
        file_kind=file_kind,
        source_type=source_type,
        current_page=current_page,
        page_size=page_size,
    )
    return Response.success(data=data)


@router.post("", summary="上传文件")
async def upload_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    parent_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    """上传文件到 COS 或本地存储"""
    try:
        file_model = await service.upload_file(upload_file=file, user_id=current_user.id, parent_id=parent_id)
        return Response.success(
            msg="上传文件成功",
            data={
                **file_response_data(file_model),
                "session_id": session_id,
            },
        )
    except Exception as e:
        if isinstance(e, AppException):
            raise
        logger.error(f"文件上传失败: {e}")
        return Response.fail(code=500, msg=f"上传失败: {e}")


@router.get("/{file_id}", summary="获取文件信息")
async def get_file_info(
    file_id: str,
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    """获取文件信息"""
    file_model = await service.get_file_info(file_id, current_user.id)
    if not file_model:
        raise NotFoundError(f"文件不存在: {file_id}")
    return Response.success(
        msg="获取文件信息成功",
        data=file_response_data(file_model),
    )


@router.get("/folders/tree", summary="获取目录树")
async def list_folder_tree(
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    return Response.success(data=await service.list_folder_tree(current_user.id))


@router.post("/folders", summary="新建目录")
async def create_folder(
    body: CreateFolderRequest,
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    folder = await service.create_folder(current_user.id, body.name, body.parent_id)
    return Response.success(data=service.to_response(folder))


@router.post("/batch-move", summary="批量移动文件")
async def batch_move_files(
    body: BatchMoveRequest,
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    files = await service.move_files(body.file_ids, current_user.id, body.parent_id)
    return Response.success(data=[service.to_response(file) for file in files])


@router.post("/batch-delete", summary="批量删除文件")
async def batch_delete_files(
    body: BatchDeleteRequest,
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    files = await service.delete_files(body.file_ids, current_user.id)
    return Response.success(data=[service.to_response(file) for file in files])


@router.patch("/{file_id}", summary="更新文件")
async def update_file(
    file_id: str,
    body: UpdateFileRequest,
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    file_model = await service.get_file_info(file_id, current_user.id)
    if body.name is not None:
        file_model = await service.rename_file(file_id, current_user.id, body.name)
    if "parent_id" in body.model_fields_set:
        file_model = (await service.move_files([file_id], current_user.id, body.parent_id))[0]
    return Response.success(data=service.to_response(file_model))


@router.delete("/{file_id}", summary="删除文件")
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> Response:
    file_model = (await service.delete_files([file_id], current_user.id))[0]
    return Response.success(data=service.to_response(file_model))


@router.get("/{file_id}/download", summary="下载文件")
async def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> StreamingResponse:
    """下载文件"""
    file_stream, file_model = await service.download_file(file_id, current_user.id)
    encoded_filename = urllib.parse.quote(file_model.filename)
    return StreamingResponse(
        content=file_stream,
        media_type=file_model.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}",
            "Content-Length": str(file_model.size),
        },
    )


@router.get("/{file_id}/preview", summary="预览文件")
async def preview_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> StreamingResponse:
    file_stream, file_model = await service.download_file(file_id, current_user.id)
    encoded_filename = urllib.parse.quote(file_model.filename)
    return StreamingResponse(
        content=file_stream,
        media_type=file_model.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"inline; filename*=utf-8''{encoded_filename}",
            "Content-Length": str(file_model.size),
        },
    )

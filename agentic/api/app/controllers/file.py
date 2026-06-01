#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File Controller - 文件上传/下载端点
"""
import logging
import urllib.parse
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form
from starlette.responses import StreamingResponse

from app.dependencies import get_file_service
from app.services.file_service import FileService
from app.schemas import Response
from app.schemas.exceptions import NotFoundError

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


@router.post("", summary="上传文件")
async def upload_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    service: FileService = Depends(get_file_service),
) -> Response:
    """上传文件到 COS 或本地存储"""
    try:
        file_model = await service.upload_file(upload_file=file)
        return Response.success(
            msg="上传文件成功",
            data={
                **file_response_data(file_model),
                "session_id": session_id,
            },
        )
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        return Response.fail(code=500, msg=f"上传失败: {e}")


@router.get("/{file_id}", summary="获取文件信息")
async def get_file_info(
    file_id: str,
    service: FileService = Depends(get_file_service),
) -> Response:
    """获取文件信息"""
    file_model = await service.get_file_info(file_id)
    if not file_model:
        raise NotFoundError(f"文件不存在: {file_id}")
    return Response.success(
        msg="获取文件信息成功",
        data=file_response_data(file_model),
    )


@router.get("/{file_id}/download", summary="下载文件")
async def download_file(
    file_id: str,
    service: FileService = Depends(get_file_service),
) -> StreamingResponse:
    """下载文件"""
    file_stream, file_model = await service.download_file(file_id)
    encoded_filename = urllib.parse.quote(file_model.filename)
    return StreamingResponse(
        content=file_stream,
        media_type=file_model.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}",
            "Content-Length": str(file_model.size),
        },
    )

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/18 17:37
@Author  : thezehui@gmail.com
@File    : file.py
"""
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class File(BaseModel):
    """文件信息Domain模型，用于记录Manus/Human上传or生成的文件"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # 文件id
    user_id: str = ""  # 用户id
    filename: str = ""  # 文件名字
    filepath: str = ""  # 文件路径
    key: str = ""  # 腾讯云cos中的路径
    extension: str = ""  # 扩展名
    mime_type: str = ""  # mime-type类型
    size: int = 0  # 文件大小，单位为字节
    parent_id: str | None = None
    entry_type: Literal["file", "folder"] = "file"
    storage_provider: Literal["local", "qcloud_cos", "aliyun_oss"] = "local"
    storage_config: dict[str, Any] = Field(default_factory=dict)
    source_type: Literal["user_upload", "agent_generated"] = "user_upload"
    status: Literal["available", "deleted"] = "available"
    sha256: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    origin_session_id: str | None = None
    origin_run_id: str | None = None
    deleted_at: datetime | None = None
    purge_after: datetime | None = None
    updated_at: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)

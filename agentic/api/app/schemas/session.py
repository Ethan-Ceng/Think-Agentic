#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Session Schemas - 请求和响应模型
"""
from datetime import datetime
from typing import List, Dict, Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.entities.skill import SkillRef


class SessionResponse(BaseModel):
    """会话完整响应模型"""
    id: str
    sandbox_id: Optional[str] = None
    task_id: Optional[str] = None
    title: str
    unread_message_count: int = 0
    latest_message: str = ""
    latest_message_at: Optional[datetime] = None
    status: str
    updated_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    session_id: str


class ListSessionItem(BaseModel):
    """会话列表项"""
    session_id: str
    title: str
    latest_message: str = ""
    latest_message_at: Optional[datetime] = None
    status: str
    unread_message_count: int = 0


class ListSessionResponse(BaseModel):
    """会话列表响应"""
    sessions: List[ListSessionItem]


class GetSessionResponse(BaseModel):
    """获取会话详情响应"""
    session_id: str
    title: str
    events: List[Any] = Field(default_factory=list)  # AgentSSEEvent 列表
    status: str
    unread_message_count: int = 0


class ChatRequest(BaseModel):
    """聊天请求"""
    message: Optional[str] = None
    attachments: Optional[List[str]] = Field(default_factory=list)
    skills: List[SkillRef] = Field(default_factory=list)
    event_id: Optional[str] = None
    timestamp: Optional[int] = None


class ResumeSessionRequest(BaseModel):
    """User-triggered recovery of a failed run in the same conversation."""
    mode: Literal["continue", "restart"]


class FileReadRequest(BaseModel):
    """文件读取请求"""
    filepath: Optional[str] = Field(default=None, description="文件路径")
    file: Optional[str] = Field(default=None, description="文件路径，兼容旧字段")

    @model_validator(mode="after")
    def validate_filepath(self) -> "FileReadRequest":
        if not self.filepath and not self.file:
            raise ValueError("filepath is required")
        return self

    @property
    def target_path(self) -> str:
        return self.filepath or self.file or ""


class FileReadResponse(BaseModel):
    """文件读取响应"""
    content: str


class ShellReadRequest(BaseModel):
    """Shell读取请求"""
    session_id: Optional[str] = Field(default=None, description="Shell会话ID")
    shell_session_id: Optional[str] = Field(default=None, description="Shell会话ID，兼容前端字段")

    @model_validator(mode="after")
    def validate_shell_session_id(self) -> "ShellReadRequest":
        if not self.session_id and not self.shell_session_id:
            raise ValueError("shell_session_id is required")
        return self

    @property
    def target_session_id(self) -> str:
        return self.shell_session_id or self.session_id or ""


class ShellReadResponse(BaseModel):
    """Shell读取响应"""
    output: str = ""
    session_id: Optional[str] = None
    console: Optional[List[Dict[str, Any]]] = None


class GetSessionFilesResponse(BaseModel):
    """会话文件列表"""
    files: List[Dict[str, Any]]

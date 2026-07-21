#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Session Schemas - 请求和响应模型
"""
from datetime import datetime
from typing import List, Dict, Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.entities.skill import SkillRef
from app.core.entities.event import InteractionDecision


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


class NextMessageResponse(BaseModel):
    id: str
    message: str
    attachment_ids: List[str] = Field(default_factory=list)
    skills: List[SkillRef] = Field(default_factory=list)
    state: Literal["queued", "processing"]
    created_at: datetime


class GetSessionResponse(BaseModel):
    """获取会话详情响应"""
    session_id: str
    title: str
    events: List[Any] = Field(default_factory=list)  # AgentSSEEvent 列表
    status: str
    unread_message_count: int = 0
    next_message: Optional[NextMessageResponse] = None


class ChatRequest(BaseModel):
    """聊天请求"""
    message: Optional[str] = None
    attachments: Optional[List[str]] = Field(default_factory=list)
    skills: List[SkillRef] = Field(default_factory=list)
    event_id: Optional[str] = None
    timestamp: Optional[int] = None


class QueueNextMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    attachments: List[str] = Field(default_factory=list, max_length=20)
    skills: List[SkillRef] = Field(default_factory=list, max_length=5)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be blank")
        return value


class ResumeSessionRequest(BaseModel):
    """User-triggered recovery of a failed run in the same conversation."""
    mode: Literal["continue", "restart"]


class ResolveInteractionRequest(BaseModel):
    """Resolve a structured question or tool approval action."""

    decision: InteractionDecision
    answer: Optional[str] = Field(default=None, max_length=10000)
    selected_values: List[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> "ResolveInteractionRequest":
        if any(not value or len(value) > 500 for value in self.selected_values):
            raise ValueError("selected_values contains an invalid value")
        if len(set(self.selected_values)) != len(self.selected_values):
            raise ValueError("selected_values must be unique")
        return self


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

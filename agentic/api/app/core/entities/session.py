#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/14 10:25
@Author  : thezehui@gmail.com
@File    : session.py
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict

from pydantic import BaseModel, Field

from .event import (
    Event,
    InteractionDecision,
    InteractionEvent,
    InteractionStatus,
    InteractionType,
    PlanEvent,
)
from .file import File
from .memory import Memory
from .plan import Plan
from .skill import SkillRef


class InteractionNotFoundError(LookupError):
    pass


class InteractionConflictError(RuntimeError):
    pass


class InteractionValidationError(ValueError):
    pass


class NextMessageNotFoundError(LookupError):
    pass


class NextMessageConflictError(RuntimeError):
    pass


class NextMessageState(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"


class NextMessage(BaseModel):
    """One durable follow-up message waiting behind the active Agent turn."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: str = Field(min_length=1, max_length=10000)
    attachment_ids: List[str] = Field(default_factory=list, max_length=20)
    skills: List[SkillRef] = Field(default_factory=list, max_length=5)
    state: NextMessageState = NextMessageState.QUEUED
    task_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    claimed_at: Optional[datetime] = None


class SessionStatus(str, Enum):
    """会话状态类型枚举"""
    PENDING = "pending"  # 等待任务
    RUNNING = "running"  # 运行中
    WAITING = "waiting"  # 等待人类响应
    COMPLETED = "completed"  # 已完成


class Session(BaseModel):
    """会话领域模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # 会话id
    user_id: str = ""  # 用户id
    sandbox_id: Optional[str] = None  # 沙箱id
    task_id: Optional[str] = None  # 任务id
    title: str = ""  # 标题
    unread_message_count: int = 0  # 未读消息数
    latest_message: str = ""  # 最新消息
    latest_message_at: Optional[datetime] = None  # 最新消息时间
    events: List[Event] = Field(default_factory=list)  # 事件列表
    files: List[File] = Field(default_factory=list)  # 文件列表
    memories: Dict[str, Memory] = Field(default_factory=dict)  # 记忆
    next_message: Optional[NextMessage] = None
    status: SessionStatus = SessionStatus.PENDING  # 状态
    updated_at: datetime = Field(default_factory=datetime.now)  # 更新时间
    created_at: datetime = Field(default_factory=datetime.now)  # 创建时间

    def get_latest_plan(self) -> Optional[Plan]:
        """获取会话中的最新计划"""
        # 1.倒序遍历会话中所有事件消息
        for event in reversed(self.events):
            # 2.判断事件的类型是否为PlanEvent，如果是则提取计划后返回
            if isinstance(event, PlanEvent):
                return event.plan

        return None

    def resolve_interaction(
            self,
            action_id: str,
            decision: InteractionDecision,
            answer: Optional[str] = None,
            selected_values: Optional[List[str]] = None,
    ) -> InteractionEvent:
        """Resolve the latest pending interaction using append-only event history."""
        selected_values = selected_values or []
        answer = answer.strip() if answer and answer.strip() else None
        latest_by_action: Dict[str, InteractionEvent] = {}
        for event in self.events:
            if isinstance(event, InteractionEvent):
                latest_by_action[event.action_id] = event

        target = latest_by_action.get(action_id)
        if target is None:
            raise InteractionNotFoundError("交互动作不存在")
        if target.status != InteractionStatus.PENDING:
            raise InteractionConflictError("交互动作已经解决")

        pending = [
            event
            for event in latest_by_action.values()
            if event.status == InteractionStatus.PENDING
        ]
        if not pending or pending[-1].action_id != action_id:
            raise InteractionConflictError("交互动作已不是当前待处理动作")
        if self.status != SessionStatus.WAITING:
            raise InteractionConflictError("会话当前不在等待交互状态")

        if target.interaction_type == InteractionType.ASK_USER:
            if decision != InteractionDecision.ANSWER:
                raise InteractionValidationError("询问交互只能提交回答")
            option_values = {option.value for option in target.options}
            if any(value not in option_values for value in selected_values):
                raise InteractionValidationError("回答包含未知选项")
            if not target.allow_multiple and len(selected_values) > 1:
                raise InteractionValidationError("该问题不允许多选")
            if not target.allow_text and answer:
                raise InteractionValidationError("该问题不允许自由文本回答")
            if not answer and not selected_values:
                raise InteractionValidationError("回答不能为空")
        elif target.interaction_type == InteractionType.TOOL_APPROVAL:
            if decision not in {InteractionDecision.APPROVE, InteractionDecision.REJECT}:
                raise InteractionValidationError("工具审批决定无效")
            if answer or selected_values:
                raise InteractionValidationError("工具审批不能携带回答内容")

        event_data = target.model_dump(
            exclude={"id", "created_at", "status", "decision", "answer", "selected_values"}
        )
        resolved = InteractionEvent(
            **event_data,
            status=InteractionStatus.RESOLVED,
            decision=decision,
            answer=answer,
            selected_values=selected_values,
        )
        self.events.append(resolved)
        return resolved

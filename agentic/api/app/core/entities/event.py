#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/18 0:54
@Author  : thezehui@gmail.com
@File    : event.py
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Literal, List, Union, Optional, Any, Dict, Annotated

from pydantic import BaseModel, Field

from .file import File
from .plan import Plan, Step
from .search import SearchResultItem
from .skill import SkillRef
from .tool_result import ToolResult


class PlanEventStatus(str, Enum):
    """规划事件状态"""
    CREATED = "created"  # 已创建
    UPDATED = "updated"  # 已更新
    COMPLETED = "completed"  # 已完成


class StepEventStatus(str, Enum):
    """步骤事件状态"""
    STARTED = "started"  # 已开始
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class ToolEventStatus(str, Enum):
    """工具事件状态类型枚举"""
    CALLING = "calling"  # 调用中
    CALLED = "called"  # 调用完毕


class InteractionType(str, Enum):
    """需要人类输入才能继续的交互类型。"""

    ASK_USER = "ask_user"
    TOOL_APPROVAL = "tool_approval"


class InteractionStatus(str, Enum):
    """交互动作的追加式状态。"""

    PENDING = "pending"
    RESOLVED = "resolved"


class InteractionDecision(str, Enum):
    """用户对交互动作作出的决定。"""

    ANSWER = "answer"
    APPROVE = "approve"
    REJECT = "reject"


class InteractionOption(BaseModel):
    """结构化询问中的稳定选项值和用户可见标签。"""

    value: str
    label: str
    description: Optional[str] = None


class InteractionResolution(BaseModel):
    """服务端校验后传入 Agent 恢复路径的交互决定。"""

    action_id: str
    interaction_type: InteractionType
    decision: InteractionDecision
    tool_call_id: str
    function_name: str
    function_args: Dict[str, Any] = Field(default_factory=dict)
    tool_name: Optional[str] = None
    risk_level: Optional[Literal["low", "medium", "high"]] = None
    answer: Optional[str] = None
    selected_values: List[str] = Field(default_factory=list)


class BaseEvent(BaseModel):
    """基础事件类型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # 事件id
    type: Literal[""] = ""  # 事件的类型
    created_at: datetime = Field(default_factory=datetime.now)  # 事件创建时间


class PlanEvent(BaseEvent):
    """规划事件类型"""
    type: Literal["plan"] = "plan"
    plan: Plan  # 规划
    status: PlanEventStatus = PlanEventStatus.CREATED  # 规划事件状态


class TitleEvent(BaseEvent):
    """标题事件类型"""
    type: Literal["title"] = "title"
    title: str = ""  # 标题


class StepEvent(BaseEvent):
    """子任务/步骤事件"""
    type: Literal["step"] = "step"
    step: Step  # 步骤信息
    status: StepEventStatus = StepEventStatus.STARTED


class MessageEvent(BaseEvent):
    """消息事件，包含人类消息和AI消息"""
    type: Literal["message"] = "message"
    role: Literal["user", "assistant"] = "assistant"  # 消息角色
    message: str = ""  # 消息本身
    attachments: List[File] = Field(default_factory=list)  # 附件列表信息
    skills: List[SkillRef] = Field(default_factory=list)  # 本次 Run 手动选择的 Skills
    visible: bool = True  # 是否作为用户可见的对话消息展示
    interaction_response: Optional[InteractionResolution] = None


class BrowserToolContent(BaseModel):
    """浏览器工具扩展内容"""
    screenshot: str  # 浏览器快照截图


class SearchToolContent(BaseModel):
    """搜索工具内容"""
    results: List[SearchResultItem]  # 搜索结果列表


class ShellToolContent(BaseModel):
    """Shell工具内容"""
    console: Any  # 控制台内容


class FileToolContent(BaseModel):
    """文件工具内容"""
    content: str  # 文件内容


class MCPToolContent(BaseModel):
    """MCP工具内容"""
    result: Any  # MCP工具结果


class A2AToolContent(BaseModel):
    """A2A智能体工具内容"""
    a2a_result: Any  # A2A智能体调用结果


ToolContent = Union[
    BrowserToolContent,
    SearchToolContent,
    ShellToolContent,
    FileToolContent,
    MCPToolContent,
    A2AToolContent,
]


class ToolEvent(BaseEvent):
    """工具事件"""
    type: Literal["tool"] = "tool"
    tool_call_id: str  # 工具调用id
    tool_name: str  # 工具箱/工具集的名字
    tool_content: Optional[ToolContent] = None  # 工具扩展内容
    function_name: str  # LLM调用函数/工具名字
    function_args: Dict[str, Any]  # LLM生成的工具调用参数
    function_result: Optional[ToolResult] = None  # 工具调用结果
    status: ToolEventStatus = ToolEventStatus.CALLING  # 工具事件状态


class InteractionEvent(BaseEvent):
    """持久化的人机交互请求或解决记录。"""

    type: Literal["interaction"] = "interaction"
    action_id: str
    interaction_type: InteractionType
    status: InteractionStatus = InteractionStatus.PENDING
    tool_call_id: str
    tool_name: str
    function_name: str
    function_args: Dict[str, Any] = Field(default_factory=dict)
    prompt: str
    description: Optional[str] = None
    options: List[InteractionOption] = Field(default_factory=list)
    allow_multiple: bool = False
    allow_text: bool = True
    placeholder: Optional[str] = None
    risk_level: Optional[Literal["low", "medium", "high"]] = None
    decision: Optional[InteractionDecision] = None
    answer: Optional[str] = None
    selected_values: List[str] = Field(default_factory=list)


class WaitEvent(BaseEvent):
    """等待事件，等待用户输入确认"""
    type: Literal["wait"] = "wait"


class ErrorEvent(BaseEvent):
    """错误事件"""
    type: Literal["error"] = "error"
    error: str = ""  # 错误信息


class DoneEvent(BaseEvent):
    """结束事件类型"""
    type: Literal["done"] = "done"


# 定义应用事件类型声明
Event = Annotated[
    Union[
        PlanEvent,
        TitleEvent,
        StepEvent,
        MessageEvent,
        ToolEvent,
        InteractionEvent,
        WaitEvent,
        ErrorEvent,
        DoneEvent,
    ],
    Field(discriminator="type"),
]

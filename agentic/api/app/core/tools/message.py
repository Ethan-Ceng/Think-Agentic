#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/16 1:09
@Author  : thezehui@gmail.com
@File    : message.py
"""
from typing import Any, Dict, Optional, Union, List

from app.core.entities.tool_result import ToolResult
from .base import BaseTool, tool


class MessageTool(BaseTool):
    """消息工具，用于完成消息工具初始化"""
    name: str = "message"

    def __init__(self) -> None:
        """构造函数，完成消息工具包初始化"""
        super().__init__()

    @tool(
        name="message_notify_user",
        description="向用户发送消息，且无需用户回复。用于确认收到消息、提供进度更新、报告任务完成情况，或解释处理方式的变更。",
        parameters={
            "text": {
                "type": "string",
                "description": "要显示给用户的消息文本",
            },
        },
        required=["text"]
    )
    async def message_notify_user(self, text: str) -> ToolResult:
        """发送通知消息给用户，不需要用户响应"""
        return ToolResult(success=True, data="Continue")

    @tool(
        name="message_ask_user",
        description="向用户提问并等待回复。用于：请求澄清、寻求确认、或收集额外信息。",
        parameters={
            "text": {
                "type": "string",
                "description": "要展示给用户的问题文本",
            },
            "description": {
                "type": "string",
                "description": "（可选）帮助用户理解问题背景的补充说明",
            },
            "options": {
                "type": "array",
                "description": "（可选）结构化选项，value 必须稳定且唯一",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "label": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["value", "label"],
                },
            },
            "allow_multiple": {
                "type": "boolean",
                "description": "是否允许多选，默认 false",
            },
            "allow_text": {
                "type": "boolean",
                "description": "是否允许自由文本回答，默认 true",
            },
            "placeholder": {
                "type": "string",
                "description": "（可选）自由文本输入框占位提示",
            },
            "attachments": {
                "anyOf": [
                    {"type": "string"},
                    {"items": {"type": "string"}, "type": "array"},
                ],
                "description": "(可选)与问题相关的文件或参考资料",
            },
            "suggest_user_takeover": {
                "type": "string",
                "enum": ["none", "browser"],
                "description": "(可选)建议用户接管的操作（例如由用户在浏览器中手动完成某些事）。"
            },
        },
        required=["text"],
    )
    async def message_ask_user(
            self,
            text: str,
            description: Optional[str] = None,
            options: Optional[List[Dict[str, Any]]] = None,
            allow_multiple: bool = False,
            allow_text: bool = True,
            placeholder: Optional[str] = None,
            attachments: Optional[Union[str, List[str]]] = None,
            suggest_user_takeover: Optional[str] = None,
    ) -> ToolResult:
        """提问用户并等待响应"""
        return ToolResult(success=True)

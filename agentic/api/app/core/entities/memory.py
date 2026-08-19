#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/17 14:56
@Author  : thezehui@gmail.com
@File    : memory.py
"""
import logging
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

from .tool_result import ToolResult

logger = logging.getLogger(__name__)

COMPACTED_TOOL_RESULT = "(compacted: tool result already consumed by the model)"


class Memory(BaseModel):
    """记忆类，定义Agent的记忆基础信息"""
    messages: List[Dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def get_message_role(cls, message: Dict[str, Any]) -> str:
        """根据传递的消息来获取消息的角色信息"""
        return message.get("role")

    def add_message(self, message: Dict[str, Any]) -> None:
        """往记忆中添加一条消息"""
        self.messages.append(message)

    def add_messages(self, messages: List[Dict[str, Any]]) -> None:
        """往记忆中添加多条消息"""
        self.messages.extend(messages)

    def get_messages(self) -> List[Dict[str, Any]]:
        """获取记忆中的所有消息列表"""
        return self.messages

    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """获取记忆中的最后一条消息，如果不存在则返回None"""
        return self.messages[-1] if len(self.messages) > 0 else None

    def roll_back(self) -> None:
        """回滚记忆，删除最后一条消息"""
        self.messages = self.messages[:-1]

    def close_pending_tool_calls(
            self,
            expected_tool_call_id: str,
            *,
            reason: str,
    ) -> List[str]:
        """Close a legacy assistant tool-call tail without executing any tool.

        OpenAI-compatible providers require one tool result for every tool call
        in the assistant message before another user message can be appended.
        The expected id prevents an unrelated memory tail from being changed.
        """
        last_message = self.get_last_message()
        if not last_message or last_message.get("role") != "assistant":
            return []

        tool_calls = last_message.get("tool_calls") or []
        call_ids = [
            tool_call.get("id")
            for tool_call in tool_calls
            if tool_call.get("id")
        ]
        if expected_tool_call_id not in call_ids:
            return []

        result_content = ToolResult(
            success=False,
            message=reason,
        ).model_dump_json()
        closed: List[str] = []
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id")
            if not tool_call_id:
                continue
            function_name = (tool_call.get("function") or {}).get("name")
            self.add_message({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "function_name": function_name,
                "content": result_content,
            })
            closed.append(tool_call_id)
        return closed

    def compact(self) -> None:
        """记忆压缩，将记忆中已经执行的工具(搜索/网页源码获取/浏览器访问结果等)这类已经执行过的消息进行压缩检索"""
        self.compact_consumed_tool_results(
            preserve_recent=0,
            min_content_chars=512,
        )
        # 1.循环遍历所有的消息列表
        for message in self.messages:
            # 2.判断消息的角色是否为tool
            if self.get_message_role(message) == "tool":
                if message.get("function_name") in ["browser_view", "browser_navigate"]:
                    message["content"] = COMPACTED_TOOL_RESULT
                    logger.debug(f"从记忆中移除对应工具的结果: {message['function_name']}")

            # 3.压缩记忆时reasoning_content内容可以去除压缩上下文
            if "reasoning_content" in message:
                logger.debug(f"从记忆中移除工具思考结果: {message['reasoning_content'][:50]}...")
                del message["reasoning_content"]

    def compact_consumed_tool_results(
            self,
            *,
            preserve_recent: int = 4,
            min_content_chars: int = 2000,
    ) -> int:
        """压缩模型已经消费过的旧工具结果，同时保留工具协议字段。"""
        tool_indexes = [
            index
            for index, message in enumerate(self.messages)
            if self.get_message_role(message) == "tool"
        ]
        preserve_count = max(0, preserve_recent)
        preserved = set(tool_indexes[-preserve_count:]) if preserve_count else set()
        compacted = 0

        for index in tool_indexes:
            if index in preserved:
                continue
            message = self.messages[index]
            content = message.get("content")
            if content is None:
                continue
            content_text = content if isinstance(content, str) else str(content)
            if content_text.startswith("(compacted:"):
                continue
            if len(content_text) < max(0, min_content_chars):
                continue
            message["content"] = COMPACTED_TOOL_RESULT
            compacted += 1

        return compacted

    @property
    def empty(self) -> bool:
        """只读属性，检查记忆是否为空"""
        return len(self.messages) == 0

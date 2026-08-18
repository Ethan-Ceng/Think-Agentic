#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/5/17 17:14
@Author  : thezehui@gmail.com
@File    : llm.py
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol, List, Dict, Any, TypeAlias


class LLMStreamingUnsupportedError(RuntimeError):
    """Provider 明确拒绝流式请求，且尚未开始返回任何流事件。"""


@dataclass(frozen=True, slots=True)
class LLMStreamDelta:
    """Provider 返回的单个内部增量，不直接作为公共聊天事件。"""

    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: tuple[Dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class LLMStreamCompleted:
    """流结束后重建的、与块响应兼容的完整 Assistant Message。"""

    message: Dict[str, Any]
    model: str | None
    finish_reason: str | None
    usage: Dict[str, Any]
    ttft_ms: int | None


LLMStreamEvent: TypeAlias = LLMStreamDelta | LLMStreamCompleted


class LLM(Protocol):
    """用于Agent应用与LLM进行交互的接口协议"""

    async def invoke(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]] = None,
            response_format: Dict[str, Any] = None,
            tool_choice: str = None,
    ) -> Dict[str, Any]:
        """传递消息列表、工具列表、响应格式、工具选择策略调用LLM接口"""
        ...

    def stream(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]] = None,
            response_format: Dict[str, Any] = None,
            tool_choice: str = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        """流式调用LLM，并在结束时返回重建后的完整消息。"""
        ...

    @property
    def model_name(self) -> str:
        """只读属性，返回LLM的名字"""
        ...

    @property
    def temperature(self) -> float:
        """只读属性，返回LLM的温度"""
        ...

    @property
    def max_tokens(self) -> int:
        """只读属性，返回LLM的最大生成token数"""
        ...

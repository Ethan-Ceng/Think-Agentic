#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/5/17 17:21
@Author  : thezehui@gmail.com
@File    : openai_llm.py
"""
import logging
import re
from collections.abc import AsyncIterator, Mapping
from time import monotonic
from typing import List, Dict, Any

from openai import AsyncOpenAI

from app.schemas.exceptions import ServerRequestsError
from app.core.llm.base import (
    LLM,
    LLMStreamCompleted,
    LLMStreamDelta,
    LLMStreamEvent,
    LLMStreamingUnsupportedError,
)
from app.core.entities.app_config import LLMConfig

logger = logging.getLogger(__name__)


class OpenAILLM(LLM):
    """基于OpenAI SDK/兼容OpenAI格式的LLM调用类"""

    def __init__(self, llm_config: LLMConfig, **kwargs) -> None:
        """构造函数，完成异步OpenAI客户端的创建和参数初始化"""
        # 1.初始化异步客户端
        self._base_url = str(llm_config.base_url)
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=llm_config.api_key,
            **kwargs,
        )

        # 2.完成其他参数的存储
        self._model_name = llm_config.model_name
        self._temperature = llm_config.temperature
        self._max_tokens = llm_config.max_tokens
        self._timeout = 3600

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    async def invoke(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]] = None,
            response_format: Dict[str, Any] = None,
            tool_choice: str = None,
    ) -> Dict[str, Any]:
        """使用异步OpenAI客户端发起块响应（该步骤可以切换成流式响应）"""
        try:
            # 1.检测是否传递了工具列表
            if tools:
                logger.info(f"调用OpenAI客户端向LLM发起请求并携带工具信息: {self._model_name}")
                response = await self._client.chat.completions.create(
                    model=self._model_name,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    messages=messages,
                    response_format=response_format,
                    tools=tools,
                    tool_choice=tool_choice,
                    parallel_tool_calls=False,  # 关闭并行工具调用(deepseek没有这个参数的)
                    timeout=self._timeout,
                )
            else:
                # 2.为传递工具则删除tools/tool_choice等参数
                logger.info(f"调用OpenAI客户端向LLM发起请求未携带: {self._model_name}")
                response = await self._client.chat.completions.create(
                    model=self._model_name,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    messages=messages,
                    response_format=response_format,
                    timeout=self._timeout,
                )

            # 3.处理响应数据并返回
            logger.info(f"OpenAI客户端返回内容: {response.model_dump()}")
            message = response.choices[0].message.model_dump()
            message["_trace_metadata"] = {
                "model": getattr(response, "model", None),
                "finish_reason": response.choices[0].finish_reason,
                "usage": response.usage.model_dump(mode="json") if response.usage else {},
            }
            return message
        except Exception as e:
            logger.error(f"调用OpenAI客户端发生错误: {str(e)}")
            raise ServerRequestsError("调用OpenAI客户端向LLM发起请求出错")

    def stream(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]] = None,
            response_format: Dict[str, Any] = None,
            tool_choice: str = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        """流式调用 Provider，并在服务端重建完整 Assistant Message。"""
        return self._stream(
            messages=messages,
            tools=tools,
            response_format=response_format,
            tool_choice=tool_choice,
        )

    async def _stream(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]] = None,
            response_format: Dict[str, Any] = None,
            tool_choice: str = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        started_at = monotonic()
        request = self._stream_request(
            messages=messages,
            tools=tools,
            response_format=response_format,
            tool_choice=tool_choice,
        )
        try:
            try:
                response = await self._create_stream(request)
            except Exception as error:
                if not self._stream_options_unsupported(error):
                    raise
                logger.warning(
                    "Provider不支持stream_options，使用无usage流式参数重试: %s",
                    self._model_name,
                )
                request.pop("stream_options", None)
                response = await self._create_stream(request)

            role = "assistant"
            content_parts: list[str] = []
            content_seen = False
            reasoning_parts: list[str] = []
            reasoning_seen = False
            tool_calls: dict[int, Dict[str, Any]] = {}
            finish_reason: str | None = None
            usage: Dict[str, Any] = {}
            response_model: str | None = None
            ttft_ms: int | None = None

            async for chunk in response:
                chunk_model = self._value(chunk, "model")
                if chunk_model:
                    response_model = str(chunk_model)

                chunk_usage = self._value(chunk, "usage")
                if chunk_usage is not None:
                    usage = self._dump(chunk_usage)

                choices = self._value(chunk, "choices") or []
                if not choices:
                    continue

                choice = choices[0]
                choice_finish_reason = self._value(choice, "finish_reason")
                if choice_finish_reason is not None:
                    finish_reason = str(choice_finish_reason)

                delta = self._value(choice, "delta")
                if delta is None:
                    continue

                delta_role = self._value(delta, "role")
                if delta_role:
                    role = str(delta_role)

                content = self._value(delta, "content")
                if content is not None:
                    content_seen = True
                    if content:
                        content_parts.append(str(content))

                reasoning = self._value(delta, "reasoning_content")
                if reasoning is not None:
                    reasoning_seen = True
                    if reasoning:
                        reasoning_parts.append(str(reasoning))

                raw_tool_calls = self._value(delta, "tool_calls") or []
                normalized_tool_calls = tuple(
                    self._tool_call_fragment(call) for call in raw_tool_calls
                )
                for raw_call, fragment in zip(raw_tool_calls, normalized_tool_calls):
                    index = self._value(raw_call, "index")
                    self._merge_tool_call(
                        tool_calls,
                        int(index) if index is not None else len(tool_calls),
                        fragment,
                    )

                if ttft_ms is None and (
                    bool(content)
                    or bool(reasoning)
                    or bool(normalized_tool_calls)
                ):
                    ttft_ms = max(0, int((monotonic() - started_at) * 1000))

                if content or reasoning or normalized_tool_calls:
                    yield LLMStreamDelta(
                        content=str(content) if content else None,
                        reasoning_content=str(reasoning) if reasoning else None,
                        tool_calls=normalized_tool_calls,
                    )

            message: Dict[str, Any] = {
                "role": role,
                "content": "".join(content_parts) if content_seen else None,
            }
            if reasoning_seen:
                message["reasoning_content"] = "".join(reasoning_parts)
            if tool_calls:
                message["tool_calls"] = [
                    tool_calls[index] for index in sorted(tool_calls)
                ]

            trace_metadata = {
                "model": response_model,
                "finish_reason": finish_reason,
                "usage": usage,
                "ttft_ms": ttft_ms,
            }
            message["_trace_metadata"] = trace_metadata
            yield LLMStreamCompleted(
                message=message,
                model=response_model,
                finish_reason=finish_reason,
                usage=usage,
                ttft_ms=ttft_ms,
            )
        except LLMStreamingUnsupportedError:
            raise
        except Exception as error:
            logger.error("调用OpenAI客户端流式响应发生错误: %s", str(error))
            raise ServerRequestsError("调用OpenAI客户端向LLM发起流式请求出错") from error

    async def _create_stream(self, request: Dict[str, Any]) -> Any:
        try:
            return await self._client.chat.completions.create(**request)
        except Exception as error:
            if self._streaming_unsupported(error):
                raise LLMStreamingUnsupportedError(
                    "Provider不支持流式响应"
                ) from error
            raise

    def _stream_request(
            self,
            *,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]] | None,
            response_format: Dict[str, Any] | None,
            tool_choice: str | None,
    ) -> Dict[str, Any]:
        request: Dict[str, Any] = {
            "model": self._model_name,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "messages": messages,
            "response_format": response_format,
            "timeout": self._timeout,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            request.update(
                tools=tools,
                tool_choice=tool_choice,
                parallel_tool_calls=False,
            )
        return request

    @staticmethod
    def _stream_options_unsupported(error: Exception) -> bool:
        message = str(error).lower()
        return "stream_options" in message and any(
            marker in message
            for marker in (
                "unknown",
                "unsupported",
                "not support",
                "unrecognized",
                "unexpected",
                "extra",
                "invalid parameter",
            )
        )

    @staticmethod
    def _streaming_unsupported(error: Exception) -> bool:
        if isinstance(error, NotImplementedError):
            return True
        message = " ".join(str(error).lower().replace("_", " ").split())
        if "stream options" in message:
            return False
        explicit_markers = (
            "streaming is not supported",
            "streaming not supported",
            "does not support streaming",
            "doesn't support streaming",
            "stream is not supported",
            "stream not supported",
            "stream must be false",
        )
        if any(marker in message for marker in explicit_markers):
            return True
        parameter_markers = (
            "unknown parameter",
            "unsupported parameter",
            "unrecognized parameter",
            "unexpected parameter",
            "invalid parameter",
            "unrecognized request argument",
        )
        return re.search(r"\bstream\b", message) is not None and any(
            marker in message for marker in parameter_markers
        )

    @staticmethod
    def _value(value: Any, key: str) -> Any:
        if isinstance(value, Mapping):
            return value.get(key)
        return getattr(value, key, None)

    @staticmethod
    def _dump(value: Any) -> Dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return model_dump(mode="json")
        return {}

    @classmethod
    def _tool_call_fragment(cls, tool_call: Any) -> Dict[str, Any]:
        function = cls._value(tool_call, "function")
        return {
            "id": cls._value(tool_call, "id"),
            "type": cls._value(tool_call, "type"),
            "function": {
                "name": cls._value(function, "name"),
                "arguments": cls._value(function, "arguments"),
            },
        }

    @staticmethod
    def _merge_tool_call(
            calls: dict[int, Dict[str, Any]],
            index: int,
            fragment: Dict[str, Any],
    ) -> None:
        call = calls.setdefault(
            index,
            {"id": "", "type": "", "function": {"name": "", "arguments": ""}},
        )
        if fragment.get("id"):
            call["id"] += str(fragment["id"])
        if fragment.get("type"):
            call["type"] = str(fragment["type"])
        function = fragment.get("function") or {}
        if function.get("name"):
            call["function"]["name"] += str(function["name"])
        if function.get("arguments"):
            call["function"]["arguments"] += str(function["arguments"])


if __name__ == "__main__":
    import asyncio


    async def main():
        llm = OpenAILLM(LLMConfig(
            base_url="https://api.deepseek.com",
            api_key="",
            model_name="deepseek-chat",
        ))
        response = await llm.invoke([{"role": "user", "content": "Hi"}])
        print(response)


    asyncio.run(main())

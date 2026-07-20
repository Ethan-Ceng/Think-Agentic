#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/19 15:31
@Author  : thezehui@gmail.com
@File    : base.py
"""
import asyncio
import logging
import uuid
from abc import ABC
from typing import Optional, List, AsyncGenerator, Dict, Any, Callable

from app.core.json_parser.base import JSONParser
from app.core.llm.base import LLM
from app.core.entities.app_config import AgentConfig
from app.core.entities.event import (
    BaseEvent,
    ErrorEvent,
    InteractionDecision,
    InteractionEvent,
    InteractionOption,
    InteractionResolution,
    InteractionStatus,
    InteractionType,
    MessageEvent,
    ToolEvent,
    ToolEventStatus,
)
from app.core.entities.memory import Memory
from app.core.entities.message import Message
from app.core.entities.tool_result import ToolResult
from app.repositories.uow import IUnitOfWork
from app.core.tools.base import BaseTool
from app.services.skill_runtime_service import SkillRuntimeContext
from app.services.trace_service import TraceService, elapsed_ms, model_call_timer

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """基础Agent智能体"""
    name: str = ""  # 智能体名字
    _system_prompt: str = ""  # 系统预设prompt
    _format: Optional[str] = None  # Agent的响应格式
    _retry_interval: float = 1.0  # 重试间隔
    _tool_choice: Optional[str] = None  # 强制选择工具

    def __init__(
            self,
            uow_factory: Callable[[], IUnitOfWork],
            session_id: str,  # 会话id
            agent_config: AgentConfig,  # Agent配置
            llm: LLM,  # 语言模型协议
            json_parser: JSONParser,  # JSON输出解析器
            tools: List[BaseTool],  # 工具列表
            trace_service: TraceService | None = None,
            skill_runtime_context: SkillRuntimeContext | None = None,
    ) -> None:
        """构造函数，完成Agent的初始化"""
        self._uow_factory = uow_factory
        self._uow = uow_factory()
        self._session_id = session_id
        self._agent_config = agent_config
        self._llm = llm
        self._memory: Optional[Memory] = None
        self._json_parser = json_parser
        self._tools = tools
        self._trace_service = trace_service
        self._skill_runtime_context = skill_runtime_context or SkillRuntimeContext()

    def set_skill_runtime_context(self, context: SkillRuntimeContext) -> None:
        """Replace the transient per-run Skill context without touching Memory."""
        self._skill_runtime_context = context

    def get_available_tool_names(self) -> set[str]:
        """Return both tool-group and callable names used by Skill constraints."""
        names = {tool.name for tool in self._tools if tool.name}
        for tool_schema in self._get_available_tools():
            function = tool_schema.get("function") or {}
            name = function.get("name")
            if name:
                names.add(name)
        return names

    def _get_llm_messages(self) -> List[Dict[str, Any]]:
        """Build one model-call view with transient context after the base prompt."""
        messages = [message.copy() for message in self._memory.get_messages()]
        prompt_block = self._skill_runtime_context.prompt_block
        if not prompt_block:
            return messages
        insert_at = 1 if messages and messages[0].get("role") == "system" else 0
        messages.insert(insert_at, {"role": "system", "content": prompt_block})
        return messages

    async def _ensure_memory(self) -> None:
        """确保智能体记忆是存在的"""
        if self._memory is None:
            async with self._uow:
                self._memory = await self._uow.session.get_memory(self._session_id, self.name)

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """获取Agent所有可用的工具列表参数声明/Schema"""
        available_tools = []
        for tool in self._tools:
            available_tools.extend(tool.get_tools())
        return available_tools

    def _get_tool(self, tool_name: str) -> BaseTool:
        """获取对应工具所在的工具集/包"""
        # 1.循环遍历所有工具包
        for tool in self._tools:
            # 2.判断工具包中是否存在该工具
            if tool.has_tool(tool_name):
                return tool

        raise ValueError(f"未知工具: {tool_name}")

    async def _invoke_llm(self, messages: List[Dict[str, Any]], format: Optional[str] = None) -> Dict[str, Any]:
        """调用语言模型并处理记忆内容"""
        # 1.将消息添加到记忆中
        await self._add_to_memory(messages)

        # 2.组装语言模型的响应格式
        response_format = {"type": format} if format else None

        # 3.循环向LLM发起提问直到最大重试次数
        error = "调用语言模型发生错误"
        for _ in range(self._agent_config.max_retries):
            available_tools = self._get_available_tools()
            llm_messages = self._get_llm_messages()
            model_call_id = None
            model_started = model_call_timer()
            try:
                if self._trace_service:
                    model_call_id = await self._trace_service.record_model_call_started(
                        agent_name=self.name,
                        llm=self._llm,
                        messages=llm_messages,
                        tools=available_tools,
                        response_format=response_format,
                        tool_choice=self._tool_choice,
                    )

                # 4.调用语言模型获取响应内容
                message = await self._llm.invoke(
                    messages=llm_messages,
                    tools=available_tools,
                    response_format=response_format,
                    tool_choice=self._tool_choice,
                )
                if self._trace_service:
                    await self._trace_service.record_model_call_finished(
                        model_call_id,
                        message=message,
                        latency_ms=elapsed_ms(model_started),
                    )

                # 5.处理AI响应内容避免空回复
                if message.get("role") == "assistant":
                    if not message.get("content") and not message.get("tool_calls"):
                        logger.warning("LLM回复了空内容，执行重试")
                        await self._add_to_memory([
                            {"role": "assistant", "content": ""},
                            {"role": "user", "content": "AI无响应内容，请继续。"}
                        ])
                        await asyncio.sleep(self._retry_interval)
                        continue

                    # 6.取出非空消息并处理工具调用(兼容DeepSeek思考模型的写法)
                    filtered_message = {"role": "assistant", "content": message.get("content")}
                    if message.get("reasoning_content"):
                        filtered_message["reasoning_content"] = message.get("reasoning_content")
                    if message.get("tool_calls"):
                        # 7.取出工具调用的数据，限制LLM一次只能调用工具
                        filtered_message["tool_calls"] = message.get("tool_calls")[:1]
                else:
                    # 8.非AI消息则记录日志并存储message
                    logger.warning(f"LLM响应内容无法确认消息角色: {message.get('role')}")
                    filtered_message = {
                        key: value
                        for key, value in message.items()
                        if key != "_trace_metadata"
                    }

                # 9.将消息添加到记忆中
                await self._add_to_memory([filtered_message])
                return filtered_message
            except Exception as e:
                if self._trace_service:
                    await self._trace_service.record_model_call_finished(
                        model_call_id,
                        error=str(e),
                        latency_ms=elapsed_ms(model_started),
                    )
                # 10.记录日志并睡眠指定的时间
                logger.error(f"调用语言模型发生错误: {str(e)}")
                error = str(e)
                await asyncio.sleep(self._retry_interval)
                continue

        # 11.所有重试均已耗尽仍未获得有效响应，抛出异常避免返回None
        raise RuntimeError(f"调用语言模型失败, 已达到最大重试次数({self._agent_config.max_retries}): {error}")

    async def _invoke_tool(self, tool: BaseTool, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """传递工具包+工具名字+对应参数调用指定工具"""
        # 1.执行循环调用工具获取结果
        err = ""
        for _ in range(self._agent_config.max_retries):
            try:
                return await tool.invoke(tool_name, **arguments)
            except Exception as e:
                err = str(e)
                logger.exception(f"调用工具[{tool_name}]出错, 错误: {str(e)}")
                await asyncio.sleep(self._retry_interval)
                continue

        # 2.循环最大重试次数后没有结果则将错误作为工具的执行结果，让LLM自行处理
        return ToolResult(success=False, message=err)

    async def _add_to_memory(self, messages: List[Dict[str, Any]]) -> None:
        """将对应的信息添加到记忆中"""
        # 1.先检查确保记忆是存在的
        await self._ensure_memory()

        # 2.检查记忆的消息列表是否为空，如果是空则需要添加预设prompt作为初始记忆
        if self._memory.empty:
            self._memory.add_message({
                "role": "system", "content": self._system_prompt,
            })

        # 3.将正常消息添加到记忆中
        self._memory.add_messages(messages)

        # 4.将记忆持久化到数据仓库中
        async with self._uow:
            await self._uow.session.save_memory(self._session_id, self.name, self._memory)

    async def compact_memory(self) -> None:
        """压缩Agent的记忆"""
        await self._ensure_memory()
        self._memory.compact()
        async with self._uow:
            await self._uow.session.save_memory(self._session_id, self.name, self._memory)

    async def roll_back(self, message: Message) -> None:
        """Agent的状态回滚，该函数用于确保Agent的消息列表状态是正确，用于发送新消息、暂停/停止任务、通知用户"""
        # 1.取出记忆中的最后一条消息，检查是否是工具调用
        await self._ensure_memory()
        last_message = self._memory.get_last_message()
        if (
                not last_message or
                not last_message.get("tool_calls") or
                len(last_message.get("tool_calls")) == 0
        ):
            return

        # 2.取出消息中的工具调用参数
        tool_call = last_message.get("tool_calls")[0]

        # 3.提取工具名字、id
        function_name = tool_call.get("function", {}).get("name")
        tool_call_id = tool_call.get("id")

        # 4.判断下当前的工具是不是通知用户(message_ask_user)
        if function_name == "message_ask_user":
            self._memory.add_message({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "function_name": function_name,
                "content": message.model_dump_json(),
            })
        else:
            # 5.否则直接删除最后一条消息
            self._memory.roll_back()

        # 6.将记忆持久化
        async with self._uow:
            await self._uow.session.save_memory(self._session_id, self.name, self._memory)

    @staticmethod
    def _interaction_options(arguments: Dict[str, Any]) -> List[InteractionOption]:
        options: List[InteractionOption] = []
        seen: set[str] = set()
        for raw_option in arguments.get("options") or []:
            try:
                option = InteractionOption.model_validate(raw_option)
            except Exception:
                continue
            if not option.value or not option.label or option.value in seen:
                continue
            seen.add(option.value)
            options.append(option)
        return options

    def _build_interaction_event(
            self,
            tool: BaseTool,
            tool_call_id: str,
            function_name: str,
            function_args: Dict[str, Any],
    ) -> InteractionEvent:
        if function_name == "message_ask_user":
            return InteractionEvent(
                action_id=str(uuid.uuid4()),
                interaction_type=InteractionType.ASK_USER,
                status=InteractionStatus.PENDING,
                tool_call_id=tool_call_id,
                tool_name=tool.name,
                function_name=function_name,
                function_args=function_args,
                prompt=str(function_args.get("text") or "请提供更多信息"),
                description=function_args.get("description"),
                options=self._interaction_options(function_args),
                allow_multiple=bool(function_args.get("allow_multiple", False)),
                allow_text=bool(function_args.get("allow_text", True)),
                placeholder=function_args.get("placeholder"),
            )

        return InteractionEvent(
            action_id=str(uuid.uuid4()),
            interaction_type=InteractionType.TOOL_APPROVAL,
            status=InteractionStatus.PENDING,
            tool_call_id=tool_call_id,
            tool_name=tool.name,
            function_name=function_name,
            function_args=function_args,
            prompt=f"确认执行高风险工具：{function_name}",
            description="该工具可能修改数据、文件或运行环境，请确认后继续。",
            allow_text=False,
            risk_level=tool.get_risk_level(function_name),
        )

    async def _continue_tool_loop(
            self,
            message: Dict[str, Any],
    ) -> AsyncGenerator[BaseEvent, None]:
        """从一个 Assistant 消息开始执行 Tool Loop，并在需要人类输入时安全暂停。"""
        for _ in range(self._agent_config.max_iterations):
            if not message or not message.get("tool_calls"):
                break

            tool_messages = []
            for tool_call in message["tool_calls"]:
                if not tool_call.get("function"):
                    continue

                tool_call_id = tool_call.get("id") or str(uuid.uuid4())
                function_name = tool_call["function"]["name"]
                function_args = await self._json_parser.invoke(
                    tool_call["function"]["arguments"]
                )
                tool = self._get_tool(function_name)

                yield ToolEvent(
                    tool_call_id=tool_call_id,
                    tool_name=tool.name,
                    function_name=function_name,
                    function_args=function_args,
                    status=ToolEventStatus.CALLING,
                )

                approval_policy = tool.get_approval_policy(function_name)
                if function_name == "message_ask_user" or approval_policy == "ask":
                    yield self._build_interaction_event(
                        tool,
                        tool_call_id,
                        function_name,
                        function_args,
                    )
                    return

                if approval_policy == "deny":
                    result = ToolResult(
                        success=False,
                        message="工具策略已禁止执行该调用。",
                    )
                else:
                    result = await self._invoke_tool(tool, function_name, function_args)

                yield ToolEvent(
                    tool_call_id=tool_call_id,
                    tool_name=tool.name,
                    function_name=function_name,
                    function_args=function_args,
                    function_result=result,
                    status=ToolEventStatus.CALLED,
                )
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "function_name": function_name,
                    "content": result.model_dump_json(),
                })

            message = await self._invoke_llm(tool_messages)
        else:
            yield ErrorEvent(
                error=f"Agent迭代超过最大迭代次数: {self._agent_config.max_iterations}, 任务处理失败"
            )
            return

        if message and message.get("content") is not None:
            yield MessageEvent(message=message["content"])
        else:
            yield ErrorEvent(error="Agent未能生成有效回复内容")

    async def resume_interaction(
            self,
            resolution: InteractionResolution,
    ) -> AsyncGenerator[BaseEvent, None]:
        """从持久化 Memory 尾部精确恢复一个待处理 Tool Call。"""
        await self._ensure_memory()
        last_message = self._memory.get_last_message()
        tool_calls = (last_message or {}).get("tool_calls") or []
        if len(tool_calls) != 1:
            raise RuntimeError("无法恢复交互：Memory 中没有唯一的待处理工具调用")

        tool_call = tool_calls[0]
        function = tool_call.get("function") or {}
        tool_call_id = tool_call.get("id")
        function_name = function.get("name")
        function_args = await self._json_parser.invoke(function.get("arguments") or "{}")

        if tool_call_id != resolution.tool_call_id:
            raise RuntimeError("无法恢复交互：Tool Call ID 不匹配")
        if function_name != resolution.function_name:
            raise RuntimeError("无法恢复交互：工具函数不匹配")
        if function_args != resolution.function_args:
            raise RuntimeError("无法恢复交互：工具参数不匹配")

        tool = self._get_tool(function_name)
        if resolution.interaction_type == InteractionType.ASK_USER:
            if function_name != "message_ask_user" or resolution.decision != InteractionDecision.ANSWER:
                raise RuntimeError("无法恢复交互：询问决定与工具不匹配")
            result = ToolResult(
                success=True,
                data={
                    "answer": resolution.answer or "",
                    "selected_values": resolution.selected_values,
                },
            )
        elif resolution.interaction_type == InteractionType.TOOL_APPROVAL:
            if resolution.decision == InteractionDecision.APPROVE:
                result = await self._invoke_tool(tool, function_name, function_args)
            elif resolution.decision == InteractionDecision.REJECT:
                result = ToolResult(success=False, message="用户拒绝执行该工具调用。")
            else:
                raise RuntimeError("无法恢复交互：审批决定无效")
        else:
            raise RuntimeError("无法恢复交互：未知交互类型")

        yield ToolEvent(
            tool_call_id=tool_call_id,
            tool_name=tool.name,
            function_name=function_name,
            function_args=function_args,
            function_result=result,
            status=ToolEventStatus.CALLED,
        )
        next_message = await self._invoke_llm([{
            "role": "tool",
            "tool_call_id": tool_call_id,
            "function_name": function_name,
            "content": result.model_dump_json(),
        }])
        async for event in self._continue_tool_loop(next_message):
            yield event

    async def invoke(self, query: str, format: Optional[str] = None) -> AsyncGenerator[BaseEvent, None]:
        """传递消息+响应格式调用程序生成异步迭代内容"""
        # 1.需要判断下是否传递了format
        format = format if format else self._format

        # 2.调用语言模型获取响应内容
        message = await self._invoke_llm(
            [{"role": "user", "content": query}],
            format,
        )

        # 3.继续执行工具循环；需要人类输入时该生成器会在实际调用前安全结束。
        async for event in self._continue_tool_loop(message):
            yield event

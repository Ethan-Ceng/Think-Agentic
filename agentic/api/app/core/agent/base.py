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
from dataclasses import dataclass
from time import monotonic
from typing import Optional, List, AsyncGenerator, Dict, Any, Callable, Literal

from app.core.json_parser.base import JSONParser
from app.core.llm.base import (
    LLM,
    LLMStreamCompleted,
    LLMStreamDelta,
    LLMStreamingUnsupportedError,
)
from app.core.llm.json_stream import TopLevelJSONStringProjector
from app.core.llm.failure import ModelFailureCode, ModelRuntimeError, model_failure
from app.core.entities.app_config import AgentConfig
from app.core.entities.failure import RunFailureCode, run_failure
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
from app.core.entities.session import BranchContextMessage
from app.core.entities.tool_result import ToolResult
from app.repositories.uow import IUnitOfWork
from app.core.tools.base import BaseTool
from app.core.tools.registry import ToolRegistry
from app.core.tools.scope import RuntimeToolScope
from app.core.tools.schema_resolver import ToolSchemaResolver
from app.services.skill_runtime_service import SkillRuntimeContext
from app.services.trace_service import TraceService, elapsed_ms, model_call_timer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProjectedMessageDelta:
    """Agent 内部的安全可见文本增量，公共事件在 Flow 边界映射。"""

    delta: str
    operation: Literal["append", "reset", "abort"] = "append"


@dataclass(frozen=True, slots=True)
class ProjectedLLMCompleted:
    """一次模型调用完成并写入 Memory 后的权威消息。"""

    message: Dict[str, Any]
    streamed: bool = False


class BaseAgent(ABC):
    """基础Agent智能体"""
    name: str = ""  # 智能体名字
    _system_prompt: str = ""  # 系统预设prompt
    _format: Optional[str] = None  # Agent的响应格式
    _retry_interval: float = 1.0  # 重试间隔
    _tool_choice: Optional[str] = None  # 强制选择工具
    _stream_batch_chars: int = 32
    _stream_batch_interval: float = 0.05

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
            tool_registry: ToolRegistry | None = None,
            runtime_tool_scope: RuntimeToolScope | None = None,
            streaming_enabled: bool = False,
    ) -> None:
        """构造函数，完成Agent的初始化"""
        self._uow_factory = uow_factory
        self._uow = uow_factory()
        self._session_id = session_id
        self._agent_config = agent_config
        self._llm = llm
        self._memory: Optional[Memory] = None
        self._branch_context_seed: List[BranchContextMessage] = []
        self._json_parser = json_parser
        self._tools = tools
        self._trace_service = trace_service
        self._skill_runtime_context = skill_runtime_context or SkillRuntimeContext()
        self._runtime_system_prompt: Optional[str] = None
        self._tool_registry = tool_registry
        self._runtime_tool_scope = runtime_tool_scope or next(
            (
                getattr(tool, "runtime_scope")
                for tool in tools
                if getattr(tool, "runtime_scope", None) is not None
            ),
            None,
        )
        self._streaming_enabled = streaming_enabled

    def set_skill_runtime_context(self, context: SkillRuntimeContext) -> None:
        """Replace the transient per-run Skill context without touching Memory."""
        self._skill_runtime_context = context

    def set_runtime_system_prompt(self, prompt: str | None) -> None:
        """Override the System Prompt in this run's LLM view, not persisted Memory."""
        self._runtime_system_prompt = prompt

    def get_available_tool_names(self) -> set[str]:
        """Return both tool-group and callable names used by Skill constraints."""
        names = {tool.name for tool in self._tools if tool.name}
        for tool_schema in self._get_configured_tools():
            function = tool_schema.get("function") or {}
            name = function.get("name")
            if name:
                names.add(name)
        return names

    def set_runtime_tool_scope(
        self,
        capabilities: List[str] | None,
        *,
        provider_ids: List[str] | None = None,
        tool_ids: List[str] | None = None,
        exact_functions: List[str] | None = None,
    ) -> None:
        """Activate the current Step boundary on all shared filtered tools."""
        if self._runtime_tool_scope is not None:
            self._runtime_tool_scope.activate(
                capabilities,
                provider_ids=provider_ids,
                tool_ids=tool_ids,
                exact_functions=exact_functions,
            )

    def _get_llm_messages(self) -> List[Dict[str, Any]]:
        """Build one model-call view with transient context after the base prompt."""
        messages = [message.copy() for message in self._memory.get_messages()]
        if self._runtime_system_prompt:
            system_index = next(
                (
                    index
                    for index, message in enumerate(messages)
                    if message.get("role") == "system"
                ),
                None,
            )
            runtime_system = {
                "role": "system",
                "content": self._runtime_system_prompt,
            }
            if system_index is None:
                messages.insert(0, runtime_system)
            else:
                messages[system_index] = runtime_system
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
                if self._memory.empty:
                    self._branch_context_seed = (
                        await self._uow.session.get_branch_context_seed(self._session_id)
                    )

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """获取Agent所有可用的工具列表参数声明/Schema"""
        return ToolSchemaResolver.resolve_tools(self._tools)

    def _get_configured_tools(self) -> List[Dict[str, Any]]:
        """Return schemas after ToolConfig but before the current runtime scope."""
        return ToolSchemaResolver.resolve_tools(
            self._tools,
            configured_only=True,
        )

    def _get_tool(self, tool_name: str) -> BaseTool:
        """获取对应工具所在的工具集/包"""
        # 1.循环遍历所有工具包
        for tool in self._tools:
            # 2.判断工具包中是否存在该工具
            if tool.has_tool(tool_name):
                return tool

        raise ValueError(f"未知工具: {tool_name}")

    def _get_registered_tool(self, tool_name: str) -> BaseTool | None:
        """Find the owning bundle without treating runtime visibility as existence."""
        for tool in self._tools:
            if tool.has_registered_tool(tool_name):
                return tool
        return None

    async def _prepare_tool_schemas(self) -> None:
        """Resolve selected external schemas before a model call, never globally."""
        for tool in self._tools:
            prepare = getattr(tool, "prepare_for_scope", None)
            if prepare is not None:
                await prepare()

    async def _invoke_llm(
            self,
            messages: List[Dict[str, Any]],
            format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """保持现有块调用接口，并复用统一模型调用生命周期。"""
        completed: ProjectedLLMCompleted | None = None
        async for event in self._invoke_llm_stream(messages, format):
            if isinstance(event, ProjectedLLMCompleted):
                completed = event
        if completed is None:
            raise RuntimeError("调用语言模型未返回完成消息")
        return completed.message

    async def _invoke_llm_stream(
            self,
            messages: List[Dict[str, Any]],
            format: Optional[str] = None,
            *,
            stream_field: str | None = None,
    ) -> AsyncGenerator[ProjectedMessageDelta | ProjectedLLMCompleted, None]:
        """统一处理流式/块响应、重试、Memory 与 Trace。"""
        await self._prepare_tool_schemas()
        await self._add_to_memory(messages)
        response_format = {"type": format} if format else None
        draft_active = False
        last_model_error = ModelRuntimeError(
            model_failure(ModelFailureCode.UNKNOWN_ERROR)
        )

        for attempt in range(self._agent_config.max_retries):
            available_tools = self._get_available_tools()
            configured_tool_count = len(self._get_configured_tools())
            llm_messages = self._get_llm_messages()
            model_call_id = None
            model_started = model_call_timer()
            trace_finished = False
            try:
                if self._trace_service:
                    model_call_id = await self._trace_service.record_model_call_started(
                        agent_name=self.name,
                        llm=self._llm,
                        messages=llm_messages,
                        tools=available_tools,
                        response_format=response_format,
                        tool_choice=self._tool_choice,
                        capability_groups=(
                            list(self._runtime_tool_scope.capabilities)
                            if self._runtime_tool_scope
                            else []
                        ),
                        provider_ids=(
                            list(self._runtime_tool_scope.provider_ids)
                            if self._runtime_tool_scope
                            else []
                        ),
                        tool_ids=(
                            list(self._runtime_tool_scope.tool_ids)
                            if self._runtime_tool_scope
                            else []
                        ),
                        tool_scope_excluded_count=max(
                            0,
                            configured_tool_count - len(available_tools),
                        ),
                    )

                stream = getattr(self._llm, "stream", None)
                use_stream = bool(stream_field and callable(stream))
                message: Dict[str, Any] | None = None
                attempt_visible = False
                pending_delta = ""
                last_emit = monotonic()

                if use_stream:
                    projector = TopLevelJSONStringProjector(stream_field)
                    stream_event_received = False
                    try:
                        async for stream_event in stream(
                            messages=llm_messages,
                            tools=available_tools,
                            response_format=response_format,
                            tool_choice=self._tool_choice,
                        ):
                            stream_event_received = True
                            if isinstance(stream_event, LLMStreamCompleted):
                                message = stream_event.message
                                continue
                            if not isinstance(stream_event, LLMStreamDelta):
                                raise RuntimeError("LLM流返回了未知事件")
                            projected = projector.feed(stream_event.content or "")
                            if not projected:
                                continue
                            if not attempt_visible:
                                attempt_visible = True
                                draft_active = True
                                last_emit = monotonic()
                                yield ProjectedMessageDelta(delta=projected)
                                continue
                            pending_delta += projected
                            if (
                                len(pending_delta) >= self._stream_batch_chars
                                or monotonic() - last_emit >= self._stream_batch_interval
                            ):
                                yield ProjectedMessageDelta(delta=pending_delta)
                                pending_delta = ""
                                last_emit = monotonic()
                    except (LLMStreamingUnsupportedError, NotImplementedError):
                        if stream_event_received:
                            raise
                        logger.warning(
                            "LLM Provider不支持流式响应，安全回退块调用: %s",
                            self._llm.model_name,
                        )
                        message = await self._llm.invoke(
                            messages=llm_messages,
                            tools=available_tools,
                            response_format=response_format,
                            tool_choice=self._tool_choice,
                        )
                        use_stream = False
                    else:
                        if pending_delta:
                            yield ProjectedMessageDelta(delta=pending_delta)
                        if message is None:
                            raise RuntimeError("LLM流未返回完成消息")
                else:
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
                    trace_finished = True

                filtered_message = self._filter_llm_message(message)
                if filtered_message is None:
                    logger.warning("LLM回复了空内容，执行重试")
                    last_model_error = ModelRuntimeError(
                        model_failure(ModelFailureCode.EMPTY_RESPONSE)
                    )
                    await self._add_to_memory([
                        {"role": "assistant", "content": ""},
                        {"role": "user", "content": "AI无响应内容，请继续。"},
                    ])
                    if draft_active:
                        operation = (
                            "abort"
                            if attempt == self._agent_config.max_retries - 1
                            else "reset"
                        )
                        yield ProjectedMessageDelta(delta="", operation=operation)
                        if operation == "abort":
                            draft_active = False
                    if attempt < self._agent_config.max_retries - 1:
                        await asyncio.sleep(self._retry_interval)
                    continue

                await self._add_to_memory([filtered_message])
                yield ProjectedLLMCompleted(
                    message=filtered_message,
                    streamed=draft_active,
                )
                return
            except Exception as exception:
                if isinstance(exception, ModelRuntimeError):
                    current_error = exception
                elif isinstance(
                    exception,
                    (LLMStreamingUnsupportedError, NotImplementedError),
                ):
                    current_error = ModelRuntimeError(
                        model_failure(ModelFailureCode.INVALID_RESPONSE),
                        cause=exception,
                    )
                else:
                    current_error = ModelRuntimeError(
                        model_failure(ModelFailureCode.UNKNOWN_ERROR),
                        cause=exception,
                    )
                last_model_error = current_error
                if self._trace_service and not trace_finished:
                    await self._trace_service.record_model_call_finished(
                        model_call_id,
                        error=current_error.failure.message,
                        latency_ms=elapsed_ms(model_started),
                    )
                logger.error(
                    "调用语言模型失败: code=%s debug_id=%s error_type=%s",
                    current_error.failure.code,
                    current_error.failure.debug_id,
                    type(exception).__name__,
                )
                terminal_attempt = (
                    not current_error.failure.retryable
                    or attempt == self._agent_config.max_retries - 1
                )
                if draft_active:
                    operation = "abort" if terminal_attempt else "reset"
                    yield ProjectedMessageDelta(delta="", operation=operation)
                    if operation == "abort":
                        draft_active = False
                if not current_error.failure.retryable:
                    raise current_error
                if not terminal_attempt:
                    await asyncio.sleep(self._retry_interval)

        raise last_model_error

    @staticmethod
    def _filter_llm_message(message: Dict[str, Any]) -> Dict[str, Any] | None:
        if message.get("role") == "assistant":
            if not message.get("content") and not message.get("tool_calls"):
                return None
            filtered_message = {
                "role": "assistant",
                "content": message.get("content"),
            }
            if message.get("reasoning_content"):
                filtered_message["reasoning_content"] = message.get("reasoning_content")
            if message.get("tool_calls"):
                filtered_message["tool_calls"] = message.get("tool_calls")[:1]
            return filtered_message

        logger.warning("LLM响应内容无法确认消息角色: %s", message.get("role"))
        return {
            key: value
            for key, value in message.items()
            if key != "_trace_metadata"
        }

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
            self._memory.add_messages([
                self._branch_seed_to_memory_message(item)
                for item in self._branch_context_seed
            ])
            self._branch_context_seed = []

        # 3.将正常消息添加到记忆中
        self._memory.add_messages(messages)

        # 4.将记忆持久化到数据仓库中
        async with self._uow:
            await self._uow.session.save_memory(self._session_id, self.name, self._memory)

    @staticmethod
    def _branch_seed_to_memory_message(
            item: BranchContextMessage,
    ) -> Dict[str, Any]:
        content = item.content
        if item.attachment_names:
            content = (
                f"{content}\n\n历史附件文件名："
                f"{'、'.join(item.attachment_names)}"
            )
        return {"role": item.role, "content": content}

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
        if function_name != "message_ask_user":
            raise RuntimeError("只有业务输入请求可以创建 Interaction")
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

    async def _continue_tool_loop(
            self,
            message: Dict[str, Any],
            *,
            stream_field: str | None = None,
    ) -> AsyncGenerator[BaseEvent | ProjectedMessageDelta, None]:
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
                tool = self._get_registered_tool(function_name)
                tool_bundle_name = tool.name if tool is not None else "unknown"

                yield ToolEvent(
                    tool_call_id=tool_call_id,
                    tool_name=tool_bundle_name,
                    function_name=function_name,
                    function_args=function_args,
                    status=ToolEventStatus.CALLING,
                )

                if tool is None:
                    result = ToolResult(
                        success=False,
                        message=f"未知工具: {function_name}",
                    )
                elif function_name == "message_ask_user" and tool.has_tool(
                    function_name
                ):
                    yield self._build_interaction_event(
                        tool,
                        tool_call_id,
                        function_name,
                        function_args,
                    )
                    return
                elif tool.get_execution_policy(function_name) == "deny":
                    result = ToolResult(
                        success=False,
                        message="工具策略已禁止执行该调用。",
                    )
                else:
                    result = await self._invoke_tool(tool, function_name, function_args)

                yield ToolEvent(
                    tool_call_id=tool_call_id,
                    tool_name=tool_bundle_name,
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

            next_message: Dict[str, Any] | None = None
            async for llm_event in self._invoke_llm_stream(
                tool_messages,
                stream_field=stream_field,
            ):
                if isinstance(llm_event, ProjectedMessageDelta):
                    yield llm_event
                else:
                    next_message = llm_event.message
            if next_message is None:
                yield ErrorEvent(
                    failure=model_failure(ModelFailureCode.INVALID_RESPONSE)
                )
                return
            message = next_message
        else:
            yield ErrorEvent(failure=run_failure(RunFailureCode.ITERATION_LIMIT))
            return

        if message and message.get("content") is not None:
            yield MessageEvent(message=message["content"])
        else:
            yield ErrorEvent(failure=model_failure(ModelFailureCode.EMPTY_RESPONSE))

    async def resume_interaction(
            self,
            resolution: InteractionResolution,
            *,
            stream_field: str | None = None,
    ) -> AsyncGenerator[BaseEvent | ProjectedMessageDelta, None]:
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
                raise RuntimeError(
                    "工具审批机制已停用，历史工具调用不能批准执行"
                )
            elif resolution.decision == InteractionDecision.REJECT:
                result = ToolResult(
                    success=False,
                    message="工具审批机制已停用；历史工具调用未执行。",
                )
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
        next_message: Dict[str, Any] | None = None
        async for llm_event in self._invoke_llm_stream(
            [{
                "role": "tool",
                "tool_call_id": tool_call_id,
                "function_name": function_name,
                "content": result.model_dump_json(),
            }],
            stream_field=stream_field,
        ):
            if isinstance(llm_event, ProjectedMessageDelta):
                yield llm_event
            else:
                next_message = llm_event.message
        if next_message is None:
            yield ErrorEvent(
                failure=model_failure(ModelFailureCode.INVALID_RESPONSE)
            )
            return
        async for event in self._continue_tool_loop(
            next_message,
            stream_field=stream_field,
        ):
            yield event

    async def invoke(
            self,
            query: str,
            format: Optional[str] = None,
            *,
            stream_field: str | None = None,
    ) -> AsyncGenerator[BaseEvent | ProjectedMessageDelta, None]:
        """传递消息+响应格式调用程序生成异步迭代内容"""
        # 1.需要判断下是否传递了format
        format = format if format else self._format

        # 2.调用语言模型获取响应内容
        message: Dict[str, Any] | None = None
        async for llm_event in self._invoke_llm_stream(
            [{"role": "user", "content": query}],
            format,
            stream_field=stream_field,
        ):
            if isinstance(llm_event, ProjectedMessageDelta):
                yield llm_event
            else:
                message = llm_event.message
        if message is None:
            yield ErrorEvent(
                failure=model_failure(ModelFailureCode.INVALID_RESPONSE)
            )
            return

        # 3.继续执行工具循环；需要人类输入时该生成器会在实际调用前安全结束。
        async for event in self._continue_tool_loop(
            message,
            stream_field=stream_field,
        ):
            yield event

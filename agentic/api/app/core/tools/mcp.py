#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/27 9:43
@Author  : thezehui@gmail.com
@File    : mcp.py
"""
import copy
import hashlib
import json
import logging
import os
import re
import unicodedata
from contextlib import AsyncExitStack
from typing import Optional, Dict, List, Any, Callable

from mcp import ClientSession, Tool, StdioServerParameters, stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

from app.schemas.exceptions import NotFoundError
from app.core.config import get_settings
from app.core.entities.app_config import MCPConfig, MCPServerConfig, MCPTransport
from app.core.entities.tool_result import ToolResult
from app.core.tools.provider_catalog import mcp_provider_id
from app.core.tools.provider_runtime import MCPProviderPool
from .base import BaseTool

"""
MCP客户端管理器的开发思路:
1.在Agent执行的过程中，有可能需要调用多次工具,
  但是因为MCP工具的每次获取都需要调用客户端会话的list_tools()方法,
  非常耗时, 所以需要我们缓存工具的参数信息, 只有在初始化的时候才调用一次,
  并且在销毁MCP客户端管理器的时候一并清除;
2.在前端UI交互中, 无论MCP服务是否启动, 都会显示工具列表信息,
  但是在Agent执行的过程中, 我们只会传递已启动的MCP服务,
  所以对于MCP客户端管理器来说, 可以根据接收的MCP配置的差异加载不同的服务器,
  而不是仅从配置文件中读取数据;
3.MCP客户端管理器会同时管理多个MCP服务, 有可能有stdio、sse、streamable_http等传输协议.
  需要根据传输协议的不同来创建客户端会话(ClientSession), 同时缓存会话;
4.另外有可能有一些环境变量是存储在我们整个系统中的, 在初始化MCP服务的时候，需要将传递进来的
  环境变量与系统的环境变量进行合并后传递给MCP服务;
5.使用AsyncExitStack异步上下文管理器来管理上下文，避免使用with多层嵌套;
6.MCPClientManager的初始化非常耗时, 所以需要有机制可以判断避免重复初始化;
7.由于config.yaml是直接暴露在项目中的, 所以在使用config.yaml进行初始化的时候必须二次校验;
8.同时缓存ClientSession+Tool-Schema, 一个是客户端会话, 一个是工具参数声明;
9.MCP客户端管理器在清除/停止使用的时候, 必须关闭异步上下文管理器、清除资源(ClientSession、Tool-Schema)、
  初始化标识等, 从而避免资源泄露;
"""

logger = logging.getLogger(__name__)

_MAX_MCP_FUNCTION_NAME = 64


def _mcp_function_token(value: str) -> str:
    """Normalize one MCP name segment and preserve collision resistance."""
    raw = str(value).strip()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_value).strip("_-").lower()
    token = token or "tool"
    if raw != token:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        token = f"{token[:32].rstrip('_-') or 'tool'}_{digest}"
    return token


def _bounded_mcp_function_name(candidate: str, identity: str) -> str:
    if len(candidate) <= _MAX_MCP_FUNCTION_NAME:
        return candidate
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8]
    prefix = candidate[: _MAX_MCP_FUNCTION_NAME - len(digest) - 1].rstrip("_-")
    return f"{prefix}_{digest}"


def _mcp_search_function_name(server_name: str) -> str:
    provider_token = _mcp_function_token(
        mcp_provider_id(server_name).removeprefix("mcp.")
    )
    return _bounded_mcp_function_name(
        f"mcp_{provider_token}_search_tools",
        f"search\0{server_name}",
    )


def _mcp_tool_function_name(server_name: str, tool_name: str) -> str:
    provider_token = _mcp_function_token(
        mcp_provider_id(server_name).removeprefix("mcp.")
    )
    tool_token = _mcp_function_token(tool_name)
    candidate = f"mcp_{provider_token}_{tool_token}"
    if candidate == _mcp_search_function_name(server_name):
        candidate = f"mcp_{provider_token}_tool_{tool_token}"
    return _bounded_mcp_function_name(
        candidate,
        f"tool\0{server_name}\0{tool_name}",
    )


class MCPClientManager:
    """MCP客户端管理器"""

    def __init__(self, mcp_config: Optional[MCPConfig] = None) -> None:
        """构造函数，完成MCP客户端管理器的初步初始化"""
        self._mcp_config: MCPConfig = mcp_config or MCPConfig()  # mcp配置信息
        self._exit_stack: AsyncExitStack = AsyncExitStack()  # 异步上下文管理器
        self._clients: Dict[str, ClientSession] = {}  # 缓存的客户端会话
        self._tools: Dict[str, List[Tool]] = {}  # 缓存的MCP工具参数声明
        self._initialized: bool = False  # 是否初始化标识

    @property
    def tools(self) -> Dict[str, List[Tool]]:
        """只读属性，返回缓存的MCP工具参数声明，键就是服务名字，值就是服务对应的工具声明"""
        return self._tools

    async def initialize(self) -> None:
        """初始化函数，用于连接所有配置的MCP服务器"""
        # 1.检查下是否已经初始化成功
        if self._initialized:
            return

        try:
            # 2.记录日志并连接MCP服务器
            logger.info(f"从config.yaml中加载了{len(self._mcp_config.mcpServers)}个MCP服务器")
            await self._connect_mcp_servers()
            self._initialized = True
            logger.info("MCP客户端管理器加载成功")
        except Exception as e:
            # 3.记录错误信息并直接抛出
            logger.error(f"MCP客户端管理器加载失败: {str(e)}")
            raise

    async def _connect_mcp_servers(self) -> None:
        """根据配置连接所有MCP服务"""
        failures: list[Exception] = []
        # 1.循环遍历传递进来的所有MCP服务器，不用理会enabled的状态，因为在外部会执行筛选
        for server_name, server_config in self._mcp_config.mcpServers.items():
            try:
                # 2.根据服务名字+服务配置连接到MCP服务器
                await self._connect_mcp_server(server_name, server_config)
            except Exception as e:
                # 3.记录错误日志并跳过错误的MCP服务器
                logger.error(f"连接MCP服务器[{server_name}]出错: {str(e)}")
                failures.append(e)
                continue
        if self._mcp_config.mcpServers and not self._clients and failures:
            raise RuntimeError("all configured MCP servers failed to connect") from failures[-1]

    async def _connect_mcp_server(self, server_name: str, server_config: MCPServerConfig) -> None:
        """根据传递的服务名字+服务配置连接到单个MCP服务"""
        try:
            # 1.获取mcp服务的传输协议
            transport = server_config.transport

            # 2.根据不同的传输协议调用不同的方法连接MCP服务器
            if transport == MCPTransport.STDIO:
                await self._connect_stdio_server(server_name, server_config)
            elif transport == MCPTransport.SSE:
                await self._connect_sse_server(server_name, server_config)
            elif transport == MCPTransport.STREAMABLE_HTTP:
                await self._connect_streamable_http_server(server_name, server_config)
            else:
                raise ValueError(f"MCP服务[{server_name}]使用了不支持的传输协议: {transport}")
        except Exception as e:
            # 3.记录日志并抛出异常
            logger.error(f"连接MCP服务器[{server_name}]出错: {str(e)}")
            raise

    async def _connect_stdio_server(self, server_name: str, server_config: MCPServerConfig) -> None:
        """根据服务名字+配置连接stdio服务"""
        # 1.从配置中提取相关命令信息
        command = server_config.command
        args = server_config.args
        env = server_config.env

        # 2.检查command是否存在
        if not command:
            raise ValueError("连接stdio-mcp服务器需要配置command命令")

        # 3.构建stdio连接参数
        server_parameters = StdioServerParameters(
            command=command,
            args=args,
            env={**os.environ, **(env or {})},
        )

        try:
            # 4.使用异步上下文管理器创建传输协议
            stdio_transport = await self._exit_stack.enter_async_context(
                stdio_client(server_parameters),
            )
            read_stream, write_stream = stdio_transport

            # 5.根据读取与写入流构建会话
            session: ClientSession = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream),
            )

            # 6.初始化MCP服务会话
            await session.initialize()

            # 7.缓存对应的mcp连接客户端
            self._clients[server_name] = session

            # 8.缓存对应mcp服务的工具列表
            await self._cache_mcp_server_tools(server_name, session)
            logger.info(f"连接stdio-mcp服务器成功: {server_name}")
        except Exception as e:
            # 记录错误日志并直接抛出异常
            logger.error(f"连接stdio-mcp服务器失败: {str(e)}")
            raise

    async def _connect_sse_server(self, server_name: str, server_config: MCPServerConfig) -> None:
        """根据服务名字+配置连接sse服务"""
        # 1.提取sse服务器的连接url并判断是否存在
        url = server_config.url
        if not url:
            raise ValueError("连接sse-mcp服务器需要配置url")

        try:
            # 2.建立sse连接
            sse_transport = await self._exit_stack.enter_async_context(
                sse_client(url=url, headers=server_config.headers),
            )
            read_stream, write_stream = sse_transport

            # 3.创建客户端会话
            session: ClientSession = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream),
            )

            # 4.初始化MCP服务会话
            await session.initialize()

            # 5.缓存对应的mcp连接客户端
            self._clients[server_name] = session

            # 6.缓存对应mcp服务的工具列表
            await self._cache_mcp_server_tools(server_name, session)
            logger.info(f"连接sse-mcp服务器成功: {server_name}")
        except Exception as e:
            # 7.记录错误日志并直接抛出异常
            logger.error(f"连接sse-mcp服务器失败: {str(e)}")
            raise

    async def _connect_streamable_http_server(self, server_name: str, server_config: MCPServerConfig) -> None:
        """根据服务名字+配置连接streamable-http服务"""
        # 1.提取streamable-http服务器的连接url并判断是否存在
        url = server_config.url
        if not url:
            raise ValueError("连接sse-mcp服务器需要配置url")

        try:
            # 2.连接streamable-http服务
            streamable_http_transport = await self._exit_stack.enter_async_context(
                streamablehttp_client(url=url, headers=server_config.headers),
            )

            # 3.streamable-http模型需要解包获取输入与输出流
            if len(streamable_http_transport) == 3:
                read_stream, write_stream, _ = streamable_http_transport
            else:
                read_stream, write_stream = streamable_http_transport

            # 4.创建客户端会话
            session: ClientSession = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream),
            )

            # 5.初始化MCP服务会话
            await session.initialize()

            # 6.缓存对应的mcp连接客户端
            self._clients[server_name] = session

            # 7.缓存对应mcp服务的工具列表
            await self._cache_mcp_server_tools(server_name, session)
            logger.info(f"连接streamable-http-mcp服务器成功: {server_name}")
        except Exception as e:
            # 7.记录错误日志并直接抛出异常
            logger.error(f"连接streamable-http-mcp服务器失败: {str(e)}")
            raise

    async def _cache_mcp_server_tools(self, server_name: str, session: ClientSession) -> None:
        """根据传递的服务名字+会话缓存mcp服务工具列表"""
        try:
            tools_response = await session.list_tools()
            tools = tools_response.tools if tools_response else []
            self._tools[server_name] = tools
            logger.info(f"MCP服务器[{server_name}]提供了{len(tools)}个工具")
        except Exception as e:
            # 记录日志并将缓存设置为空
            logger.error(f"获取MCP服务器[{server_name}]工具列表失败: {str(e)}")
            self._tools[server_name] = []
            raise

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """获取所有MCP工具列表，返回LLM可以使用的工具参数声明列表并处理MCP的名字"""
        # 1.定义一个变量存储所有结果
        all_tools = []

        # 2.循环遍历所有缓存的工具
        for server_name, tools in self._tools.items():
            # 3.循环取出每个MCP服务的工具列表
            for tool in tools:
                # 4.修改工具名字加上mcp_前缀+服务名字
                tool_name = _mcp_tool_function_name(server_name, tool.name)

                # 5.生成OpenAI工具描述
                tool_schema = {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": f"[{server_name}] {tool.description or tool.name}",
                        "parameters": tool.inputSchema,
                    }
                }
                all_tools.append(tool_schema)

        return all_tools

    async def invoke(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """根据传递的工具名字+参数调用MCP工具"""
        try:
            # 1.定义变量存储原始的服务名字+工具
            original_server_name = None
            original_tool_name = None

            # 2. Resolve the model-facing name through the same normalized map.
            for server_name, tools in self._tools.items():
                expected_names = {
                    _mcp_tool_function_name(server_name, tool.name): tool.name
                    for tool in tools
                }

                if tool_name in expected_names:
                    original_server_name = server_name
                    original_tool_name = expected_names[tool_name]
                    break

            # 6.判断服务名字+工具是否都存在
            if not original_server_name or not original_tool_name:
                raise NotFoundError(f"服务器解析MCP工具不存在: {tool_name}")

            # 7.获取该工具所属的会话
            session = self._clients.get(original_server_name)
            if not session:
                raise RuntimeError("MCP server session is unavailable")

            # 8.使用会话调用工具
            result = await session.call_tool(original_tool_name, arguments)

            # 9.判断结果是否存在执行不同的操作
            if result:
                # 10.处理MCP工具生成的content
                content = []
                if hasattr(result, "content") and result.content:
                    for item in result.content:
                        if hasattr(item, "text"):
                            content.append(item.text)
                        else:
                            content.append(str(item))

                # 11.返回工具结果
                return ToolResult(
                    success=True,
                    data="\n".join(content) if content else "工具执行成功"
                )
            else:
                return ToolResult(success=True, data="工具执行成功")
        except Exception:
            # The Actor owns failure classification, backoff and public output.
            logger.exception("调用 MCP 工具 [%s] 失败", tool_name)
            raise

    async def cleanup(self) -> None:
        """当退出MCP服务时，清除对应资源

        该方法是幂等的，多次调用不会产生副作用。
        注意：必须在初始化MCP的同一个asyncio Task中调用此方法，
        否则anyio会因cancel scope上下文不匹配而抛出RuntimeError。
        """
        try:
            await self._exit_stack.aclose()
            logger.info("清除MCP客户端管理器成功")
        except RuntimeError as e:
            # 防御性处理：anyio.create_task_group() 在不同任务中退出的已知问题
            if "Attempted to exit cancel scope in a different task" in str(e):
                logger.warning(f"清理MCP客户端管理器时遇到任务上下文切换警告（可忽略）: {str(e)}")
            else:
                logger.error(f"清理MCP客户端管理器失败: {str(e)}")
        except Exception as e:
            logger.error(f"清理MCP客户端管理器失败: {str(e)}")
        finally:
            # 无论aclose()是否成功，都必须清除缓存并重置状态
            self._clients.clear()
            self._tools.clear()
            self._initialized = False
            self._exit_stack = AsyncExitStack()


class MCPTool(BaseTool):
    """Provider-scoped MCP adapter with explicit Schema budget fallback."""
    name: str = "mcp"

    def __init__(
        self,
        mcp_config: Optional[MCPConfig] = None,
        *,
        manager_factory: Callable[[MCPConfig], MCPClientManager] | None = None,
        provider_pool: MCPProviderPool | None = None,
        user_id: str = "local",
    ) -> None:
        super().__init__()
        self._mcp_config = mcp_config or MCPConfig()
        self._manager_factory = manager_factory or (
            lambda config: MCPClientManager(mcp_config=config)
        )
        settings = get_settings()
        self._provider_pool = provider_pool or MCPProviderPool(
            manager_factory=self._manager_factory,
            snapshot_ttl_seconds=settings.mcp_schema_snapshot_ttl_seconds,
            snapshot_max_entries=settings.mcp_schema_snapshot_max_entries,
            idle_ttl_seconds=settings.mcp_provider_idle_ttl_seconds,
            operation_timeout_seconds=(
                settings.mcp_provider_operation_timeout_seconds
            ),
            backoff_base_seconds=settings.mcp_provider_backoff_base_seconds,
            backoff_max_seconds=settings.mcp_provider_backoff_max_seconds,
        )
        self._owns_provider_pool = provider_pool is None
        self._user_id = user_id
        self._initialized: bool = False
        self._tools: List[Dict[str, Any]] = []
        self._manager: MCPClientManager | None = None
        self._schemas_by_provider: Dict[str, List[Dict[str, Any]]] = {}
        self._active_names_by_provider: Dict[str, set[str]] = {}
        self._search_mode_provider_ids: set[str] = set()
        self._pending_scope_tool_ids: List[str] | None = None
        self._visible_provider_ids: set[str] = set()
        self._provider_by_function: Dict[str, str] = {}
        self._search_name_by_provider = {
            mcp_provider_id(server_name): _mcp_search_function_name(server_name)
            for server_name, config in self._mcp_config.mcpServers.items()
            if config.enabled
        }
        self._provider_by_search_name = {
            function_name: provider_id
            for provider_id, function_name in self._search_name_by_provider.items()
        }
        self._search_top_k = 8
        self._max_tool_schemas = 32
        self._max_schema_chars = 60000

    @property
    def config(self) -> MCPConfig:
        return self._mcp_config

    async def initialize(self, mcp_config: Optional[MCPConfig] = None) -> None:
        """Compatibility entry point; explicit callers still initialize enabled Providers."""
        if mcp_config is not None and mcp_config != self._mcp_config:
            shared_provider_pool = (
                None if self._owns_provider_pool else self._provider_pool
            )
            if self._owns_provider_pool:
                await self._provider_pool.close()
            self.__init__(
                mcp_config,
                manager_factory=self._manager_factory,
                provider_pool=shared_provider_pool,
                user_id=self._user_id,
            )
        await self.prepare_for_scope(
            capabilities=("mcp",),
            provider_ids=tuple(self._search_name_by_provider),
            max_tool_schemas=256,
            max_schema_chars=500000,
            search_top_k=32,
        )

    async def prepare_for_scope(
        self,
        *,
        capabilities,
        provider_ids,
        max_tool_schemas: int,
        max_schema_chars: int,
        search_top_k: int,
    ) -> bool:
        """Discover schemas only for explicitly selected MCP Providers."""
        previous_visible = set(self._visible_provider_ids)
        if "mcp" not in capabilities:
            self._visible_provider_ids.clear()
            return previous_visible != self._visible_provider_ids
        configured = set(self._search_name_by_provider)
        selected = [item for item in provider_ids if item in configured]
        if not provider_ids and len(configured) == 1:
            selected = sorted(configured)
        if not selected:
            self._visible_provider_ids.clear()
            return previous_visible != self._visible_provider_ids

        self._search_top_k = min(search_top_k, max_tool_schemas)
        self._max_tool_schemas = max_tool_schemas
        self._max_schema_chars = max_schema_chars
        self._visible_provider_ids = set(selected)
        changed = previous_visible != self._visible_provider_ids
        for provider_id in selected:
            if provider_id in self._schemas_by_provider:
                continue
            server_name = self._server_name(provider_id)
            if server_name is None:
                continue
            server_config = self._mcp_config.mcpServers[server_name]
            snapshot = await self._provider_pool.discover(
                user_id=self._user_id,
                provider_id=provider_id,
                server_name=server_name,
                server_config=server_config,
            )
            schemas = [
                copy.deepcopy(schema)
                for schema in snapshot.schemas
            ]
            self._schemas_by_provider[provider_id] = schemas
            for schema in schemas:
                self._provider_by_function[
                    schema["function"]["name"]
                ] = provider_id
            changed = True

        selected_schemas = [
            schema
            for provider_id in selected
            for schema in self._schemas_by_provider.get(provider_id, [])
        ]
        within_budget = self._schemas_fit_budget(selected_schemas)
        for provider_id in selected:
            previous_active = self._active_names_by_provider.get(provider_id, set())
            if within_budget:
                active = {
                    schema["function"]["name"]
                    for schema in self._schemas_by_provider.get(provider_id, [])
                }
                self._search_mode_provider_ids.discard(provider_id)
            else:
                if provider_id not in self._search_mode_provider_ids:
                    active = set()
                    self._search_mode_provider_ids.add(provider_id)
                else:
                    active = previous_active
            if active != previous_active:
                changed = True
            self._active_names_by_provider[provider_id] = active

        if not within_budget and self._clip_active_schemas_to_budget(selected):
            changed = True
        self._initialized = bool(self._schemas_by_provider)
        return changed

    def get_tools(self) -> List[Dict[str, Any]]:
        if not self._search_name_by_provider:
            return [copy.deepcopy(schema) for schema in self._tools]
        schemas: List[Dict[str, Any]] = []
        for provider_id in sorted(self._visible_provider_ids):
            schemas.append(self._search_schema(provider_id))
            active_names = self._active_names_by_provider.get(provider_id, set())
            schemas.extend(
                copy.deepcopy(schema)
                for schema in self._schemas_by_provider.get(provider_id, [])
                if schema["function"]["name"] in active_names
            )
        return schemas

    def provider_tool_schemas(
        self,
    ) -> List[tuple[str, str, List[Dict[str, Any]]]]:
        result = []
        for provider_id in sorted(self._search_name_by_provider):
            server_name = self._server_name(provider_id) or provider_id
            provider_schemas = [self._search_schema(provider_id)]
            active_names = self._active_names_by_provider.get(provider_id, set())
            provider_schemas.extend(
                copy.deepcopy(schema)
                for schema in self._schemas_by_provider.get(provider_id, [])
                if schema["function"]["name"] in active_names
            )
            result.append((provider_id, server_name, provider_schemas))
        if not result and self._tools:
            result.append(
                (
                    "mcp.dynamic",
                    "MCP",
                    [copy.deepcopy(schema) for schema in self._tools],
                )
            )
        return result

    def consume_scope_tool_ids(self) -> List[str] | None:
        """Return Tool IDs selected by search-tools exactly once."""
        tool_ids = (
            list(self._pending_scope_tool_ids)
            if self._pending_scope_tool_ids is not None
            else None
        )
        self._pending_scope_tool_ids = None
        return tool_ids

    def has_tool(self, tool_name: str) -> bool:
        return any(
            schema["function"]["name"] == tool_name
            for schema in self.get_tools()
        )

    async def invoke(self, tool_name: str, **kwargs) -> ToolResult:
        provider_id = self._provider_by_search_name.get(tool_name)
        if provider_id is not None:
            return self._search_tools(provider_id, str(kwargs.get("query") or ""))
        provider_id = self._provider_by_function.get(tool_name)
        if provider_id is None:
            return ToolResult(success=False, message="MCP Provider 未连接或不在当前范围内")
        server_name = self._server_name(provider_id)
        if server_name is None:
            return ToolResult(success=False, message="MCP Provider 未配置或已禁用")
        return await self._provider_pool.invoke(
            user_id=self._user_id,
            provider_id=provider_id,
            server_name=server_name,
            server_config=self._mcp_config.mcpServers[server_name],
            tool_name=tool_name,
            arguments=kwargs,
        )

    async def cleanup(self) -> None:
        if self._owns_provider_pool:
            await self._provider_pool.close()
        self._schemas_by_provider.clear()
        self._active_names_by_provider.clear()
        self._search_mode_provider_ids.clear()
        self._pending_scope_tool_ids = None
        self._visible_provider_ids.clear()
        self._provider_by_function.clear()
        self._manager = None
        self._initialized = False

    def _search_tools(self, provider_id: str, query: str) -> ToolResult:
        tokens = {
            token
            for token in re.findall(r"[\w-]+", query.lower())
            if token
        }
        ranked = []
        for schema in self._schemas_by_provider.get(provider_id, []):
            function = schema["function"]
            searchable = (
                f"{function['name']} {function.get('description', '')}"
            ).lower()
            score = sum(token in searchable for token in tokens)
            ranked.append((-score, function["name"], schema))
        ranked.sort(key=lambda item: (item[0], item[1]))
        selected = [item[2] for item in ranked[: self._search_top_k]]
        self._active_names_by_provider[provider_id] = {
            schema["function"]["name"] for schema in selected
        }
        self._clip_active_schemas_to_budget(sorted(self._visible_provider_ids))
        active_names = self._active_names_by_provider[provider_id]
        selected = [
            schema
            for schema in selected
            if schema["function"]["name"] in active_names
        ]
        self._pending_scope_tool_ids = [
            f"{active_provider_id}.{self._search_name_by_provider[active_provider_id]}"
            for active_provider_id in sorted(self._visible_provider_ids)
        ] + [
            f"{active_provider_id}.{schema['function']['name']}"
            for active_provider_id in sorted(self._visible_provider_ids)
            for schema in self._schemas_by_provider.get(active_provider_id, [])
            if schema["function"]["name"]
            in self._active_names_by_provider.get(active_provider_id, set())
        ]
        return ToolResult(
            success=True,
            data=[
                {
                    "tool_id": f"{provider_id}.{schema['function']['name']}",
                    "function_name": schema["function"]["name"],
                    "description": schema["function"].get("description", ""),
                }
                for schema in selected
            ],
        )

    def _schemas_fit_budget(self, schemas: List[Dict[str, Any]]) -> bool:
        if len(schemas) > self._max_tool_schemas:
            return False
        schema_chars = len(
            json.dumps(schemas, ensure_ascii=False, separators=(",", ":"))
        )
        return schema_chars <= self._max_schema_chars

    def _clip_active_schemas_to_budget(self, provider_ids: List[str]) -> bool:
        """Keep the selected Providers' active schemas within one Step budget."""
        kept_by_provider = {provider_id: set() for provider_id in provider_ids}
        kept_schemas: List[Dict[str, Any]] = []
        for provider_id in provider_ids:
            active_names = self._active_names_by_provider.get(provider_id, set())
            for schema in self._schemas_by_provider.get(provider_id, []):
                function_name = schema["function"]["name"]
                if function_name not in active_names:
                    continue
                candidate = [*kept_schemas, schema]
                if not self._schemas_fit_budget(candidate):
                    continue
                kept_schemas.append(schema)
                kept_by_provider[provider_id].add(function_name)

        changed = False
        for provider_id, kept_names in kept_by_provider.items():
            if self._active_names_by_provider.get(provider_id, set()) != kept_names:
                self._active_names_by_provider[provider_id] = kept_names
                changed = True
        return changed

    def _search_schema(self, provider_id: str) -> Dict[str, Any]:
        server_name = self._server_name(provider_id) or provider_id
        return {
            "type": "function",
            "function": {
                "name": self._search_name_by_provider[provider_id],
                "description": (
                    f"Search the available tools from MCP Provider [{server_name}] "
                    "when its full schema set is too large."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Capability or operation to find.",
                        }
                    },
                    "required": ["query"],
                },
            },
        }

    def _server_name(self, provider_id: str) -> str | None:
        for server_name, config in self._mcp_config.mcpServers.items():
            if config.enabled and mcp_provider_id(server_name) == provider_id:
                return server_name
        return None

    @staticmethod
    def _search_function_name(server_name: str) -> str:
        return _mcp_search_function_name(server_name)

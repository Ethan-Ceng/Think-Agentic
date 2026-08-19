#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import List

from app.core.browser.base import Browser
from app.core.entities.tool_config import ToolConfig
from app.core.sandbox.base import Sandbox
from app.core.search.base import SearchEngine
from app.core.tools.a2a import A2ATool
from app.core.tools.api import APITool
from app.core.tools.base import BaseTool
from app.core.tools.builtin import build_builtin_runtime_tools
from app.core.tools.filter import FilteredTool
from app.core.tools.execution import ToolExecutorRouter
from app.core.tools.mcp import MCPTool
from app.core.tools.provider_catalog import build_external_provider_descriptors
from app.core.tools.registry import ToolRegistry
from app.core.tools.scope import RuntimeToolScope
from app.core.tools.schema_resolver import ToolSchemaResolver


class ToolFactory:
    """创建当前 Agent 可用工具，并应用工具管理配置。"""

    def __init__(self, tool_config: ToolConfig | None = None) -> None:
        self.tool_config = tool_config or ToolConfig()
        self.registry = ToolRegistry(tool_config=self.tool_config)
        self.runtime_scope = RuntimeToolScope(self.registry)
        self.schema_resolver = ToolSchemaResolver(
            registry=self.registry,
            tool_config=self.tool_config,
            runtime_scope=self.runtime_scope,
        )
        self.executor_router = ToolExecutorRouter(
            registry=self.registry,
            tool_config=self.tool_config,
            runtime_scope=self.runtime_scope,
        )

    def build(
        self,
        sandbox: Sandbox,
        browser: Browser,
        search_engine: SearchEngine,
        mcp_tool: MCPTool,
        a2a_tool: A2ATool,
    ) -> List[BaseTool]:
        self.registry.register_provider_descriptors(
            build_external_provider_descriptors(
                tool_config=self.tool_config,
                mcp_config=mcp_tool.config,
                a2a_config=a2a_tool.config,
            )
        )
        tools = build_builtin_runtime_tools(
            sandbox=sandbox,
            browser=browser,
            search_engine=search_engine,
            mcp_tool=mcp_tool,
            a2a_tool=a2a_tool,
        )
        api_tool = APITool(self.tool_config)
        if api_tool.get_tools():
            tools.append(api_tool)
        self.refresh_mcp_tools(mcp_tool)
        return [
            FilteredTool(
                inner=tool,
                tool_config=self.tool_config,
                registry=self.registry,
                runtime_scope=self.runtime_scope,
                schema_resolver=self.schema_resolver,
                executor_router=self.executor_router,
                after_prepare=(
                    (lambda: self.refresh_mcp_tools(mcp_tool))
                    if tool is mcp_tool
                    else None
                ),
            )
            for tool in tools
        ]

    def refresh_mcp_tools(self, mcp_tool: MCPTool) -> None:
        """Register static search and discovered schemas under real Providers."""
        for provider_id, provider_label, schemas in mcp_tool.provider_tool_schemas():
            self.registry.replace_runtime_schemas(
                schemas,
                provider_id=provider_id,
                provider_label=provider_label,
                group="mcp",
                executor_type="mcp",
                source_type="mcp",
                execution_backend="external_provider",
                execution_class="external_read",
                category="MCP",
                requires_credentials=True,
            )
        resolved_tool_ids = mcp_tool.consume_scope_tool_ids()
        if resolved_tool_ids is not None:
            self.runtime_scope.replace_resolved_tool_ids(resolved_tool_ids)

    def build_contextual(self, runtime_tool: BaseTool) -> BaseTool:
        """Apply the same Run ToolConfig policy to a context-gated tool."""
        self.registry.register_runtime_tool(runtime_tool)
        return FilteredTool(
            inner=runtime_tool,
            tool_config=self.tool_config,
            registry=self.registry,
            runtime_scope=self.runtime_scope,
            schema_resolver=self.schema_resolver,
            executor_router=self.executor_router,
        )

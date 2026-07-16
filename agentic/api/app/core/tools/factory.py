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
from app.core.tools.mcp import MCPTool
from app.core.tools.registry import ToolRegistry


class ToolFactory:
    """创建当前 Agent 可用工具，并应用工具管理配置。"""

    def __init__(self, tool_config: ToolConfig | None = None) -> None:
        self.tool_config = tool_config or ToolConfig()
        self.registry = ToolRegistry(tool_config=self.tool_config)

    def build(
        self,
        sandbox: Sandbox,
        browser: Browser,
        search_engine: SearchEngine,
        mcp_tool: MCPTool,
        a2a_tool: A2ATool,
    ) -> List[BaseTool]:
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
        return [
            FilteredTool(
                inner=tool,
                tool_config=self.tool_config,
                registry=self.registry,
            )
            for tool in tools
        ]

    def build_contextual(self, runtime_tool: BaseTool) -> BaseTool:
        """Apply the same Run ToolConfig policy to a context-gated tool."""
        self.registry.register_runtime_tool(runtime_tool)
        return FilteredTool(
            inner=runtime_tool,
            tool_config=self.tool_config,
            registry=self.registry,
        )

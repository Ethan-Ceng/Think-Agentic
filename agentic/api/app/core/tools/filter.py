#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import Any, Dict, List

from app.core.entities.tool_config import ToolConfig
from app.core.entities.tool_result import ToolResult
from app.core.tools.base import BaseTool
from app.core.tools.registry import ToolRegistry


class FilteredTool(BaseTool):
    """按 ToolConfig 过滤一个现有工具包。"""

    def __init__(
        self,
        inner: BaseTool,
        tool_config: ToolConfig,
        registry: ToolRegistry,
    ) -> None:
        super().__init__()
        self.inner = inner
        self.name = inner.name
        self.tool_config = tool_config
        self.registry = registry

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            schema
            for schema in self.inner.get_tools()
            if self._is_enabled(schema["function"]["name"])
        ]

    def has_tool(self, tool_name: str) -> bool:
        return self._is_enabled(tool_name) and self.inner.has_tool(tool_name)

    async def invoke(self, tool_name: str, **kwargs) -> ToolResult:
        if not self._is_enabled(tool_name):
            tool_id = self.registry.tool_id_for_function(self.name, tool_name)
            return ToolResult(success=False, message=f"工具已禁用: {tool_id}")
        return await self.inner.invoke(tool_name, **kwargs)

    def _is_enabled(self, function_name: str) -> bool:
        return self.registry.is_function_enabled(
            tool_config=self.tool_config,
            tool_name=self.name,
            function_name=function_name,
        )

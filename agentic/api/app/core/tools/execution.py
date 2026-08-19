#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Literal

from app.core.entities.tool_config import ToolConfig
from app.core.entities.tool_result import ToolResult
from app.core.tools.base import BaseTool
from app.core.tools.registry import ToolRegistry
from app.core.tools.scope import RuntimeToolScope


class ToolExecutorRouter:
    """Enforce the selected Tool boundary before invoking its runtime adapter."""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        tool_config: ToolConfig,
        runtime_scope: RuntimeToolScope | None,
    ) -> None:
        self._registry = registry
        self._tool_config = tool_config
        self._runtime_scope = runtime_scope

    def is_in_scope(self, tool_name: str, function_name: str) -> bool:
        return (
            self._runtime_scope is None
            or self._runtime_scope.allows(tool_name, function_name)
        )

    def is_enabled(self, tool_name: str, function_name: str) -> bool:
        return self._registry.is_function_enabled(
            tool_config=self._tool_config,
            tool_name=tool_name,
            function_name=function_name,
        )

    def execution_policy(
        self,
        tool_name: str,
        function_name: str,
    ) -> Literal["allow", "deny"]:
        if function_name in {"message_notify_user", "message_ask_user"}:
            return "allow"
        _, binding, _, _ = self._registry.resolve_binding(
            self._tool_config,
            tool_name,
            function_name,
        )
        return binding.execution_policy

    async def invoke(
        self,
        inner: BaseTool,
        function_name: str,
        arguments: Dict[str, Any],
    ) -> ToolResult:
        if not inner.has_tool(function_name):
            return ToolResult(
                success=False,
                message=f"未知工具: {function_name}",
            )
        if not self.is_enabled(inner.name, function_name):
            tool_id = self._registry.tool_id_for_function(
                inner.name,
                function_name,
            )
            return ToolResult(success=False, message=f"工具已禁用: {tool_id}")
        if self.execution_policy(inner.name, function_name) == "deny":
            return ToolResult(
                success=False,
                message="工具策略已禁止执行该调用。",
            )
        if not self.is_in_scope(inner.name, function_name):
            return ToolResult(
                success=False,
                message=f"工具不在当前步骤能力范围内: {function_name}",
            )
        return await inner.invoke(function_name, **arguments)

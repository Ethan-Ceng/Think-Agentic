#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Dict, List

from app.core.entities.tool_config import ToolConfig
from app.core.tools.base import BaseTool
from app.core.tools.registry import ToolRegistry
from app.core.tools.scope import RuntimeToolScope


class ToolSchemaResolver:
    """Resolve model-visible schemas without acquiring execution resources."""

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

    def resolve_bundle(
        self,
        inner: BaseTool,
        *,
        apply_runtime_scope: bool = True,
    ) -> List[Dict[str, Any]]:
        schemas: List[Dict[str, Any]] = []
        for schema in inner.get_tools():
            function_name = schema["function"]["name"]
            if not self.is_enabled(inner.name, function_name):
                continue
            if not self.is_policy_allowed(inner.name, function_name):
                continue
            if (
                apply_runtime_scope
                and self._runtime_scope is not None
                and not self._runtime_scope.allows(inner.name, function_name)
            ):
                continue
            schemas.append(schema)
        return schemas

    def is_enabled(self, tool_name: str, function_name: str) -> bool:
        return self._registry.is_function_enabled(
            tool_config=self._tool_config,
            tool_name=tool_name,
            function_name=function_name,
        )

    def is_policy_allowed(self, tool_name: str, function_name: str) -> bool:
        if function_name in {"message_notify_user", "message_ask_user"}:
            return True
        _, binding, _, _ = self._registry.resolve_binding(
            self._tool_config,
            tool_name,
            function_name,
        )
        return binding.execution_policy == "allow"

    @staticmethod
    def resolve_tools(
        tools: Iterable[BaseTool],
        *,
        configured_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Collect schemas from governed Tool adapters in stable Tool order."""
        schemas: List[Dict[str, Any]] = []
        for runtime_tool in tools:
            getter = (
                getattr(runtime_tool, "get_configured_tools", None)
                if configured_only
                else None
            )
            schemas.extend(getter() if getter else runtime_tool.get_tools())
        return schemas

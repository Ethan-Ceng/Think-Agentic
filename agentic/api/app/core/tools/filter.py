#!/usr/bin/env python
# -*- coding: utf-8 -*-
from collections.abc import Callable
from typing import Any, Dict, List, Literal

from app.core.entities.tool_config import ToolConfig
from app.core.entities.tool_result import ToolResult
from app.core.tools.base import BaseTool
from app.core.tools.execution import ToolExecutorRouter
from app.core.tools.registry import ToolRegistry
from app.core.tools.schema_resolver import ToolSchemaResolver
from app.core.tools.scope import RuntimeToolScope


class FilteredTool(BaseTool):
    """按 ToolConfig 过滤一个现有工具包。"""

    def __init__(
        self,
        inner: BaseTool,
        tool_config: ToolConfig,
        registry: ToolRegistry,
        runtime_scope: RuntimeToolScope | None = None,
        schema_resolver: ToolSchemaResolver | None = None,
        executor_router: ToolExecutorRouter | None = None,
        after_prepare: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.inner = inner
        self.name = inner.name
        self.tool_config = tool_config
        self.registry = registry
        self.runtime_scope = runtime_scope
        self.schema_resolver = schema_resolver or ToolSchemaResolver(
            registry=registry,
            tool_config=tool_config,
            runtime_scope=runtime_scope,
        )
        self.executor_router = executor_router or ToolExecutorRouter(
            registry=registry,
            tool_config=tool_config,
            runtime_scope=runtime_scope,
        )
        self._after_prepare = after_prepare

    async def prepare_for_scope(self) -> None:
        """Prepare only external schemas selected by the immutable Scope."""
        prepare = getattr(self.inner, "prepare_for_scope", None)
        if prepare is None or self.runtime_scope is None:
            return
        snapshot = self.runtime_scope.snapshot
        changed = await prepare(
            capabilities=snapshot.capabilities,
            provider_ids=snapshot.provider_ids,
            max_tool_schemas=self.tool_config.runtime_policy.max_external_tool_schemas,
            max_schema_chars=self.tool_config.runtime_policy.max_external_schema_chars,
            search_top_k=self.tool_config.runtime_policy.external_tool_search_top_k,
        )
        if changed and self._after_prepare is not None:
            self._after_prepare()
            self.runtime_scope.refresh_from_registry()

    def get_tools(self) -> List[Dict[str, Any]]:
        return self.schema_resolver.resolve_bundle(self.inner)

    def has_tool(self, tool_name: str) -> bool:
        return (
            self._is_in_scope(tool_name)
            and self._is_enabled(tool_name)
            and self.inner.has_tool(tool_name)
        )

    async def invoke(self, tool_name: str, **kwargs) -> ToolResult:
        result = await self.executor_router.invoke(self.inner, tool_name, kwargs)
        if self._after_prepare is not None:
            self._after_prepare()
            if self.runtime_scope is not None:
                self.runtime_scope.refresh_from_registry()
        return result

    def get_configured_tools(self) -> List[Dict[str, Any]]:
        """Return ToolConfig-filtered schemas before the runtime scope is applied."""
        return self.schema_resolver.resolve_bundle(
            self.inner,
            apply_runtime_scope=False,
        )

    def get_risk_level(self, tool_name: str) -> Literal["low", "medium", "high"]:
        _, binding, _, _ = self.registry.resolve_binding(
            self.tool_config,
            self.name,
            tool_name,
        )
        risk_level = binding.risk_level
        if risk_level not in {"low", "medium", "high"}:
            return "low"
        return risk_level

    def get_execution_policy(self, tool_name: str) -> Literal["allow", "deny"]:
        """Resolve the deterministic platform policy without user approval."""
        return self.executor_router.execution_policy(self.name, tool_name)

    def _is_enabled(self, function_name: str) -> bool:
        return self.executor_router.is_enabled(self.name, function_name)

    def _is_in_scope(self, function_name: str) -> bool:
        return self.executor_router.is_in_scope(self.name, function_name)

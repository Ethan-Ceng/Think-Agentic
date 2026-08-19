from __future__ import annotations

import asyncio

from app.core.entities.tool_config import ToolBinding, ToolConfig
from app.core.entities.tool_result import ToolResult
from app.core.tools.base import BaseTool, tool
from app.core.tools.execution import ToolExecutorRouter
from app.core.tools.filter import FilteredTool
from app.core.tools.registry import ToolRegistry
from app.core.tools.scope import RuntimeToolScope


class RecordingTool(BaseTool):
    name = "compute"

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[int] = []

    @tool(
        name="compute_double",
        description="Double a value.",
        parameters={"value": {"type": "integer"}},
        required=["value"],
    )
    async def double(self, value: int) -> ToolResult:
        self.calls.append(value)
        return ToolResult(success=True, data={"value": value * 2})


def build_filtered(
    config: ToolConfig | None = None,
) -> tuple[RecordingTool, FilteredTool, RuntimeToolScope, ToolRegistry]:
    effective_config = config or ToolConfig()
    inner = RecordingTool()
    registry = ToolRegistry(tool_config=effective_config)
    registry.register_runtime_tool(
        inner,
        provider_id="runtime.compute",
        provider_label="Compute",
        group="compute",
        source_type="builtin",
        execution_backend="in_process",
    )
    scope = RuntimeToolScope(registry)
    router = ToolExecutorRouter(
        registry=registry,
        tool_config=effective_config,
        runtime_scope=scope,
    )
    return (
        inner,
        FilteredTool(
            inner,
            effective_config,
            registry,
            scope,
            executor_router=router,
        ),
        scope,
        registry,
    )


def test_router_rejects_out_of_scope_call_before_inner_tool() -> None:
    inner, filtered, scope, _ = build_filtered()
    scope.activate([])

    result = asyncio.run(filtered.invoke("compute_double", value=3))

    assert result.success is False
    assert "当前步骤" in result.message
    assert inner.calls == []


def test_router_invokes_selected_tool_exactly_once() -> None:
    inner, filtered, scope, _ = build_filtered()
    scope.activate(
        ["compute"],
        provider_ids=["runtime.compute"],
        tool_ids=["runtime.compute.compute_double"],
    )

    result = asyncio.run(filtered.invoke("compute_double", value=3))

    assert result.success is True
    assert result.data == {"value": 6}
    assert inner.calls == [3]


def test_router_enforces_disabled_and_denied_policy_for_direct_invocation() -> None:
    for binding, expected_message in (
        (ToolBinding(enabled=False), "工具已禁用"),
        (ToolBinding(execution_policy="deny"), "工具策略已禁止"),
    ):
        config = ToolConfig(
            bindings={"runtime.compute.compute_double": binding},
        )
        inner, filtered, scope, _ = build_filtered(config)
        scope.activate(["compute"])

        result = asyncio.run(filtered.invoke("compute_double", value=3))

        assert result.success is False
        assert expected_message in result.message
        assert inner.calls == []


def test_router_returns_unknown_tool_without_calling_inner() -> None:
    inner, _, scope, registry = build_filtered()
    scope.activate(["compute"])
    router = ToolExecutorRouter(
        registry=registry,
        tool_config=ToolConfig(),
        runtime_scope=scope,
    )

    result = asyncio.run(
        router.invoke(inner, "compute_missing", {"value": 3})
    )

    assert result.success is False
    assert "未知工具" in result.message
    assert inner.calls == []

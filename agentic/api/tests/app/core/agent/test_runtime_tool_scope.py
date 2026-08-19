from __future__ import annotations

import json

import pytest

from app.core.entities.tool_config import ToolConfig
from app.core.entities.app_config import AgentConfig, MCPConfig, MCPServerConfig
from app.core.agent.planner import PlannerAgent
from app.core.agent.react import ReActAgent
from app.core.tools.a2a import A2ATool
from app.core.tools.factory import ToolFactory
from app.core.tools.mcp import MCPTool
from app.core.tools.registry import ToolRegistry
from app.core.tools.scope import RuntimeToolScope
from app.services.trace_service import summarize_tool_registry, tool_schema_bytes


def test_builtin_registry_baseline_separates_sandbox_browser_and_context_tools() -> None:
    summary = summarize_tool_registry(ToolRegistry(), ToolConfig())

    assert summary["group_count"] == 6
    assert summary["function_count"] == 27
    assert summary["categories"] == {
        "requires_sandbox": 10,
        "requires_browser": 12,
        "no_sandbox": 5,
    }
    assert summary["groups"] == {
        "a2a": {"function_count": 2, "category": "no_sandbox"},
        "browser": {"function_count": 12, "category": "requires_browser"},
        "file": {"function_count": 5, "category": "requires_sandbox"},
        "message": {"function_count": 2, "category": "no_sandbox"},
        "search": {"function_count": 1, "category": "no_sandbox"},
        "shell": {"function_count": 5, "category": "requires_sandbox"},
    }
    assert summary["tool_schema_bytes"] == 12933


def test_tool_schema_bytes_handles_empty_dynamic_and_chinese_schemas() -> None:
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "api_company_search",
                "description": "搜索公司内部资料",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "关键词"}},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "mcp_paper_search",
                "description": "Search papers",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    assert tool_schema_bytes([]) == 0
    canonical = json.dumps(
        schemas,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert tool_schema_bytes(schemas) == len(canonical.encode("utf-8"))
    assert tool_schema_bytes(schemas) > len(canonical)


def test_planner_receives_zero_schemas_and_react_defaults_to_system_message_only() -> None:
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )
    common = {
        "uow_factory": lambda: object(),
        "session_id": "session-1",
        "agent_config": AgentConfig(),
        "llm": object(),
        "json_parser": object(),
        "tools": tools,
        "tool_registry": factory.registry,
        "runtime_tool_scope": factory.runtime_scope,
    }
    planner = PlannerAgent(**common)
    react = ReActAgent(**common)

    planner_schemas = planner._get_available_tools()
    react_schemas = react._get_available_tools()

    assert planner._tool_choice == "none"
    assert planner_schemas == []
    assert _function_names(react_schemas) == {
        "message_ask_user",
        "message_notify_user",
    }
    assert tool_schema_bytes(planner_schemas) == 0


def test_react_scope_exposes_shell_and_file_without_browser() -> None:
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )
    react = ReActAgent(
        uow_factory=lambda: object(),
        session_id="session-1",
        agent_config=AgentConfig(),
        llm=object(),
        json_parser=object(),
        tools=tools,
        tool_registry=factory.registry,
        runtime_tool_scope=factory.runtime_scope,
    )

    react.set_runtime_tool_scope(["shell", "file"])
    names = _function_names(react._get_available_tools())

    assert {"shell_execute", "read_file", "message_ask_user"} <= names
    assert not any(name.startswith("browser_") for name in names)
    assert "search_web" not in names


def test_empty_and_unknown_scopes_never_mean_all_tools() -> None:
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )

    factory.runtime_scope.activate([])
    empty_names = {
        schema["function"]["name"]
        for tool in tools
        for schema in tool.get_tools()
    }
    factory.runtime_scope.activate(["does-not-exist"])
    unknown_names = {
        schema["function"]["name"]
        for tool in tools
        for schema in tool.get_tools()
    }

    assert empty_names == {"message_ask_user", "message_notify_user"}
    assert unknown_names == empty_names
    assert factory.runtime_scope.unknown_capabilities == ("does-not-exist",)


def test_exact_recovery_scope_restores_only_the_persisted_function() -> None:
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )

    factory.runtime_scope.activate([], exact_functions=["shell_execute"])
    names = {
        schema["function"]["name"]
        for tool in tools
        for schema in tool.get_tools()
    }

    assert names == {
        "message_ask_user",
        "message_notify_user",
        "shell_execute",
    }


def test_scope_snapshot_narrows_capability_by_provider_and_tool_id() -> None:
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )

    factory.runtime_scope.activate(
        ["shell"],
        provider_ids=["builtin.shell"],
        tool_ids=["builtin.shell.shell_execute"],
    )
    snapshot = factory.runtime_scope.snapshot
    names = {
        schema["function"]["name"]
        for tool in tools
        for schema in tool.get_tools()
    }

    assert names == {
        "message_ask_user",
        "message_notify_user",
        "shell_execute",
    }
    assert snapshot.capabilities == ("shell",)
    assert snapshot.provider_ids == ("builtin.shell",)
    assert snapshot.tool_ids == ("builtin.shell.shell_execute",)
    with pytest.raises(AttributeError):
        snapshot.tool_ids = ()


def test_unknown_or_mismatched_provider_and_tool_ids_never_expand_scope() -> None:
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )

    factory.runtime_scope.activate(
        ["shell"],
        provider_ids=["builtin.file", "missing.provider"],
        tool_ids=["builtin.shell.shell_execute", "missing.tool"],
    )
    names = {
        schema["function"]["name"]
        for tool in tools
        for schema in tool.get_tools()
    }

    assert names == {"message_ask_user", "message_notify_user"}
    assert factory.runtime_scope.unknown_provider_ids == ("missing.provider",)
    assert factory.runtime_scope.unknown_tool_ids == ("missing.tool",)


def test_exact_provider_only_constrains_its_own_capability_group() -> None:
    factory = ToolFactory(ToolConfig())
    factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(
            MCPConfig(
                mcpServers={
                    "github": MCPServerConfig(url="https://mcp.example.test")
                }
            )
        ),
        a2a_tool=A2ATool(),
    )

    capabilities, provider_ids, tool_ids = factory.registry.resolve_scope_selection(
        ["shell", "mcp"],
        tool_ids=["builtin.shell.shell_execute"],
    )
    factory.runtime_scope.activate(
        capabilities,
        provider_ids=provider_ids,
        tool_ids=tool_ids,
    )

    assert provider_ids == ["mcp.github"]
    assert tool_ids == ["builtin.shell.shell_execute"]
    assert factory.runtime_scope.allows("shell", "shell_execute") is True
    assert factory.runtime_scope.allows("shell", "shell_wait") is False


@pytest.mark.parametrize(
    ("provider_ids", "tool_ids"),
    [
        (["missing.provider"], ["builtin.shell.shell_execute"]),
        (["builtin.shell"], ["missing.tool"]),
    ],
)
def test_unknown_only_exact_constraints_never_fall_back_to_capability_scope(
    provider_ids: list[str],
    tool_ids: list[str],
) -> None:
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )

    factory.runtime_scope.activate(
        ["shell"],
        provider_ids=provider_ids,
        tool_ids=tool_ids,
    )
    names = {
        schema["function"]["name"]
        for tool in tools
        for schema in tool.get_tools()
    }

    assert names == {"message_ask_user", "message_notify_user"}


@pytest.mark.parametrize(
    ("provider_ids", "tool_ids"),
    [
        (["missing.provider"], []),
        ([], ["missing.tool"]),
    ],
)
def test_unknown_exact_constraints_reject_unregistered_runtime_functions(
    provider_ids: list[str],
    tool_ids: list[str],
) -> None:
    registry = ToolRegistry()
    scope = RuntimeToolScope(registry)

    scope.activate(
        ["shell"],
        provider_ids=provider_ids,
        tool_ids=tool_ids,
    )

    assert scope.allows("shell", "runtime_only_shell") is False


def _function_names(schemas: list[dict]) -> set[str]:
    return {schema["function"]["name"] for schema in schemas}

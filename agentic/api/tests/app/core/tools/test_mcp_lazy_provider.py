#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import re
from types import SimpleNamespace

from app.core.entities.app_config import MCPConfig, MCPServerConfig
from app.core.entities.tool_config import RuntimeToolPolicy, ToolConfig
from app.core.tools.a2a import A2ATool
from app.core.tools.factory import ToolFactory
from app.core.tools.mcp import (
    MCPTool,
    MCPClientManager,
    _mcp_search_function_name,
    _mcp_tool_function_name,
)


def _schema(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        },
    }


def test_mcp_model_function_names_are_bounded_valid_and_collision_resistant() -> None:
    function_pattern = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

    assert _mcp_search_function_name("github") != _mcp_search_function_name(
        "GitHub"
    )
    assert _mcp_search_function_name("foo.bar") != _mcp_search_function_name(
        "foo_bar"
    )
    assert _mcp_tool_function_name("github", "search_tools") != (
        _mcp_search_function_name("github")
    )
    names = {
        _mcp_tool_function_name("Git Hub / 企业", "Find issues now"),
        _mcp_tool_function_name("Git Hub / 企业", "find_issues_now"),
        _mcp_tool_function_name("x" * 100, "y" * 100),
    }

    assert len(names) == 3
    assert all(function_pattern.fullmatch(name) for name in names)


def test_mcp_manager_routes_normalized_function_name_to_original_tool() -> None:
    manager = MCPClientManager(
        MCPConfig(
            mcpServers={
                "Git Hub / 企业": MCPServerConfig(url="https://mcp.example.test")
            }
        )
    )
    remote_tool = SimpleNamespace(
        name="Find issues now",
        description="Find issues",
        inputSchema={"type": "object", "properties": {}},
    )
    captured: dict = {}

    class FakeSession:
        async def call_tool(self, tool_name: str, arguments: dict):
            captured.update(tool_name=tool_name, arguments=arguments)
            return SimpleNamespace(content=[])

    manager._tools = {"Git Hub / 企业": [remote_tool]}
    manager._clients = {"Git Hub / 企业": FakeSession()}

    async def run() -> tuple[str, bool]:
        schemas = await manager.get_all_tools()
        function_name = schemas[0]["function"]["name"]
        result = await manager.invoke(function_name, {"query": "bug"})
        return function_name, result.success

    function_name, success = asyncio.run(run())

    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", function_name)
    assert success is True
    assert captured == {
        "tool_name": "Find issues now",
        "arguments": {"query": "bug"},
    }


class FakeMCPManager:
    def __init__(self, config, calls: list[str], schemas: dict[str, list[dict]]) -> None:
        self.config = config
        self.calls = calls
        self.schemas = schemas
        self.server_name = next(iter(config.mcpServers))

    async def initialize(self) -> None:
        self.calls.append(f"initialize:{self.server_name}")

    async def get_all_tools(self) -> list[dict]:
        return self.schemas[self.server_name]

    async def invoke(self, tool_name: str, arguments: dict):
        self.calls.append(f"invoke:{self.server_name}:{tool_name}")
        from app.core.entities.tool_result import ToolResult

        return ToolResult(success=True, data=arguments)

    async def cleanup(self) -> None:
        self.calls.append(f"cleanup:{self.server_name}")


def _build_runtime(
    *,
    calls: list[str],
    schemas: dict[str, list[dict]],
    policy: RuntimeToolPolicy | None = None,
):
    mcp_config = MCPConfig(
        mcpServers={
            server_name: MCPServerConfig(url=f"https://{server_name}.example.test")
            for server_name in schemas
        }
    )
    mcp_tool = MCPTool(
        mcp_config,
        manager_factory=lambda config: FakeMCPManager(config, calls, schemas),
    )
    factory = ToolFactory(ToolConfig(runtime_policy=policy or RuntimeToolPolicy()))
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=mcp_tool,
        a2a_tool=A2ATool(),
    )
    filtered_mcp = next(tool for tool in tools if tool.name == "mcp")
    return factory, mcp_tool, filtered_mcp


def test_unselected_or_unknown_mcp_provider_never_connects() -> None:
    calls: list[str] = []
    factory, _, filtered = _build_runtime(
        calls=calls,
        schemas={
            "github": [_schema("mcp_github_search_issues", "Search issues")],
            "gitlab": [_schema("mcp_gitlab_search_issues", "Search issues")],
        },
    )

    async def run() -> None:
        factory.runtime_scope.activate([])
        await filtered.prepare_for_scope()
        factory.runtime_scope.activate(["mcp"])
        await filtered.prepare_for_scope()
        assert filtered.get_tools() == []
        factory.runtime_scope.activate(["mcp"], provider_ids=["mcp.unknown"])
        await filtered.prepare_for_scope()

    asyncio.run(run())

    assert calls == []


def test_selected_mcp_provider_discovers_and_registers_only_its_tools() -> None:
    calls: list[str] = []
    factory, _, filtered = _build_runtime(
        calls=calls,
        schemas={
            "github": [_schema("mcp_github_search_issues", "Search issues")],
            "gitlab": [_schema("mcp_gitlab_search_issues", "Search issues")],
        },
    )

    async def run() -> list[str]:
        factory.runtime_scope.activate(["mcp"], provider_ids=["mcp.github"])
        await filtered.prepare_for_scope()
        return [item["function"]["name"] for item in filtered.get_tools()]

    visible_names = asyncio.run(run())

    assert [call for call in calls if call.startswith("initialize:")] == [
        "initialize:github"
    ]
    assert "mcp_github_search_issues" in visible_names
    assert "mcp_gitlab_search_issues" not in visible_names
    descriptor = factory.registry.get_by_function_name("mcp_github_search_issues")
    assert descriptor is not None
    assert descriptor.provider_id == "mcp.github"
    assert descriptor.execution_backend == "external_provider"


def test_single_mcp_provider_is_deterministically_selected() -> None:
    calls: list[str] = []
    factory, _, _ = _build_runtime(
        calls=calls,
        schemas={
            "github": [_schema("mcp_github_search_issues", "Search issues")],
        },
    )

    assert factory.registry.resolve_scope_selection(["mcp"]) == (
        ["mcp"],
        ["mcp.github"],
        [],
    )


def test_schema_budget_uses_explicit_search_then_injects_top_k() -> None:
    calls: list[str] = []
    policy = RuntimeToolPolicy(
        max_external_tool_schemas=2,
        max_external_schema_chars=100000,
        external_tool_search_top_k=1,
    )
    factory, _, filtered = _build_runtime(
        calls=calls,
        schemas={
            "github": [
                _schema("mcp_github_search_issues", "Search issue tracker"),
                _schema("mcp_github_list_pulls", "List pull requests"),
                _schema("mcp_github_get_repo", "Get repository"),
            ],
        },
        policy=policy,
    )

    async def run() -> tuple[list[str], list[str]]:
        factory.runtime_scope.activate(
            ["mcp"],
            provider_ids=["mcp.github"],
            tool_ids=["mcp.github.mcp_github_search_tools"],
        )
        await filtered.prepare_for_scope()
        before = [item["function"]["name"] for item in filtered.get_tools()]
        search_name = next(name for name in before if name.endswith("_search_tools"))
        result = await filtered.invoke(search_name, query="issue tracker")
        assert result.success is True
        after = [item["function"]["name"] for item in filtered.get_tools()]
        return before, after

    before, after = asyncio.run(run())

    assert before == ["mcp_github_search_tools"]
    assert after == [
        "mcp_github_search_tools",
        "mcp_github_search_issues",
    ]
    assert factory.runtime_scope.tool_ids == (
        "mcp.github.mcp_github_search_tools",
        "mcp.github.mcp_github_search_issues",
    )


def test_schema_budget_is_enforced_across_all_selected_providers() -> None:
    calls: list[str] = []
    factory, _, filtered = _build_runtime(
        calls=calls,
        schemas={
            "github": [
                _schema("mcp_github_issue", "Issue"),
                _schema("mcp_github_pull", "Pull"),
            ],
            "gitlab": [
                _schema("mcp_gitlab_issue", "Issue"),
                _schema("mcp_gitlab_merge", "Merge"),
            ],
        },
        policy=RuntimeToolPolicy(
            max_external_tool_schemas=3,
            max_external_schema_chars=100000,
        ),
    )

    async def run() -> list[str]:
        factory.runtime_scope.activate(
            ["mcp"],
            provider_ids=["mcp.github", "mcp.gitlab"],
        )
        await filtered.prepare_for_scope()
        return [item["function"]["name"] for item in filtered.get_tools()]

    visible_names = asyncio.run(run())

    assert [call for call in calls if call.startswith("initialize:")] == [
        "initialize:github",
        "initialize:gitlab",
    ]
    assert visible_names == [
        "mcp_github_search_tools",
        "mcp_gitlab_search_tools",
    ]


def test_repeated_search_replaces_stale_provider_descriptors() -> None:
    calls: list[str] = []
    factory, _, filtered = _build_runtime(
        calls=calls,
        schemas={
            "github": [
                _schema("mcp_github_search_issues", "Search issue tracker"),
                _schema("mcp_github_list_pulls", "List pull requests"),
                _schema("mcp_github_get_repo", "Get repository"),
            ],
        },
        policy=RuntimeToolPolicy(
            max_external_tool_schemas=2,
            max_external_schema_chars=100000,
            external_tool_search_top_k=1,
        ),
    )

    async def run() -> None:
        factory.runtime_scope.activate(["mcp"], provider_ids=["mcp.github"])
        await filtered.prepare_for_scope()
        await filtered.invoke("mcp_github_search_tools", query="issue tracker")
        assert (
            factory.registry.get_by_function_name("mcp_github_search_issues")
            is not None
        )
        await filtered.invoke("mcp_github_search_tools", query="pull requests")

    asyncio.run(run())

    assert factory.registry.get_by_function_name("mcp_github_search_issues") is None
    assert factory.registry.get_by_function_name("mcp_github_list_pulls") is not None


def test_lazy_discovery_reclassifies_persisted_tool_id_without_widening_scope() -> None:
    calls: list[str] = []
    factory, _, filtered = _build_runtime(
        calls=calls,
        schemas={
            "github": [_schema("mcp_github_search_issues", "Search issues")],
        },
    )
    tool_id = "mcp.github.mcp_github_search_issues"

    async def run() -> list[str]:
        factory.runtime_scope.activate(
            ["mcp"],
            provider_ids=["mcp.github"],
            tool_ids=[tool_id],
        )
        assert factory.runtime_scope.unknown_tool_ids == (tool_id,)
        await filtered.prepare_for_scope()
        assert factory.runtime_scope.tool_ids == (tool_id,)
        assert factory.runtime_scope.unknown_tool_ids == ()
        return [item["function"]["name"] for item in filtered.get_tools()]

    assert asyncio.run(run()) == ["mcp_github_search_issues"]

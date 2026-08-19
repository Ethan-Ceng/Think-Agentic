from __future__ import annotations

import asyncio

from app.core.entities.app_config import MCPConfig, MCPServerConfig
from app.core.entities.tool_result import ToolResult
from app.core.tools.mcp import MCPTool
from app.core.tools.provider_runtime import MCPProviderPool


def _schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "mcp_github_search",
            "description": "Search GitHub",
            "parameters": {"type": "object", "properties": {}},
        },
    }


class FakeManager:
    def __init__(self, config, calls: list[str]) -> None:
        self.calls = calls
        self.server_name = next(iter(config.mcpServers))

    async def initialize(self) -> None:
        self.calls.append(f"initialize:{self.server_name}")

    async def get_all_tools(self) -> list[dict]:
        self.calls.append(f"discover:{self.server_name}")
        return [_schema()]

    async def invoke(self, tool_name: str, arguments: dict) -> ToolResult:
        self.calls.append(f"invoke:{self.server_name}:{tool_name}")
        return ToolResult(success=True, data=arguments)

    async def cleanup(self) -> None:
        self.calls.append(f"cleanup:{self.server_name}")


async def _prepare(tool: MCPTool) -> None:
    await tool.prepare_for_scope(
        capabilities=("mcp",),
        provider_ids=("mcp.github",),
        max_tool_schemas=32,
        max_schema_chars=60000,
        search_top_k=8,
    )


def test_two_runs_share_snapshot_and_actor_but_runner_cleanup_does_not_close_pool() -> None:
    calls: list[str] = []
    pool = MCPProviderPool(
        manager_factory=lambda config: FakeManager(config, calls),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
    )
    config = MCPConfig(
        mcpServers={"github": MCPServerConfig(url="https://mcp.example.test")}
    )
    first = MCPTool(config, provider_pool=pool, user_id="user-1")
    second = MCPTool(config, provider_pool=pool, user_id="user-1")

    async def run() -> ToolResult:
        await _prepare(first)
        await first.cleanup()
        assert pool.actor_count == 1

        await _prepare(second)
        result = await second.invoke("mcp_github_search", query="bug")
        await second.cleanup()
        assert pool.actor_count == 1
        await pool.close()
        return result

    result = asyncio.run(run())

    assert result.success is True
    assert calls == [
        "initialize:github",
        "discover:github",
        "invoke:github:mcp_github_search",
        "cleanup:github",
    ]


def test_same_provider_id_does_not_share_runtime_across_users() -> None:
    calls: list[str] = []
    pool = MCPProviderPool(
        manager_factory=lambda config: FakeManager(config, calls),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
    )
    config = MCPConfig(
        mcpServers={"github": MCPServerConfig(url="https://mcp.example.test")}
    )
    first = MCPTool(config, provider_pool=pool, user_id="user-1")
    second = MCPTool(config, provider_pool=pool, user_id="user-2")

    async def run() -> None:
        await _prepare(first)
        await _prepare(second)
        await pool.close()

    asyncio.run(run())

    assert calls.count("initialize:github") == 2
    assert calls.count("discover:github") == 2
    assert calls.count("cleanup:github") == 2


def test_reconfigure_keeps_application_scoped_provider_pool() -> None:
    calls: list[str] = []
    pool = MCPProviderPool(
        manager_factory=lambda config: FakeManager(config, calls),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
    )
    first_config = MCPConfig(
        mcpServers={"github": MCPServerConfig(url="https://mcp.example.test")}
    )
    second_config = MCPConfig(
        mcpServers={"gitlab": MCPServerConfig(url="https://mcp.example.test")}
    )
    tool = MCPTool(first_config, provider_pool=pool, user_id="user-1")

    async def run() -> None:
        await tool.initialize(second_config)
        assert tool._provider_pool is pool
        assert tool._owns_provider_pool is False
        await tool.cleanup()
        assert pool.actor_count == 1
        assert "cleanup:gitlab" not in calls
        await pool.close()

    asyncio.run(run())

    assert "cleanup:gitlab" in calls

from __future__ import annotations

import asyncio

import pytest

from app.core.entities.app_config import MCPServerConfig
from app.core.entities.tool_result import ToolResult
from app.core.tools.provider_runtime import (
    MCPProviderPool,
    ProviderFailureCode,
    ProviderRuntimeError,
)


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _schema(name: str = "mcp_github_search") -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Search",
            "parameters": {"type": "object", "properties": {}},
        },
    }


class FakeManager:
    def __init__(
        self,
        config,
        calls: list[tuple[str, str, int]],
        *,
        fail_initialize: BaseException | None = None,
        fail_discover: BaseException | None = None,
        fail_invoke: BaseException | None = None,
    ) -> None:
        self.server_name = next(iter(config.mcpServers))
        self.calls = calls
        self.fail_initialize = fail_initialize
        self.fail_discover = fail_discover
        self.fail_invoke = fail_invoke

    def _record(self, operation: str) -> None:
        task = asyncio.current_task()
        self.calls.append((self.server_name, operation, id(task)))

    async def initialize(self) -> None:
        self._record("initialize")
        if self.fail_initialize is not None:
            raise self.fail_initialize

    async def get_all_tools(self) -> list[dict]:
        self._record("discover")
        if self.fail_discover is not None:
            raise self.fail_discover
        return [_schema(f"mcp_{self.server_name}_search")]

    async def invoke(self, tool_name: str, arguments: dict) -> ToolResult:
        self._record("invoke")
        if self.fail_invoke is not None:
            raise self.fail_invoke
        return ToolResult(success=True, data={"tool": tool_name, **arguments})

    async def cleanup(self) -> None:
        self._record("cleanup")


async def test_concurrent_first_discovery_uses_one_actor_and_connection() -> None:
    calls: list[tuple[str, str, int]] = []
    pool = MCPProviderPool(
        manager_factory=lambda config: FakeManager(config, calls),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
    )
    config = MCPServerConfig(url="https://mcp.example.test")

    try:
        snapshots = await asyncio.gather(
            *[
                pool.discover(
                    user_id="user-1",
                    provider_id="mcp.github",
                    server_name="github",
                    server_config=config,
                )
                for _ in range(12)
            ]
        )
    finally:
        await pool.close()

    assert all(snapshot.schemas for snapshot in snapshots)
    assert [operation for _, operation, _ in calls].count("initialize") == 1
    assert [operation for _, operation, _ in calls].count("discover") == 1


async def test_actor_owns_initialize_discover_invoke_and_cleanup_in_one_task() -> None:
    calls: list[tuple[str, str, int]] = []
    pool = MCPProviderPool(
        manager_factory=lambda config: FakeManager(config, calls),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
    )
    config = MCPServerConfig(url="https://mcp.example.test")

    await pool.discover(
        user_id="user-1",
        provider_id="mcp.github",
        server_name="github",
        server_config=config,
    )
    result = await pool.invoke(
        user_id="user-1",
        provider_id="mcp.github",
        server_name="github",
        server_config=config,
        tool_name="mcp_github_search",
        arguments={"query": "bug"},
    )
    await pool.close()

    assert result.success is True
    assert {task_id for _, _, task_id in calls} == {calls[0][2]}
    assert [operation for _, operation, _ in calls] == [
        "initialize",
        "discover",
        "invoke",
        "cleanup",
    ]


async def test_provider_cancel_becomes_typed_failure_and_other_provider_continues() -> None:
    calls: list[tuple[str, str, int]] = []

    def factory(config):
        server_name = next(iter(config.mcpServers))
        return FakeManager(
            config,
            calls,
            fail_initialize=(
                asyncio.CancelledError("provider cancel scope")
                if server_name == "broken"
                else None
            ),
        )

    pool = MCPProviderPool(
        manager_factory=factory,
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
    )
    config = MCPServerConfig(url="https://mcp.example.test")

    try:
        with pytest.raises(ProviderRuntimeError) as captured:
            await pool.discover(
                user_id="user-1",
                provider_id="mcp.broken",
                server_name="broken",
                server_config=config,
            )
        healthy = await pool.discover(
            user_id="user-1",
            provider_id="mcp.healthy",
            server_name="healthy",
            server_config=config,
        )
    finally:
        await pool.close()

    assert captured.value.failure.code == ProviderFailureCode.CONNECT_FAILED.value
    assert captured.value.failure.provider_id == "mcp.broken"
    assert healthy.schemas[0]["function"]["name"] == "mcp_healthy_search"


async def test_provider_invoke_cancel_returns_failed_tool_result_not_cancel() -> None:
    calls: list[tuple[str, str, int]] = []
    pool = MCPProviderPool(
        manager_factory=lambda config: FakeManager(
            config,
            calls,
            fail_invoke=asyncio.CancelledError("provider invoke cancel"),
        ),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
    )
    config = MCPServerConfig(url="https://mcp.example.test")

    try:
        result = await pool.invoke(
            user_id="user-1",
            provider_id="mcp.github",
            server_name="github",
            server_config=config,
            tool_name="mcp_github_search",
            arguments={},
        )
    finally:
        await pool.close()

    assert result.success is False
    assert result.failure is not None
    assert result.failure.code == ProviderFailureCode.PROTOCOL_ERROR.value


async def test_backoff_prevents_repeated_connect_storm() -> None:
    calls: list[tuple[str, str, int]] = []
    now = [100.0]
    pool = MCPProviderPool(
        manager_factory=lambda config: FakeManager(
            config,
            calls,
            fail_initialize=RuntimeError("offline"),
        ),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
        backoff_base_seconds=5,
        backoff_max_seconds=20,
        clock=lambda: now[0],
    )
    config = MCPServerConfig(url="https://mcp.example.test")

    try:
        for _ in range(2):
            with pytest.raises(ProviderRuntimeError):
                await pool.discover(
                    user_id="user-1",
                    provider_id="mcp.github",
                    server_name="github",
                    server_config=config,
                )
        assert [operation for _, operation, _ in calls].count("initialize") == 1

        now[0] = 105.0
        with pytest.raises(ProviderRuntimeError):
            await pool.discover(
                user_id="user-1",
                provider_id="mcp.github",
                server_name="github",
                server_config=config,
            )
    finally:
        await pool.close()

    assert [operation for _, operation, _ in calls].count("initialize") == 2


async def test_repeated_schema_failure_uses_exponential_backoff() -> None:
    calls: list[tuple[str, str, int]] = []
    now = [100.0]
    pool = MCPProviderPool(
        manager_factory=lambda config: FakeManager(
            config,
            calls,
            fail_discover=RuntimeError("bad schema response"),
        ),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
        backoff_base_seconds=5,
        backoff_max_seconds=20,
        clock=lambda: now[0],
    )
    config = MCPServerConfig(url="https://mcp.example.test")

    try:
        with pytest.raises(ProviderRuntimeError):
            await pool.discover(
                user_id="user-1",
                provider_id="mcp.github",
                server_name="github",
                server_config=config,
            )

        now[0] = 105.0
        with pytest.raises(ProviderRuntimeError):
            await pool.discover(
                user_id="user-1",
                provider_id="mcp.github",
                server_name="github",
                server_config=config,
            )

        now[0] = 109.0
        with pytest.raises(ProviderRuntimeError):
            await pool.discover(
                user_id="user-1",
                provider_id="mcp.github",
                server_name="github",
                server_config=config,
            )
        assert [operation for _, operation, _ in calls].count("initialize") == 2

        now[0] = 115.0
        with pytest.raises(ProviderRuntimeError):
            await pool.discover(
                user_id="user-1",
                provider_id="mcp.github",
                server_name="github",
                server_config=config,
            )
    finally:
        await pool.close()

    assert [operation for _, operation, _ in calls].count("initialize") == 3
    assert [operation for _, operation, _ in calls].count("discover") == 3


async def test_idle_ttl_and_config_change_close_actors_without_leaks() -> None:
    calls: list[tuple[str, str, int]] = []
    pool = MCPProviderPool(
        manager_factory=lambda config: FakeManager(config, calls),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=0.02,
    )
    first_config = MCPServerConfig(
        url="https://mcp.example.test",
        headers={"Authorization": "first"},
    )
    second_config = MCPServerConfig(
        url="https://mcp.example.test",
        headers={"Authorization": "second"},
    )

    await pool.discover(
        user_id="user-1",
        provider_id="mcp.github",
        server_name="github",
        server_config=first_config,
    )
    await pool.discover(
        user_id="user-1",
        provider_id="mcp.github",
        server_name="github",
        server_config=second_config,
    )
    assert [operation for _, operation, _ in calls].count("cleanup") == 1

    # Switching back must not resurrect first_config's still-fresh snapshot.
    await pool.discover(
        user_id="user-1",
        provider_id="mcp.github",
        server_name="github",
        server_config=first_config,
    )
    assert [operation for _, operation, _ in calls].count("discover") == 3
    assert [operation for _, operation, _ in calls].count("cleanup") == 2

    await asyncio.sleep(0.05)
    assert pool.actor_count == 0
    assert [operation for _, operation, _ in calls].count("cleanup") == 3

    await pool.close()
    await pool.close()


async def test_provider_operation_timeout_is_typed_and_close_is_bounded() -> None:
    calls: list[tuple[str, str, int]] = []

    class HangingManager(FakeManager):
        async def initialize(self) -> None:
            self._record("initialize")
            await asyncio.Event().wait()

    pool = MCPProviderPool(
        manager_factory=lambda config: HangingManager(config, calls),
        snapshot_ttl_seconds=60,
        idle_ttl_seconds=60,
        operation_timeout_seconds=0.01,
    )
    config = MCPServerConfig(url="https://mcp.example.test")

    with pytest.raises(ProviderRuntimeError) as captured:
        await pool.discover(
            user_id="user-1",
            provider_id="mcp.github",
            server_name="github",
            server_config=config,
        )

    assert captured.value.failure.code == ProviderFailureCode.TIMEOUT.value
    await asyncio.wait_for(pool.close(), timeout=0.1)

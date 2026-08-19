from __future__ import annotations

import pytest

import app.main as main_module
from app.main import _application_shutdown_steps, _shutdown_resources


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_shutdown_resources_continues_after_cleanup_failure() -> None:
    calls: list[str] = []

    async def failing() -> None:
        calls.append("failing")
        raise RuntimeError("cleanup failed")

    async def healthy() -> None:
        calls.append("healthy")

    await _shutdown_resources(
        (
            ("failing resource", failing),
            ("healthy resource", healthy),
        )
    )

    assert calls == ["failing", "healthy"]


async def test_application_shutdown_closes_provider_runtimes_after_tasks(
    monkeypatch,
) -> None:
    calls: list[str] = []

    class Resource:
        def __init__(self, name: str) -> None:
            self.name = name

        async def close(self) -> None:
            calls.append(self.name)

        async def shutdown(self) -> None:
            calls.append(self.name)

    class Tasks:
        @staticmethod
        async def destroy() -> None:
            calls.append("tasks")

    a2a = Resource("a2a")
    mcp = Resource("mcp")
    database = Resource("database")
    redis = Resource("redis")
    monkeypatch.setattr(main_module, "task_cls", Tasks)
    monkeypatch.setattr(
        main_module,
        "get_a2a_provider_runtime",
        lambda: a2a,
    )
    monkeypatch.setattr(main_module, "get_mcp_provider_pool", lambda: mcp)
    monkeypatch.setattr(main_module, "get_db", lambda: database)
    monkeypatch.setattr(main_module, "get_redis", lambda: redis)

    steps = _application_shutdown_steps()
    assert [name for name, _ in steps] == [
        "agent tasks",
        "A2A Provider Runtime",
        "MCP Provider Pool",
        "database",
        "Redis",
    ]

    await _shutdown_resources(steps)

    assert calls == ["tasks", "a2a", "mcp", "database", "redis"]

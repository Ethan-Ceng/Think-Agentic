#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio

from app.core.entities.app_config import A2AConfig, A2AServerConfig
from app.core.entities.tool_config import ToolConfig
from app.core.entities.tool_result import ToolResult
from app.core.tools.a2a import A2ATool
from app.core.tools.factory import ToolFactory
from app.core.tools.mcp import MCPTool


class FakeA2AManager:
    def __init__(self, config: A2AConfig, calls: list[str]) -> None:
        self.config = config
        self.calls = calls
        self.agent_cards = {
            "researcher": {
                "name": "Researcher",
                "url": "https://runtime-only.example.test",
            }
        }

    async def initialize(self) -> None:
        self.calls.append("initialize")

    async def invoke(self, agent_id: str, query: str) -> ToolResult:
        self.calls.append(f"invoke:{agent_id}:{query}")
        return ToolResult(success=True, data={"agent_id": agent_id})

    async def cleanup(self) -> None:
        self.calls.append("cleanup")


def test_a2a_schema_is_static_and_runtime_initializes_only_on_real_call() -> None:
    calls: list[str] = []
    config = A2AConfig(
        a2a_servers=[
            A2AServerConfig(
                id="researcher",
                base_url="https://configured.example.test",
            )
        ]
    )
    a2a_tool = A2ATool(
        config,
        manager_factory=lambda value: FakeA2AManager(value, calls),
    )
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=a2a_tool,
    )
    filtered = next(tool for tool in tools if tool.name == "a2a")
    factory.runtime_scope.activate(["a2a"], provider_ids=["a2a.remote"])

    assert {
        schema["function"]["name"] for schema in filtered.get_tools()
    } == {"get_remote_agent_cards", "call_remote_agent"}
    assert calls == []

    async def run() -> None:
        cards = await filtered.invoke("get_remote_agent_cards")
        assert cards.success is True
        called = await filtered.invoke(
            "call_remote_agent",
            id="researcher",
            query="summarize",
        )
        assert called.success is True
        await a2a_tool.cleanup()

    asyncio.run(run())

    assert calls == [
        "initialize",
        "invoke:researcher:summarize",
        "cleanup",
    ]


def test_a2a_cleanup_without_activation_is_a_noop() -> None:
    calls: list[str] = []
    tool = A2ATool(
        A2AConfig(),
        manager_factory=lambda value: FakeA2AManager(value, calls),
    )

    asyncio.run(tool.cleanup())

    assert calls == []

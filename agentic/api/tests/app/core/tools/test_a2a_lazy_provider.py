#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio

from app.core.entities.app_config import A2AConfig, A2AServerConfig
from app.core.entities.tool_config import ToolConfig
from app.core.entities.tool_result import ToolResult
from app.core.tools.a2a import A2ATool
from app.core.tools.a2a_runtime import (
    A2AFailureCode,
    A2ARuntimeError,
    DelegationTargetDescriptor,
    a2a_failure,
)
from app.core.tools.factory import ToolFactory
from app.core.tools.mcp import MCPTool


class FakeA2ARuntime:
    def __init__(
        self,
        calls: list[str],
        *,
        failing_targets: set[str] | None = None,
    ) -> None:
        self.calls = calls
        self.failing_targets = failing_targets or set()

    async def describe(
        self,
        *,
        user_id: str,
        target_config: A2AServerConfig,
    ) -> DelegationTargetDescriptor:
        self.calls.append(f"describe:{user_id}:{target_config.id}")
        if target_config.id in self.failing_targets:
            raise A2ARuntimeError(
                a2a_failure(
                    A2AFailureCode.CARD_DISCOVERY_FAILED,
                    target_id=target_config.id,
                )
            )
        return DelegationTargetDescriptor(
            target_id=target_config.id,
            name=f"Agent {target_config.id}",
            description="Safe summary",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
            snapshot_state="fresh",
        )

    async def invoke(
        self,
        *,
        user_id: str,
        target_config: A2AServerConfig,
        query: str,
    ) -> ToolResult:
        self.calls.append(
            f"invoke:{user_id}:{target_config.id}:{query}"
        )
        return ToolResult(success=True, data={"target_id": target_config.id})

    async def close(self) -> None:
        self.calls.append("close")


def _config() -> A2AConfig:
    return A2AConfig(
        a2a_servers=[
            A2AServerConfig(
                id="researcher",
                base_url="https://researcher.example.test",
            ),
            A2AServerConfig(
                id="writer",
                base_url="https://writer.example.test",
            ),
            A2AServerConfig(
                id="disabled",
                base_url="https://disabled.example.test",
                enabled=False,
            ),
        ]
    )


def test_a2a_schema_is_static_and_runtime_activates_only_on_real_call() -> None:
    calls: list[str] = []
    runtime = FakeA2ARuntime(calls)
    a2a_tool = A2ATool(
        _config(),
        provider_runtime=runtime,
        user_id="user-a",
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
        assert [item["target_id"] for item in cards.data["targets"]] == [
            "researcher",
            "writer",
        ]
        called = await filtered.invoke(
            "call_remote_agent",
            id="researcher",
            query="summarize",
        )
        assert called.success is True
        await a2a_tool.cleanup()

    asyncio.run(run())

    assert calls == [
        "describe:user-a:researcher",
        "describe:user-a:writer",
        "invoke:user-a:researcher:summarize",
    ]


def test_directory_returns_safe_partial_results_without_raw_card_fields() -> None:
    calls: list[str] = []
    tool = A2ATool(
        _config(),
        provider_runtime=FakeA2ARuntime(
            calls,
            failing_targets={"writer"},
        ),
        user_id="user-a",
    )

    result = asyncio.run(tool.get_remote_agent_cards())

    assert result.success is True
    assert result.data["unavailable_target_ids"] == ["writer"]
    assert result.data["targets"] == [
        {
            "target_id": "researcher",
            "provider_id": "a2a.remote",
            "target_type": "remote_a2a",
            "name": "Agent researcher",
            "description": "Safe summary",
            "skills": [],
            "protocol_binding": "JSONRPC",
            "protocol_version": "1.0",
            "snapshot_state": "fresh",
            "metadata_trust": "untrusted_external",
        }
    ]
    serialized = str(result.data)
    assert "base_url" not in serialized
    assert "security" not in serialized


def test_directory_returns_typed_failure_when_every_target_is_unavailable() -> None:
    tool = A2ATool(
        _config(),
        provider_runtime=FakeA2ARuntime(
            [],
            failing_targets={"researcher", "writer"},
        ),
    )

    result = asyncio.run(tool.get_remote_agent_cards())

    assert result.success is False
    assert result.failure is not None
    assert result.failure.code == "A2A_CARD_DISCOVERY_FAILED"
    assert result.data == {
        "targets": [],
        "unavailable_target_ids": ["researcher", "writer"],
    }


def test_call_remote_agent_rejects_unknown_or_disabled_target() -> None:
    calls: list[str] = []
    tool = A2ATool(
        _config(),
        provider_runtime=FakeA2ARuntime(calls),
    )

    unknown = asyncio.run(tool.call_remote_agent("unknown", "work"))
    disabled = asyncio.run(tool.call_remote_agent("disabled", "work"))

    assert unknown.failure is not None
    assert unknown.failure.code == "A2A_TARGET_NOT_FOUND"
    assert disabled.failure is not None
    assert disabled.failure.code == "A2A_TARGET_NOT_FOUND"
    assert calls == []


def test_shared_runtime_cleanup_is_a_noop() -> None:
    calls: list[str] = []
    tool = A2ATool(
        A2AConfig(),
        provider_runtime=FakeA2ARuntime(calls),
    )

    asyncio.run(tool.cleanup())

    assert calls == []


def test_owned_runtime_is_closed_even_without_activation() -> None:
    calls: list[str] = []
    runtime = FakeA2ARuntime(calls)
    tool = A2ATool(
        A2AConfig(),
        runtime_factory=lambda: runtime,
    )

    asyncio.run(tool.cleanup())

    assert calls == ["close"]

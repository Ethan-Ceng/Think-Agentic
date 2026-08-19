#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json

from app.core.entities.app_config import (
    A2AConfig,
    A2AServerConfig,
    MCPConfig,
    MCPServerConfig,
)
from app.core.entities.tool_config import ToolConfig, ToolRegistration
from app.core.tools.provider_catalog import (
    build_external_provider_descriptors,
    mcp_provider_id,
)
from app.core.tools.a2a import A2ATool
from app.core.tools.factory import ToolFactory
from app.core.tools.mcp import MCPTool
from app.core.tools.registry import ToolRegistry


def test_external_provider_catalog_is_safe_and_offline() -> None:
    tool_config = ToolConfig(
        registrations={
            "weather": ToolRegistration(
                registration_id="weather",
                provider_id="api.weather",
                provider_label="Weather API",
                source_type="api",
                executor_type="api",
                group="weather",
                description="Read current weather",
                requires_credentials=True,
                config={
                    "base_url": "https://api-secret.example.test",
                    "headers": {"Authorization": "Bearer top-secret"},
                    "openapi_schema": {
                        "paths": {
                            "/weather": {
                                "get": {
                                    "parameters": [{"name": "city"}],
                                }
                            }
                        }
                    },
                },
            )
        }
    )
    mcp_config = MCPConfig(
        mcpServers={
            "github": MCPServerConfig(
                url="https://mcp-secret.example.test",
                headers={"Authorization": "Bearer mcp-secret"},
                env={"TOKEN": "hidden"},
                description="Search GitHub issues",
            ),
            "disabled": MCPServerConfig(
                url="https://disabled.example.test",
                enabled=False,
            ),
        }
    )
    a2a_config = A2AConfig(
        a2a_servers=[
            A2AServerConfig(
                id="researcher",
                base_url="https://a2a-secret.example.test",
            )
        ]
    )

    descriptors = build_external_provider_descriptors(
        tool_config=tool_config,
        mcp_config=mcp_config,
        a2a_config=a2a_config,
    )
    payload = json.dumps(
        [item.model_dump(mode="json") for item in descriptors],
        ensure_ascii=False,
    )

    assert {item.provider_id for item in descriptors} == {
        "api.weather",
        "mcp.github",
        "mcp.disabled",
        "a2a.remote",
    }
    assert next(
        item for item in descriptors if item.provider_id == "mcp.disabled"
    ).enabled is False
    assert next(
        item for item in descriptors if item.provider_id == "mcp.github"
    ).credential_state == "configured"
    assert "Search GitHub issues" in payload
    assert "api-secret" not in payload
    assert "mcp-secret" not in payload
    assert "a2a-secret" not in payload
    assert "top-secret" not in payload
    assert "hidden" not in payload
    assert "parameters" not in payload


def test_registry_lists_unconnected_mcp_provider_without_tool_schema() -> None:
    registry = ToolRegistry(tool_config=ToolConfig())
    registry.register_provider_descriptors(
        build_external_provider_descriptors(
            tool_config=ToolConfig(),
            mcp_config=MCPConfig(
                mcpServers={
                    "github": MCPServerConfig(
                        url="https://mcp.example.test",
                        description="Search GitHub issues",
                    )
                }
            ),
            a2a_config=A2AConfig(),
        )
    )

    mcp_entry = next(
        item for item in registry.list_capability_catalog() if item["group"] == "mcp"
    )

    assert mcp_entry["tools"] == []
    assert mcp_entry["providers"] == [
        {
            "provider_id": "mcp.github",
            "provider_type": "mcp",
            "label": "github",
            "description": "Search GitHub issues",
            "semantic_tags": ["mcp", "streamable_http"],
            "metadata_trust": "untrusted_configuration",
            "credential_state": "not_required",
            "snapshot_state": "missing",
            "health_state": "unknown",
        }
    ]
    assert "mcp.github" in registry.provider_ids()
    assert registry.resolve_scope_selection(
        ["mcp"],
        ["mcp.github"],
    ) == (["mcp"], ["mcp.github"], [])


def test_mcp_provider_id_is_stable_and_namespaced() -> None:
    assert mcp_provider_id("github") == "mcp.github"
    assert mcp_provider_id("GitHub") != mcp_provider_id("github")
    assert mcp_provider_id("Git Hub / 企业") == mcp_provider_id("Git Hub / 企业")
    assert mcp_provider_id("Git Hub / 企业").startswith("mcp.git-hub-")
    assert len(mcp_provider_id("a" * 100)) <= 61


def test_tool_factory_registers_provider_catalog_without_initializing_runtime() -> None:
    mcp_tool = MCPTool(
        MCPConfig(
            mcpServers={
                "github": MCPServerConfig(
                    url="https://mcp.example.test",
                    description="Search GitHub issues",
                )
            }
        )
    )
    a2a_tool = A2ATool(A2AConfig())
    factory = ToolFactory(ToolConfig())

    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=mcp_tool,
        a2a_tool=a2a_tool,
    )

    assert mcp_tool._manager is None
    assert a2a_tool.manager is None
    assert all(
        tool._after_prepare is None
        for tool in tools
        if tool.name != "mcp"
    )
    assert "mcp.github" in factory.registry.provider_ids()
    assert "a2a.remote" not in factory.registry.provider_ids()

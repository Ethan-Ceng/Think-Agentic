from __future__ import annotations

import json

from app.core.entities.tool_config import ToolConfig
from app.core.entities.app_config import AgentConfig
from app.core.agent.planner import PlannerAgent
from app.core.agent.react import ReActAgent
from app.core.tools.a2a import A2ATool
from app.core.tools.factory import ToolFactory
from app.core.tools.mcp import MCPTool
from app.core.tools.registry import ToolRegistry
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


def test_current_planner_and_react_both_receive_all_enabled_schemas() -> None:
    tools = ToolFactory(ToolConfig()).build(
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
    }
    planner = PlannerAgent(**common)
    react = ReActAgent(**common)

    planner_schemas = planner._get_available_tools()
    react_schemas = react._get_available_tools()

    assert planner._tool_choice == "none"
    assert len(planner_schemas) == 27
    assert len(react_schemas) == 27
    assert tool_schema_bytes(planner_schemas) == 12933
    assert tool_schema_bytes(react_schemas) == 12933

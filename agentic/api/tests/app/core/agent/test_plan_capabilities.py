from __future__ import annotations

import json

import pytest

from app.core.agent.planner import PlannerAgent
from app.core.entities.app_config import AgentConfig
from app.core.entities.plan import Plan, Step
from app.core.entities.tool_config import ToolConfig
from app.core.entities.tool_result import ToolResult
from app.core.tools.a2a import A2ATool
from app.core.tools.base import BaseTool, tool
from app.core.tools.factory import ToolFactory
from app.core.tools.mcp import MCPTool


class ContextSearchTool(BaseTool):
    name = "context_search"

    @tool(
        name="context_search_run",
        description="Search the selected context.",
        parameters={"query": {"type": "string"}},
        required=["query"],
    )
    async def search(self, query: str) -> ToolResult:
        return ToolResult(success=True, data={"query": query})


def build_factory() -> ToolFactory:
    factory = ToolFactory(ToolConfig())
    factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )
    return factory


def test_old_step_json_without_capabilities_remains_compatible() -> None:
    step = Step.model_validate({"id": "legacy", "description": "旧步骤"})

    assert step.capabilities == []


def test_step_capabilities_are_trimmed_and_deduplicated() -> None:
    step = Step(capabilities=[" shell ", "file", "shell", ""])

    assert step.capabilities == ["shell", "file"]


def test_compact_capability_catalog_contains_no_parameter_schemas() -> None:
    factory = build_factory()

    catalog = factory.registry.list_capability_catalog()
    serialized = json.dumps(catalog, ensure_ascii=False)
    by_group = {item["group"]: item for item in catalog}

    assert by_group["file"]["requires_sandbox"] is True
    assert by_group["browser"]["requires_browser"] is True
    assert by_group["search"]["requires_sandbox"] is False
    assert "parameters" not in serialized
    assert "properties" not in serialized


def test_planner_accepts_only_groups_from_current_registry() -> None:
    factory = build_factory()
    planner = PlannerAgent(
        uow_factory=lambda: object(),
        session_id="session-1",
        agent_config=AgentConfig(),
        llm=object(),
        json_parser=object(),
        tools=[],
        tool_registry=factory.registry,
        runtime_tool_scope=factory.runtime_scope,
    )

    planner._validate_plan_capabilities(
        Plan(steps=[Step(description="run", capabilities=["shell", "file"])])
    )
    plan = Plan(
        steps=[Step(description="run", capabilities=["unknown", "search"])]
    )
    planner._validate_plan_capabilities(plan)

    assert plan.steps[0].capabilities == ["search"]
    with pytest.raises(ValueError, match="未知 capability group"):
        factory.registry.validate_capability_groups(["unknown"])


def test_contextual_tool_is_visible_only_when_its_group_is_in_scope() -> None:
    factory = build_factory()
    contextual = factory.build_contextual(ContextSearchTool())

    factory.runtime_scope.activate([])
    assert contextual.get_tools() == []

    factory.runtime_scope.activate(["context_search"])
    assert [
        schema["function"]["name"]
        for schema in contextual.get_tools()
    ] == ["context_search_run"]


def test_mcp_capability_catalog_refreshes_after_async_initialization() -> None:
    factory = ToolFactory(ToolConfig())
    mcp_tool = MCPTool()
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=mcp_tool,
        a2a_tool=A2ATool(),
    )
    filtered_mcp = next(tool for tool in tools if tool.name == "mcp")

    assert "mcp" not in factory.registry.capability_groups()

    mcp_tool._tools = [
        {
            "type": "function",
            "function": {
                "name": "mcp_search",
                "description": "Search an MCP source.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
        }
    ]
    factory.refresh_mcp_tools(mcp_tool)

    assert "mcp" in factory.registry.capability_groups()
    factory.runtime_scope.activate(["mcp"])
    assert [
        schema["function"]["name"]
        for schema in filtered_mcp.get_tools()
    ] == ["mcp_search"]

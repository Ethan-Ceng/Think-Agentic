from __future__ import annotations

import pytest

from app.core.agent.lead_decision import LeadDecisionPolicy
from app.core.entities.app_config import A2AConfig, MCPConfig, MCPServerConfig
from app.core.entities.lead import LeadMode
from app.core.entities.message import Message
from app.core.entities.tool_config import ToolConfig
from app.core.tools.provider_catalog import build_external_provider_descriptors
from app.core.tools.registry import ToolRegistry


class StubToolRegistry:
    def capability_groups(self) -> set[str]:
        return {"browser", "file", "search", "shell"}

    def resolve_scope_selection(
        self,
        capabilities,
        provider_ids=None,
        tool_ids=None,
    ):
        known_capabilities = self.capability_groups()
        resolved_capabilities = [
            value for value in capabilities if value in known_capabilities
        ]
        allowed = {
            "browser": ("builtin.browser", "builtin.browser.browser_navigate"),
            "file": ("builtin.file", "builtin.file.write_file"),
            "search": ("builtin.search", "builtin.search.search_web"),
            "shell": ("builtin.shell", "builtin.shell.shell_execute"),
        }
        allowed_providers = {
            allowed[group][0] for group in resolved_capabilities
        }
        resolved_providers = [
            value for value in provider_ids or [] if value in allowed_providers
        ]
        allowed_tools = {
            allowed[group][1] for group in resolved_capabilities
        }
        resolved_tools = [
            value for value in tool_ids or [] if value in allowed_tools
        ]
        return resolved_capabilities, resolved_providers, resolved_tools


def policy() -> LeadDecisionPolicy:
    instance = object.__new__(LeadDecisionPolicy)
    instance._tool_registry = StubToolRegistry()
    return instance


ROUTING_CASES = [
    (
        "今天几号",
        {
            "mode": "direct",
            "title": "日期",
            "language": "zh-CN",
            "answer": "今天是指定日期。",
        },
        LeadMode.DIRECT,
    ),
    (
        "Explain what recursion is in one paragraph",
        {
            "mode": "direct",
            "title": "Recursion",
            "language": "en",
            "answer": "Recursion is a definition or process that refers to itself.",
        },
        LeadMode.DIRECT,
    ),
    (
        "把这句话翻译成英文：今天天气很好",
        {
            "mode": "direct",
            "title": "翻译",
            "language": "zh-CN",
            "answer": "The weather is nice today.",
        },
        LeadMode.DIRECT,
    ),
    (
        "Give me three names for a cache helper",
        {
            "mode": "direct",
            "title": "Naming ideas",
            "language": "en",
            "answer": "CacheStore, CacheBridge, and CacheShelf.",
        },
        LeadMode.DIRECT,
    ),
    (
        "What is the latest stable Python release?",
        {
            "mode": "react",
            "title": "Python release",
            "language": "en",
            "goal": "Verify the latest stable Python release",
            "capabilities": ["search"],
        },
        LeadMode.REACT,
    ),
    (
        "Open https://example.com and summarize it",
        {
            "mode": "react",
            "title": "Page summary",
            "language": "en",
            "goal": "Open and summarize the supplied page",
            "capabilities": ["browser"],
        },
        LeadMode.REACT,
    ),
    (
        "Run the focused unit test and report the result",
        {
            "mode": "react",
            "title": "Unit test",
            "language": "en",
            "goal": "Run the focused unit test and report its result",
            "capabilities": ["shell"],
            "provider_ids": ["builtin.shell"],
            "tool_ids": ["builtin.shell.shell_execute"],
        },
        LeadMode.REACT,
    ),
    (
        "Create a short report file from the supplied facts",
        {
            "mode": "react",
            "title": "Report file",
            "language": "en",
            "goal": "Create and deliver the report file",
            "capabilities": ["file"],
        },
        LeadMode.REACT,
    ),
    (
        "Research three frameworks, compare them, and produce a recommendation report",
        {
            "mode": "plan",
            "title": "Framework comparison",
            "language": "en",
            "goal": "Produce an evidence-based framework recommendation",
            "message": "I will research, compare, and synthesize the findings.",
            "steps": [
                {
                    "id": "1",
                    "description": "Research primary sources for the frameworks",
                    "capabilities": ["search"],
                },
                {
                    "id": "2",
                    "description": "Compare the evidence and write the report",
                    "capabilities": ["file"],
                },
            ],
        },
        LeadMode.PLAN,
    ),
    (
        "Refactor the authentication module, update callers, and run regression tests",
        {
            "mode": "plan",
            "title": "Authentication refactor",
            "language": "en",
            "goal": "Safely refactor authentication and verify callers",
            "message": "I will update the module, callers, and regression coverage.",
            "steps": [
                {
                    "id": "1",
                    "description": "Inspect and refactor the authentication module",
                    "capabilities": ["file"],
                },
                {
                    "id": "2",
                    "description": "Update callers and run regression tests",
                    "capabilities": ["file", "shell"],
                },
            ],
        },
        LeadMode.PLAN,
    ),
    (
        "Migrate the configuration format and verify backward compatibility",
        {
            "mode": "plan",
            "title": "Configuration migration",
            "language": "en",
            "goal": "Migrate configuration without compatibility regressions",
            "message": "I will migrate the format and verify compatibility.",
            "steps": [
                {
                    "id": "1",
                    "description": "Implement the configuration migration",
                    "capabilities": ["file"],
                },
                {
                    "id": "2",
                    "description": "Run compatibility and regression checks",
                    "capabilities": ["shell"],
                },
            ],
        },
        LeadMode.PLAN,
    ),
]


@pytest.mark.parametrize(("message", "raw_decision", "expected_mode"), ROUTING_CASES)
def test_representative_routing_contract(
    message: str,
    raw_decision: dict,
    expected_mode: LeadMode,
) -> None:
    decision = policy()._normalize_decision(
        raw_decision,
        Message(message=message),
    )

    assert decision.mode == expected_mode


def test_representative_suite_has_mode_coverage() -> None:
    counts = {
        mode: sum(expected == mode for _, _, expected in ROUTING_CASES)
        for mode in LeadMode
    }

    assert counts[LeadMode.DIRECT] >= 3
    assert counts[LeadMode.REACT] >= 4
    assert counts[LeadMode.PLAN] >= 3


def test_explicit_code_execution_keeps_exact_sandbox_backed_tool_scope() -> None:
    decision = policy()._normalize_decision(
        {
            "mode": "react",
            "title": "Unit test",
            "language": "en",
            "goal": "Run the focused unit test",
            "capabilities": ["shell"],
            "provider_ids": ["builtin.shell"],
            "tool_ids": ["builtin.shell.shell_execute"],
        },
        Message(message="Run the focused unit test"),
    )

    assert decision.provider_ids == ["builtin.shell"]
    assert decision.tool_ids == ["builtin.shell.shell_execute"]


@pytest.mark.parametrize(
    ("servers", "requested", "expected"),
    [
        (["github"], [], ["mcp.github"]),
        (["github", "gitlab"], [], []),
        (["github", "gitlab"], ["mcp.github"], ["mcp.github"]),
    ],
)
def test_mcp_provider_selection_is_deterministic_without_global_fallback(
    servers: list[str],
    requested: list[str],
    expected: list[str],
) -> None:
    registry = ToolRegistry(tool_config=ToolConfig())
    registry.register_provider_descriptors(
        build_external_provider_descriptors(
            tool_config=ToolConfig(),
            mcp_config=MCPConfig(
                mcpServers={
                    name: MCPServerConfig(url=f"https://{name}.example.test")
                    for name in servers
                }
            ),
            a2a_config=A2AConfig(),
        )
    )
    instance = object.__new__(LeadDecisionPolicy)
    instance._tool_registry = registry

    decision = instance._normalize_decision(
        {
            "mode": "react",
            "title": "Search issues",
            "language": "en",
            "goal": "Search issue trackers",
            "capabilities": ["mcp"],
            "provider_ids": requested,
            "tool_ids": [],
        },
        Message(message="Search issue trackers"),
    )

    assert decision.capabilities == ["mcp"]
    assert decision.provider_ids == expected

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.core.agent.lead_decision import LeadDecisionPolicy
from app.core.entities.app_config import AgentConfig
from app.core.entities.lead import (
    DirectDecision,
    LeadMode,
    PlanDecision,
    ReactDecision,
)
from app.core.entities.memory import Memory
from app.core.entities.message import Message
from app.core.prompts.lead import LEAD_DECISION_PROMPT, LEAD_SYSTEM_PROMPT


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MemoryRepository:
    def __init__(self) -> None:
        self.memories: dict[tuple[str, str], Memory] = {}

    async def get_memory(self, session_id: str, agent_name: str) -> Memory:
        return self.memories.setdefault((session_id, agent_name), Memory())

    async def save_memory(
        self, session_id: str, agent_name: str, memory: Memory
    ) -> None:
        self.memories[(session_id, agent_name)] = memory.model_copy(deep=True)

    async def get_branch_context_seed(self, session_id: str) -> list:
        return []


class FakeUow:
    def __init__(self, session: MemoryRepository) -> None:
        self.session = session

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class JsonParser:
    async def invoke(self, value: str):
        return json.loads(value)


class RecordingLlm:
    model_name = "lead-decision-test"
    temperature = 0
    max_tokens = 256

    def __init__(self, content: dict) -> None:
        self.content = content
        self.calls: list[dict] = []

    async def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "role": "assistant",
            "content": json.dumps(self.content, ensure_ascii=False),
        }


class StubToolRegistry:
    def list_capability_catalog(self) -> list[dict]:
        return [
            {
                "group": "search",
                "description": "Search current information.",
                "requires_sandbox": False,
                "requires_browser": False,
                "tools": [
                    {
                        "tool_id": "builtin.search.search_web",
                        "function_name": "search_web",
                        "provider_id": "builtin.search",
                    }
                ],
            }
        ]

    def capability_groups(self) -> set[str]:
        return {"search"}

    def resolve_scope_selection(
        self,
        capabilities,
        provider_ids=None,
        tool_ids=None,
    ) -> tuple[list[str], list[str], list[str]]:
        resolved_capabilities = [
            value for value in capabilities if value == "search"
        ]
        resolved_providers = [
            value
            for value in provider_ids or []
            if value == "builtin.search" and resolved_capabilities
        ]
        resolved_tools = [
            value
            for value in tool_ids or []
            if value == "builtin.search.search_web"
            and resolved_capabilities
            and (not resolved_providers or "builtin.search" in resolved_providers)
        ]
        return resolved_capabilities, resolved_providers, resolved_tools


def make_policy(content: dict) -> tuple[LeadDecisionPolicy, RecordingLlm]:
    repository = MemoryRepository()
    llm = RecordingLlm(content)
    policy = LeadDecisionPolicy(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2),
        llm=llm,
        json_parser=JsonParser(),
        tools=[],
        tool_registry=StubToolRegistry(),
    )
    return policy, llm


def test_decision_models_are_strict_and_require_non_empty_values() -> None:
    with pytest.raises(ValidationError):
        DirectDecision(
            mode="direct",
            title=" ",
            language="zh-CN",
            answer="answer",
        )

    with pytest.raises(ValidationError):
        ReactDecision(
            mode="react",
            title="search",
            language="zh-CN",
            goal="find it",
            capabilities=[],
            unexpected=True,
        )

    with pytest.raises(ValidationError):
        PlanDecision(
            mode="plan",
            title="plan",
            language="zh-CN",
            goal="finish",
            steps=[],
        )


def test_lead_decide_prompt_is_bilingual_before_language_is_known() -> None:
    assert "最轻充分策略" in LEAD_SYSTEM_PROMPT
    assert "lightest sufficient strategy" in LEAD_SYSTEM_PROMPT
    assert "选择且只选择一种执行模式" in LEAD_DECISION_PROMPT
    assert "Choose exactly one execution mode" in LEAD_DECISION_PROMPT


async def test_decide_calls_model_once_without_tool_schemas() -> None:
    policy, llm = make_policy(
        {
            "mode": "direct",
            "title": "Greeting",
            "language": "en",
            "answer": "Hello!",
        }
    )

    decision = await policy.decide(Message(message="Say hello"))

    assert decision == DirectDecision(
        title="Greeting",
        language="en",
        answer="Hello!",
    )
    assert len(llm.calls) == 1
    assert llm.calls[0]["tools"] == []
    serialized_messages = json.dumps(llm.calls[0]["messages"], ensure_ascii=False)
    assert "search" in serialized_messages
    assert "parameters" not in serialized_messages
    assert "LingShu" in serialized_messages
    assert "<browser_rules>" not in serialized_messages
    assert "选择且只选择一种执行模式" in serialized_messages
    assert "Choose exactly one execution mode" in serialized_messages
    assert "dominant language of the user's message" in serialized_messages
    assert serialized_messages.count("Say hello") == 1


async def test_unknown_capabilities_are_removed() -> None:
    policy, _ = make_policy(
        {
            "mode": "react",
            "title": "Research",
            "language": "en",
            "goal": "Find the result",
            "capabilities": ["unknown", "search", "search"],
            "provider_ids": ["unknown", "builtin.search"],
            "tool_ids": ["unknown", "builtin.search.search_web"],
        }
    )

    decision = await policy.decide(Message(message="Find the latest result"))

    assert isinstance(decision, ReactDecision)
    assert decision.capabilities == ["search"]
    assert decision.provider_ids == ["builtin.search"]
    assert decision.tool_ids == ["builtin.search.search_web"]


async def test_single_step_plan_downgrades_to_react() -> None:
    policy, _ = make_policy(
        {
            "mode": "plan",
            "title": "Research",
            "language": "en",
            "goal": "Research one topic",
            "message": "I will research it.",
            "steps": [
                {
                    "id": "1",
                    "description": "Find the latest primary source",
                    "capabilities": ["search"],
                    "provider_ids": ["builtin.search"],
                    "tool_ids": ["builtin.search.search_web"],
                }
            ],
        }
    )

    decision = await policy.decide(Message(message="Find the latest source"))

    assert decision.mode == LeadMode.REACT
    assert isinstance(decision, ReactDecision)
    assert decision.goal == "Find the latest primary source"
    assert decision.capabilities == ["search"]
    assert decision.provider_ids == ["builtin.search"]
    assert decision.tool_ids == ["builtin.search.search_web"]


@pytest.mark.parametrize(
    "message",
    [
        Message(message="Summarize this", attachments=["/tmp/input.txt"]),
        Message(message="What is the latest release?"),
        Message(message="Please search for the official documentation"),
        Message(message="Open https://example.com and summarize it"),
    ],
)
async def test_direct_is_rejected_when_external_information_or_action_is_required(
    message: Message,
) -> None:
    policy, _ = make_policy(
        {
            "mode": "direct",
            "title": "Answer",
            "language": "en",
            "answer": "Unverified answer",
        }
    )

    with pytest.raises(ValueError, match="Direct 模式不允许"):
        await policy.decide(message)

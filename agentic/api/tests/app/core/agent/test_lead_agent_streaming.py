from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import pytest

from app.core.agent.lead import LeadAgent
from app.core.agent.lead_decision import (
    LeadDecisionCompleted,
    LeadDecisionPolicy,
)
from app.core.entities.app_config import AgentConfig
from app.core.entities.event import (
    BaseEvent,
    MessageDeltaEvent,
    MessageEvent,
)
from app.core.entities.lead import DirectDecision
from app.core.entities.memory import Memory
from app.core.entities.message import Message
from app.core.entities.session import BranchContextMessage, SessionStatus
from app.core.llm.base import LLMStreamCompleted, LLMStreamDelta


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeSession:
    def __init__(self) -> None:
        self.status = SessionStatus.PENDING


class Repository:
    def __init__(self) -> None:
        self.memories: dict[tuple[str, str], Memory] = {}
        self.session = FakeSession()
        self.statuses: list[SessionStatus] = []

    async def get_memory(self, session_id: str, agent_name: str) -> Memory:
        return self.memories.setdefault(
            (session_id, agent_name), Memory()
        ).model_copy(deep=True)

    async def save_memory(
        self,
        session_id: str,
        agent_name: str,
        memory: Memory,
    ) -> None:
        self.memories[(session_id, agent_name)] = memory.model_copy(deep=True)

    async def get_branch_context_seed(
        self,
        session_id: str,
    ) -> list[BranchContextMessage]:
        return []

    async def get_by_id(self, session_id: str) -> FakeSession:
        return self.session

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        self.session.status = status
        self.statuses.append(status)


class FakeUow:
    def __init__(self, repository: Repository) -> None:
        self.session = repository

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class JsonParser:
    async def invoke(self, value: str) -> dict[str, Any]:
        return json.loads(value)


class StreamingLLM:
    model_name = "lead-stream-model"
    temperature = 0
    max_tokens = 256

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    def stream(self, **kwargs) -> AsyncIterator[Any]:
        self.calls += 1

        async def generate() -> AsyncIterator[Any]:
            yield LLMStreamDelta(content=self.payload)
            message = {
                "role": "assistant",
                "content": self.payload,
                "_trace_metadata": {},
            }
            yield LLMStreamCompleted(
                message=message,
                model=self.model_name,
                finish_reason="stop",
                usage={},
                ttft_ms=1,
            )

        return generate()

    async def invoke(self, **kwargs) -> dict[str, Any]:
        raise AssertionError("streaming decision must remain one model call")


class FakeRegistry:
    def list_capability_catalog(self) -> list[dict[str, Any]]:
        return []

    def capability_groups(self) -> set[str]:
        return set()


class FakeLegacyFlow:
    async def invoke(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        yield MessageEvent(message="legacy")

    async def roll_back(self, message: Message) -> None:
        return None

    def set_skill_runtime_context(self, context) -> None:
        return None

    def get_available_tool_names(self) -> set[str]:
        return set()

    def refresh_mcp_tools(self) -> None:
        return None

    @property
    def done(self) -> bool:
        return True


def make_policy(
    payload: dict[str, Any],
) -> tuple[LeadDecisionPolicy, StreamingLLM, Repository]:
    repository = Repository()
    llm = StreamingLLM(json.dumps(payload, ensure_ascii=False))
    policy = LeadDecisionPolicy(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2),
        llm=llm,
        json_parser=JsonParser(),
        tools=[],
        tool_registry=FakeRegistry(),
        streaming_enabled=True,
    )
    policy._retry_interval = 0
    return policy, llm, repository


async def test_direct_decision_streams_only_answer_and_keeps_one_model_call() -> None:
    policy, llm, _ = make_policy(
        {
            "mode": "direct",
            "title": "Greeting",
            "language": "en",
            "answer": "Hello!",
        }
    )

    events = [event async for event in policy.decide_stream(Message(message="Hi"))]

    assert len(events) == 2
    assert isinstance(events[0], MessageDeltaEvent)
    assert events[0].delta == "Hello!"
    assert "answer" not in events[0].delta
    assert isinstance(events[1], LeadDecisionCompleted)
    assert events[1].decision == DirectDecision(
        title="Greeting",
        language="en",
        answer="Hello!",
    )
    assert events[1].stream_id == events[0].stream_id
    assert llm.calls == 1


async def test_direct_safety_failure_aborts_visible_draft() -> None:
    policy, _, _ = make_policy(
        {
            "mode": "direct",
            "title": "Latest",
            "language": "en",
            "answer": "Unverified",
        }
    )
    events: list[Any] = []

    with pytest.raises(ValueError, match="Direct 模式不允许"):
        async for event in policy.decide_stream(
            Message(message="What is the latest release?")
        ):
            events.append(event)

    assert [(event.operation, event.delta) for event in events] == [
        ("append", "Unverified"),
        ("abort", ""),
    ]
    assert events[0].stream_id == events[1].stream_id
    assert [event.sequence for event in events] == [0, 1]


async def test_lead_direct_final_replaces_the_streamed_decision_draft() -> None:
    policy, llm, repository = make_policy(
        {
            "mode": "direct",
            "title": "Greeting",
            "language": "en",
            "answer": "Hello!",
        }
    )
    lead = LeadAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        enabled=True,
        streaming_enabled=True,
        legacy_flow=FakeLegacyFlow(),
        decision_policy=policy,
    )

    events = [event async for event in lead.invoke(Message(message="Hi"))]

    assert [event.type for event in events] == [
        "message_delta",
        "title",
        "message",
        "done",
    ]
    delta = events[0]
    final = events[2]
    assert delta.delta == final.message == "Hello!"
    assert delta.stream_id == final.stream_id
    assert llm.calls == 1


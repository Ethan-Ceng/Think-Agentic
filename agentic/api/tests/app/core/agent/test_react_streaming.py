from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.agent.react import ReActAgent
from app.core.entities.app_config import AgentConfig
from app.core.entities.event import MessageDeltaEvent, MessageEvent, StepEvent
from app.core.entities.memory import Memory
from app.core.entities.message import Message
from app.core.entities.plan import Plan, Step
from app.core.entities.session import BranchContextMessage
from app.core.llm.base import LLMStreamCompleted, LLMStreamDelta


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Repository:
    def __init__(self) -> None:
        self.memories: dict[tuple[str, str], Memory] = {}

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


class QueueStreamingLLM:
    model_name = "react-stream-model"
    temperature = 0
    max_tokens = 256

    def __init__(self, payloads: list[str]) -> None:
        self.payloads = list(payloads)
        self.stream_calls = 0

    def stream(self, **kwargs) -> AsyncIterator[Any]:
        payload = self.payloads.pop(0)
        self.stream_calls += 1

        async def generate() -> AsyncIterator[Any]:
            split_at = max(1, len(payload) // 2)
            yield LLMStreamDelta(content=payload[:split_at])
            yield LLMStreamDelta(content=payload[split_at:])
            message = {
                "role": "assistant",
                "content": payload,
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
        raise AssertionError("enabled React output must use stream")


def make_agent(payloads: list[str], *, enabled: bool = True) -> ReActAgent:
    repository = Repository()
    agent = ReActAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2),
        llm=QueueStreamingLLM(payloads),
        json_parser=JsonParser(),
        tools=[],
        streaming_enabled=enabled,
    )
    agent._retry_interval = 0
    return agent


async def test_goal_streams_message_and_final_uses_same_stream_id() -> None:
    payload = json.dumps(
        {"message": "Goal complete", "attachments": []},
        ensure_ascii=False,
    )
    agent = make_agent([payload])

    events = [
        event
        async for event in agent.execute_goal(
            "finish",
            "en",
            [],
            Message(message="finish"),
        )
    ]

    deltas = [event for event in events if isinstance(event, MessageDeltaEvent)]
    final = events[-1]
    assert isinstance(final, MessageEvent)
    assert "".join(event.delta for event in deltas) == "Goal complete"
    assert final.message == "Goal complete"
    assert {event.stream_id for event in deltas} == {final.stream_id}


async def test_step_result_is_hidden_from_visible_chat_stream() -> None:
    payload = json.dumps(
        {"success": True, "result": "Step complete", "attachments": []},
        ensure_ascii=False,
    )
    agent = make_agent([payload])
    plan = Plan(language="en", steps=[Step(id="step-1", description="Do it")])

    events = [
        event
        async for event in agent.execute_step(
            plan,
            plan.steps[0],
            Message(message="Do it"),
        )
    ]

    deltas = [event for event in events if isinstance(event, MessageDeltaEvent)]
    step_events = [event for event in events if isinstance(event, StepEvent)]
    final = events[-1]
    assert len(step_events) == 2
    assert isinstance(final, MessageEvent)
    assert deltas == []
    assert final.message == "Step complete"
    assert final.visible is False


async def test_summarizer_streams_message_field() -> None:
    payload = json.dumps(
        {"message": "Final summary", "attachments": []},
        ensure_ascii=False,
    )
    agent = make_agent([payload])

    events = [event async for event in agent.summarize("en")]

    deltas = [event for event in events if isinstance(event, MessageDeltaEvent)]
    final = events[-1]
    assert isinstance(final, MessageEvent)
    assert "".join(event.delta for event in deltas) == "Final summary"
    assert final.message == "Final summary"
    assert {event.stream_id for event in deltas} == {final.stream_id}


async def test_invalid_final_contract_aborts_visible_goal_draft() -> None:
    payload = json.dumps(
        {"message": "Draft", "attachments": "not-a-list"},
        ensure_ascii=False,
    )
    agent = make_agent([payload])
    events: list[Any] = []

    with pytest.raises(ValidationError):
        async for event in agent.execute_goal(
            "finish",
            "en",
            [],
            Message(message="finish"),
        ):
            events.append(event)

    assert [(event.operation, event.delta) for event in events] == [
        ("append", "Draft"),
        ("abort", ""),
    ]
    assert events[0].stream_id == events[1].stream_id

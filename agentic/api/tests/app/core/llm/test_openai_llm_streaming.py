from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.entities.app_config import LLMConfig
from app.core.llm.base import (
    LLMStreamCompleted,
    LLMStreamDelta,
    LLMStreamingUnsupportedError,
)
from app.core.llm.failure import ModelFailureCode, ModelRuntimeError
from app.core.llm.openai_llm import OpenAILLM


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Dumpable(SimpleNamespace):
    def model_dump(self, *args, **kwargs) -> dict[str, Any]:
        return vars(self).copy()


class FakeStream:
    def __init__(self, chunks: list[Any], error: Exception | None = None) -> None:
        self.chunks = chunks
        self.error = error

    async def __aiter__(self) -> AsyncIterator[Any]:
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error


class FakeCompletions:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def chunk(
    *,
    delta: Any | None = None,
    finish_reason: str | None = None,
    usage: Any | None = None,
    model: str = "deepseek-chat",
) -> Any:
    choices = []
    if delta is not None:
        choices.append(SimpleNamespace(delta=delta, finish_reason=finish_reason))
    return SimpleNamespace(choices=choices, usage=usage, model=model)


def make_llm(completions: FakeCompletions) -> OpenAILLM:
    llm = OpenAILLM(
        LLMConfig(
            base_url="https://example.com/v1",
            api_key="test-key",
            model_name="deepseek-chat",
            temperature=0.2,
            max_tokens=512,
        )
    )
    llm._client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    return llm


async def collect(llm: OpenAILLM, **kwargs) -> list[Any]:
    return [event async for event in llm.stream(**kwargs)]


async def test_stream_yields_content_and_rebuilds_block_response() -> None:
    usage = Dumpable(prompt_tokens=7, completion_tokens=3, total_tokens=10)
    completions = FakeCompletions(
        FakeStream(
            [
                chunk(delta=SimpleNamespace(role="assistant", content='{"answer":"Hel')),
                chunk(
                    delta=SimpleNamespace(role=None, content='lo"}'),
                    finish_reason="stop",
                ),
                chunk(usage=usage),
            ]
        )
    )
    llm = make_llm(completions)

    events = await collect(
        llm,
        messages=[{"role": "user", "content": "hello"}],
        response_format={"type": "json_object"},
    )

    assert [type(event) for event in events] == [
        LLMStreamDelta,
        LLMStreamDelta,
        LLMStreamCompleted,
    ]
    assert [event.content for event in events[:-1]] == [
        '{"answer":"Hel',
        'lo"}',
    ]
    completed = events[-1]
    assert completed.message["role"] == "assistant"
    assert completed.message["content"] == '{"answer":"Hello"}'
    assert completed.finish_reason == "stop"
    assert completed.usage == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
    }
    assert completed.ttft_ms is not None
    assert completed.ttft_ms >= 0
    assert completed.message["_trace_metadata"] == {
        "model": "deepseek-chat",
        "finish_reason": "stop",
        "usage": completed.usage,
        "ttft_ms": completed.ttft_ms,
    }
    assert completions.calls == [
        {
            "model": "deepseek-chat",
            "temperature": 0.2,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": "hello"}],
            "response_format": {"type": "json_object"},
            "timeout": 3600,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
    ]


async def test_stream_aggregates_reasoning_and_split_tool_calls() -> None:
    first_tool = SimpleNamespace(
        index=0,
        id="call_",
        type="function",
        function=SimpleNamespace(name="sea", arguments='{"q":'),
    )
    second_tool = SimpleNamespace(
        index=0,
        id="123",
        type=None,
        function=SimpleNamespace(name="rch", arguments='"agent"}'),
    )
    completions = FakeCompletions(
        FakeStream(
            [
                chunk(
                    delta=SimpleNamespace(
                        role="assistant",
                        content=None,
                        reasoning_content="think ",
                        tool_calls=[first_tool],
                    )
                ),
                chunk(
                    delta=SimpleNamespace(
                        role=None,
                        content=None,
                        reasoning_content="then act",
                        tool_calls=[second_tool],
                    ),
                    finish_reason="tool_calls",
                ),
            ]
        )
    )
    llm = make_llm(completions)

    events = await collect(
        llm,
        messages=[{"role": "user", "content": "search"}],
        tools=[{"type": "function", "function": {"name": "search"}}],
        tool_choice="auto",
    )

    assert [type(event) for event in events] == [
        LLMStreamDelta,
        LLMStreamDelta,
        LLMStreamCompleted,
    ]
    assert events[0].reasoning_content == "think "
    assert events[1].reasoning_content == "then act"
    completed = events[-1]
    assert completed.message["content"] is None
    assert completed.message["reasoning_content"] == "think then act"
    assert completed.message["tool_calls"] == [
        {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": '{"q":"agent"}',
            },
        }
    ]
    assert completed.finish_reason == "tool_calls"
    assert completions.calls[0]["tools"] == [
        {"type": "function", "function": {"name": "search"}}
    ]
    assert completions.calls[0]["tool_choice"] == "auto"
    assert completions.calls[0]["parallel_tool_calls"] is False


async def test_stream_retries_without_stream_options_only_when_unsupported() -> None:
    completions = FakeCompletions(
        ValueError("Unknown parameter: stream_options"),
        FakeStream(
            [
                chunk(
                    delta=SimpleNamespace(role="assistant", content="done"),
                    finish_reason="stop",
                )
            ]
        ),
    )
    llm = make_llm(completions)

    events = await collect(
        llm,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert isinstance(events[-1], LLMStreamCompleted)
    assert len(completions.calls) == 2
    assert completions.calls[0]["stream_options"] == {"include_usage": True}
    assert "stream_options" not in completions.calls[1]


async def test_stream_does_not_replay_after_consumption_started() -> None:
    completions = FakeCompletions(
        FakeStream(
            [chunk(delta=SimpleNamespace(role="assistant", content="partial"))],
            error=RuntimeError("connection lost"),
        ),
        FakeStream([]),
    )
    llm = make_llm(completions)

    with pytest.raises(ModelRuntimeError) as exc_info:
        await collect(
            llm,
            messages=[{"role": "user", "content": "hello"}],
        )

    assert exc_info.value.failure.code == ModelFailureCode.UNKNOWN_ERROR.value
    assert len(completions.calls) == 1


async def test_stream_does_not_retry_unrelated_create_errors() -> None:
    completions = FakeCompletions(
        RuntimeError("provider unavailable"),
        FakeStream([]),
    )
    llm = make_llm(completions)

    with pytest.raises(ModelRuntimeError) as exc_info:
        await collect(
            llm,
            messages=[{"role": "user", "content": "hello"}],
        )

    assert exc_info.value.failure.code == ModelFailureCode.UNKNOWN_ERROR.value
    assert len(completions.calls) == 1


async def test_stream_reports_explicit_provider_incompatibility() -> None:
    completions = FakeCompletions(
        ValueError("This model does not support streaming"),
    )
    llm = make_llm(completions)

    with pytest.raises(LLMStreamingUnsupportedError):
        await collect(
            llm,
            messages=[{"role": "user", "content": "hello"}],
        )

    assert len(completions.calls) == 1

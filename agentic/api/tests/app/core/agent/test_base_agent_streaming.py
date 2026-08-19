from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.core.agent.base import (
    BaseAgent,
    ProjectedLLMCompleted,
    ProjectedMessageDelta,
)
from app.core.entities.app_config import AgentConfig
from app.core.entities.event import InteractionEvent, MessageEvent, ToolEvent
from app.core.entities.memory import Memory
from app.core.entities.session import BranchContextMessage
from app.core.entities.tool_config import ToolConfig
from app.core.entities.tool_result import ToolResult
from app.core.llm.base import (
    LLMStreamCompleted,
    LLMStreamDelta,
    LLMStreamingUnsupportedError,
)
from app.core.llm.failure import ModelFailureCode, ModelRuntimeError, model_failure
from app.core.tools.base import BaseTool, tool
from app.core.tools.a2a import A2ATool
from app.core.tools.factory import ToolFactory
from app.core.tools.mcp import MCPTool


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MemoryRepository:
    def __init__(self) -> None:
        self.memories: dict[tuple[str, str], Memory] = {}
        self.save_count = 0

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
        self.save_count += 1
        self.memories[(session_id, agent_name)] = memory.model_copy(deep=True)

    async def get_branch_context_seed(
        self,
        session_id: str,
    ) -> list[BranchContextMessage]:
        return []


class FakeUow:
    def __init__(self, repository: MemoryRepository) -> None:
        self.session = repository

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class JsonParser:
    async def invoke(self, value: str) -> dict[str, Any]:
        return {}


class ExampleAgent(BaseAgent):
    name = "stream-test"
    _system_prompt = "system"


class StreamingLLM:
    model_name = "stream-test-model"
    temperature = 0
    max_tokens = 128

    def __init__(self, attempts: list[list[Any]]) -> None:
        self.attempts = list(attempts)
        self.stream_calls = 0
        self.invoke_calls = 0

    def stream(self, **kwargs) -> AsyncIterator[Any]:
        attempt = self.attempts.pop(0)
        self.stream_calls += 1

        async def generate() -> AsyncIterator[Any]:
            for item in attempt:
                if isinstance(item, Exception):
                    raise item
                yield item

        return generate()

    async def invoke(self, **kwargs) -> dict[str, Any]:
        self.invoke_calls += 1
        raise AssertionError("streaming path must not call invoke")


class BlockLLM:
    model_name = "block-test-model"
    temperature = 0
    max_tokens = 128

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.invoke_calls = 0

    async def invoke(self, **kwargs) -> dict[str, Any]:
        self.invoke_calls += 1
        return self.response


class FailingBlockLLM:
    model_name = "failing-block-model"
    temperature = 0
    max_tokens = 128

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.invoke_calls = 0

    async def invoke(self, **kwargs) -> dict[str, Any]:
        self.invoke_calls += 1
        raise self.error


class UnsupportedStreamingLLM(BlockLLM):
    def __init__(
        self,
        response: dict[str, Any],
        *,
        events: list[Any] | None = None,
    ) -> None:
        super().__init__(response)
        self.events = list(events or [])
        self.stream_calls = 0

    def stream(self, **kwargs) -> AsyncIterator[Any]:
        self.stream_calls += 1

        async def generate() -> AsyncIterator[Any]:
            for event in self.events:
                yield event
            raise LLMStreamingUnsupportedError("streaming unsupported")

        return generate()


class FakeTrace:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.finished: list[dict[str, Any]] = []

    async def record_model_call_started(self, **kwargs) -> str:
        self.started.append(kwargs)
        return f"call-{len(self.started)}"

    async def record_model_call_finished(self, call_id: str, **kwargs) -> None:
        self.finished.append({"call_id": call_id, **kwargs})


class EchoTool(BaseTool):
    name = "echo-tools"

    @tool(
        name="echo",
        description="Return a fixed successful result",
        parameters={},
        required=[],
    )
    async def echo(self) -> ToolResult:
        return ToolResult(success=True, data={"value": "tool secret"})


def completed(content: str) -> LLMStreamCompleted:
    message = {
        "role": "assistant",
        "content": content,
        "_trace_metadata": {
            "model": "stream-test-model",
            "finish_reason": "stop",
            "usage": {},
            "ttft_ms": 4,
        },
    }
    return LLMStreamCompleted(
        message=message,
        model="stream-test-model",
        finish_reason="stop",
        usage={},
        ttft_ms=4,
    )


def make_agent(
    llm,
    *,
    trace=None,
    max_retries: int = 2,
    tools: list[BaseTool] | None = None,
    tool_registry=None,
    runtime_tool_scope=None,
) -> tuple[ExampleAgent, MemoryRepository]:
    repository = MemoryRepository()
    agent = ExampleAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        agent_config=AgentConfig(max_retries=max_retries),
        llm=llm,
        json_parser=JsonParser(),
        tools=tools or [],
        trace_service=trace,
        tool_registry=tool_registry,
        runtime_tool_scope=runtime_tool_scope,
    )
    agent._retry_interval = 0
    return agent, repository


async def collect(agent: BaseAgent, field: str = "answer") -> list[Any]:
    return [
        event
        async for event in agent._invoke_llm_stream(
            [{"role": "user", "content": "hello"}],
            "json_object",
            stream_field=field,
        )
    ]


async def test_streams_projected_text_then_returns_one_authoritative_message() -> None:
    payload = '{"answer":"Hello world"}'
    llm = StreamingLLM(
        [[
            LLMStreamDelta(content='{"answer":"H'),
            LLMStreamDelta(content="ello"),
            LLMStreamDelta(content=' world"}'),
            completed(payload),
        ]]
    )
    trace = FakeTrace()
    agent, repository = make_agent(llm, trace=trace)

    events = await collect(agent)

    assert [(event.operation, event.delta) for event in events[:-1]] == [
        ("append", "H"),
        ("append", "ello world"),
    ]
    assert isinstance(events[-1], ProjectedLLMCompleted)
    assert events[-1].message == {"role": "assistant", "content": payload}
    assert events[-1].streamed is True
    assert llm.stream_calls == 1
    assert llm.invoke_calls == 0
    assert len(trace.started) == 1
    assert len(trace.finished) == 1
    assert trace.finished[0]["message"]["_trace_metadata"]["ttft_ms"] == 4
    assert [message["role"] for message in repository.memories[("session-1", "stream-test")].messages] == [
        "system",
        "user",
        "assistant",
    ]


async def test_long_character_stream_is_batched_after_the_first_visible_fragment() -> None:
    answer = "x" * 96
    payload = f'{{"answer":"{answer}"}}'
    llm = StreamingLLM(
        [[
            *[LLMStreamDelta(content=character) for character in payload],
            completed(payload),
        ]]
    )
    agent, _ = make_agent(llm)
    agent._stream_batch_chars = 16
    agent._stream_batch_interval = 3600

    events = await collect(agent)
    deltas = [
        event.delta
        for event in events
        if isinstance(event, ProjectedMessageDelta)
    ]

    assert "".join(deltas) == answer
    assert deltas[0] == "x"
    assert len(deltas) == 7


async def test_retry_resets_a_visible_draft_before_streaming_again() -> None:
    payload = '{"answer":"new"}'
    llm = StreamingLLM(
        [
            [LLMStreamDelta(content='{"answer":"old'), RuntimeError("lost")],
            [LLMStreamDelta(content=payload), completed(payload)],
        ]
    )
    agent, _ = make_agent(llm)

    events = await collect(agent)

    assert [
        (event.operation, event.delta)
        for event in events
        if isinstance(event, ProjectedMessageDelta)
    ] == [
        ("append", "old"),
        ("reset", ""),
        ("append", "new"),
    ]
    assert isinstance(events[-1], ProjectedLLMCompleted)
    assert llm.stream_calls == 2


async def test_retry_exhaustion_aborts_any_visible_draft() -> None:
    llm = StreamingLLM(
        [
            [LLMStreamDelta(content='{"answer":"old'), RuntimeError("lost")],
            [RuntimeError("still unavailable")],
        ]
    )
    agent, _ = make_agent(llm)
    events: list[Any] = []

    with pytest.raises(ModelRuntimeError) as exc_info:
        async for event in agent._invoke_llm_stream(
            [{"role": "user", "content": "hello"}],
            "json_object",
            stream_field="answer",
        ):
            events.append(event)

    assert exc_info.value.failure.code == ModelFailureCode.UNKNOWN_ERROR.value
    assert [(event.operation, event.delta) for event in events] == [
        ("append", "old"),
        ("reset", ""),
        ("abort", ""),
    ]


async def test_llm_without_stream_method_uses_existing_block_path() -> None:
    llm = BlockLLM({"role": "assistant", "content": '{"answer":"done"}'})
    agent, _ = make_agent(llm)

    events = await collect(agent)

    assert len(events) == 1
    assert isinstance(events[0], ProjectedLLMCompleted)
    assert events[0].streamed is False
    assert llm.invoke_calls == 1


async def test_provider_stream_incompatibility_falls_back_to_block_call() -> None:
    llm = UnsupportedStreamingLLM(
        {"role": "assistant", "content": '{"answer":"done"}'},
    )
    agent, _ = make_agent(llm)

    events = await collect(agent)

    assert len(events) == 1
    assert isinstance(events[0], ProjectedLLMCompleted)
    assert events[0].streamed is False
    assert llm.stream_calls == 1
    assert llm.invoke_calls == 1


async def test_provider_stream_incompatibility_never_falls_back_after_a_chunk() -> None:
    llm = UnsupportedStreamingLLM(
        {"role": "assistant", "content": '{"answer":"duplicate"}'},
        events=[LLMStreamDelta(content='{"answer":"partial')],
    )
    agent, _ = make_agent(llm, max_retries=2)
    events: list[Any] = []

    with pytest.raises(ModelRuntimeError) as exc_info:
        async for event in agent._invoke_llm_stream(
            [{"role": "user", "content": "hello"}],
            "json_object",
            stream_field="answer",
        ):
            events.append(event)

    assert exc_info.value.failure.code == ModelFailureCode.INVALID_RESPONSE.value
    assert [(event.operation, event.delta) for event in events] == [
        ("append", "partial"),
        ("reset", ""),
        ("append", "partial"),
        ("abort", ""),
    ]
    assert llm.stream_calls == 2
    assert llm.invoke_calls == 0


async def test_non_retryable_model_failure_stops_after_one_attempt() -> None:
    failure = model_failure(ModelFailureCode.AUTHENTICATION_FAILED)
    llm = FailingBlockLLM(ModelRuntimeError(failure))
    agent, _ = make_agent(llm, max_retries=3)

    with pytest.raises(ModelRuntimeError) as exc_info:
        await collect(agent)

    assert llm.invoke_calls == 1
    assert exc_info.value.failure.debug_id == failure.debug_id
    assert exc_info.value.failure.code == ModelFailureCode.AUTHENTICATION_FAILED.value


async def test_retryable_model_failure_preserves_last_failure_after_limit() -> None:
    failure = model_failure(ModelFailureCode.TIMEOUT)
    llm = FailingBlockLLM(ModelRuntimeError(failure))
    agent, _ = make_agent(llm, max_retries=3)

    with pytest.raises(ModelRuntimeError) as exc_info:
        await collect(agent)

    assert llm.invoke_calls == 3
    assert exc_info.value.failure.debug_id == failure.debug_id
    assert exc_info.value.failure.code == ModelFailureCode.TIMEOUT.value


async def test_tool_loop_streams_only_the_post_tool_visible_field() -> None:
    tool_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "echo", "arguments": "{}"},
            }
        ],
        "_trace_metadata": {},
    }
    payload = '{"answer":"tool finished"}'
    llm = StreamingLLM(
        [
            [
                LLMStreamDelta(
                    reasoning_content="must stay internal",
                    tool_calls=(tool_message["tool_calls"][0],),
                ),
                LLMStreamCompleted(
                    message=tool_message,
                    model="stream-test-model",
                    finish_reason="tool_calls",
                    usage={},
                    ttft_ms=3,
                ),
            ],
            [LLMStreamDelta(content=payload), completed(payload)],
        ]
    )
    agent, _ = make_agent(llm, tools=[EchoTool()])

    events = [
        event
        async for event in agent.invoke("use the tool", stream_field="answer")
    ]

    assert [type(event) for event in events] == [
        ToolEvent,
        ToolEvent,
        ProjectedMessageDelta,
        MessageEvent,
    ]
    assert events[2].delta == "tool finished"
    assert "secret" not in events[2].delta
    assert events[3].message == payload
    assert llm.stream_calls == 2


@pytest.mark.parametrize(
    ("function_name", "arguments", "expected_message"),
    [
        (
            "browser_navigate",
            '{"url":"https://example.test"}',
            "当前步骤能力范围",
        ),
        ("totally_unknown_tool", "{}", "未知工具"),
    ],
)
async def test_unavailable_tool_becomes_observation_instead_of_crashing(
    function_name: str,
    arguments: str,
    expected_message: str,
) -> None:
    tool_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-browser",
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": arguments,
                },
            }
        ],
        "_trace_metadata": {},
    }
    payload = '{"answer":"continued after rejected tool"}'
    llm = StreamingLLM(
        [
            [
                LLMStreamCompleted(
                    message=tool_message,
                    model="stream-test-model",
                    finish_reason="tool_calls",
                    usage={},
                    ttft_ms=3,
                )
            ],
            [LLMStreamDelta(content=payload), completed(payload)],
        ]
    )
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=object(),
        browser=object(),
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )
    agent, _ = make_agent(
        llm,
        tools=tools,
        tool_registry=factory.registry,
        runtime_tool_scope=factory.runtime_scope,
    )
    agent.set_runtime_tool_scope(
        ["search"],
        provider_ids=["builtin.search"],
        tool_ids=["builtin.search.search_web"],
    )

    events = [
        event
        async for event in agent.invoke("research", stream_field="answer")
    ]

    tool_events = [event for event in events if isinstance(event, ToolEvent)]
    assert len(tool_events) == 2
    assert tool_events[0].function_name == function_name
    assert tool_events[1].function_result is not None
    assert tool_events[1].function_result.success is False
    assert expected_message in (tool_events[1].function_result.message or "")
    assert not any(isinstance(event, InteractionEvent) for event in events)
    assert isinstance(events[-1], MessageEvent)
    assert events[-1].message == payload
    assert llm.stream_calls == 2

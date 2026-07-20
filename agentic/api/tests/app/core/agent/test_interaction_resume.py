import json
from collections.abc import Callable

import pytest

from app.core.agent.react import ReActAgent
from app.core.entities.app_config import AgentConfig
from app.core.entities.event import (
    InteractionDecision,
    InteractionEvent,
    InteractionResolution,
    InteractionType,
    MessageEvent,
    ToolEvent,
    ToolEventStatus,
    WaitEvent,
)
from app.core.entities.message import Message
from app.core.entities.memory import Memory
from app.core.entities.plan import ExecutionStatus, Plan, Step
from app.core.entities.tool_result import ToolResult
from app.core.tools.base import BaseTool, tool
from app.core.tools.message import MessageTool


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MemoryRepository:
    def __init__(self) -> None:
        self.memories: dict[tuple[str, str], Memory] = {}

    async def get_memory(self, session_id: str, agent_name: str) -> Memory:
        return self.memories.setdefault((session_id, agent_name), Memory()).model_copy(deep=True)

    async def save_memory(self, session_id: str, agent_name: str, memory: Memory) -> None:
        self.memories[(session_id, agent_name)] = memory.model_copy(deep=True)


class FakeUow:
    def __init__(self, repository: MemoryRepository) -> None:
        self.session = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class JsonParser:
    async def invoke(self, value):
        return json.loads(value) if isinstance(value, str) else value


class QueueLlm:
    model_name = "interaction-test"
    temperature = 0
    max_tokens = 128

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    async def invoke(self, messages, **kwargs):
        self.calls.append(messages)
        return self.responses.pop(0)


class RiskyTool(BaseTool):
    name = "risky"

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict] = []

    def get_risk_level(self, tool_name: str):
        return "high"

    def get_approval_policy(self, tool_name: str):
        return "ask"

    @tool(
        name="dangerous_write",
        description="Write protected state",
        parameters={"path": {"type": "string"}, "content": {"type": "string"}},
        required=["path", "content"],
    )
    async def dangerous_write(self, path: str, content: str) -> ToolResult:
        self.calls.append({"path": path, "content": content})
        return ToolResult(success=True, data={"written": path})


def build_agent(
    repository: MemoryRepository,
    llm: QueueLlm,
    tools: list[BaseTool],
) -> ReActAgent:
    def uow_factory() -> FakeUow:
        return FakeUow(repository)

    return ReActAgent(
        uow_factory=uow_factory,
        session_id="session-1",
        agent_config=AgentConfig(max_retries=2, max_iterations=5),
        llm=llm,
        json_parser=JsonParser(),
        tools=tools,
    )


def tool_call_response(function_name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call-1",
                "function": {
                    "name": function_name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        ],
    }


async def collect(generator) -> list:
    return [event async for event in generator]


async def test_high_risk_tool_pauses_before_execution_and_resumes_exact_call() -> None:
    repository = MemoryRepository()
    risky = RiskyTool()
    arguments = {"path": "/tmp/report.md", "content": "safe"}
    first_llm = QueueLlm([tool_call_response("dangerous_write", arguments)])

    pending_events = await collect(build_agent(repository, first_llm, [risky]).invoke("write it"))
    pending = next(event for event in pending_events if isinstance(event, InteractionEvent))

    assert pending.interaction_type == InteractionType.TOOL_APPROVAL
    assert pending.function_args == arguments
    assert pending.risk_level == "high"
    assert risky.calls == []

    resumed_llm = QueueLlm([{"role": "assistant", "content": "completed"}])
    resumed_agent = build_agent(repository, resumed_llm, [risky])
    resolved = InteractionResolution(
        action_id=pending.action_id,
        interaction_type=pending.interaction_type,
        decision=InteractionDecision.APPROVE,
        tool_call_id=pending.tool_call_id,
        function_name=pending.function_name,
        function_args=pending.function_args,
    )
    resumed_events = await collect(resumed_agent.resume_interaction(resolved))

    assert risky.calls == [arguments]
    called = next(
        event
        for event in resumed_events
        if isinstance(event, ToolEvent) and event.status == ToolEventStatus.CALLED
    )
    assert called.function_result and called.function_result.success is True
    assert any(isinstance(event, MessageEvent) and event.message == "completed" for event in resumed_events)


async def test_rejected_tool_never_executes_and_returns_rejection_to_model() -> None:
    repository = MemoryRepository()
    risky = RiskyTool()
    arguments = {"path": "/tmp/report.md", "content": "safe"}
    pending_events = await collect(
        build_agent(repository, QueueLlm([tool_call_response("dangerous_write", arguments)]), [risky]).invoke(
            "write it"
        )
    )
    pending = next(event for event in pending_events if isinstance(event, InteractionEvent))

    resumed_llm = QueueLlm([{"role": "assistant", "content": "I will not write it."}])
    resolution = InteractionResolution(
        action_id=pending.action_id,
        interaction_type=pending.interaction_type,
        decision=InteractionDecision.REJECT,
        tool_call_id=pending.tool_call_id,
        function_name=pending.function_name,
        function_args=pending.function_args,
    )
    events = await collect(build_agent(repository, resumed_llm, [risky]).resume_interaction(resolution))

    assert risky.calls == []
    called = next(event for event in events if isinstance(event, ToolEvent))
    assert called.function_result and called.function_result.success is False
    assert "拒绝" in (called.function_result.message or "")


async def test_structured_ask_user_pauses_and_answer_resumes_as_tool_result() -> None:
    repository = MemoryRepository()
    args = {
        "text": "选择环境",
        "options": [
            {"value": "staging", "label": "预发布"},
            {"value": "production", "label": "生产"},
        ],
        "allow_text": False,
    }
    pending_events = await collect(
        build_agent(repository, QueueLlm([tool_call_response("message_ask_user", args)]), [MessageTool()]).invoke(
            "deploy"
        )
    )
    pending = next(event for event in pending_events if isinstance(event, InteractionEvent))

    assert pending.interaction_type == InteractionType.ASK_USER
    assert [option.value for option in pending.options] == ["staging", "production"]
    assert pending.allow_text is False

    resumed_llm = QueueLlm([{"role": "assistant", "content": "using staging"}])
    resolution = InteractionResolution(
        action_id=pending.action_id,
        interaction_type=pending.interaction_type,
        decision=InteractionDecision.ANSWER,
        tool_call_id=pending.tool_call_id,
        function_name=pending.function_name,
        function_args=pending.function_args,
        answer="预发布",
        selected_values=["staging"],
    )
    events = await collect(
        build_agent(repository, resumed_llm, [MessageTool()]).resume_interaction(resolution)
    )

    called = next(event for event in events if isinstance(event, ToolEvent))
    assert called.function_result and called.function_result.success is True
    assert called.function_result.data == {
        "answer": "预发布",
        "selected_values": ["staging"],
    }


async def test_resume_rejects_tampered_arguments_before_tool_execution() -> None:
    repository = MemoryRepository()
    risky = RiskyTool()
    arguments = {"path": "/tmp/report.md", "content": "safe"}
    pending_events = await collect(
        build_agent(repository, QueueLlm([tool_call_response("dangerous_write", arguments)]), [risky]).invoke(
            "write it"
        )
    )
    pending = next(event for event in pending_events if isinstance(event, InteractionEvent))
    resolution = InteractionResolution(
        action_id=pending.action_id,
        interaction_type=pending.interaction_type,
        decision=InteractionDecision.APPROVE,
        tool_call_id=pending.tool_call_id,
        function_name=pending.function_name,
        function_args={**pending.function_args, "path": "/tmp/tampered.md"},
    )

    with pytest.raises(RuntimeError, match="参数"):
        await collect(
            build_agent(repository, QueueLlm([]), [risky]).resume_interaction(resolution)
        )

    assert risky.calls == []


async def test_react_step_waits_without_duplicate_prompt_and_resumes_current_step() -> None:
    repository = MemoryRepository()
    risky = RiskyTool()
    arguments = {"path": "/tmp/report.md", "content": "safe"}
    plan = Plan(language="zh-CN", steps=[Step(description="write report")])
    step = plan.steps[0]

    pending_events = await collect(
        build_agent(
            repository,
            QueueLlm([tool_call_response("dangerous_write", arguments)]),
            [risky],
        ).execute_step(plan, step, Message(message="write it"))
    )
    pending = next(event for event in pending_events if isinstance(event, InteractionEvent))

    assert isinstance(pending_events[-1], WaitEvent)
    assert step.status == ExecutionStatus.RUNNING
    assert not any(isinstance(event, MessageEvent) for event in pending_events)

    completed_step = {
        "id": step.id,
        "description": step.description,
        "status": "completed",
        "success": True,
        "result": "written",
        "attachments": [],
    }
    resolution = InteractionResolution(
        action_id=pending.action_id,
        interaction_type=pending.interaction_type,
        decision=InteractionDecision.APPROVE,
        tool_call_id=pending.tool_call_id,
        function_name=pending.function_name,
        function_args=pending.function_args,
    )
    resumed_events = await collect(
        build_agent(
            repository,
            QueueLlm([{"role": "assistant", "content": json.dumps(completed_step)}]),
            [risky],
        ).resume_step(plan, step, resolution)
    )

    assert step.status == ExecutionStatus.COMPLETED
    assert step.success is True
    assert risky.calls == [arguments]
    assert any(isinstance(event, MessageEvent) and event.message == "written" for event in resumed_events)

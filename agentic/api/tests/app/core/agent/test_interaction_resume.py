from __future__ import annotations

import json

import pytest

from app.core.agent.react import ReActAgent
from app.core.entities.app_config import AgentConfig
from app.core.entities.event import (
    InteractionDecision,
    InteractionEvent,
    InteractionResolution,
    InteractionType,
    MessageEvent,
    StepEvent,
    StepEventStatus,
    ToolEvent,
    ToolEventStatus,
    WaitEvent,
)
from app.core.entities.message import Message
from app.core.entities.memory import Memory
from app.core.entities.session import BranchContextMessage
from app.core.entities.plan import ExecutionStatus, Plan, Step
from app.core.entities.tool_result import ToolResult
from app.core.entities.tool_config import ToolConfig
from app.core.sandbox.runtime import LazySandboxRuntime
from app.core.tools.a2a import A2ATool
from app.core.tools.base import BaseTool, tool
from app.core.tools.factory import ToolFactory
from app.core.tools.message import MessageTool
from app.core.tools.mcp import MCPTool


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MemoryRepository:
    def __init__(self) -> None:
        self.memories: dict[tuple[str, str], Memory] = {}
        self.sandbox_id: str | None = None
        self.sandbox_claims: list[tuple[str, str, str | None]] = []

    async def get_memory(self, session_id: str, agent_name: str) -> Memory:
        return self.memories.setdefault((session_id, agent_name), Memory()).model_copy(deep=True)

    async def save_memory(self, session_id: str, agent_name: str, memory: Memory) -> None:
        self.memories[(session_id, agent_name)] = memory.model_copy(deep=True)

    async def get_branch_context_seed(
        self, session_id: str
    ) -> list[BranchContextMessage]:
        return []

    async def claim_sandbox_id(
        self,
        session_id: str,
        candidate_id: str,
        *,
        expected_sandbox_id: str | None,
    ) -> str:
        self.sandbox_claims.append(
            (session_id, candidate_id, expected_sandbox_id)
        )
        self.sandbox_id = candidate_id
        return candidate_id


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
        self.call_kwargs: list[dict] = []

    async def invoke(self, messages, **kwargs):
        self.calls.append(messages)
        self.call_kwargs.append(kwargs)
        return self.responses.pop(0)


class RiskyTool(BaseTool):
    name = "risky"

    def __init__(self, policy: str = "ask") -> None:
        super().__init__()
        self.calls: list[dict] = []
        self.policy = policy

    def get_risk_level(self, tool_name: str):
        return "high"

    def get_execution_policy(self, tool_name: str):
        return self.policy

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
    *,
    tool_registry=None,
    runtime_tool_scope=None,
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
        tool_registry=tool_registry,
        runtime_tool_scope=runtime_tool_scope,
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


async def test_high_risk_tool_executes_without_creating_approval_interaction() -> None:
    repository = MemoryRepository()
    risky = RiskyTool()
    arguments = {"path": "/tmp/report.md", "content": "safe"}
    llm = QueueLlm(
        [
            tool_call_response("dangerous_write", arguments),
            {"role": "assistant", "content": "completed"},
        ]
    )

    events = await collect(build_agent(repository, llm, [risky]).invoke("write it"))

    assert risky.calls == [arguments]
    called = next(
        event
        for event in events
        if isinstance(event, ToolEvent) and event.status == ToolEventStatus.CALLED
    )
    assert called.function_result and called.function_result.success is True
    assert not any(isinstance(event, InteractionEvent) for event in events)
    assert not any(isinstance(event, WaitEvent) for event in events)
    assert any(isinstance(event, MessageEvent) and event.message == "completed" for event in events)


async def test_platform_denied_tool_never_executes_and_returns_failure_to_model() -> None:
    repository = MemoryRepository()
    risky = RiskyTool(policy="deny")
    arguments = {"path": "/tmp/report.md", "content": "safe"}
    llm = QueueLlm(
        [
            tool_call_response("dangerous_write", arguments),
            {"role": "assistant", "content": "I cannot write it."},
        ]
    )
    events = await collect(build_agent(repository, llm, [risky]).invoke("write it"))

    assert risky.calls == []
    called = next(
        event
        for event in events
        if isinstance(event, ToolEvent) and event.status == ToolEventStatus.CALLED
    )
    assert called.function_result and called.function_result.success is False
    assert "禁止" in (called.function_result.message or "")
    assert not any(isinstance(event, InteractionEvent) for event in events)


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
    tool_call = tool_call_response("dangerous_write", arguments)
    repository.memories[("session-1", "react")] = Memory(
        messages=[tool_call]
    )
    resolution = InteractionResolution(
        action_id="legacy-action",
        interaction_type=InteractionType.TOOL_APPROVAL,
        decision=InteractionDecision.APPROVE,
        tool_call_id="call-1",
        function_name="dangerous_write",
        function_args={**arguments, "path": "/tmp/tampered.md"},
    )

    with pytest.raises(RuntimeError, match="参数"):
        await collect(
            build_agent(repository, QueueLlm([]), [risky]).resume_interaction(resolution)
        )

    assert risky.calls == []


async def test_legacy_approval_can_never_execute_a_tool() -> None:
    repository = MemoryRepository()
    risky = RiskyTool()
    arguments = {"path": "/tmp/report.md", "content": "safe"}
    repository.memories[("session-1", "react")] = Memory(
        messages=[tool_call_response("dangerous_write", arguments)]
    )
    resolution = InteractionResolution(
        action_id="legacy-action",
        interaction_type=InteractionType.TOOL_APPROVAL,
        decision=InteractionDecision.APPROVE,
        tool_call_id="call-1",
        function_name="dangerous_write",
        function_args=arguments,
    )

    with pytest.raises(RuntimeError, match="已停用"):
        await collect(
            build_agent(repository, QueueLlm([]), [risky]).resume_interaction(
                resolution
            )
        )

    assert risky.calls == []


async def test_react_step_waits_without_duplicate_prompt_and_resumes_current_step() -> None:
    repository = MemoryRepository()
    arguments = {
        "text": "选择环境",
        "options": [{"value": "staging", "label": "预发布"}],
        "allow_text": False,
    }
    plan = Plan(language="en", steps=[Step(description="write report")])
    step = plan.steps[0]

    pending_llm = QueueLlm([tool_call_response("message_ask_user", arguments)])
    pending_events = await collect(
        build_agent(
            repository,
            pending_llm,
            [MessageTool()],
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
        decision=InteractionDecision.ANSWER,
        tool_call_id=pending.tool_call_id,
        function_name=pending.function_name,
        function_args=pending.function_args,
        answer="预发布",
        selected_values=["staging"],
    )
    resumed_llm = QueueLlm(
        [{"role": "assistant", "content": json.dumps(completed_step)}]
    )
    resumed_events = await collect(
        build_agent(
            repository,
            resumed_llm,
            [MessageTool()],
        ).resume_step(plan, step, resolution)
    )

    assert step.status == ExecutionStatus.COMPLETED
    assert step.success is True
    assert "You are LingShu" in pending_llm.calls[0][0]["content"]
    assert "You are LingShu" in resumed_llm.calls[0][0]["content"]
    assert any(isinstance(event, MessageEvent) and event.message == "written" for event in resumed_events)


async def test_react_step_marks_structured_failure_as_failed() -> None:
    repository = MemoryRepository()
    plan = Plan(language="en", steps=[Step(description="attempt task")])
    step = plan.steps[0]
    failed_step = {
        "id": step.id,
        "description": step.description,
        "status": "failed",
        "success": False,
        "result": "could not complete",
        "attachments": [],
    }

    events = await collect(
        build_agent(
            repository,
            QueueLlm([{"role": "assistant", "content": json.dumps(failed_step)}]),
            [],
        ).execute_step(plan, step, Message(message="try it"))
    )

    assert step.status == ExecutionStatus.FAILED
    assert any(
        isinstance(event, StepEvent)
        and event.status == StepEventStatus.FAILED
        for event in events
    )


class LazyApprovalSandbox:
    create_calls = 0
    instances: dict[str, "LazyApprovalSandbox"] = {}

    def __init__(self, sandbox_id: str) -> None:
        self.id = sandbox_id
        self.vnc_url = f"ws://{sandbox_id}/vnc"
        self.cdp_url = f"http://{sandbox_id}/cdp"
        self.exec_calls: list[tuple[str, str, str]] = []

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = 0
        cls.instances = {}

    @classmethod
    async def create(cls) -> "LazyApprovalSandbox":
        cls.create_calls += 1
        sandbox = cls(f"sandbox-{cls.create_calls}")
        cls.instances[sandbox.id] = sandbox
        return sandbox

    @classmethod
    async def get(cls, sandbox_id: str) -> "LazyApprovalSandbox" | None:
        return cls.instances.get(sandbox_id)

    async def ensure_sandbox(self) -> None:
        return None

    async def exec_command(
        self,
        session_id: str,
        exec_dir: str,
        command: str,
    ) -> ToolResult:
        self.exec_calls.append((session_id, exec_dir, command))
        return ToolResult(success=True, data={"output": "done"})

    async def destroy(self) -> bool:
        return True


async def test_shell_executes_without_approval_and_starts_lazy_sandbox_once() -> None:
    repository = MemoryRepository()
    LazyApprovalSandbox.reset()

    def uow_factory() -> FakeUow:
        return FakeUow(repository)

    runtime = LazySandboxRuntime(
        session_id="session-1",
        sandbox_id=None,
        sandbox_cls=LazyApprovalSandbox,
        uow_factory=uow_factory,
    )
    factory = ToolFactory(ToolConfig())
    tools = factory.build(
        sandbox=runtime.sandbox,
        browser=runtime.browser,
        search_engine=object(),
        mcp_tool=MCPTool(),
        a2a_tool=A2ATool(),
    )
    arguments = {
        "session_id": "shell-1",
        "exec_dir": "/tmp",
        "command": "echo ready",
    }
    plan = Plan(
        language="zh-CN",
        steps=[
            Step(
                description="run approved command",
                capabilities=["shell"],
                provider_ids=["builtin.shell"],
                tool_ids=["builtin.shell.shell_execute"],
            )
        ],
    )
    step = plan.steps[0]
    completed_step = {
        "id": step.id,
        "description": step.description,
        "status": "completed",
        "success": True,
        "result": "done",
        "attachments": [],
    }
    run_llm = QueueLlm(
        [
            tool_call_response("shell_execute", arguments),
            {"role": "assistant", "content": json.dumps(completed_step)},
        ]
    )
    events = await collect(
        build_agent(
            repository,
            run_llm,
            tools,
            tool_registry=factory.registry,
            runtime_tool_scope=factory.runtime_scope,
        ).execute_step(plan, step, Message(message="run it"))
    )

    sandbox = LazyApprovalSandbox.instances["sandbox-1"]
    assert LazyApprovalSandbox.create_calls == 1
    assert sandbox.exec_calls == [
        ("shell-1", "/tmp", "echo ready"),
    ]
    assert repository.sandbox_claims == [
        ("session-1", "sandbox-1", None),
    ]
    assert not any(isinstance(event, InteractionEvent) for event in events)
    assert step.status == ExecutionStatus.COMPLETED
    followup_tool_names = {
        schema["function"]["name"]
        for schema in run_llm.call_kwargs[1]["tools"]
    }
    assert followup_tool_names == {
        "message_ask_user",
        "message_notify_user",
        "shell_execute",
    }

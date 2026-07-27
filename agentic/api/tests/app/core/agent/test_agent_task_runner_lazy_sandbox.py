from __future__ import annotations

import asyncio

from app.core.agent.agent_task_runner import AgentTaskRunner
from app.core.entities.event import MessageEvent
from app.core.entities.file import File
from app.core.sandbox.runtime import SandboxActivation
from app.core.entities.session import SessionStatus


class RecordingSessionRepository:
    def __init__(self) -> None:
        self.statuses: list[SessionStatus] = []
        self.files: list[File] = []

    async def add_event(self, session_id: str, event) -> None:
        assert session_id == "session-1"

    async def finish_or_claim_next_message(self, session_id: str, task_id: str):
        assert session_id == "session-1"
        self.statuses.append(SessionStatus.COMPLETED)
        return None

    async def add_file(self, session_id: str, file: File) -> None:
        assert session_id == "session-1"
        self.files.append(file)


class FakeUow:
    def __init__(self) -> None:
        self.session = RecordingSessionRepository()

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class FakeInputStream:
    def __init__(self, event: MessageEvent) -> None:
        self.item = ("input-1", event.model_dump_json())

    async def is_empty(self) -> bool:
        return self.item is None

    async def pop(self):
        item = self.item
        self.item = None
        return item


class FakeOutputStream:
    async def put(self, payload: str) -> str:
        return "output-1"


class FakeTask:
    id = "task-1"

    def __init__(self, event: MessageEvent) -> None:
        self.input_stream = FakeInputStream(event)
        self.output_stream = FakeOutputStream()


class RecordingRuntime:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.manifests: list[list[File]] = []

    def set_attachment_manifest(self, attachments: list[File]):
        self.calls.append("set_attachment_manifest")
        self.manifests.append(attachments)
        return [
            type(
                "Entry",
                (),
                {
                    "prompt_text": (
                        f"{attachment.filename}; "
                        f"sandbox_path_after_activation=/home/ubuntu/upload/{attachment.filename}"
                    )
                },
            )()
            for attachment in attachments
        ]


def make_runner(calls: list[str]) -> AgentTaskRunner:
    runner = object.__new__(AgentTaskRunner)
    runner._session_id = "session-1"
    runner._user_id = "user-1"
    runner._uow = FakeUow()
    runner._uow_factory = lambda: runner._uow
    runner._sandbox_runtime = RecordingRuntime(calls)
    runner._sandbox = object()
    runner._mcp_config = object()
    runner._mcp_tool = type("MCP", (), {"initialize": lambda self, _: _record(calls, "mcp")})()
    runner._a2a_config = object()
    runner._a2a_tool = type("A2A", (), {"initialize": lambda self, _: _record(calls, "a2a")})()
    runner._trace_service = type("Trace", (), {"project_event": lambda self, _: _noop()})()
    runner._prepare_skill_runtime = lambda task, event: _record(calls, "prepare_trace")
    runner._cleanup_tools = lambda: _noop()

    async def empty_flow(message):
        calls.append("flow")
        if False:
            yield None

    runner._run_flow = empty_flow
    return runner


async def _record(calls: list[str], name: str) -> None:
    calls.append(name)


async def _noop() -> None:
    return None


def test_runner_only_prepares_attachment_manifest_before_flow() -> None:
    calls: list[str] = []
    runner = make_runner(calls)

    asyncio.run(runner.invoke(FakeTask(MessageEvent(role="user", message="hello"))))

    assert calls[:5] == [
        "mcp",
        "a2a",
        "set_attachment_manifest",
        "prepare_trace",
        "flow",
    ]


def test_runner_passes_safe_attachment_manifest_without_downloading_file() -> None:
    calls: list[str] = []
    runner = make_runner(calls)
    file = File(
        id="file-1",
        user_id="user-1",
        filename="contract.txt",
        filepath="provider/private/path",
    )
    received_attachments: list[str] = []

    async def capture_flow(message):
        received_attachments.extend(message.attachments)
        if False:
            yield None

    runner._run_flow = capture_flow

    asyncio.run(
        runner.invoke(
            FakeTask(
                MessageEvent(role="user", message="hello", attachments=[file])
            )
        )
    )

    assert runner._sandbox_runtime.manifests == [[file]]
    assert received_attachments == [
        "contract.txt; sandbox_path_after_activation=/home/ubuntu/upload/contract.txt"
    ]
    assert "provider/private/path" not in received_attachments[0]


def test_lazy_activation_is_projected_to_trace_and_session_files() -> None:
    calls: list[str] = []
    runner = make_runner(calls)
    recorded: list[dict] = []
    materialized = File(
        id="file-1",
        user_id="user-1",
        filename="contract.txt",
        filepath="/home/ubuntu/upload/contract.txt",
    )

    class RecordingTrace:
        async def record_sandbox_activation(self, **kwargs) -> None:
            recorded.append(kwargs)

    runner._trace_service = RecordingTrace()
    runner._on_sandbox_activation = AgentTaskRunner._on_sandbox_activation.__get__(
        runner,
        AgentTaskRunner,
    )

    asyncio.run(
        runner._on_sandbox_activation(
            SandboxActivation(
                activation_reason="tool_invocation",
                first_capability="sandbox",
                operation_counts={
                    "create": 1,
                    "get": 0,
                    "ensure": 1,
                    "get_browser": 0,
                    "upload_file": 1,
                },
                startup_ms=25,
                attachment_sync_bytes=100,
                materialized_files=(materialized,),
            )
        )
    )

    assert len(recorded) == 1
    assert recorded[0]["activation_reason"] == "tool_invocation"
    assert recorded[0]["first_capability"] == "sandbox"
    assert recorded[0]["operation_counts"]["create"] == 1
    assert recorded[0]["attachment_sync_bytes"] == 100
    assert runner._uow.session.files == [materialized]

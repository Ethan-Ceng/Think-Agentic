from __future__ import annotations

import asyncio

from app.core.agent.agent_task_runner import AgentTaskRunner
from app.core.entities.event import MessageEvent
from app.core.entities.file import File
from app.core.entities.session import SessionStatus
from app.core.entities.tool_result import ToolResult


class RecordingSessionRepository:
    def __init__(self) -> None:
        self.statuses: list[SessionStatus] = []

    async def add_event(self, session_id: str, event) -> None:
        assert session_id == "session-1"

    async def finish_or_claim_next_message(self, session_id: str, task_id: str):
        assert session_id == "session-1"
        self.statuses.append(SessionStatus.COMPLETED)
        return None


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


class RecordingSandbox:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.uploaded_bytes = 0

    async def ensure_sandbox(self) -> None:
        self.calls.append("ensure_sandbox")

    async def upload_file(self, file_data, filepath: str, filename: str):
        self.uploaded_bytes += len(file_data)
        return ToolResult(success=True)


def make_runner(calls: list[str]) -> AgentTaskRunner:
    runner = object.__new__(AgentTaskRunner)
    runner._session_id = "session-1"
    runner._user_id = "user-1"
    runner._uow = FakeUow()
    runner._sandbox = RecordingSandbox(calls)
    runner._mcp_config = object()
    runner._mcp_tool = type("MCP", (), {"initialize": lambda self, _: _record(calls, "mcp")})()
    runner._a2a_config = object()
    runner._a2a_tool = type("A2A", (), {"initialize": lambda self, _: _record(calls, "a2a")})()
    runner._trace_service = type("Trace", (), {"project_event": lambda self, _: _noop()})()
    runner._sandbox_activation_summary = {
        "activation_reason": "task_initialization",
        "first_capability": None,
        "operation_counts": {
            "create": 1,
            "get": 0,
            "ensure": 0,
            "get_browser": 1,
            "upload_file": 0,
        },
        "startup_ms": 10,
        "attachment_sync_bytes": 0,
    }
    runner._prepare_skill_runtime = lambda task, event: _record(calls, "prepare_trace")
    runner._cleanup_tools = lambda: _noop()

    async def sync_attachments(event: MessageEvent) -> None:
        calls.append("sync_attachments")

    async def empty_flow(message):
        calls.append("flow")
        if False:
            yield None

    runner._sync_message_attachments_to_sandbox = sync_attachments
    runner._run_flow = empty_flow
    return runner


async def _record(calls: list[str], name: str) -> None:
    calls.append(name)


async def _noop() -> None:
    return None


def test_current_runner_ensures_sandbox_and_syncs_attachments_before_flow() -> None:
    calls: list[str] = []
    runner = make_runner(calls)

    asyncio.run(runner.invoke(FakeTask(MessageEvent(role="user", message="hello"))))

    assert calls[:6] == [
        "ensure_sandbox",
        "mcp",
        "a2a",
        "sync_attachments",
        "prepare_trace",
        "flow",
    ]
    assert runner._sandbox_activation_summary["operation_counts"]["ensure"] == 1


def test_current_attachment_materialization_records_uploaded_bytes() -> None:
    calls: list[str] = []
    runner = make_runner(calls)
    payload = b"contract-data"
    file = File(id="file-1", user_id="user-1", filename="contract.txt", size=len(payload))
    runner._file_storage = type(
        "Storage",
        (),
        {"download_file": lambda self, file_id, user_id: _download(payload, file)},
    )()

    synced = asyncio.run(runner._sync_file_to_sandbox(file.id))

    assert synced.filepath == "/home/ubuntu/upload/contract.txt"
    assert runner._sandbox.uploaded_bytes == len(payload)
    assert runner._sandbox_activation_summary["operation_counts"]["upload_file"] == 1
    assert runner._sandbox_activation_summary["attachment_sync_bytes"] == len(payload)


def test_first_trace_run_receives_eager_sandbox_activation_summary_once() -> None:
    calls: list[str] = []
    runner = make_runner(calls)
    recorded: list[dict] = []

    class RecordingTrace:
        async def start_run(self, **kwargs) -> str:
            return "run-1"

        async def record_sandbox_activation(self, **kwargs) -> None:
            recorded.append(kwargs)

    runner._trace_service = RecordingTrace()
    runner._flow = type(
        "Flow",
        (),
        {"set_skill_runtime_context": lambda self, context: None},
    )()
    runner._skill_runtime_service = None
    runner._prepare_skill_runtime = AgentTaskRunner._prepare_skill_runtime.__get__(
        runner,
        AgentTaskRunner,
    )

    asyncio.run(
        runner._prepare_skill_runtime(
            FakeTask(MessageEvent(role="user", message="hello")),
            MessageEvent(role="user", message="hello"),
        )
    )

    assert len(recorded) == 1
    assert recorded[0]["activation_reason"] == "task_initialization"
    assert recorded[0]["operation_counts"]["create"] == 1
    assert recorded[0]["operation_counts"]["get_browser"] == 1
    assert runner._sandbox_activation_summary is None


async def _download(payload: bytes, file: File):
    return payload, file

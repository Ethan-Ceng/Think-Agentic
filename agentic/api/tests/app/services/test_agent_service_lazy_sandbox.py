from __future__ import annotations

import asyncio
from typing import Any

from app.core.entities.app_config import (
    A2AConfig,
    AgentConfig,
    AppConfig,
    LLMConfig,
    MCPConfig,
)
from app.core.entities.session import Session
from app.core.entities.tool_config import ToolConfig
from app.core.sandbox.runtime import LazySandboxRuntime
from app.services.agent_service import AgentService


class RecordingSessionRepository:
    def __init__(self) -> None:
        self.runtime_updates: list[dict[str, str]] = []

    async def update_runtime_handles(self, session_id: str, **values: str) -> None:
        assert session_id == "session-1"
        self.runtime_updates.append(values)


class FakeUow:
    def __init__(self, session: RecordingSessionRepository) -> None:
        self.session = session

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class RecordingSandbox:
    def __init__(self, sandbox_id: str) -> None:
        self.id = sandbox_id
        self.browser_calls = 0

    async def get_browser(self) -> object:
        self.browser_calls += 1
        return object()


class RecordingSandboxClass:
    create_calls = 0
    get_calls: list[str] = []
    existing: dict[str, RecordingSandbox] = {}

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = 0
        cls.get_calls = []
        cls.existing = {}

    @classmethod
    async def create(cls) -> RecordingSandbox:
        cls.create_calls += 1
        return RecordingSandbox("sandbox-created")

    @classmethod
    async def get(cls, sandbox_id: str) -> RecordingSandbox | None:
        cls.get_calls.append(sandbox_id)
        return cls.existing.get(sandbox_id)


class RecordingTask:
    created_runners: list[Any] = []

    def __init__(self) -> None:
        self.id = "task-created"

    @classmethod
    def create(cls, *, task_runner: Any) -> "RecordingTask":
        cls.created_runners.append(task_runner)
        return cls()


class FakeUserConfigService:
    async def get_app_config(self, user_id: str) -> AppConfig:
        assert user_id == "user-1"
        return AppConfig(
            llm_config=LLMConfig(),
            agent_config=AgentConfig(),
            mcp_config=MCPConfig(),
            a2a_config=A2AConfig(),
            tool_config=ToolConfig(),
        )


def make_service() -> tuple[AgentService, RecordingSessionRepository]:
    RecordingSandboxClass.reset()
    RecordingTask.created_runners = []
    session_repo = RecordingSessionRepository()
    uow = FakeUow(session_repo)
    service = AgentService(
        uow_factory=lambda: uow,
        user_config_service=FakeUserConfigService(),
        llm_factory=lambda *_: object(),
        sandbox_cls=RecordingSandboxClass,
        task_cls=RecordingTask,
        json_parser=object(),
        search_engine=object(),
        file_storage=object(),
    )
    return service, session_repo


def test_task_initialization_builds_lazy_runtime_without_starting_sandbox() -> None:
    service, session_repo = make_service()
    session = Session(id="session-1", user_id="user-1")

    task = asyncio.run(service._create_task(session))

    assert task.id == "task-created"
    assert RecordingSandboxClass.get_calls == []
    assert RecordingSandboxClass.create_calls == 0
    runner = RecordingTask.created_runners[0]
    assert isinstance(runner._sandbox_runtime, LazySandboxRuntime)
    assert runner._sandbox_runtime.is_activated is False
    assert runner._sandbox is runner._sandbox_runtime.sandbox
    assert runner._browser is runner._sandbox_runtime.browser
    assert session.sandbox_id is None
    assert session_repo.runtime_updates == [{"task_id": "task-created"}]


def test_existing_handle_is_not_restored_until_sandbox_capability_is_used() -> None:
    service, _ = make_service()
    existing = RecordingSandbox("sandbox-existing")
    RecordingSandboxClass.existing[existing.id] = existing
    session = Session(
        id="session-1",
        user_id="user-1",
        sandbox_id=existing.id,
    )

    asyncio.run(service._create_task(session))

    assert RecordingSandboxClass.get_calls == []
    assert RecordingSandboxClass.create_calls == 0
    assert existing.browser_calls == 0
    runtime = RecordingTask.created_runners[0]._sandbox_runtime
    assert runtime.is_activated is False

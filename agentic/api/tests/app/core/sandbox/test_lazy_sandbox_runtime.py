from __future__ import annotations

import asyncio
from collections import deque

import pytest

from app.core.sandbox.runtime import (
    LazySandboxRuntime,
    SandboxNotActivatedError,
)


class RecordingSessionRepository:
    def __init__(
        self,
        *,
        sandbox_id: str | None = None,
        deleted: bool = False,
    ) -> None:
        self.sandbox_id = sandbox_id
        self.deleted = deleted
        self.claims: list[tuple[str, str, str | None]] = []

    async def claim_sandbox_id(
        self,
        session_id: str,
        candidate_id: str,
        *,
        expected_sandbox_id: str | None,
    ) -> str:
        self.claims.append((session_id, candidate_id, expected_sandbox_id))
        if self.deleted:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        if self.sandbox_id != expected_sandbox_id:
            if self.sandbox_id is None:
                raise RuntimeError("Sandbox runtime handle changed unexpectedly")
            return self.sandbox_id
        self.sandbox_id = candidate_id
        return candidate_id


class FakeUow:
    def __init__(self, repository: RecordingSessionRepository) -> None:
        self.session = repository

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class RecordingBrowser:
    def __init__(self) -> None:
        self.navigate_calls: list[str] = []

    async def navigate(self, url: str) -> str:
        self.navigate_calls.append(url)
        return f"visited:{url}"


class RecordingSandbox:
    def __init__(self, sandbox_id: str) -> None:
        self.id = sandbox_id
        self.cdp_url = f"http://{sandbox_id}/cdp"
        self.vnc_url = f"ws://{sandbox_id}/vnc"
        self.browser = RecordingBrowser()
        self.browser_calls = 0
        self.destroy_calls = 0
        self.ensure_calls = 0
        self.exec_calls: list[tuple[str, str, str]] = []

    async def get_browser(self) -> RecordingBrowser:
        self.browser_calls += 1
        return self.browser

    async def destroy(self) -> bool:
        self.destroy_calls += 1
        return True

    async def ensure_sandbox(self) -> None:
        self.ensure_calls += 1

    async def exec_command(
        self,
        session_id: str,
        exec_dir: str,
        command: str,
    ) -> str:
        self.exec_calls.append((session_id, exec_dir, command))
        return "executed"


class RecordingSandboxClass:
    create_calls = 0
    get_calls: list[str] = []
    existing: dict[str, RecordingSandbox] = {}
    create_results: deque[RecordingSandbox | BaseException] = deque()
    create_started: asyncio.Event | None = None
    allow_create: asyncio.Event | None = None

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = 0
        cls.get_calls = []
        cls.existing = {}
        cls.create_results = deque()
        cls.create_started = None
        cls.allow_create = None

    @classmethod
    async def create(cls) -> RecordingSandbox:
        cls.create_calls += 1
        if cls.create_started is not None:
            cls.create_started.set()
        if cls.allow_create is not None:
            await cls.allow_create.wait()
        result = (
            cls.create_results.popleft()
            if cls.create_results
            else RecordingSandbox(f"sandbox-{cls.create_calls}")
        )
        if isinstance(result, BaseException):
            raise result
        return result

    @classmethod
    async def get(cls, sandbox_id: str) -> RecordingSandbox | None:
        cls.get_calls.append(sandbox_id)
        return cls.existing.get(sandbox_id)


def make_runtime(
    *,
    sandbox_id: str | None = None,
    repository: RecordingSessionRepository | None = None,
) -> tuple[LazySandboxRuntime, RecordingSessionRepository]:
    RecordingSandboxClass.reset()
    repository = repository or RecordingSessionRepository(sandbox_id=sandbox_id)
    runtime = LazySandboxRuntime(
        session_id="session-1",
        sandbox_id=sandbox_id,
        sandbox_cls=RecordingSandboxClass,
        uow_factory=lambda: FakeUow(repository),
    )
    return runtime, repository


def test_construction_and_proxy_properties_do_not_activate_sandbox() -> None:
    runtime, repository = make_runtime()

    assert runtime.is_activated is False
    assert RecordingSandboxClass.create_calls == 0
    assert repository.claims == []
    with pytest.raises(SandboxNotActivatedError):
        _ = runtime.sandbox.id
    with pytest.raises(SandboxNotActivatedError):
        _ = runtime.sandbox.vnc_url


def test_concurrent_first_access_creates_and_persists_only_one_sandbox() -> None:
    async def scenario() -> None:
        runtime, repository = make_runtime()
        RecordingSandboxClass.create_started = asyncio.Event()
        RecordingSandboxClass.allow_create = asyncio.Event()

        first = asyncio.create_task(runtime.get_sandbox())
        await RecordingSandboxClass.create_started.wait()
        second = asyncio.create_task(runtime.get_sandbox())
        RecordingSandboxClass.allow_create.set()

        first_result, second_result = await asyncio.gather(first, second)

        assert first_result is second_result
        assert RecordingSandboxClass.create_calls == 1
        assert repository.claims == [
            ("session-1", first_result.id, None),
        ]
        assert runtime.sandbox.id == first_result.id

    asyncio.run(scenario())


def test_existing_handle_is_restored_without_creating_a_new_sandbox() -> None:
    async def scenario() -> None:
        runtime, repository = make_runtime(sandbox_id="sandbox-existing")
        existing = RecordingSandbox("sandbox-existing")
        RecordingSandboxClass.existing[existing.id] = existing

        result = await runtime.get_sandbox()

        assert result is existing
        assert RecordingSandboxClass.get_calls == ["sandbox-existing"]
        assert RecordingSandboxClass.create_calls == 0
        assert repository.claims == []

    asyncio.run(scenario())


def test_missing_persisted_sandbox_is_replaced_atomically() -> None:
    async def scenario() -> None:
        runtime, repository = make_runtime(sandbox_id="sandbox-expired")
        created = RecordingSandbox("sandbox-replacement")
        RecordingSandboxClass.create_results.append(created)

        result = await runtime.get_sandbox()

        assert result is created
        assert RecordingSandboxClass.get_calls == ["sandbox-expired"]
        assert repository.claims == [
            ("session-1", "sandbox-replacement", "sandbox-expired"),
        ]
        assert repository.sandbox_id == "sandbox-replacement"

    asyncio.run(scenario())


def test_concurrent_database_winner_is_reused_and_loser_is_destroyed() -> None:
    async def scenario() -> None:
        repository = RecordingSessionRepository(sandbox_id="sandbox-winner")
        runtime, _ = make_runtime(repository=repository)
        loser = RecordingSandbox("sandbox-loser")
        winner = RecordingSandbox("sandbox-winner")
        RecordingSandboxClass.create_results.append(loser)
        RecordingSandboxClass.existing[winner.id] = winner

        result = await runtime.get_sandbox()

        assert result is winner
        assert loser.destroy_calls == 1
        assert RecordingSandboxClass.get_calls == ["sandbox-winner"]
        assert repository.claims == [
            ("session-1", "sandbox-loser", None),
        ]

    asyncio.run(scenario())


def test_failed_create_is_not_cached_and_later_access_can_retry() -> None:
    async def scenario() -> None:
        runtime, repository = make_runtime()
        recovered = RecordingSandbox("sandbox-retry")
        RecordingSandboxClass.create_results.extend(
            [RuntimeError("create failed"), recovered]
        )

        with pytest.raises(RuntimeError, match="create failed"):
            await runtime.get_sandbox()

        assert runtime.is_activated is False
        assert repository.claims == []
        assert await runtime.get_sandbox() is recovered
        assert RecordingSandboxClass.create_calls == 2

    asyncio.run(scenario())


def test_created_sandbox_is_destroyed_when_session_was_deleted() -> None:
    async def scenario() -> None:
        repository = RecordingSessionRepository(deleted=True)
        runtime, _ = make_runtime(repository=repository)
        created = RecordingSandbox("sandbox-orphan")
        RecordingSandboxClass.create_results.append(created)

        with pytest.raises(ValueError, match="不存在"):
            await runtime.get_sandbox()

        assert created.destroy_calls == 1
        assert runtime.is_activated is False

    asyncio.run(scenario())


def test_browser_proxy_activates_once_on_first_browser_method() -> None:
    async def scenario() -> None:
        runtime, _ = make_runtime()

        result = await runtime.browser.navigate("https://example.com")
        second_result = await runtime.browser.navigate("https://example.org")
        sandbox = await runtime.get_sandbox()

        assert result == "visited:https://example.com"
        assert second_result == "visited:https://example.org"
        assert RecordingSandboxClass.create_calls == 1
        assert sandbox.browser_calls == 1
        assert sandbox.browser.navigate_calls == [
            "https://example.com",
            "https://example.org",
        ]

    asyncio.run(scenario())


def test_sandbox_proxy_delegates_async_methods_after_activation() -> None:
    async def scenario() -> None:
        runtime, _ = make_runtime()

        result = await runtime.sandbox.exec_command("shell-1", "/tmp", "pwd")
        sandbox = await runtime.get_sandbox()

        assert result == "executed"
        assert sandbox.exec_calls == [("shell-1", "/tmp", "pwd")]

    asyncio.run(scenario())


def test_destroy_before_activation_is_a_noop() -> None:
    async def scenario() -> None:
        runtime, _ = make_runtime()

        assert await runtime.destroy() is True
        assert RecordingSandboxClass.create_calls == 0

    asyncio.run(scenario())


def test_destroy_after_activation_delegates_once() -> None:
    async def scenario() -> None:
        runtime, _ = make_runtime()
        sandbox = await runtime.get_sandbox()

        assert await runtime.destroy() is True
        assert sandbox.destroy_calls == 1
        assert runtime.is_activated is False
        assert await runtime.destroy() is True
        assert sandbox.destroy_calls == 1

    asyncio.run(scenario())

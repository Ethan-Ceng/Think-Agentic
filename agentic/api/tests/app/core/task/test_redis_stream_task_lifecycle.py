from __future__ import annotations

import asyncio

import pytest

from app.core.task.redis_stream_task import RedisStreamTask
from app.core.task.base import RunCancellationReason


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Runner:
    def __init__(self) -> None:
        self.destroy_calls = 0

    async def destroy(self) -> None:
        self.destroy_calls += 1


class RegisteredTask:
    def __init__(self, task_id: str, runner: Runner) -> None:
        self.id = task_id
        self._task_runner = runner
        self.cancel_calls = 0

    def cancel(
        self,
        *,
        reason: RunCancellationReason = RunCancellationReason.USER,
        requested_by: str = "user",
    ) -> bool:
        self.cancel_calls += 1
        self.cancel_reason = reason
        self.requested_by = requested_by
        RedisStreamTask._task_registry.pop(self.id, None)
        return True


async def test_shutdown_destroys_all_registered_runners_while_cancel_mutates_registry() -> None:
    runners = [Runner(), Runner()]
    tasks = [
        RegisteredTask("task-1", runners[0]),
        RegisteredTask("task-2", runners[1]),
    ]
    RedisStreamTask._task_registry = {
        task.id: task
        for task in tasks
    }

    try:
        await RedisStreamTask.destroy()
    finally:
        RedisStreamTask._task_registry.clear()

    assert [task.cancel_calls for task in tasks] == [1, 1]
    assert [task.cancel_reason for task in tasks] == [
        RunCancellationReason.SHUTDOWN,
        RunCancellationReason.SHUTDOWN,
    ]
    assert [task.requested_by for task in tasks] == ["application", "application"]
    assert [runner.destroy_calls for runner in runners] == [1, 1]
    assert RedisStreamTask._task_registry == {}


async def test_shutdown_waits_for_execution_finally_before_destroying_runner() -> None:
    class LifecycleRunner:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.execution_exited = False
            self.destroy_observed_exit = False

        async def invoke(self, task) -> None:
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.execution_exited = True

        async def destroy(self) -> None:
            self.destroy_observed_exit = self.execution_exited

        async def on_done(self, task) -> None:
            pass

    runner = LifecycleRunner()
    task = RedisStreamTask(runner)
    await task.invoke()
    await runner.started.wait()

    try:
        await RedisStreamTask.destroy()
    finally:
        RedisStreamTask._task_registry.clear()

    assert task.done is True
    assert runner.destroy_observed_exit is True


async def test_shutdown_continues_when_one_runner_cleanup_fails() -> None:
    class FailingRunner(Runner):
        async def destroy(self) -> None:
            await super().destroy()
            raise RuntimeError("cleanup failed")

    failing = FailingRunner()
    healthy = Runner()
    tasks = [
        RegisteredTask("task-failing", failing),
        RegisteredTask("task-healthy", healthy),
    ]
    RedisStreamTask._task_registry = {task.id: task for task in tasks}

    try:
        await RedisStreamTask.destroy()
    finally:
        RedisStreamTask._task_registry.clear()

    assert failing.destroy_calls == 1
    assert healthy.destroy_calls == 1
    assert RedisStreamTask._task_registry == {}

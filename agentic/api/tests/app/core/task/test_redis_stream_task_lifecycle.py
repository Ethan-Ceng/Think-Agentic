from __future__ import annotations

import pytest

from app.core.task.redis_stream_task import RedisStreamTask


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

    def cancel(self) -> bool:
        self.cancel_calls += 1
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
    assert [runner.destroy_calls for runner in runners] == [1, 1]
    assert RedisStreamTask._task_registry == {}

from __future__ import annotations

import pytest

from app.main import _shutdown_resources


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_shutdown_resources_continues_after_cleanup_failure() -> None:
    calls: list[str] = []

    async def failing() -> None:
        calls.append("failing")
        raise RuntimeError("cleanup failed")

    async def healthy() -> None:
        calls.append("healthy")

    await _shutdown_resources(
        (
            ("failing resource", failing),
            ("healthy resource", healthy),
        )
    )

    assert calls == ["failing", "healthy"]

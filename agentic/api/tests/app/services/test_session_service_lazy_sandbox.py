from __future__ import annotations

import pytest

from app.core.entities.session import Session, SessionStatus
from app.core.sandbox.runtime import LazySandboxRuntime
from app.schemas.exceptions import NotFoundError
from app.services.session_service import SessionService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class SessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.claims: list[tuple[str, str, str | None]] = []

    async def get_by_id_for_user(
        self,
        session_id: str,
        user_id: str,
    ) -> Session | None:
        if self.session.id == session_id and self.session.user_id == user_id:
            return self.session
        return None

    async def claim_sandbox_id(
        self,
        session_id: str,
        candidate_id: str,
        *,
        expected_sandbox_id: str | None,
    ) -> str:
        self.claims.append((session_id, candidate_id, expected_sandbox_id))
        if self.session.sandbox_id != expected_sandbox_id:
            if self.session.sandbox_id is None:
                raise RuntimeError("sandbox handle changed unexpectedly")
            return self.session.sandbox_id
        self.session.sandbox_id = candidate_id
        return candidate_id


class Uow:
    def __init__(self, repository: SessionRepository) -> None:
        self.session = repository

    async def __aenter__(self) -> "Uow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class Browser:
    async def navigate(self, url: str) -> str:
        return url


class Sandbox:
    def __init__(self, sandbox_id: str) -> None:
        self.id = sandbox_id
        self.vnc_url = f"ws://{sandbox_id}/vnc"
        self.cdp_url = f"http://{sandbox_id}/cdp"
        self.browser = Browser()

    async def ensure_sandbox(self) -> None:
        return None

    async def get_browser(self) -> Browser:
        return self.browser

    async def destroy(self) -> bool:
        return True


class SandboxClass:
    create_calls = 0
    get_calls: list[str] = []
    existing: dict[str, Sandbox] = {}

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = 0
        cls.get_calls = []
        cls.existing = {}

    @classmethod
    async def create(cls) -> Sandbox:
        cls.create_calls += 1
        sandbox = Sandbox(f"sandbox-{cls.create_calls}")
        cls.existing[sandbox.id] = sandbox
        return sandbox

    @classmethod
    async def get(cls, sandbox_id: str) -> Sandbox | None:
        cls.get_calls.append(sandbox_id)
        return cls.existing.get(sandbox_id)


async def test_running_session_without_sandbox_returns_stable_vnc_error_without_activation() -> None:
    SandboxClass.reset()
    session = Session(
        id="session-1",
        user_id="user-1",
        status=SessionStatus.RUNNING,
    )
    repository = SessionRepository(session)
    service = SessionService(
        lambda: Uow(repository),
        sandbox_cls=SandboxClass,
    )

    with pytest.raises(NotFoundError) as exc_info:
        await service.get_vnc_url(session.id, session.user_id)

    assert exc_info.value.msg == "当前会话无沙箱环境"
    assert SandboxClass.create_calls == 0
    assert SandboxClass.get_calls == []
    assert session.sandbox_id is None


async def test_browser_activation_persists_handle_and_makes_vnc_available() -> None:
    SandboxClass.reset()
    session = Session(id="session-1", user_id="user-1")
    repository = SessionRepository(session)

    def uow_factory() -> Uow:
        return Uow(repository)

    runtime = LazySandboxRuntime(
        session_id=session.id,
        sandbox_id=None,
        sandbox_cls=SandboxClass,
        uow_factory=uow_factory,
    )
    service = SessionService(uow_factory, sandbox_cls=SandboxClass)

    await runtime.browser.navigate("https://example.com")
    vnc_url = await service.get_vnc_url(session.id, session.user_id)

    assert vnc_url == "ws://sandbox-1/vnc"
    assert SandboxClass.create_calls == 1
    assert SandboxClass.get_calls == ["sandbox-1"]
    assert repository.claims == [
        ("session-1", "sandbox-1", None),
    ]

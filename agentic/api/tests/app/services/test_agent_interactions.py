from datetime import datetime

import pytest

from app.core.entities.event import (
    InteractionDecision,
    InteractionEvent,
    InteractionOption,
    InteractionStatus,
    InteractionType,
)
from app.core.entities.session import (
    InteractionConflictError,
    InteractionNotFoundError,
    InteractionValidationError,
    Session,
    SessionStatus,
)
from app.schemas.exceptions import ConflictError, NotFoundError
from app.services.agent_service import AgentService


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def pending_question() -> InteractionEvent:
    return InteractionEvent(
        action_id="action-1",
        interaction_type=InteractionType.ASK_USER,
        tool_call_id="call-1",
        tool_name="message",
        function_name="message_ask_user",
        function_args={"text": "Choose", "allow_text": False},
        prompt="Choose",
        options=[
            InteractionOption(value="staging", label="Staging"),
            InteractionOption(value="production", label="Production"),
        ],
        allow_text=False,
    )


def test_session_resolves_latest_interaction_once_and_keeps_append_only_history() -> None:
    pending = pending_question()
    session = Session(
        id="session-1",
        user_id="user-1",
        status=SessionStatus.WAITING,
        events=[pending],
    )

    resolved = session.resolve_interaction(
        action_id=pending.action_id,
        decision=InteractionDecision.ANSWER,
        selected_values=["staging"],
    )

    assert session.events == [pending, resolved]
    assert resolved.status == InteractionStatus.RESOLVED
    assert resolved.selected_values == ["staging"]
    with pytest.raises(InteractionConflictError):
        session.resolve_interaction(
            action_id=pending.action_id,
            decision=InteractionDecision.ANSWER,
            selected_values=["staging"],
        )


def test_session_rejects_unknown_or_invalid_question_answers() -> None:
    for selected_values, answer in [(["unknown"], None), ([], "free text")]:
        session = Session(
            status=SessionStatus.WAITING,
            events=[pending_question()],
        )
        with pytest.raises(InteractionValidationError):
            session.resolve_interaction(
                action_id="action-1",
                decision=InteractionDecision.ANSWER,
                answer=answer,
                selected_values=selected_values,
            )


class FakeSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def resolve_interaction(self, session_id, user_id, **kwargs):
        if session_id != self.session.id or user_id != self.session.user_id:
            raise InteractionNotFoundError("session or interaction not found")
        return self.session.resolve_interaction(**kwargs)


class FakeUow:
    def __init__(self, repository: FakeSessionRepository) -> None:
        self.session = repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


def make_service(session: Session) -> AgentService:
    uow = FakeUow(FakeSessionRepository(session))
    return AgentService(
        uow_factory=lambda: uow,
        user_config_service=object(),
        llm_factory=lambda *_: object(),
        sandbox_cls=object(),
        task_cls=object(),
        json_parser=object(),
        search_engine=object(),
        file_storage=object(),
    )


async def test_service_returns_server_owned_resolution_and_hides_cross_user_actions() -> None:
    pending = pending_question()
    session = Session(
        id="session-1",
        user_id="user-1",
        status=SessionStatus.WAITING,
        events=[pending],
    )
    service = make_service(session)

    resolved, payload = await service.resolve_interaction(
        session_id=session.id,
        user_id=session.user_id,
        action_id=pending.action_id,
        decision=InteractionDecision.ANSWER,
        selected_values=["production"],
    )

    assert resolved.status == InteractionStatus.RESOLVED
    assert payload.tool_call_id == pending.tool_call_id
    assert payload.function_name == pending.function_name
    assert payload.function_args == pending.function_args

    hidden_service = make_service(Session(
        id="session-2",
        user_id="owner",
        status=SessionStatus.WAITING,
        events=[pending_question()],
    ))
    with pytest.raises(NotFoundError):
        await hidden_service.resolve_interaction(
            session_id="session-2",
            user_id="attacker",
            action_id="action-1",
            decision=InteractionDecision.ANSWER,
            selected_values=["staging"],
        )


async def test_service_maps_duplicate_resolution_to_conflict() -> None:
    pending = pending_question()
    session = Session(
        id="session-1",
        user_id="user-1",
        status=SessionStatus.WAITING,
        events=[pending],
    )
    service = make_service(session)
    await service.resolve_interaction(
        session_id=session.id,
        user_id=session.user_id,
        action_id=pending.action_id,
        decision=InteractionDecision.ANSWER,
        selected_values=["staging"],
    )

    with pytest.raises(ConflictError):
        await service.resolve_interaction(
            session_id=session.id,
            user_id=session.user_id,
            action_id=pending.action_id,
            decision=InteractionDecision.ANSWER,
            selected_values=["staging"],
        )

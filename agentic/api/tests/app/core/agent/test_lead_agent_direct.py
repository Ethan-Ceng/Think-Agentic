from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from app.core.agent.lead import LeadAgent
from app.core.entities.event import BaseEvent, DoneEvent, MessageEvent, TitleEvent
from app.core.entities.lead import DirectDecision, ReactDecision
from app.core.entities.message import Message
from app.core.entities.session import SessionStatus
from app.services.skill_runtime_service import SkillRuntimeContext


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeSession:
    def __init__(self, status: SessionStatus = SessionStatus.PENDING) -> None:
        self.status = status


class FakeSessionRepository:
    def __init__(self, session: FakeSession | None = None) -> None:
        self.session = session or FakeSession()
        self.statuses: list[SessionStatus] = []

    async def get_by_id(self, session_id: str) -> FakeSession | None:
        return self.session

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        self.session.status = status
        self.statuses.append(status)


class FakeUow:
    def __init__(self, session: FakeSessionRepository) -> None:
        self.session = session

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class FakeDecisionPolicy:
    def __init__(self, decision) -> None:
        self.decision = decision
        self.decide_calls = 0
        self.rollback_calls = 0
        self.skill_contexts: list[SkillRuntimeContext] = []

    async def decide(self, message: Message):
        self.decide_calls += 1
        return self.decision

    async def roll_back(self, message: Message) -> None:
        self.rollback_calls += 1

    def set_skill_runtime_context(self, context: SkillRuntimeContext) -> None:
        self.skill_contexts.append(context)


class FakeLegacyFlow:
    def __init__(self) -> None:
        self.invoke_calls = 0
        self.rollback_calls = 0
        self.skill_contexts: list[SkillRuntimeContext] = []
        self.refreshed = False

    async def invoke(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        self.invoke_calls += 1
        yield MessageEvent(message="legacy")
        yield DoneEvent()

    async def roll_back(self, message: Message) -> None:
        self.rollback_calls += 1

    def set_skill_runtime_context(self, context: SkillRuntimeContext) -> None:
        self.skill_contexts.append(context)

    def get_available_tool_names(self) -> set[str]:
        return {"search"}

    def refresh_mcp_tools(self) -> None:
        self.refreshed = True

    @property
    def done(self) -> bool:
        return True


class FakeLeadTrace:
    def __init__(self) -> None:
        self.decisions: list[dict] = []
        self.completions: list[dict] = []
        self.fallbacks: list[dict] = []

    async def record_lead_decision(self, **kwargs) -> None:
        self.decisions.append(kwargs)

    async def record_lead_completion(self, **kwargs) -> None:
        self.completions.append(kwargs)

    async def record_lead_fallback(self, **kwargs) -> None:
        self.fallbacks.append(kwargs)


def make_lead(
    decision,
    *,
    enabled: bool = True,
    status: SessionStatus = SessionStatus.PENDING,
    trace_service=None,
) -> tuple[LeadAgent, FakeDecisionPolicy, FakeLegacyFlow, FakeSessionRepository]:
    repository = FakeSessionRepository(FakeSession(status))
    policy = FakeDecisionPolicy(decision)
    legacy = FakeLegacyFlow()
    lead = LeadAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        enabled=enabled,
        legacy_flow=legacy,
        decision_policy=policy,
        trace_service=trace_service,
    )
    return lead, policy, legacy, repository


async def collect(lead: LeadAgent, message: Message) -> list[BaseEvent]:
    return [event async for event in lead.invoke(message)]


async def test_direct_emits_final_answer_without_legacy_or_plan_events() -> None:
    lead, policy, legacy, repository = make_lead(
        DirectDecision(
            title="Greeting",
            language="en",
            answer="Hello!",
        )
    )

    events = await collect(lead, Message(message="Say hello"))

    assert [type(event) for event in events] == [TitleEvent, MessageEvent, DoneEvent]
    assert events[1].message == "Hello!"
    assert policy.decide_calls == 1
    assert legacy.invoke_calls == 0
    assert repository.statuses == [SessionStatus.RUNNING]


async def test_disabled_lead_delegates_to_legacy_without_deciding() -> None:
    lead, policy, legacy, _ = make_lead(
        DirectDecision(title="Greeting", language="en", answer="Hello!"),
        enabled=False,
    )

    events = await collect(lead, Message(message="Say hello"))

    assert [event.type for event in events] == ["message", "done"]
    assert policy.decide_calls == 0
    assert legacy.invoke_calls == 1


async def test_unimplemented_strategy_temporarily_delegates_to_legacy() -> None:
    lead, policy, legacy, _ = make_lead(
        ReactDecision(
            title="Search",
            language="en",
            goal="Find it",
            capabilities=["search"],
        )
    )

    events = await collect(lead, Message(message="Find it"))

    assert [event.type for event in events] == ["message", "done"]
    assert policy.decide_calls == 1
    assert legacy.invoke_calls == 1


async def test_runtime_context_reaches_strategies_without_manual_mcp_refresh() -> None:
    lead, policy, legacy, _ = make_lead(
        DirectDecision(title="Greeting", language="en", answer="Hello!")
    )
    context = SkillRuntimeContext(prompt_block="temporary")

    lead.set_skill_runtime_context(context)
    assert policy.skill_contexts == [context]
    assert legacy.skill_contexts == [context]
    assert legacy.refreshed is False
    assert lead.get_available_tool_names() == {"search"}


async def test_direct_rolls_back_internal_memories_for_replacement_message() -> None:
    lead, policy, legacy, _ = make_lead(
        DirectDecision(title="Greeting", language="en", answer="Hello!"),
        status=SessionStatus.RUNNING,
    )

    await collect(lead, Message(message="Replace the current request"))

    assert policy.rollback_calls == 1
    assert legacy.rollback_calls == 1


async def test_direct_records_strategy_and_completion() -> None:
    trace = FakeLeadTrace()
    lead, _, _, _ = make_lead(
        DirectDecision(title="Greeting", language="en", answer="Hello!"),
        trace_service=trace,
    )

    await collect(lead, Message(message="Say hello"))

    assert trace.decisions[0]["mode"] == "direct"
    assert trace.decisions[0]["reason_code"] == "direct_selected"
    assert trace.decisions[0]["latency_ms"] >= 0
    assert trace.completions == [{"mode": "direct", "status": "completed"}]
    assert trace.fallbacks == []

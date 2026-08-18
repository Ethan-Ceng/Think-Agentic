from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest

from app.core.agent.lead import LeadAgent
from app.core.entities.event import (
    BaseEvent,
    InteractionDecision,
    InteractionEvent,
    InteractionResolution,
    InteractionType,
    MessageEvent,
    ToolEvent,
    ToolEventStatus,
    WaitEvent,
)
from app.core.entities.lead import ReactDecision
from app.core.entities.message import Message
from app.core.entities.session import SessionStatus
from app.core.entities.skill import SkillRef, SkillSource
from app.core.entities.tool_result import ToolResult


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeSession:
    def __init__(self, status: SessionStatus) -> None:
        self.status = status


class FakeSessionRepository:
    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.statuses: list[SessionStatus] = []

    async def get_by_id(self, session_id: str) -> FakeSession:
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
    def __init__(self, decision: ReactDecision) -> None:
        self.decision = decision
        self.decide_calls = 0

    async def decide(self, message: Message) -> ReactDecision:
        self.decide_calls += 1
        return self.decision

    def set_skill_runtime_context(self, context) -> None:
        return None


class FakeLegacyFlow:
    async def invoke(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        yield MessageEvent(message="legacy")

    def set_skill_runtime_context(self, context) -> None:
        return None

    def get_available_tool_names(self) -> set[str]:
        return {"search"}

    def refresh_mcp_tools(self) -> None:
        return None

    @property
    def done(self) -> bool:
        return True


class FakeReactAgent:
    def __init__(self, events: list[BaseEvent]) -> None:
        self.events = events
        self.execute_calls: list[tuple] = []
        self.resume_calls: list[InteractionResolution] = []

    async def execute_goal(
        self,
        goal: str,
        language: str,
        capabilities: list[str],
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        self.execute_calls.append((goal, language, capabilities, message))
        for event in self.events:
            yield event

    async def resume_goal(
        self,
        resolution: InteractionResolution,
    ) -> AsyncGenerator[BaseEvent, None]:
        self.resume_calls.append(resolution)
        for event in self.events:
            yield event


def make_react_lead(
    events: list[BaseEvent],
    *,
    session_status: SessionStatus = SessionStatus.PENDING,
    enabled: bool = True,
) -> tuple[
    LeadAgent,
    FakeDecisionPolicy,
    FakeReactAgent,
    FakeSessionRepository,
]:
    decision = ReactDecision(
        title="Research",
        language="en",
        goal="Find the primary source",
        capabilities=["search"],
    )
    policy = FakeDecisionPolicy(decision)
    legacy = FakeLegacyFlow()
    react = FakeReactAgent(events)
    repository = FakeSessionRepository(FakeSession(session_status))
    lead = LeadAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        enabled=enabled,
        legacy_flow=legacy,
        decision_policy=policy,
        react_agent=react,
    )
    return lead, policy, react, repository


async def collect(lead: LeadAgent, message: Message) -> list[BaseEvent]:
    return [event async for event in lead.invoke(message)]


async def test_react_runs_goal_without_plan_or_step_events() -> None:
    tool_event = ToolEvent(
        tool_call_id="call-1",
        tool_name="search",
        function_name="search_web",
        function_args={"query": "source"},
        function_result=ToolResult(success=True),
        status=ToolEventStatus.CALLED,
    )
    lead, policy, react, repository = make_react_lead(
        [tool_event, MessageEvent(message="Found it")]
    )

    events = await collect(lead, Message(message="Find the primary source"))

    assert [event.type for event in events] == ["title", "tool", "message", "done"]
    assert policy.decide_calls == 1
    assert len(react.execute_calls) == 1
    assert react.execute_calls[0][0:3] == (
        "Find the primary source",
        "en",
        ["search"],
    )
    assert repository.statuses == [SessionStatus.RUNNING]
    assert not any(event.type in {"plan", "step"} for event in events)


async def test_react_interaction_persists_strategy_context_and_waits() -> None:
    interaction = InteractionEvent(
        action_id="action-1",
        interaction_type=InteractionType.ASK_USER,
        tool_call_id="call-1",
        tool_name="message",
        function_name="message_ask_user",
        function_args={"text": "Which source should be used?"},
        prompt="Which source should be used?",
    )
    lead, _, _, _ = make_react_lead([interaction, WaitEvent()])
    skill_ref = SkillRef(
        source=SkillSource.PERSONAL,
        skill_id="skill-1",
        name="report-writer",
    )
    lead.set_skill_runtime_context(
        SimpleNamespace(selected=[SimpleNamespace(ref=skill_ref)])
    )

    events = await collect(lead, Message(message="Find it"))

    persisted = next(event for event in events if isinstance(event, InteractionEvent))
    assert persisted.lead_mode == "react"
    assert persisted.lead_goal == "Find the primary source"
    assert persisted.lead_language == "en"
    assert persisted.lead_capabilities == ["search"]
    assert persisted.skills == [skill_ref]
    assert isinstance(events[-1], WaitEvent)
    assert not any(event.type == "done" for event in events)


async def test_react_resume_skips_decision_and_continues_original_goal() -> None:
    lead, policy, react, repository = make_react_lead(
        [MessageEvent(message="Answered result")],
        session_status=SessionStatus.RUNNING,
    )
    resolution = InteractionResolution(
        action_id="action-1",
        interaction_type=InteractionType.ASK_USER,
        decision=InteractionDecision.ANSWER,
        tool_call_id="call-1",
        function_name="message_ask_user",
        function_args={"text": "Which source should be used?"},
        answer="Use the primary source",
        lead_mode="react",
        lead_goal="Find the primary source",
        lead_language="en",
        lead_capabilities=["search"],
    )

    events = await collect(
        lead,
        Message(message="Resolve interaction", interaction_response=resolution),
    )

    assert policy.decide_calls == 0
    assert react.resume_calls == [resolution]
    assert [event.type for event in events] == ["message", "done"]
    assert repository.statuses == []


async def test_inflight_react_resume_ignores_newly_disabled_feature_flag() -> None:
    lead, policy, react, _ = make_react_lead(
        [MessageEvent(message="Answered result")],
        session_status=SessionStatus.WAITING,
        enabled=False,
    )
    resolution = InteractionResolution(
        action_id="action-1",
        interaction_type=InteractionType.ASK_USER,
        decision=InteractionDecision.ANSWER,
        tool_call_id="call-1",
        function_name="message_ask_user",
        function_args={"text": "Which source should be used?"},
        answer="Use the primary source",
        lead_mode="react",
        lead_goal="Find the primary source",
        lead_language="en",
        lead_capabilities=["search"],
    )

    events = await collect(
        lead,
        Message(message="Resolve interaction", interaction_response=resolution),
    )

    assert policy.decide_calls == 0
    assert react.resume_calls == [resolution]
    assert [event.type for event in events] == ["message", "done"]

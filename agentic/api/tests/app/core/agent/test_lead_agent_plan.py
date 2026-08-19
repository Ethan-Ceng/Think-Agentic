from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from app.core.agent.lead import LeadAgent
from app.core.entities.event import (
    BaseEvent,
    InteractionDecision,
    InteractionEvent,
    InteractionResolution,
    InteractionType,
    MessageEvent,
    PlanEvent,
    PlanEventStatus,
    StepEvent,
    StepEventStatus,
    WaitEvent,
)
from app.core.entities.lead import PlanDecision
from app.core.entities.message import Message
from app.core.entities.plan import ExecutionStatus, Plan, Step
from app.core.entities.session import SessionStatus


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeSession:
    def __init__(self) -> None:
        self.status = SessionStatus.PENDING
        self.latest_plan: Plan | None = None

    def get_latest_plan(self) -> Plan | None:
        return self.latest_plan


class FakeSessionRepository:
    def __init__(self) -> None:
        self.session = FakeSession()
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
    def __init__(self, decision: PlanDecision) -> None:
        self.decision = decision
        self.decide_calls = 0

    async def decide(self, message: Message) -> PlanDecision:
        self.decide_calls += 1
        return self.decision

    def set_skill_runtime_context(self, context) -> None:
        return None


class FakeLegacyFlow:
    async def invoke(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        raise AssertionError("Plan strategy must not delegate to legacy flow")
        yield

    def set_skill_runtime_context(self, context) -> None:
        return None

    def get_available_tool_names(self) -> set[str]:
        return {"search"}

    def refresh_mcp_tools(self) -> None:
        return None

    @property
    def done(self) -> bool:
        return True


class FakePlannerAgent:
    def __init__(self, replacement_steps: list[Step] | None = None) -> None:
        self.replacement_steps = replacement_steps
        self.update_calls: list[str] = []

    async def update_plan(
        self,
        plan: Plan,
        step: Step,
    ) -> AsyncGenerator[BaseEvent, None]:
        self.update_calls.append(step.id)
        current_index = next(
            index for index, current in enumerate(plan.steps) if current.id == step.id
        )
        plan.steps = plan.steps[: current_index + 1] + [
            replacement.model_copy(deep=True)
            for replacement in (self.replacement_steps or [])
        ]
        yield PlanEvent(plan=plan, status=PlanEventStatus.UPDATED)


class FakeReactAgent:
    def __init__(
        self,
        outcomes: dict[str, bool | str],
        *,
        resume_success: bool = True,
    ) -> None:
        self.outcomes = outcomes
        self.resume_success = resume_success
        self.execute_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.summarize_calls = 0
        self.compact_calls = 0

    async def execute_step(
        self,
        plan: Plan,
        step: Step,
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        self.execute_calls.append(step.id)
        step.status = ExecutionStatus.RUNNING
        yield StepEvent(step=step, status=StepEventStatus.STARTED)
        outcome = self.outcomes[step.id]
        if outcome == "wait":
            yield InteractionEvent(
                action_id="action-1",
                interaction_type=InteractionType.ASK_USER,
                tool_call_id="call-1",
                tool_name="message",
                function_name="message_ask_user",
                function_args={"text": "Which source should be used?"},
                prompt="Which source should be used?",
            )
            yield WaitEvent()
            return
        step.success = bool(outcome)
        step.result = "ok" if step.success else "failed"
        step.status = (
            ExecutionStatus.COMPLETED if step.success else ExecutionStatus.FAILED
        )
        yield StepEvent(
            step=step,
            status=(
                StepEventStatus.COMPLETED
                if step.success
                else StepEventStatus.FAILED
            ),
        )

    async def resume_step(
        self,
        plan: Plan,
        step: Step,
        resolution: InteractionResolution,
    ) -> AsyncGenerator[BaseEvent, None]:
        self.resume_calls.append(step.id)
        step.success = self.resume_success
        step.result = "resumed" if step.success else "resume failed"
        step.status = (
            ExecutionStatus.COMPLETED if step.success else ExecutionStatus.FAILED
        )
        yield StepEvent(
            step=step,
            status=(
                StepEventStatus.COMPLETED
                if step.success
                else StepEventStatus.FAILED
            ),
        )

    async def summarize(
        self,
        language: str | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        self.summarize_calls += 1
        yield MessageEvent(message="final summary")

    async def compact_memory(self) -> None:
        self.compact_calls += 1


def decision() -> PlanDecision:
    return PlanDecision(
        title="Complex task",
        language="en",
        goal="Complete the complex task",
        message="Starting the task.",
        steps=[
            Step(
                id="step-1",
                description="First",
                capabilities=["search"],
                provider_ids=["builtin.search"],
                tool_ids=["builtin.search.search_web"],
            ),
            Step(id="step-2", description="Second"),
        ],
    )


def make_lead(
    react: FakeReactAgent,
    planner: FakePlannerAgent,
) -> tuple[LeadAgent, FakeDecisionPolicy, FakeSessionRepository]:
    repository = FakeSessionRepository()
    policy = FakeDecisionPolicy(decision())
    lead = LeadAgent(
        uow_factory=lambda: FakeUow(repository),
        session_id="session-1",
        enabled=True,
        legacy_flow=FakeLegacyFlow(),
        decision_policy=policy,
        planner_agent=planner,
        react_agent=react,
    )
    return lead, policy, repository


async def collect(lead: LeadAgent, message: Message) -> list[BaseEvent]:
    return [event async for event in lead.invoke(message)]


async def test_successful_plan_does_not_call_model_replanner() -> None:
    react = FakeReactAgent({"step-1": True, "step-2": True})
    planner = FakePlannerAgent()
    lead, _, _ = make_lead(react, planner)

    events = await collect(lead, Message(message="Do the complex task"))

    assert planner.update_calls == []
    assert react.execute_calls == ["step-1", "step-2"]
    assert react.summarize_calls == 1
    assert len(
        [
            event
            for event in events
            if isinstance(event, PlanEvent)
            and event.status == PlanEventStatus.UPDATED
        ]
    ) == 2
    final_plan = next(
        event.plan
        for event in reversed(events)
        if isinstance(event, PlanEvent)
    )
    assert final_plan.status == ExecutionStatus.COMPLETED
    assert events[-1].type == "done"


async def test_failed_step_replans_once_and_executes_replacement() -> None:
    repair = Step(id="repair", description="Repair", capabilities=["search"])
    react = FakeReactAgent({"step-1": False, "repair": True})
    planner = FakePlannerAgent([repair])
    lead, _, _ = make_lead(react, planner)

    events = await collect(lead, Message(message="Do the complex task"))

    assert planner.update_calls == ["step-1"]
    assert react.execute_calls == ["step-1", "repair"]
    assert any(
        isinstance(event, StepEvent)
        and event.step.id == "step-1"
        and event.status == StepEventStatus.FAILED
        for event in events
    )
    final_plan = next(
        event.plan
        for event in reversed(events)
        if isinstance(event, PlanEvent)
    )
    assert final_plan.status == ExecutionStatus.COMPLETED


async def test_plan_interaction_resumes_exact_step_without_new_decision() -> None:
    react = FakeReactAgent({"step-1": "wait", "step-2": True})
    planner = FakePlannerAgent()
    lead, policy, repository = make_lead(react, planner)

    pending_events = await collect(lead, Message(message="Do the complex task"))
    pending = next(
        event for event in pending_events if isinstance(event, InteractionEvent)
    )
    created_plan = next(
        event.plan for event in pending_events if isinstance(event, PlanEvent)
    )
    repository.session.latest_plan = created_plan
    repository.session.status = SessionStatus.RUNNING

    assert pending.lead_mode == "plan"
    assert pending.plan_id == created_plan.id
    assert pending.step_id == "step-1"
    assert pending.lead_provider_ids == ["builtin.search"]
    assert pending.lead_tool_ids == ["builtin.search.search_web"]
    resolution = InteractionResolution(
        action_id=pending.action_id,
        interaction_type=pending.interaction_type,
        decision=InteractionDecision.ANSWER,
        tool_call_id=pending.tool_call_id,
        function_name=pending.function_name,
        function_args=pending.function_args,
        answer="Use the primary source",
        lead_mode=pending.lead_mode,
        lead_goal=pending.lead_goal,
        lead_language=pending.lead_language,
        lead_capabilities=pending.lead_capabilities,
        lead_provider_ids=pending.lead_provider_ids,
        lead_tool_ids=pending.lead_tool_ids,
        plan_id=pending.plan_id,
        step_id=pending.step_id,
    )

    resumed_events = await collect(
        lead,
        Message(message="Resolve interaction", interaction_response=resolution),
    )

    assert policy.decide_calls == 1
    assert react.resume_calls == ["step-1"]
    assert react.execute_calls == ["step-1", "step-2"]
    assert resumed_events[-1].type == "done"


async def test_plan_resume_preserves_replan_limit() -> None:
    react = FakeReactAgent({}, resume_success=False)
    planner = FakePlannerAgent([Step(id="unexpected", description="Do not add")])
    lead, _, repository = make_lead(react, planner)
    step = Step(
        id="repair",
        description="Last repair",
        status=ExecutionStatus.RUNNING,
    )
    plan = Plan(
        id="plan-1",
        title="Repair",
        goal="Repair the task",
        language="en",
        steps=[step],
        status=ExecutionStatus.RUNNING,
    )
    repository.session.latest_plan = plan
    repository.session.status = SessionStatus.WAITING
    resolution = InteractionResolution(
        action_id="action-2",
        interaction_type=InteractionType.ASK_USER,
        decision=InteractionDecision.ANSWER,
        tool_call_id="call-2",
        function_name="message_ask_user",
        function_args={"text": "Which repair path?"},
        answer="Use the safe repair path",
        lead_mode="plan",
        lead_goal=plan.goal,
        lead_language=plan.language,
        plan_id=plan.id,
        step_id=step.id,
        lead_replan_count=2,
    )

    events = await collect(
        lead,
        Message(message="Resolve interaction", interaction_response=resolution),
    )

    assert planner.update_calls == []
    final_plan = next(
        event.plan
        for event in reversed(events)
        if isinstance(event, PlanEvent)
    )
    assert final_plan.status == ExecutionStatus.FAILED

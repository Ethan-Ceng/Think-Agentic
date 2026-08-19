from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from app.core.entities.event import (
    BaseEvent,
    MessageEvent,
    PlanEvent,
    PlanEventStatus,
    StepEvent,
    StepEventStatus,
)
from app.core.entities.message import Message
from app.core.entities.plan import ExecutionStatus, Plan, Step
from app.core.entities.session import SessionStatus
from app.core.flows.base import FlowStatus
from app.core.flows.planner_react import PlannerReActFlow


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Session:
    status = SessionStatus.PENDING

    @staticmethod
    def get_latest_plan() -> None:
        return None


class SessionRepository:
    def __init__(self) -> None:
        self.session = Session()

    async def get_by_id(self, session_id: str) -> Session:
        return self.session

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        self.session.status = status


class Uow:
    def __init__(self) -> None:
        self.session = SessionRepository()

    async def __aenter__(self) -> "Uow":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        return None


class Planner:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.update_calls: list[str] = []

    async def create_plan(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        yield PlanEvent(plan=self.plan, status=PlanEventStatus.CREATED)

    async def update_plan(
        self,
        plan: Plan,
        step: Step,
    ) -> AsyncGenerator[BaseEvent, None]:
        self.update_calls.append(step.id)
        yield PlanEvent(plan=plan, status=PlanEventStatus.UPDATED)

    async def roll_back(self, message: Message) -> None:
        return None


class React:
    name = "ReAct"

    def __init__(self) -> None:
        self.execute_calls: list[str] = []

    async def execute_step(
        self,
        plan: Plan,
        step: Step,
        message: Message,
    ) -> AsyncGenerator[BaseEvent, None]:
        self.execute_calls.append(step.id)
        step.status = ExecutionStatus.RUNNING
        yield StepEvent(step=step, status=StepEventStatus.STARTED)
        step.status = ExecutionStatus.COMPLETED
        step.success = True
        step.result = f"{step.id} result"
        yield StepEvent(step=step, status=StepEventStatus.COMPLETED)

    async def compact_memory(self) -> None:
        return None

    async def summarize(self, language: str) -> AsyncGenerator[BaseEvent, None]:
        yield MessageEvent(message="final")

    async def roll_back(self, message: Message) -> None:
        return None


async def test_successful_legacy_plan_advances_without_model_replan() -> None:
    plan = Plan(
        title="Plan",
        goal="Run sequentially",
        language="en",
        message="Starting plan",
        steps=[
            Step(id="step-1", description="First"),
            Step(id="step-2", description="Second"),
        ],
    )
    flow = object.__new__(PlannerReActFlow)
    flow._uow = Uow()
    flow._session_id = "session-1"
    flow.status = FlowStatus.IDLE
    flow.plan = None
    flow.planner = Planner(plan)
    flow.react = React()

    events = [event async for event in flow.invoke(Message(message="Do it"))]

    assert flow.planner.update_calls == []
    assert flow.react.execute_calls == ["step-1", "step-2"]
    assert [
        event.status
        for event in events
        if isinstance(event, PlanEvent)
    ] == [
        PlanEventStatus.CREATED,
        PlanEventStatus.UPDATED,
        PlanEventStatus.UPDATED,
        PlanEventStatus.COMPLETED,
    ]
    plan_message = next(
        event
        for event in events
        if isinstance(event, MessageEvent) and event.message == "Starting plan"
    )
    assert plan_message.visible is False

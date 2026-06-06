import uuid

import pytest

from app.core.exceptions import FailException
from app.services.task_engine_service import TaskEngineService, TaskStatus


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.flushed = 0

    def add(self, model_instance) -> None:  # noqa: ANN001
        if getattr(model_instance, "id", None) is None:
            model_instance.id = uuid.uuid4()
        self.added.append(model_instance)

    def flush(self) -> None:
        self.flushed += 1

    def refresh(self, model_instance) -> None:  # noqa: ANN001
        return None


def test_task_lifecycle_transitions_and_versions() -> None:
    service = TaskEngineService()
    session = FakeSession()
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()

    task = service.create_task(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        user_input={"query": "summarize this"},
    )

    assert task.status == TaskStatus.CREATED
    assert task.version == 0
    assert task.user_input == {"query": "summarize this"}
    assert task.final_result == {}

    service.start_task(session, task)

    assert task.status == TaskStatus.RUNNING
    assert task.version == 1
    assert task.started_at is not None

    service.succeed_task(session, task, final_result={"answer": "done"})

    assert task.status == TaskStatus.SUCCEEDED
    assert task.version == 2
    assert task.final_result == {"answer": "done"}
    assert task.finished_at is not None

    with pytest.raises(FailException):
        service.start_task(session, task)


def test_task_can_wait_for_approval_and_resume() -> None:
    service = TaskEngineService()
    session = FakeSession()
    task = service.create_task(
        session,
        tenant_id=uuid.uuid4(),
        router_agent_id=uuid.uuid4(),
    )

    service.start_task(session, task)
    service.wait_for_approval(session, task)

    assert task.status == TaskStatus.WAITING
    assert task.error_code == "waiting_approval"
    assert task.version == 2

    service.resume_task(session, task)

    assert task.status == TaskStatus.RUNNING
    assert task.error_code == ""
    assert task.version == 3


def test_task_can_wait_for_user_and_resume() -> None:
    service = TaskEngineService()
    session = FakeSession()
    task = service.create_task(
        session,
        tenant_id=uuid.uuid4(),
        router_agent_id=uuid.uuid4(),
    )

    service.start_task(session, task)
    service.wait_for_user(
        session,
        task,
        final_result={"missing_info": ["city"]},
        error_message="需要用户提供城市",
    )

    assert task.status == TaskStatus.WAITING
    assert task.error_code == "waiting_user"
    assert task.error_message == "需要用户提供城市"
    assert task.final_result == {"missing_info": ["city"]}
    assert task.version == 2

    service.resume_task(session, task)

    assert task.status == TaskStatus.RUNNING
    assert task.error_code == ""
    assert task.error_message == ""
    assert task.version == 3


def test_plan_and_step_inherit_task_context() -> None:
    service = TaskEngineService()
    session = FakeSession()
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    task = service.create_task(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
    )
    plan = service.create_plan(
        session,
        task=task,
        plan_json={"steps": [{"key": "search"}]},
        risk_level="medium",
    )

    step = service.create_step(
        session,
        plan=plan,
        step_key="search",
        worker_agent_id=worker_agent_id,
        dependencies=["classify"],
        input_json={"query": "llmops"},
        timeout_seconds=30,
    )

    assert plan.tenant_id == tenant_id
    assert plan.task_id == task.id
    assert plan.router_agent_id == router_agent_id
    assert plan.risk_level == "medium"
    assert step.tenant_id == tenant_id
    assert step.task_id == task.id
    assert step.plan_id == plan.id
    assert step.dependencies == ["classify"]
    assert step.timeout_seconds == 30

    service.start_step(session, step)
    service.wait_step_for_user(session, step, output_json={"missing_info": ["city"]})

    assert step.status == TaskStatus.WAITING
    assert step.output_json == {"missing_info": ["city"]}

    service.resume_step(session, step)
    service.succeed_step(session, step, output_json={"result": "ok"})

    assert step.status == TaskStatus.SUCCEEDED
    assert step.output_json == {"result": "ok"}
    assert step.started_at is not None
    assert step.finished_at is not None


def test_worker_and_capability_calls_are_recorded_from_step() -> None:
    service = TaskEngineService()
    session = FakeSession()
    capability_id = uuid.uuid4()
    approval_id = uuid.uuid4()
    task = service.create_task(
        session,
        tenant_id=uuid.uuid4(),
        router_agent_id=uuid.uuid4(),
    )
    plan = service.create_plan(session, task=task, plan_json={"steps": []})
    step = service.create_step(
        session,
        plan=plan,
        step_key="tool-use",
        worker_agent_id=uuid.uuid4(),
    )

    worker_call = service.record_worker_call(
        session,
        step=step,
        invocation_json={"messages": [{"role": "user", "content": "run"}]},
    )
    service.start_worker_call(session, worker_call)
    service.complete_worker_call(
        session,
        worker_call,
        result_json={"content": "ok"},
        token_count=12,
        cost=0.001,
        latency=0.25,
    )

    assert worker_call.status == TaskStatus.SUCCEEDED
    assert worker_call.task_id == task.id
    assert worker_call.step_id == step.id
    assert worker_call.worker_agent_id == step.worker_agent_id
    assert worker_call.token_count == 12

    capability_call = service.record_capability_call(
        session,
        step=step,
        worker_call_id=worker_call.id,
        capability_id=capability_id,
        input_json={"location": "HK"},
        risk_level="high",
        approval_id=approval_id,
        idempotency_key="capability-1",
    )
    service.start_capability_call(session, capability_call)
    service.wait_capability_for_approval(session, capability_call, approval_id=approval_id)

    assert capability_call.status == TaskStatus.WAITING_APPROVAL

    service.resume_capability_call(session, capability_call)
    service.complete_capability_call(
        session,
        capability_call,
        output_json={"temperature": 28},
        latency=0.5,
    )

    assert capability_call.status == TaskStatus.SUCCEEDED
    assert capability_call.worker_call_id == worker_call.id
    assert capability_call.capability_id == capability_id
    assert capability_call.output_json == {"temperature": 28}
    assert capability_call.risk_level == "high"
    assert capability_call.approval_id == approval_id
    assert capability_call.idempotency_key == "capability-1"


def test_call_completion_rejects_non_terminal_status() -> None:
    service = TaskEngineService()
    session = FakeSession()
    task = service.create_task(
        session,
        tenant_id=uuid.uuid4(),
        router_agent_id=uuid.uuid4(),
    )
    plan = service.create_plan(session, task=task, plan_json={})
    step = service.create_step(
        session,
        plan=plan,
        step_key="worker",
        worker_agent_id=uuid.uuid4(),
    )
    worker_call = service.record_worker_call(session, step=step, invocation_json={})

    with pytest.raises(FailException):
        service.complete_worker_call(session, worker_call, status=TaskStatus.RUNNING)

import uuid
from types import SimpleNamespace

from app.core.agent import AgentThought, QueueEvent
from app.domain.agent_runtime.protocols import WorkerInvocation
from app.domain.agent_runtime.react_worker_agent import ReActWorkerAgent
from app.domain.agent_runtime.worker_runtime import WorkerRuntime
from app.models.account import Account
from app.models.agent import Agent


def test_worker_runtime_invokes_app_backed_react_worker_agent() -> None:
    app_id = uuid.uuid4()
    expected_conversation_id = uuid.uuid4()
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    worker = Agent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="Research Worker",
        runtime_type="worker",
        product_category="custom",
        status="published",
        target_ref_type="app",
        target_ref_id=str(app_id),
    )
    invocation = WorkerInvocation(
        trace_id="trace-1",
        tenant_id=worker.tenant_id,
        account_id=account.id,
        task_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        router_id=str(uuid.uuid4()),
        worker_id=str(worker.id),
        task={"task": "summarize sales notes"},
        context={"conversation_id": str(expected_conversation_id)},
    )

    class FakeAppService:
        def run_app_worker(  # noqa: ANN001
            self,
            session,
            *,
            app_id,
            task_id,
            query,
            image_urls,
            account,
            conversation_id,
        ):
            assert session == "db"
            assert app_id == uuid.UUID(worker.target_ref_id)
            assert task_id == invocation.task_id
            assert query == "summarize sales notes"
            assert image_urls == []
            assert account.id == invocation.account_id
            assert conversation_id == expected_conversation_id
            yield AgentThought(
                id=uuid.uuid4(),
                task_id=task_id,
                event=QueueEvent.AGENT_ACTION,
                observation="now",
                tool="current_time",
                tool_input={},
            )
            yield AgentThought(
                id=uuid.uuid4(),
                task_id=task_id,
                event=QueueEvent.AGENT_MESSAGE,
                thought="summary",
                answer="summary",
            )
            yield AgentThought(id=uuid.uuid4(), task_id=task_id, event=QueueEvent.AGENT_END)

    runtime = WorkerRuntime(react_worker_agent=ReActWorkerAgent(app_service=FakeAppService()))

    result = runtime.invoke(invocation, session="db", worker=worker, account=account)

    assert result.status == "succeeded"
    assert result.summary == "summary"
    assert result.data["answer"] == "summary"
    assert result.actions[0]["tool"] == "current_time"
    assert result.evidence[0]["observation"] == "now"
    assert result.used_capabilities == ["current_time"]
    assert [event.event_type for event in result.events] == ["agent_action", "agent_message", "agent_end"]


def test_worker_runtime_maps_executor_type_to_execution_agent_type() -> None:
    worker = Agent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="Worker",
        runtime_type="worker",
        product_category="custom",
        status="published",
        target_ref_type="app",
        target_ref_id=str(uuid.uuid4()),
    )

    assert (
        WorkerRuntime._execution_agent_type(
            worker,
            SimpleNamespace(worker_config={"executor_type": "app"}),
        )
        == "react_worker"
    )
    assert (
        WorkerRuntime._execution_agent_type(
            worker,
            SimpleNamespace(worker_config={"executor_type": "a2a"}),
        )
        == "a2a_worker"
    )

    a2a_worker = Agent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="External Worker",
        runtime_type="worker",
        product_category="a2a",
        status="published",
        target_ref_type="a2a_agent",
        target_ref_id=str(uuid.uuid4()),
    )
    assert WorkerRuntime._execution_agent_type(a2a_worker, None) == "a2a_worker"

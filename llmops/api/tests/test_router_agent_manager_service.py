import uuid
from types import SimpleNamespace

import pytest

from app.core.agent import AgentThought, QueueEvent
from app.core.exceptions import FailException
from app.core.language_model.entities import BaseLanguageModel
from app.domain.agent_runtime.planner import PlannerResult
from app.domain.agent_runtime.protocols import ArtifactRef, RouterPlan, RouterPlanStep, WorkerResult
from app.domain.agent_runtime.router_runtime import RouterRuntime
from app.models.account import Account
from app.models.agent import Agent
from app.models.task import WorkerCall
from app.models.trace import TraceEvent
from app.services.router_agent_manager_service import RouterAgentManagerService
from app.services.task_engine_service import TaskStatus


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


def test_router_runtime_rejects_duplicate_steps_and_unknown_dependencies() -> None:
    worker_id = str(uuid.uuid4())
    runtime = RouterRuntime()

    with pytest.raises(FailException):
        runtime.validate_plan(
            RouterPlan(
                router_id=str(uuid.uuid4()),
                user_intent="test",
                steps=[
                    RouterPlanStep(step_id="same", worker_id=worker_id, task="one"),
                    RouterPlanStep(step_id="same", worker_id=worker_id, task="two"),
                ],
            )
        )

    with pytest.raises(FailException):
        runtime.validate_plan(
            RouterPlan(
                router_id=str(uuid.uuid4()),
                user_intent="test",
                steps=[RouterPlanStep(step_id="step_1", worker_id=worker_id, task="one", dependencies=["missing"])],
            )
        )


def test_manager_plan_selects_bound_workers_and_validates_worker_scope() -> None:
    tenant_id = uuid.uuid4()
    router = Agent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Router",
        runtime_type="router",
        product_category="router",
        status="published",
    )
    first_worker = Agent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Research",
        runtime_type="worker",
        product_category="custom",
        status="published",
    )
    second_worker = Agent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Writer",
        runtime_type="worker",
        product_category="custom",
        status="published",
    )

    plan = RouterAgentManagerService().build_manager_plan(
        router_agent=router,
        workers=[first_worker, second_worker],
        user_input={"query": "prepare a launch brief"},
        requested_worker_ids=[second_worker.id],
    )

    assert plan.router_id == str(router.id)
    assert plan.user_intent == "prepare a launch brief"
    assert len(plan.steps) == 1
    assert plan.steps[0].worker_id == str(second_worker.id)
    assert plan.steps[0].task == "prepare a launch brief"


def test_create_manager_task_from_plan_persists_task_plan_and_steps() -> None:
    service = RouterAgentManagerService()
    session = FakeSession()
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    plan = RouterPlan(
        router_id=str(router_agent_id),
        user_intent="summarize sales notes",
        risk_assessment={"risk_level": "medium"},
        steps=[
            RouterPlanStep(
                step_id="summarize",
                worker_id=str(worker_agent_id),
                task="summarize sales notes",
                execution_mode="sync",
            )
        ],
    )

    result = service.create_manager_task_from_plan(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        plan=plan,
        user_input={"query": "summarize sales notes"},
        user_id=uuid.uuid4(),
    )

    assert result.task.status == TaskStatus.RUNNING
    assert result.task.version == 1
    assert result.plan.task_id == result.task.id
    assert result.plan.risk_level == "medium"
    assert len(result.steps) == 1
    assert result.steps[0].step_key == "summarize"
    assert result.steps[0].worker_agent_id == worker_agent_id
    assert result.steps[0].input_json["user_input"] == {"query": "summarize sales notes"}
    trace_events = [item for item in session.added if isinstance(item, TraceEvent)]
    assert [event.event_type for event in trace_events] == ["router.manager_run.created"]
    assert trace_events[0].trace_id == result.trace_id


def test_create_manager_task_waits_when_plan_requires_approval() -> None:
    service = RouterAgentManagerService()
    session = FakeSession()
    plan = RouterPlan(
        router_id=str(uuid.uuid4()),
        user_intent="export customer data",
        steps=[
            RouterPlanStep(
                step_id="export",
                worker_id=str(uuid.uuid4()),
                task="export customer data",
                required_approval=True,
            )
        ],
    )

    result = service.create_manager_task_from_plan(
        session,
        tenant_id=uuid.uuid4(),
        router_agent_id=uuid.uuid4(),
        plan=plan,
        user_input={"query": "export customer data"},
    )

    assert result.task.status == TaskStatus.WAITING_APPROVAL
    assert result.task.version == 2


def test_stream_planner_debug_run_stops_before_plan_generation() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    planner_app_id = uuid.uuid4()
    planner_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    session = FakeSession()

    class FakeAppService:
        def get_app(self, session, app_id, account):  # noqa: ANN001
            return SimpleNamespace(id=app_id, agent_type="planner", account_id=account.id)

        def get_or_create_debug_conversation(self, session, app, account):  # noqa: ANN001
            return SimpleNamespace(id=conversation_id)

    class FakeRouterService(RouterAgentManagerService):
        def create_planner_agent_from_app(self, session, *, tenant_id, app_id, account, status=None):  # noqa: ANN001
            return (
                Agent(
                    id=planner_agent_id,
                    tenant_id=tenant_id,
                    name="Planner",
                    runtime_type="router",
                    product_category="planner",
                    status="draft",
                ),
                SimpleNamespace(id=uuid.uuid4()),
            )

        def list_bound_workers(self, session, *, tenant_id, router_agent_id):  # noqa: ANN001
            return [
                Agent(
                    id=worker_agent_id,
                    tenant_id=tenant_id,
                    name="Worker",
                    runtime_type="worker",
                    product_category="custom",
                    status="published",
                )
            ]

        def _build_planner_or_fallback_plan(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("planner should not run after stop")

    created_task_ids = []
    service = FakeRouterService(app_service=FakeAppService())

    events = list(
        service.stream_planner_debug_run(
            session,
            planner_app_id=planner_app_id,
            query="plan this",
            account=account,
            on_task_created=created_task_ids.append,
            is_stopped=lambda task_id: True,
        )
    )

    assert created_task_ids
    assert [event.thought.event for event in events] == [QueueEvent.AGENT_THOUGHT, QueueEvent.STOP]
    assert events[-1].thought.observation == "PlannerAgent 调试已停止"
    task = next(item for item in session.added if item.id == created_task_ids[0])
    assert task.status == TaskStatus.CANCELLED


def test_create_manager_run_uses_llm_planner_plan() -> None:
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    account = Account(id=tenant_id, name="tester", email="tester@example.test")

    class FakeLanguageModelService:
        def load_language_model(self, model_config, *, session, account):  # noqa: ANN001
            return BaseLanguageModel(provider="fake", model="planner", parameters={})

    class FakePlannerAgent:
        def create_plan(self, *, model, planner_input):  # noqa: ANN001
            assert planner_input.router_id == str(router_agent_id)
            assert planner_input.recent_history == [
                {"role": "user", "content": "天气如何"},
                {"role": "assistant", "content": "请提供城市。"},
            ]
            return PlannerResult(
                plan=RouterPlan(
                    router_id=str(router_agent_id),
                    user_intent=planner_input.query,
                    risk_assessment={"risk_level": "low", "source": "llm_planner_v1"},
                    steps=[
                        RouterPlanStep(
                            step_id="step_1",
                            worker_id=str(worker_agent_id),
                            task="research launch plan",
                        )
                    ],
                ),
                raw_output='{"schema_version":"router_plan_v1"}',
                usage={"total_tokens": 12},
                latency_ms=30,
            )

    class FakeRouterService(RouterAgentManagerService):
        def get_router_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            return Agent(
                id=agent_id,
                tenant_id=tenant_id,
                name="Planner",
                runtime_type="router",
                product_category="planner",
                status="draft",
            )

        def list_bound_workers(self, session, *, tenant_id, router_agent_id):  # noqa: ANN001
            return [
                Agent(
                    id=worker_agent_id,
                    tenant_id=tenant_id,
                    name="Research",
                    runtime_type="worker",
                    product_category="custom",
                    status="published",
                    target_ref_type="app",
                    target_ref_id=str(uuid.uuid4()),
                )
            ]

    session = FakeSession()
    service = FakeRouterService(
        planner_agent=FakePlannerAgent(),
        language_model_service=FakeLanguageModelService(),
    )

    run = service.create_manager_run(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        user_input={
            "query": "launch plan",
            "recent_history": [
                {"role": "user", "content": "天气如何"},
                {"role": "assistant", "content": "请提供城市。"},
            ],
        },
        account=account,
    )

    assert run.plan.plan_json["risk_assessment"]["source"] == "llm_planner_v1"
    assert run.steps[0].worker_agent_id == worker_agent_id
    trace_events = [item for item in session.added if isinstance(item, TraceEvent)]
    assert [event.event_type for event in trace_events] == [
        "planner.started",
        "planner.generated",
        "planner.validated",
        "router.manager_run.created",
    ]


def test_create_manager_run_falls_back_when_planner_fails() -> None:
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    account = Account(id=tenant_id, name="tester", email="tester@example.test")

    class FakeLanguageModelService:
        def load_language_model(self, model_config, *, session, account):  # noqa: ANN001
            return BaseLanguageModel(provider="fake", model="planner", parameters={})

    class FakePlannerAgent:
        def create_plan(self, *, model, planner_input):  # noqa: ANN001
            return PlannerResult(plan=None, raw_output="not-json", error="bad json")

    class FakeRouterService(RouterAgentManagerService):
        def get_router_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            return Agent(
                id=agent_id,
                tenant_id=tenant_id,
                name="Planner",
                runtime_type="router",
                product_category="planner",
                status="draft",
            )

        def list_bound_workers(self, session, *, tenant_id, router_agent_id):  # noqa: ANN001
            return [
                Agent(
                    id=worker_agent_id,
                    tenant_id=tenant_id,
                    name="Research",
                    runtime_type="worker",
                    product_category="custom",
                    status="published",
                    target_ref_type="app",
                    target_ref_id=str(uuid.uuid4()),
                )
            ]

    session = FakeSession()
    service = FakeRouterService(
        planner_agent=FakePlannerAgent(),
        language_model_service=FakeLanguageModelService(),
    )

    run = service.create_manager_run(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        user_input={"query": "launch plan"},
        account=account,
    )

    assert run.plan.plan_json["risk_assessment"]["source"] == "manager_rule_v1"
    assert run.steps[0].input_json["task"] == "launch plan"
    trace_events = [item for item in session.added if isinstance(item, TraceEvent)]
    assert [event.event_type for event in trace_events] == [
        "planner.started",
        "planner.generated",
        "planner.failed",
        "planner.fallback",
        "router.manager_run.created",
    ]


def test_execute_manager_run_steps_invokes_legacy_app_worker() -> None:
    expected_conversation_id = uuid.uuid4()

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
            assert query == "summarize sales notes"
            assert image_urls == []
            assert conversation_id == expected_conversation_id
            yield AgentThought(
                id=uuid.uuid4(),
                task_id=task_id,
                event=QueueEvent.AGENT_MESSAGE,
                thought="summary",
                answer="summary",
            )
            yield AgentThought(id=uuid.uuid4(), task_id=task_id, event=QueueEvent.AGENT_END)

    class FakeRouterService(RouterAgentManagerService):
        def get_worker_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            return Agent(
                id=agent_id,
                tenant_id=tenant_id,
                name="Legacy App Worker",
                runtime_type="worker",
                product_category="custom",
                status="published",
                target_ref_type="app",
                target_ref_id=str(app_id),
            )

    session = FakeSession()
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    app_id = uuid.uuid4()
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    service = FakeRouterService(app_service=FakeAppService())
    plan = RouterPlan(
        router_id=str(router_agent_id),
        user_intent="summarize sales notes",
        steps=[RouterPlanStep(step_id="summarize", worker_id=str(worker_agent_id), task="summarize sales notes")],
    )
    run = service.create_manager_task_from_plan(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        plan=plan,
        user_input={"query": "summarize sales notes"},
        conversation_id=expected_conversation_id,
    )

    service.execute_manager_run_steps(session, run=run, account=account)

    assert run.task.status == TaskStatus.SUCCEEDED
    assert run.steps[0].status == TaskStatus.SUCCEEDED
    assert run.steps[0].output_json["answer"] == "summary"
    assert run.steps[0].output_json["schema_version"] == "worker_result_v1"
    assert run.steps[0].output_json["data"]["answer"] == "summary"
    assert run.task.final_result["steps"][0]["output"]["answer"] == "summary"
    worker_calls = [item for item in session.added if isinstance(item, WorkerCall)]
    assert worker_calls[0].invocation_json["schema_version"] == "worker_invocation_v1"
    assert worker_calls[0].invocation_json["execution_policy"]["execution_agent_type"] == "react_worker"
    assert worker_calls[0].result_json["schema_version"] == "worker_result_v1"
    trace_events = [item for item in session.added if isinstance(item, TraceEvent)]
    assert [event.event_type for event in trace_events] == [
        "router.manager_run.created",
        "router.step.started",
        "worker.call.started",
        "worker.event.agent_message",
        "worker.event.agent_end",
        "worker.call.succeeded",
        "router.step.succeeded",
        "router.manager_run.succeeded",
    ]
    assert all(event.trace_id == run.trace_id for event in trace_events)


def test_execute_manager_run_steps_passes_input_files_to_worker_context() -> None:
    input_file_id = uuid.uuid4()

    class FakeFileService:
        def to_agent_input_ref(self, session, account, file_id):  # noqa: ANN001
            assert file_id == input_file_id
            return {
                "id": file_id,
                "file_id": str(file_id),
                "name": "sales-notes.md",
                "mime_type": "text/markdown",
                "content": "Quarterly notes mention expansion revenue.",
                "content_truncated": False,
            }

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
            assert "summarize sales notes" in query
            assert "Input files:" in query
            assert "Quarterly notes mention expansion revenue." in query
            assert conversation_id is None
            yield AgentThought(
                id=uuid.uuid4(),
                task_id=task_id,
                event=QueueEvent.AGENT_MESSAGE,
                answer="summary",
            )
            yield AgentThought(id=uuid.uuid4(), task_id=task_id, event=QueueEvent.AGENT_END)

    class FakeRouterService(RouterAgentManagerService):
        def get_worker_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            return Agent(
                id=agent_id,
                tenant_id=tenant_id,
                name="Legacy App Worker",
                runtime_type="worker",
                product_category="custom",
                status="published",
                target_ref_type="app",
                target_ref_id=str(app_id),
            )

    session = FakeSession()
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    app_id = uuid.uuid4()
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    service = FakeRouterService(app_service=FakeAppService(), file_service=FakeFileService())
    plan = RouterPlan(
        router_id=str(router_agent_id),
        user_intent="summarize sales notes",
        steps=[RouterPlanStep(step_id="summarize", worker_id=str(worker_agent_id), task="summarize sales notes")],
    )
    run = service.create_manager_task_from_plan(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        plan=plan,
        user_input={"query": "summarize sales notes", "input_file_ids": [str(input_file_id)]},
    )

    service.execute_manager_run_steps(session, run=run, account=account)

    worker_calls = [item for item in session.added if isinstance(item, WorkerCall)]
    input_files = worker_calls[0].invocation_json["context"]["input_files"]
    assert input_files[0]["file_id"] == str(input_file_id)
    assert input_files[0]["content"] == "Quarterly notes mention expansion revenue."


def test_execute_manager_run_steps_registers_and_propagates_artifacts() -> None:
    created_file_id = uuid.uuid4()

    class FakeFileService:
        def create_agent_artifact(self, session, account, *, name, content, mime_type, extension, metadata):  # noqa: ANN001
            assert name == "analysis.txt"
            assert content == "analysis report body"
            assert metadata["step_key"] == "analyze"
            assert "content" not in metadata
            return SimpleNamespace(
                id=created_file_id,
                account_id=account.id,
                parent_id=None,
                type="file",
                name=name,
                extension=extension,
                mime_type=mime_type,
                size=len(content),
                storage_provider="local",
                file_path="agent/analysis.txt",
                hash="hash",
                source="agent",
                status="available",
                meta=metadata,
                created_at=None,
                updated_at=None,
            )

        def to_response(self, session, file):  # noqa: ANN001
            return {
                "id": file.id,
                "name": file.name,
                "extension": file.extension,
                "mime_type": file.mime_type,
                "size": file.size,
                "storage_provider": file.storage_provider,
                "file_path": file.file_path,
                "source": file.source,
                "download_url": "http://files/agent/analysis.txt",
                "preview_url": "http://files/agent/analysis.txt",
            }

    class FakeWorkerRuntime:
        def __init__(self) -> None:
            self.invocations = []

        def invoke(self, invocation, *, session, worker, account):  # noqa: ANN001
            self.invocations.append(invocation)
            if len(self.invocations) == 1:
                return WorkerResult(
                    trace_id=invocation.trace_id,
                    task_id=invocation.task_id,
                    step_id=invocation.step_id,
                    worker_id=invocation.worker_id,
                    status=TaskStatus.SUCCEEDED.value,
                    summary="analysis complete",
                    data={"answer": "analysis complete"},
                    artifacts=[
                        ArtifactRef(
                            name="analysis.txt",
                            summary="Analysis report",
                            metadata={"content": "analysis report body"},
                        )
                    ],
                )
            assert self.invocations[1].context["artifacts"][0]["file_id"] == str(created_file_id)
            return WorkerResult(
                trace_id=invocation.trace_id,
                task_id=invocation.task_id,
                step_id=invocation.step_id,
                worker_id=invocation.worker_id,
                status=TaskStatus.SUCCEEDED.value,
                summary="final complete",
                data={"answer": "final complete"},
            )

    class FakeRouterService(RouterAgentManagerService):
        def get_worker_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            return Agent(
                id=agent_id,
                tenant_id=tenant_id,
                name="Worker",
                runtime_type="worker",
                product_category="custom",
                status="published",
                target_ref_type="app",
                target_ref_id=str(uuid.uuid4()),
            )

    session = FakeSession()
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    first_worker_id = uuid.uuid4()
    second_worker_id = uuid.uuid4()
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    worker_runtime = FakeWorkerRuntime()
    service = FakeRouterService(worker_runtime=worker_runtime, file_service=FakeFileService())
    plan = RouterPlan(
        router_id=str(router_agent_id),
        user_intent="analyze and write",
        steps=[
            RouterPlanStep(step_id="analyze", worker_id=str(first_worker_id), task="analyze"),
            RouterPlanStep(step_id="write", worker_id=str(second_worker_id), task="write", dependencies=["analyze"]),
        ],
    )
    run = service.create_manager_task_from_plan(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        plan=plan,
        user_input={"query": "analyze and write"},
    )

    service.execute_manager_run_steps(session, run=run, account=account)

    assert run.task.status == TaskStatus.SUCCEEDED
    first_artifact = run.steps[0].output_json["artifacts"][0]
    assert first_artifact["file_id"] == str(created_file_id)
    assert first_artifact["metadata"]["file"]["file_path"] == "agent/analysis.txt"
    assert "content" not in first_artifact["metadata"]
    assert worker_runtime.invocations[1].context["artifacts"][0]["file_id"] == str(created_file_id)
    assert run.task.final_result["artifacts"][0]["file_id"] == str(created_file_id)

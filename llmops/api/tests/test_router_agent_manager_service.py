import uuid
from types import SimpleNamespace

import pytest

from app.core.agent import AgentThought, QueueEvent
from app.core.exceptions import FailException
from app.core.language_model.entities import BaseLanguageModel
from app.domain.agent_runtime.planner import (
    PlannerPlanFeedbackInput,
    PlannerReplanInput,
    PlannerResult,
    PlannerWorkerDescriptor,
    RouterPlannerAgent,
)
from app.domain.agent_runtime.protocols import ArtifactRef, RouterPlan, RouterPlanStep, WorkerResult
from app.domain.agent_runtime.router_runtime import RouterRuntime
from app.models.account import Account
from app.models.agent import Agent
from app.models.task import AgentPlan, WorkerCall
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


def test_router_planner_update_plan_normalizes_replan_output() -> None:
    router_agent_id = uuid.uuid4()
    replacement_worker_id = uuid.uuid4()

    class FakeChatRuntime:
        def create_response(self, **kwargs):  # noqa: ANN001, ANN003
            assert kwargs["response_format"] == {"type": "json_object"}
            assert "Create a replacement RouterPlan" in kwargs["query"]
            return SimpleNamespace(
                content=(
                    '{"schema_version":"router_plan_v1",'
                    f'"router_id":"{router_agent_id}",'
                    '"user_intent":"recover",'
                    '"risk_assessment":{"risk_level":"low","source":"llm_planner_v1"},'
                    f'"steps":[{{"step_id":"repair","worker_id":"{replacement_worker_id}",'
                    '"task":"recover with replacement","dependencies":["old_step"]}],'
                    '"final_response_policy":{"mode":"summarize_worker_results"}}'
                ),
                usage={"total_tokens": 10},
            )

    planner = RouterPlannerAgent(chat_runtime=FakeChatRuntime())
    result = planner.update_plan(
        model=BaseLanguageModel(provider="fake", model="planner", parameters={}),
        replan_input=PlannerReplanInput(
            router_id=str(router_agent_id),
            original_query="recover",
            current_plan={"steps": []},
            failed_step={"step_key": "old_step"},
            failure={"error_code": "worker_execution_failed"},
            completed_steps=[],
            workers=[
                PlannerWorkerDescriptor(
                    worker_id=str(replacement_worker_id),
                    name="Replacement",
                    description="",
                    runtime_type="worker",
                    product_category="custom",
                    target_ref_type="app",
                    target_ref_id=str(uuid.uuid4()),
                )
            ],
            attempt=2,
        ),
    )

    assert result.succeeded
    assert result.plan is not None
    assert result.plan.risk_assessment["source"] == "llm_replan_v1"
    assert result.plan.steps[0].step_id == "replan_2_step_1"
    assert result.plan.steps[0].dependencies == []


def test_router_planner_update_plan_from_feedback_normalizes_output() -> None:
    router_agent_id = uuid.uuid4()
    update_worker_id = uuid.uuid4()

    class FakeChatRuntime:
        def create_response(self, **kwargs):  # noqa: ANN001, ANN003
            assert kwargs["response_format"] == {"type": "json_object"}
            assert "Update the remaining RouterPlan after a successful worker result" in kwargs["query"]
            return SimpleNamespace(
                content=(
                    '{"schema_version":"router_plan_v1",'
                    f'"router_id":"{router_agent_id}",'
                    '"user_intent":"write updated",'
                    '"risk_assessment":{"risk_level":"low","source":"llm_planner_v1"},'
                    f'"steps":[{{"step_id":"write","worker_id":"{update_worker_id}",'
                    '"task":"write with updated evidence","dependencies":["old_step"],'
                    '"expected_output":"final brief",'
                    '"success_criteria":["uses evidence"],'
                    '"required_artifacts":["brief.md"],'
                    '"handoff_context":"deliver final"}],'
                    '"final_response_policy":{"mode":"summarize_worker_results"}}'
                ),
                usage={"total_tokens": 11},
            )

    planner = RouterPlannerAgent(chat_runtime=FakeChatRuntime())
    result = planner.update_plan_from_feedback(
        model=BaseLanguageModel(provider="fake", model="planner", parameters={}),
        feedback_input=PlannerPlanFeedbackInput(
            router_id=str(router_agent_id),
            original_query="write updated",
            current_plan={"steps": []},
            completed_steps=[],
            latest_step={"step_key": "old_step"},
            worker_result={"answer": "new evidence"},
            plan_feedback={"needs_plan_update": True, "reason_code": "new_constraint_found"},
            workers=[
                PlannerWorkerDescriptor(
                    worker_id=str(update_worker_id),
                    name="Writer",
                    description="",
                    runtime_type="worker",
                    product_category="custom",
                    target_ref_type="app",
                    target_ref_id=str(uuid.uuid4()),
                )
            ],
            attempt=3,
        ),
    )

    assert result.succeeded
    assert result.plan is not None
    assert result.plan.risk_assessment["source"] == "llm_plan_feedback_v1"
    assert result.plan.steps[0].step_id == "update_3_step_1"
    assert result.plan.steps[0].dependencies == []
    assert result.plan.steps[0].expected_output == "final brief"
    assert result.plan.steps[0].success_criteria == ["uses evidence"]


def test_bind_worker_agent_to_planner_binds_existing_worker_agent() -> None:
    planner_app_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    router_agent = Agent(
        id=uuid.uuid4(),
        tenant_id=account.id,
        name="Planner",
        runtime_type="router",
        product_category="planner",
        status="published",
    )
    worker_agent = Agent(
        id=worker_agent_id,
        tenant_id=account.id,
        name="Worker",
        runtime_type="worker",
        product_category="custom",
        status="published",
    )

    class FakeRouterService(RouterAgentManagerService):
        def __init__(self) -> None:
            super().__init__()
            self.bound_args = None

        def create_planner_agent_from_app(self, session, *, tenant_id, app_id, account, status=None):  # noqa: ANN001
            assert tenant_id == account.id
            assert app_id == planner_app_id
            return router_agent, None

        def get_worker_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            assert tenant_id == account.id
            assert agent_id == worker_agent_id
            return worker_agent

        def bind_worker(self, session, **kwargs):  # noqa: ANN001, ANN003
            self.bound_args = kwargs
            return SimpleNamespace(id=uuid.uuid4())

    service = FakeRouterService()

    binding = service.bind_worker_agent_to_planner(
        None,
        planner_app_id=planner_app_id,
        worker_agent_id=worker_agent_id,
        account=account,
        priority=20,
        conditions={"mode": "test"},
        enabled=True,
    )

    assert binding.id
    assert service.bound_args["tenant_id"] == account.id
    assert service.bound_args["router_agent_id"] == router_agent.id
    assert service.bound_args["worker_agent_id"] == worker_agent_id
    assert service.bound_args["priority"] == 20
    assert service.bound_args["conditions"] == {"mode": "test"}


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

    assert result.task.status == TaskStatus.WAITING
    assert result.task.error_code == "waiting_approval"
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
        "router.capability_preflight.started",
        "router.capability_preflight.succeeded",
        "router.manager_run.created",
    ]
    started = next(event for event in trace_events if event.event_type == "planner.started")
    assert started.payload["workers"][0]["name"] == "Research"
    validated = next(event for event in trace_events if event.event_type == "planner.validated")
    assert validated.payload["planned_steps"][0]["worker_name"] == "Research"
    assert validated.payload["planned_steps"][0]["task"] == "research launch plan"
    assert validated.payload["planned_steps"][0]["selection_reason"]
    assert validated.payload["plan_snapshot"]["steps"][0]["worker_name"] == "Research"
    created = next(event for event in trace_events if event.event_type == "router.manager_run.created")
    assert created.payload["plan_snapshot"]["steps"][0]["selection_reason"]
    assert run.steps[0].input_json["planner_selection"]["reason"]


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
        "router.capability_preflight.started",
        "router.capability_preflight.succeeded",
        "router.manager_run.created",
    ]


def test_create_manager_run_fails_with_structured_preflight_error() -> None:
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    account = Account(id=tenant_id, name="tester", email="tester@example.test")

    class FakeLanguageModelService:
        def load_language_model(self, model_config, *, session, account):  # noqa: ANN001
            return BaseLanguageModel(provider="fake", model="planner", parameters={})

    class FakePlannerAgent:
        def create_plan(self, *, model, planner_input):  # noqa: ANN001
            return PlannerResult(
                plan=RouterPlan(
                    router_id=str(router_agent_id),
                    user_intent=planner_input.query,
                    risk_assessment={"risk_level": "low", "source": "llm_planner_v1"},
                    steps=[
                        RouterPlanStep(
                            step_id="step_1",
                            worker_id=str(worker_agent_id),
                            task="search latest weather alert",
                        )
                    ],
                )
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
                    name="Weather",
                    runtime_type="worker",
                    product_category="custom",
                    status="published",
                    target_ref_type="app",
                    target_ref_id=str(uuid.uuid4()),
                )
            ]

        def _worker_capability_map(self, session, workers, *, account):  # noqa: ANN001
            return {
                str(worker_agent_id): {
                    "schema_version": "worker_capability_v2",
                    "input_modalities": ["text/plain"],
                    "model_features": ["tool_call"],
                    "semantic_tags": ["weather"],
                }
            }

    session = FakeSession()
    service = FakeRouterService(
        planner_agent=FakePlannerAgent(),
        language_model_service=FakeLanguageModelService(),
    )

    run = service.create_manager_run(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        user_input={"query": "搜索最新广州天气预警"},
        account=account,
    )

    assert run.task.status == TaskStatus.FAILED
    assert run.task.error_code == "capability_missing:search"
    assert run.plan.plan_json["preflight"]["status"] == "failed"
    assert run.steps[0].input_json["preflight"]["checks"][0]["error_code"] == "capability_missing:search"
    assert run.steps[0].status == TaskStatus.FAILED


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
            runtime_policy,
        ):
            assert query == "summarize sales notes"
            assert image_urls == []
            assert conversation_id == expected_conversation_id
            assert runtime_policy["max_iterations"] == 5
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
    assert worker_calls[0].invocation_json["execution_policy"]["executor_type"] == "app"
    assert worker_calls[0].result_json["schema_version"] == "worker_result_v1"
    assert worker_calls[0].result_json["data"]["runtime"]["mode"] == "worker_react_v1"
    trace_events = [item for item in session.added if isinstance(item, TraceEvent)]
    assert [event.event_type for event in trace_events] == [
        "router.manager_run.created",
        "router.step.started",
        "worker.call.started",
        "worker.runtime.started",
        "worker.runtime.state_changed",
        "worker.memory.compacted",
        "worker.runtime.completed",
        "worker.call.succeeded",
        "router.step.succeeded",
        "router.manager_run.succeeded",
    ]
    assert all(event.trace_id == run.trace_id for event in trace_events)
    worker_started = next(event for event in trace_events if event.event_type == "worker.call.started")
    assert worker_started.payload["worker_name"] == "Legacy App Worker"
    assert worker_started.payload["task"] == "summarize sales notes"
    assert worker_started.payload["selection_reason"]


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
            runtime_policy,
        ):
            assert "summarize sales notes" in query
            assert "Input files:" in query
            assert "Quarterly notes mention expansion revenue." in query
            assert conversation_id is None
            assert runtime_policy["allow_tool_calls"] is True
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


def test_execute_manager_run_steps_updates_remaining_plan_from_worker_feedback() -> None:
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    research_worker_id = uuid.uuid4()
    writer_worker_id = uuid.uuid4()
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    router_agent = Agent(
        id=router_agent_id,
        tenant_id=tenant_id,
        name="Planner",
        runtime_type="router",
        product_category="planner",
        status="published",
    )
    research_worker = Agent(
        id=research_worker_id,
        tenant_id=tenant_id,
        name="Research Worker",
        runtime_type="worker",
        product_category="custom",
        status="published",
        target_ref_type="app",
        target_ref_id=str(uuid.uuid4()),
    )
    writer_worker = Agent(
        id=writer_worker_id,
        tenant_id=tenant_id,
        name="Writer Worker",
        runtime_type="worker",
        product_category="custom",
        status="published",
        target_ref_type="app",
        target_ref_id=str(uuid.uuid4()),
    )

    class FakeLanguageModelService:
        def load_language_model(self, model_config, *, session, account):  # noqa: ANN001
            return BaseLanguageModel(provider="fake", model="planner", parameters={})

    class FakePlannerAgent:
        def update_plan_from_feedback(self, *, model, feedback_input):  # noqa: ANN001
            assert feedback_input.attempt == 1
            assert feedback_input.plan_feedback["reason_code"] == "new_constraint_found"
            assert feedback_input.completed_steps[0]["step_key"] == "research"
            return PlannerResult(
                plan=RouterPlan(
                    router_id=str(router_agent_id),
                    user_intent=feedback_input.original_query,
                    risk_assessment={"risk_level": "low", "source": "llm_plan_feedback_v1"},
                    steps=[
                        RouterPlanStep(
                            step_id="update_1_step_1",
                            worker_id=str(writer_worker_id),
                            task="write final using new evidence",
                            expected_output="final brief",
                            success_criteria=["uses research evidence"],
                            handoff_context="research already completed",
                        )
                    ],
                ),
                raw_output='{"schema_version":"router_plan_v1"}',
                usage={"total_tokens": 8},
                latency_ms=18,
            )

    class FakeWorkerRuntime:
        def __init__(self) -> None:
            self.invocations = []

        def invoke(self, invocation, *, session, worker, account):  # noqa: ANN001
            self.invocations.append(invocation)
            if worker.id == research_worker_id:
                return WorkerResult(
                    trace_id=invocation.trace_id,
                    task_id=invocation.task_id,
                    step_id=invocation.step_id,
                    worker_id=invocation.worker_id,
                    status=TaskStatus.SUCCEEDED.value,
                    summary="research complete",
                    data={
                        "answer": "research complete",
                        "plan_feedback": {
                            "schema_version": "worker_plan_feedback_v1",
                            "needs_plan_update": True,
                            "completed_enough": False,
                            "reason_code": "new_constraint_found",
                            "summary": "new evidence changes writing step",
                        },
                    },
                )
            assert invocation.task["expected_output"] == "final brief"
            assert invocation.task["success_criteria"] == ["uses research evidence"]
            return WorkerResult(
                trace_id=invocation.trace_id,
                task_id=invocation.task_id,
                step_id=invocation.step_id,
                worker_id=invocation.worker_id,
                status=TaskStatus.SUCCEEDED.value,
                summary="final brief",
                data={"answer": "final brief"},
            )

    class FakeCapabilityService:
        def ensure_worker_capability_summary(self, session, worker, account=None):  # noqa: ANN001
            return {
                "schema_version": "worker_capability_v2",
                "input_modalities": ["text/plain"],
                "model_features": ["tool_call"],
                "semantic_tags": ["general"],
                "executor_type": "app",
            }

        def validate_routing_policy(self, routing_policy):  # noqa: ANN001
            return {
                "routing_policy": {
                    "schema_version": "routing_policy_v1",
                    "rules": [],
                    "fallback_policy": {
                        "on_preflight_failed": "structured_error",
                        "on_worker_failed": "replan_once",
                        "on_plan_feedback": "update_once",
                        "max_plan_update_attempts": 1,
                    },
                }
            }

    class FakeRouterService(RouterAgentManagerService):
        def get_router_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            assert agent_id == router_agent_id
            return router_agent

        def list_bound_workers(self, session, *, tenant_id, router_agent_id):  # noqa: ANN001
            return [research_worker, writer_worker]

        def get_worker_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            return {
                research_worker_id: research_worker,
                writer_worker_id: writer_worker,
            }[agent_id]

    session = FakeSession()
    worker_runtime = FakeWorkerRuntime()
    service = FakeRouterService(
        planner_agent=FakePlannerAgent(),
        worker_runtime=worker_runtime,
        language_model_service=FakeLanguageModelService(),
        capability_service=FakeCapabilityService(),
    )
    plan = RouterPlan(
        router_id=str(router_agent_id),
        user_intent="research and write",
        steps=[
            RouterPlanStep(step_id="research", worker_id=str(research_worker_id), task="research"),
            RouterPlanStep(step_id="write", worker_id=str(writer_worker_id), task="write"),
        ],
    )
    run = service.create_manager_task_from_plan(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        plan=plan,
        user_input={"query": "research and write"},
    )

    result = service.execute_manager_run_steps(session, run=run, account=account)

    assert result.task.status == TaskStatus.SUCCEEDED
    assert run.plan.status == "superseded"
    assert len(worker_runtime.invocations) == 2
    assert worker_runtime.invocations[0].execution_policy["plan_attempt"] == 0
    assert worker_runtime.invocations[1].execution_policy["plan_attempt"] == 1
    assert worker_runtime.invocations[1].task["task"] == "write final using new evidence"
    plans = [item for item in session.added if isinstance(item, AgentPlan)]
    assert len(plans) == 2
    assert plans[1].plan_json["plan_update"]["attempt"] == 1
    assert plans[1].plan_json["plan_update"]["parent_plan_id"] == str(run.plan.id)
    assert plans[1].plan_json["steps"][0]["expected_output"] == "final brief"
    assert result.task.final_result["steps"][0]["output"]["answer"] == "research complete"
    assert result.task.final_result["steps"][1]["output"]["answer"] == "final brief"
    trace_event_types = [item.event_type for item in session.added if isinstance(item, TraceEvent)]
    assert "planner.plan_update.requested" in trace_event_types
    assert "planner.plan_update.generated" in trace_event_types
    assert "planner.plan_update.validated" in trace_event_types
    assert "planner.plan_update.preflight.succeeded" in trace_event_types
    assert "planner.plan_update.applied" in trace_event_types
    plan_update_applied = next(
        item
        for item in session.added
        if isinstance(item, TraceEvent) and item.event_type == "planner.plan_update.applied"
    )
    assert plan_update_applied.payload["plan_diff"]["summary"]["added"] == 1
    assert plan_update_applied.payload["feedback"]["reason_code"] == "new_constraint_found"


def test_execute_manager_run_steps_waits_when_worker_requests_user_input() -> None:
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    class FakeWorkerRuntime:
        def invoke(self, invocation, *, session, worker, account):  # noqa: ANN001
            return WorkerResult(
                trace_id=invocation.trace_id,
                task_id=invocation.task_id,
                step_id=invocation.step_id,
                worker_id=invocation.worker_id,
                status=TaskStatus.WAITING_USER.value,
                summary="需要用户提供城市",
                data={
                    "answer": "需要用户提供城市",
                    "plan_feedback": {
                        "schema_version": "worker_plan_feedback_v1",
                        "needs_plan_update": False,
                        "completed_enough": False,
                        "reason_code": "waiting_user",
                        "missing_info": ["city"],
                    },
                },
            )

    class FakeRouterService(RouterAgentManagerService):
        def get_worker_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            return Agent(
                id=agent_id,
                tenant_id=tenant_id,
                name="Weather Worker",
                runtime_type="worker",
                product_category="custom",
                status="published",
                target_ref_type="app",
                target_ref_id=str(uuid.uuid4()),
            )

    session = FakeSession()
    service = FakeRouterService(worker_runtime=FakeWorkerRuntime())
    plan = RouterPlan(
        router_id=str(router_agent_id),
        user_intent="weather",
        steps=[RouterPlanStep(step_id="weather", worker_id=str(worker_agent_id), task="query weather")],
    )
    run = service.create_manager_task_from_plan(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        plan=plan,
        user_input={"query": "天气怎么样"},
    )

    service.execute_manager_run_steps(session, run=run, account=account)

    assert run.task.status == TaskStatus.WAITING
    assert run.task.error_code == "waiting_user"
    assert run.steps[0].status == TaskStatus.WAITING
    service.task_engine.resume_task(session, run.task)
    service.task_engine.resume_step(session, run.steps[0])
    assert run.steps[0].status == TaskStatus.RUNNING
    worker_calls = [item for item in session.added if isinstance(item, WorkerCall)]
    assert worker_calls[0].status == TaskStatus.SUCCEEDED
    wait_event = next(
        item for item in session.added if isinstance(item, TraceEvent) and item.event_type == "wait.user.requested"
    )
    assert wait_event.payload["status"] == TaskStatus.WAITING.value
    assert wait_event.payload["worker_result_status"] == TaskStatus.WAITING_USER.value
    assert wait_event.payload["wait_type"] == "user_input"
    assert wait_event.payload["resume_policy"] == "resume_same_step"
    assert wait_event.payload["missing_info"] == ["city"]


def test_execute_manager_run_steps_replans_once_after_worker_failure() -> None:
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    failed_worker_id = uuid.uuid4()
    replacement_worker_id = uuid.uuid4()
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    router_agent = Agent(
        id=router_agent_id,
        tenant_id=tenant_id,
        name="Planner",
        runtime_type="router",
        product_category="planner",
        status="published",
    )
    failed_worker = Agent(
        id=failed_worker_id,
        tenant_id=tenant_id,
        name="Failing Worker",
        runtime_type="worker",
        product_category="custom",
        status="published",
        target_ref_type="app",
        target_ref_id=str(uuid.uuid4()),
    )
    replacement_worker = Agent(
        id=replacement_worker_id,
        tenant_id=tenant_id,
        name="Replacement Worker",
        runtime_type="worker",
        product_category="custom",
        status="published",
        target_ref_type="app",
        target_ref_id=str(uuid.uuid4()),
    )

    class FakeLanguageModelService:
        def load_language_model(self, model_config, *, session, account):  # noqa: ANN001
            return BaseLanguageModel(provider="fake", model="planner", parameters={})

    class FakePlannerAgent:
        def update_plan(self, *, model, replan_input):  # noqa: ANN001
            assert replan_input.attempt == 1
            assert [worker.worker_id for worker in replan_input.workers] == [str(replacement_worker_id)]
            assert replan_input.failure["error_code"] == "worker_failed"
            return PlannerResult(
                plan=RouterPlan(
                    router_id=str(router_agent_id),
                    user_intent=replan_input.original_query,
                    risk_assessment={"risk_level": "low", "source": "llm_replan_v1"},
                    steps=[
                        RouterPlanStep(
                            step_id="replan_1_step_1",
                            worker_id=str(replacement_worker_id),
                            task="recover with replacement",
                        )
                    ],
                ),
                raw_output='{"schema_version":"router_plan_v1"}',
                usage={"total_tokens": 7},
                latency_ms=25,
            )

    class FakeWorkerRuntime:
        def __init__(self) -> None:
            self.invocations = []

        def invoke(self, invocation, *, session, worker, account):  # noqa: ANN001
            self.invocations.append(invocation)
            if worker.id == failed_worker_id:
                return WorkerResult(
                    trace_id=invocation.trace_id,
                    task_id=invocation.task_id,
                    step_id=invocation.step_id,
                    worker_id=invocation.worker_id,
                    status=TaskStatus.FAILED.value,
                    summary="worker failed",
                    error_code="worker_failed",
                    retryable=True,
                )
            return WorkerResult(
                trace_id=invocation.trace_id,
                task_id=invocation.task_id,
                step_id=invocation.step_id,
                worker_id=invocation.worker_id,
                status=TaskStatus.SUCCEEDED.value,
                summary="recovered",
                data={"answer": "recovered"},
            )

    class FakeCapabilityService:
        def ensure_worker_capability_summary(self, session, worker, account=None):  # noqa: ANN001
            return {
                "schema_version": "worker_capability_v2",
                "input_modalities": ["text/plain"],
                "model_features": ["tool_call"],
                "semantic_tags": ["general"],
                "executor_type": "app",
            }

    class FakeRouterService(RouterAgentManagerService):
        def get_router_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            assert agent_id == router_agent_id
            return router_agent

        def list_bound_workers(self, session, *, tenant_id, router_agent_id):  # noqa: ANN001
            return [failed_worker, replacement_worker]

        def get_worker_agent(self, session, tenant_id, agent_id):  # noqa: ANN001
            return {
                failed_worker_id: failed_worker,
                replacement_worker_id: replacement_worker,
            }[agent_id]

        def _routing_policy_for_agent(self, session, agent):  # noqa: ANN001
            return {
                "schema_version": "routing_policy_v1",
                "rules": [],
                "fallback_policy": {
                    "on_preflight_failed": "structured_error",
                    "on_worker_failed": "replan_once",
                    "max_replan_attempts": 1,
                },
            }

    session = FakeSession()
    worker_runtime = FakeWorkerRuntime()
    service = FakeRouterService(
        planner_agent=FakePlannerAgent(),
        worker_runtime=worker_runtime,
        language_model_service=FakeLanguageModelService(),
        capability_service=FakeCapabilityService(),
    )
    plan = RouterPlan(
        router_id=str(router_agent_id),
        user_intent="recover",
        steps=[RouterPlanStep(step_id="step_1", worker_id=str(failed_worker_id), task="recover")],
    )
    run = service.create_manager_task_from_plan(
        session,
        tenant_id=tenant_id,
        router_agent_id=router_agent_id,
        plan=plan,
        user_input={"query": "recover"},
    )

    result = service.execute_manager_run_steps(session, run=run, account=account)

    assert result.task.status == TaskStatus.SUCCEEDED
    assert run.plan.status == "superseded"
    assert len(worker_runtime.invocations) == 2
    assert worker_runtime.invocations[0].execution_policy["plan_attempt"] == 0
    assert worker_runtime.invocations[1].worker_id == str(replacement_worker_id)
    assert worker_runtime.invocations[1].execution_policy["plan_attempt"] == 1
    plans = [item for item in session.added if isinstance(item, AgentPlan)]
    assert len(plans) == 2
    assert plans[1].plan_json["replan"]["attempt"] == 1
    assert plans[1].plan_json["replan"]["parent_plan_id"] == str(run.plan.id)
    worker_calls = [item for item in session.added if isinstance(item, WorkerCall)]
    assert [call.status for call in worker_calls] == [TaskStatus.FAILED, TaskStatus.SUCCEEDED]
    trace_event_types = [item.event_type for item in session.added if isinstance(item, TraceEvent)]
    assert "planner.replan.requested" in trace_event_types
    assert "planner.replan.generated" in trace_event_types
    assert "planner.replan.validated" in trace_event_types
    assert "planner.replan.preflight.succeeded" in trace_event_types
    assert "planner.replan.applied" in trace_event_types
    replan_applied = next(
        item for item in session.added if isinstance(item, TraceEvent) and item.event_type == "planner.replan.applied"
    )
    assert replan_applied.payload["previous_plan"]["steps"][0]["worker_name"] == "Failing Worker"
    assert replan_applied.payload["new_plan"]["steps"][0]["worker_name"] == "Replacement Worker"
    assert replan_applied.payload["plan_diff"]["summary"]["added"] == 1
    assert replan_applied.payload["plan_diff"]["summary"]["removed"] == 1


def test_dry_run_planner_returns_plan_without_creating_task() -> None:
    tenant_id = uuid.uuid4()
    router_agent_id = uuid.uuid4()
    worker_agent_id = uuid.uuid4()
    planner_app_id = uuid.uuid4()
    account = Account(id=tenant_id, name="tester", email="tester@example.test")

    class FakeLanguageModelService:
        def load_language_model(self, model_config, *, session, account):  # noqa: ANN001
            return BaseLanguageModel(provider="fake", model="planner", parameters={})

    class FakePlannerAgent:
        def create_plan(self, *, model, planner_input):  # noqa: ANN001
            return PlannerResult(
                plan=RouterPlan(
                    router_id=str(router_agent_id),
                    user_intent=planner_input.query,
                    risk_assessment={"risk_level": "low", "source": "llm_planner_v1"},
                    steps=[
                        RouterPlanStep(
                            step_id="step_1",
                            worker_id=str(worker_agent_id),
                            task="draft answer",
                            selection_reason="best writer",
                            selection_signals=["semantic:writing"],
                        )
                    ],
                ),
                raw_output='{"schema_version":"router_plan_v1"}',
                usage={"total_tokens": 9},
                latency_ms=20,
            )

    class FakeCapabilityService:
        def ensure_worker_capability_summary(self, session, worker, account=None):  # noqa: ANN001
            return {
                "schema_version": "worker_capability_v2",
                "input_modalities": ["text/plain"],
                "semantic_tags": ["writing"],
                "model_features": [],
                "executor_type": "app",
            }

        def validate_routing_policy(self, routing_policy):  # noqa: ANN001
            return {"routing_policy": {"schema_version": "routing_policy_v1", "rules": []}}

    class FakeRouterService(RouterAgentManagerService):
        def create_planner_agent_from_app(self, session, *, tenant_id, app_id, account, status=None):  # noqa: ANN001
            assert app_id == planner_app_id
            return (
                Agent(
                    id=router_agent_id,
                    tenant_id=tenant_id,
                    name="Planner",
                    runtime_type="router",
                    product_category="planner",
                    status="draft",
                ),
                SimpleNamespace(id=uuid.uuid4(), router_config={}),
            )

        def list_bound_workers(self, session, *, tenant_id, router_agent_id):  # noqa: ANN001
            return [
                Agent(
                    id=worker_agent_id,
                    tenant_id=tenant_id,
                    name="Writer",
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
        capability_service=FakeCapabilityService(),
    )

    result = service.dry_run_planner(
        session,
        planner_app_id=planner_app_id,
        account=account,
        query="write launch copy",
    )

    assert result["dry_run"] is True
    assert result["status"] == "ready"
    assert result["planned_steps"][0]["worker_name"] == "Writer"
    assert result["planned_steps"][0]["selection_reason"] == "best writer"
    assert result["preflight"]["status"] == "succeeded"
    assert session.added == []

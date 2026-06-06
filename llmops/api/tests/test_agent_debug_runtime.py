import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_app_service, get_current_account, get_db_session
from app.app_factory import create_app
from app.core.agent import AgentQueueManager, AgentThought, QueueEvent
from app.core.config import Settings
from app.core.conversation import InvokeFrom, MessageStatus
from app.core.exceptions import FailException
from app.core.language_model.chat_runtime import ChatCompletionResult, ChatCompletionRuntime, ChatToolCall
from app.core.language_model.entities import BaseLanguageModel, ModelFeature
from app.models.account import Account
from app.models.agent import Agent
from app.models.conversation import Message, MessageAgentThought
from app.models.task import AgentPlan, AgentStep, AgentTask, WorkerCall
from app.models.trace import TraceEvent
from app.services.app_service import AppService
from app.services.chat_runtime_event_service import ChatRuntimeEventService


def test_agent_queue_manager_respects_task_owner() -> None:
    task_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    AgentQueueManager.register_task(task_id, InvokeFrom.DEBUGGER, owner_id)
    AgentQueueManager.set_stop_flag(task_id, InvokeFrom.DEBUGGER, uuid.uuid4())

    assert AgentQueueManager.is_stopped(task_id) is False

    AgentQueueManager.set_stop_flag(task_id, InvokeFrom.DEBUGGER, owner_id)

    assert AgentQueueManager.is_stopped(task_id) is True
    AgentQueueManager.clear_task(task_id)


def test_chat_runtime_event_service_converts_realtime_plan_and_wait_events() -> None:
    service = ChatRuntimeEventService()
    task_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    message_id = uuid.uuid4()
    worker_id = uuid.uuid4()

    plan_events = service.events_from_agent_thought(
        AgentThought(
            id=uuid.uuid4(),
            task_id=task_id,
            event=QueueEvent.AGENT_ACTION,
            observation="计划生成完成",
            tool="planner.plan",
            tool_input={
                "source": "llm_planner_v1",
                "steps": [
                    {
                        "step_id": "step_1",
                        "worker_id": str(worker_id),
                        "worker_name": "Research",
                        "task": "收集资料",
                        "dependencies": [],
                    }
                ],
            },
        ),
        conversation_id=conversation_id,
        message_id=message_id,
    )

    assert plan_events[0]["type"] == "plan"
    assert plan_events[0]["status"] == "created"
    assert plan_events[0]["steps"][0]["worker_name"] == "Research"
    assert plan_events[0]["steps"][0]["description"] == "收集资料"

    wait_events = service.events_from_agent_thought(
        AgentThought(
            id=uuid.uuid4(),
            task_id=task_id,
            event=QueueEvent.AGENT_ACTION,
            observation="需要补充行业范围",
            tool="Research",
            tool_input={
                "step_key": "step_1",
                "status": "waiting_user",
                "worker_agent_id": str(worker_id),
                "worker_name": "Research",
                "missing_info": ["行业范围"],
                "reason_code": "missing_info",
                "resume_policy": "resume_same_step",
            },
        ),
        conversation_id=conversation_id,
        message_id=message_id,
    )

    assert [event["type"] for event in wait_events] == ["step", "wait"]
    assert wait_events[0]["status"] == "waiting"
    assert wait_events[1]["payload"]["missing_info"] == ["行业范围"]
    assert wait_events[1]["payload"]["resume_policy"] == "resume_same_step"


def test_chat_runtime_event_service_replays_history_events_for_message() -> None:
    class FakeQuery:
        def __init__(self, items) -> None:  # noqa: ANN001
            self.items = list(items)

        def filter(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return self

        def order_by(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return self

        def all(self):
            return self.items

    class FakeSession:
        def __init__(self, mapping) -> None:  # noqa: ANN001
            self.mapping = mapping

        def query(self, model):  # noqa: ANN001
            return FakeQuery(self.mapping.get(model, []))

    now = datetime.now()
    app_id = uuid.uuid4()
    account_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    message_id = uuid.uuid4()
    router_id = uuid.uuid4()
    worker_id = uuid.uuid4()
    task_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    step_id = uuid.uuid4()
    worker_call_id = uuid.uuid4()

    message = Message(
        id=message_id,
        app_id=app_id,
        conversation_id=conversation_id,
        invoke_from=InvokeFrom.DEBUGGER.value,
        created_by=account_id,
        query="分析市场",
        image_urls=[],
        message=[],
        answer="",
        status=MessageStatus.NORMAL.value,
        error="",
        created_at=now,
        updated_at=now,
    )
    task = AgentTask(
        id=task_id,
        tenant_id=account_id,
        conversation_id=conversation_id,
        router_agent_id=router_id,
        user_id=account_id,
        status="waiting",
        user_input={"query": "分析市场", "context": {"message_id": str(message_id)}},
        final_result={},
        error_code="waiting_user",
        error_message="需要补充行业范围",
        version=1,
        created_at=now,
        updated_at=now,
    )
    plan = AgentPlan(
        id=plan_id,
        tenant_id=account_id,
        task_id=task_id,
        router_agent_id=router_id,
        schema_version="router_plan_v1",
        plan_json={
            "user_intent": "分析市场",
            "steps": [{"step_id": "step_1", "worker_id": str(worker_id), "task": "收集资料"}],
        },
        risk_level="low",
        status="running",
        created_at=now,
        updated_at=now,
    )
    step = AgentStep(
        id=step_id,
        tenant_id=account_id,
        task_id=task_id,
        plan_id=plan_id,
        step_key="step_1",
        worker_agent_id=worker_id,
        dependencies=[],
        execution_mode="sync",
        status="waiting",
        input_json={"task": "收集资料"},
        output_json={"summary": "需要补充行业范围"},
        retry_count=0,
        timeout_seconds=120,
        created_at=now,
        updated_at=now,
    )
    worker_call = WorkerCall(
        id=worker_call_id,
        tenant_id=account_id,
        task_id=task_id,
        step_id=step_id,
        worker_agent_id=worker_id,
        invocation_json={"task": {"description": "收集资料"}},
        result_json={"summary": "需要补充行业范围"},
        status="waiting",
        token_count=0,
        cost=0,
        latency=0,
        created_at=now,
        updated_at=now,
    )
    trace_event = TraceEvent(
        id=uuid.uuid4(),
        tenant_id=account_id,
        trace_id="trace-1",
        task_id=task_id,
        plan_id=plan_id,
        step_id=step_id,
        worker_call_id=worker_call_id,
        event_type="wait.user.requested",
        payload={
            "summary": "需要补充行业范围",
            "missing_info": ["行业范围"],
            "reason_code": "missing_info",
            "resume_policy": "resume_same_step",
        },
        created_at=now,
        updated_at=now,
    )
    router = Agent(
        id=router_id,
        tenant_id=account_id,
        created_by=account_id,
        name="Planner",
        runtime_type="router",
        product_category="planner",
        status="published",
    )
    worker = Agent(
        id=worker_id,
        tenant_id=account_id,
        created_by=account_id,
        name="Research",
        runtime_type="worker",
        product_category="custom",
        status="published",
    )
    session = FakeSession(
        {
            AgentTask: [task],
            AgentPlan: [plan],
            AgentStep: [step],
            WorkerCall: [worker_call],
            TraceEvent: [trace_event],
            Agent: [router, worker],
        }
    )

    events = ChatRuntimeEventService().runtime_events_for_message(session, message, account_id=account_id)

    assert [event["type"] for event in events] == ["plan", "step", "tool", "wait"]
    assert events[0]["steps"][0]["worker_name"] == "Research"
    assert events[1]["status"] == "waiting"
    assert events[3]["payload"]["missing_info"] == ["行业范围"]


def test_chat_runtime_event_service_replays_saved_message_thoughts_without_agent_task() -> None:
    now = datetime.now()
    app_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    message_id = uuid.uuid4()
    end_user_id = uuid.uuid4()

    action = MessageAgentThought(
        id=uuid.uuid4(),
        app_id=app_id,
        conversation_id=conversation_id,
        message_id=message_id,
        invoke_from=InvokeFrom.WEB_APP.value,
        created_by=end_user_id,
        position=1,
        event=QueueEvent.AGENT_ACTION.value,
        thought="",
        observation="查询当前时间",
        tool="current_time",
        tool_input={"timezone": "Asia/Hong_Kong"},
        message=[],
        answer="",
        total_token_count=0,
        total_price=0,
        latency=0.1,
        created_at=now,
        updated_at=now,
    )
    done = MessageAgentThought(
        id=uuid.uuid4(),
        app_id=app_id,
        conversation_id=conversation_id,
        message_id=message_id,
        invoke_from=InvokeFrom.WEB_APP.value,
        created_by=end_user_id,
        position=2,
        event=QueueEvent.AGENT_END.value,
        thought="",
        observation="",
        tool="",
        tool_input={},
        message=[],
        answer="",
        total_token_count=0,
        total_price=0,
        latency=0.2,
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=message_id,
        app_id=app_id,
        conversation_id=conversation_id,
        invoke_from=InvokeFrom.WEB_APP.value,
        created_by=end_user_id,
        query="几点了",
        image_urls=[],
        message=[],
        answer="现在是 12:00",
        status=MessageStatus.NORMAL.value,
        error="",
        created_at=now,
        updated_at=now,
    )
    message.agent_thoughts = [action, done]

    events = ChatRuntimeEventService().runtime_events_from_message_thoughts(message)

    assert [event["type"] for event in events] == ["tool", "done"]
    assert events[0]["title"] == "current_time 调用完成"
    assert events[0]["payload"]["function_args"] == {"timezone": "Asia/Hong_Kong"}


def test_chat_runtime_builds_multimodal_messages() -> None:
    messages = ChatCompletionRuntime._build_messages(
        system_prompt="system",
        history=[{"role": "assistant", "content": "hello"}],
        query="describe",
        image_urls=["https://example.test/image.png"],
    )

    assert messages[0] == {"role": "system", "content": "system"}
    assert messages[1] == {"role": "assistant", "content": "hello"}
    assert messages[2]["content"][0] == {"type": "text", "text": "describe"}
    assert messages[2]["content"][1]["image_url"]["url"] == "https://example.test/image.png"


def test_chat_runtime_rejects_image_input_for_text_only_model() -> None:
    llm = BaseLanguageModel(provider="deepseek", model="deepseek-v4-pro", features=[])
    messages = ChatCompletionRuntime._build_messages(
        system_prompt="",
        history=[],
        query="describe",
        image_urls=["https://example.test/image.png"],
    )

    with pytest.raises(FailException, match="does not support image input"):
        ChatCompletionRuntime().create_response(model=llm, messages=messages)


def test_app_service_converts_local_upload_image_url_to_data_url(monkeypatch) -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    service = AppService()
    file = SimpleNamespace(
        account_id=account.id,
        file_path="2026/06/02/image.png",
        storage_provider="local",
        mime_type="image/png",
        status="available",
    )

    class FakeQuery:
        def filter(self, *args):  # noqa: ANN001
            return self

        def one_or_none(self):
            return file

    class FakeSession:
        def query(self, model):  # noqa: ANN001
            return FakeQuery()

    monkeypatch.setattr(
        service.storage_service,
        "read",
        lambda session, account_id, storage_provider, file_path: b"\x89PNG",
    )

    image_urls = service._prepare_image_urls_for_model(  # noqa: SLF001
        FakeSession(),
        account,
        ["/api/upload-files/2026/06/02/image.png"],
    )

    assert image_urls == ["data:image/png;base64,iVBORw=="]


def test_chat_runtime_keeps_deepseek_v4_parameters_and_reasoning_content() -> None:
    safe_parameters = ChatCompletionRuntime._safe_parameters(
        {
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
            "enable_thinking": False,
            "thinking_budget": 4096,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "top_p": 0,
            "max_tokens": 0,
            "unsupported": "drop",
        }
    )

    assert safe_parameters == {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
        "enable_thinking": False,
        "thinking_budget": 4096,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    assert ChatCompletionRuntime._normalize_assistant_message(
        {"content": "", "reasoning_content": "thinking trace"}
    )["reasoning_content"] == "thinking trace"


def test_chat_runtime_parses_openai_tool_calls() -> None:
    tool_calls = ChatCompletionRuntime._parse_tool_calls(
        {
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "current_time", "arguments": "{}"},
                }
            ]
        }
    )

    assert tool_calls == [ChatToolCall(id="call-1", name="current_time", args={})]


def test_chat_runtime_parses_provider_tool_call_variants() -> None:
    tool_calls = ChatCompletionRuntime._parse_tool_calls(
        {
            "function_call": {"name": "lookup", "arguments": '"{\\"query\\": \\"docs\\"}"'},
        }
    )

    assert tool_calls == [ChatToolCall(id=tool_calls[0].id, name="lookup", args={"query": "docs"})]
    normalized_tool_call = ChatCompletionRuntime._normalize_assistant_message(
        {"function_call": {"name": "lookup", "arguments": {}}}
    )["tool_calls"][0]
    assert normalized_tool_call["function"]["name"] == "lookup"
    assert normalized_tool_call["function"]["arguments"] == "{}"


def test_chat_runtime_marks_malformed_tool_arguments() -> None:
    tool_calls = ChatCompletionRuntime._parse_tool_calls(
        {
            "tool_calls": {
                "id": "call-1",
                "function": {"name": "current_time", "arguments": '{"timezone": '},
            },
        }
    )

    assert tool_calls[0].name == "current_time"
    assert tool_calls[0].args == {}
    assert "invalid JSON" in tool_calls[0].parse_error


def test_app_service_executes_configured_builtin_tool_context() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    task_id = uuid.uuid4()
    config = {
        "tools": [{"type": "builtin_tool", "provider_id": "time", "tool_id": "current_time", "params": {}}],
        "workflows": [],
    }

    context, thoughts = AppService()._execute_configured_capabilities(None, task_id, config, "now", account)  # noqa: SLF001

    assert "current_time" in context
    assert len(thoughts) == 1
    assert thoughts[0].event == "agent_action"
    assert thoughts[0].tool == "current_time"


def test_app_service_iterative_function_call_executes_tool_then_answers(monkeypatch) -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    task_id = uuid.uuid4()
    llm = BaseLanguageModel(
        provider="openai",
        model="gpt-4o-mini",
        features=[ModelFeature.TOOL_CALL, ModelFeature.AGENT_THOUGHT],
    )
    capabilities = AppService()._build_runtime_capabilities(  # noqa: SLF001
        None,
        {"tools": [{"type": "builtin_tool", "provider_id": "time", "tool_id": "current_time", "params": {}}]},
        account,
    )
    responses = [
        ChatCompletionResult(
            content="",
            message={
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "current_time", "arguments": "{}"},
                    }
                ],
            },
            tool_calls=[ChatToolCall(id="call-1", name="current_time", args={})],
        ),
        ChatCompletionResult(content="It is done.", message={"role": "assistant", "content": "It is done."}),
    ]

    def fake_create_response(self, **kwargs):  # noqa: ANN001
        return responses.pop(0)

    monkeypatch.setattr(ChatCompletionRuntime, "create_response", fake_create_response)

    thoughts = list(
        AppService()._run_iterative_agent(  # noqa: SLF001
            session=None,
            task_id=task_id,
            query="what time",
            image_urls=[],
            history=[],
            system_prompt="system",
            llm=llm,
            review_config={"enable": False},
            capabilities=capabilities,
            account=account,
            start_at=0,
        )
    )

    assert [thought.event for thought in thoughts] == [
        "agent_thought",
        "agent_action",
        "agent_message",
        "agent_end",
    ]
    assert thoughts[1].tool == "current_time"
    assert thoughts[2].answer == "It is done."


def test_app_service_iterative_react_executes_json_tool_call(monkeypatch) -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    task_id = uuid.uuid4()
    llm = BaseLanguageModel(
        provider="deepseek",
        model="deepseek-chat",
        features=[ModelFeature.AGENT_THOUGHT],
    )
    capabilities = AppService()._build_runtime_capabilities(  # noqa: SLF001
        None,
        {"tools": [{"type": "builtin_tool", "provider_id": "time", "tool_id": "current_time", "params": {}}]},
        account,
    )
    responses = [
        ChatCompletionResult(
            content='```json\n{"name": "current_time", "args": {}}\n```',
            message={"role": "assistant", "content": ""},
        ),
        ChatCompletionResult(content="Finished.", message={"role": "assistant", "content": "Finished."}),
    ]

    def fake_create_response(self, **kwargs):  # noqa: ANN001
        return responses.pop(0)

    monkeypatch.setattr(ChatCompletionRuntime, "create_response", fake_create_response)

    thoughts = list(
        AppService()._run_iterative_agent(  # noqa: SLF001
            session=None,
            task_id=task_id,
            query="what time",
            image_urls=[],
            history=[],
            system_prompt="system",
            llm=llm,
            review_config={"enable": False},
            capabilities=capabilities,
            account=account,
            start_at=0,
        )
    )

    assert thoughts[0].event == "agent_thought"
    assert thoughts[1].event == "agent_action"
    assert thoughts[1].tool == "current_time"
    assert thoughts[2].answer == "Finished."


def test_app_service_falls_back_to_react_when_provider_returns_json_text(monkeypatch) -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    task_id = uuid.uuid4()
    llm = BaseLanguageModel(
        provider="openai",
        model="gpt-4o-mini",
        features=[ModelFeature.TOOL_CALL],
    )
    capabilities = AppService()._build_runtime_capabilities(  # noqa: SLF001
        None,
        {"tools": [{"type": "builtin_tool", "provider_id": "time", "tool_id": "current_time", "params": {}}]},
        account,
    )
    responses = [
        ChatCompletionResult(
            content='I will call it.\n```json\n{"name": "current_time", "args": {}}\n```',
            message={"role": "assistant", "content": ""},
        ),
        ChatCompletionResult(content="Finished.", message={"role": "assistant", "content": "Finished."}),
    ]

    def fake_create_response(self, **kwargs):  # noqa: ANN001
        return responses.pop(0)

    monkeypatch.setattr(ChatCompletionRuntime, "create_response", fake_create_response)

    thoughts = list(
        AppService()._run_iterative_agent(  # noqa: SLF001
            session=None,
            task_id=task_id,
            query="what time",
            image_urls=[],
            history=[],
            system_prompt="system",
            llm=llm,
            review_config={"enable": False},
            capabilities=capabilities,
            account=account,
            start_at=0,
        )
    )

    assert thoughts[1].event == "agent_action"
    assert thoughts[1].tool == "current_time"
    assert thoughts[2].answer == "Finished."


def test_app_service_returns_tool_argument_parse_error_as_observation(monkeypatch) -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    task_id = uuid.uuid4()
    llm = BaseLanguageModel(
        provider="openai",
        model="gpt-4o-mini",
        features=[ModelFeature.TOOL_CALL],
    )
    capabilities = AppService()._build_runtime_capabilities(  # noqa: SLF001
        None,
        {"tools": [{"type": "builtin_tool", "provider_id": "time", "tool_id": "current_time", "params": {}}]},
        account,
    )
    responses = [
        ChatCompletionResult(
            content="",
            message={
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "current_time", "arguments": '{"timezone": '},
                    }
                ],
            },
            tool_calls=[
                ChatToolCall(
                    id="call-1",
                    name="current_time",
                    args={},
                    parse_error="Tool call arguments are invalid JSON: Expecting value.",
                )
            ],
        ),
        ChatCompletionResult(content="Retried.", message={"role": "assistant", "content": "Retried."}),
    ]

    def fake_create_response(self, **kwargs):  # noqa: ANN001
        return responses.pop(0)

    monkeypatch.setattr(ChatCompletionRuntime, "create_response", fake_create_response)

    thoughts = list(
        AppService()._run_iterative_agent(  # noqa: SLF001
            session=None,
            task_id=task_id,
            query="what time",
            image_urls=[],
            history=[],
            system_prompt="system",
            llm=llm,
            review_config={"enable": False},
            capabilities=capabilities,
            account=account,
            start_at=0,
        )
    )

    assert thoughts[1].event == "agent_action"
    assert thoughts[1].tool == "current_time"
    assert "invalid JSON" in thoughts[1].observation
    assert thoughts[2].answer == "Retried."


def test_app_service_iterative_agent_respects_runtime_policy_max_iterations(monkeypatch) -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    task_id = uuid.uuid4()
    llm = BaseLanguageModel(
        provider="openai",
        model="gpt-4o-mini",
        features=[ModelFeature.TOOL_CALL],
    )
    capabilities = AppService()._build_runtime_capabilities(  # noqa: SLF001
        None,
        {"tools": [{"type": "builtin_tool", "provider_id": "time", "tool_id": "current_time", "params": {}}]},
        account,
    )

    def fake_create_response(self, **kwargs):  # noqa: ANN001
        return ChatCompletionResult(
            content="",
            message={
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "current_time", "arguments": "{}"},
                    }
                ],
            },
            tool_calls=[ChatToolCall(id="call-1", name="current_time", args={})],
        )

    monkeypatch.setattr(ChatCompletionRuntime, "create_response", fake_create_response)

    thoughts = list(
        AppService()._run_iterative_agent(  # noqa: SLF001
            session=None,
            task_id=task_id,
            query="what time",
            image_urls=[],
            history=[],
            system_prompt="system",
            llm=llm,
            review_config={"enable": False},
            capabilities=capabilities,
            account=account,
            start_at=0,
            runtime_policy={"max_iterations": 1},
        )
    )

    assert [thought.event for thought in thoughts] == [
        "agent_thought",
        "agent_action",
        "agent_message",
        "agent_end",
    ]
    assert thoughts[0].metadata["runtime_policy"]["max_iterations"] == 1
    assert "iteration count exceeded" in thoughts[2].answer


def test_debug_chat_route_streams_service_generator() -> None:
    app_id = uuid.uuid4()
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    class FakeAppService:
        def debug_chat(self, session, target_app_id, req, current_user):  # noqa: ANN001
            assert target_app_id == app_id
            assert req.query == "hi"
            assert current_user.id == account.id
            yield "event: agent_message\ndata:{\"answer\":\"hello\"}\n\n"

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: account
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_app_service] = lambda: FakeAppService()

    with TestClient(app) as client:
        response = client.post(f"/apps/{app_id}/debug-chat", json={"query": "hi", "image_urls": []})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: agent_message" in response.text

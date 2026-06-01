import uuid

from fastapi.testclient import TestClient

from app.api.deps import get_app_service, get_current_account, get_db_session
from app.app_factory import create_app
from app.core.agent import AgentQueueManager
from app.core.config import Settings
from app.core.conversation import InvokeFrom
from app.core.language_model.chat_runtime import ChatCompletionResult, ChatCompletionRuntime, ChatToolCall
from app.core.language_model.entities import BaseLanguageModel, ModelFeature
from app.models.account import Account
from app.services.app_service import AppService


def test_agent_queue_manager_respects_task_owner() -> None:
    task_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    AgentQueueManager.register_task(task_id, InvokeFrom.DEBUGGER, owner_id)
    AgentQueueManager.set_stop_flag(task_id, InvokeFrom.DEBUGGER, uuid.uuid4())

    assert AgentQueueManager.is_stopped(task_id) is False

    AgentQueueManager.set_stop_flag(task_id, InvokeFrom.DEBUGGER, owner_id)

    assert AgentQueueManager.is_stopped(task_id) is True
    AgentQueueManager.clear_task(task_id)


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

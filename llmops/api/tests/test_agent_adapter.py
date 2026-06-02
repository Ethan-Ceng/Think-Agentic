import uuid
from types import SimpleNamespace

from app.models.account import Account
from app.models.app import App
from app.services.agent_adapter_service import LegacyAppWorkerAdapter
from app.services.app_service import AppService


def test_legacy_app_worker_descriptor_classifies_app_as_worker_agent() -> None:
    app = App(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        name="Support Bot",
        icon="https://example.test/icon.png",
        description="Handles support",
        status="published",
    )
    config = {
        "model_config": {"provider": "openai", "model": "gpt-4o-mini", "parameters": {"temperature": 0.2}},
        "preset_prompt": "Help users",
        "tools": [{"type": "builtin_tool", "provider_id": "time", "tool_id": "current_time", "params": {}}],
        "workflows": [str(uuid.uuid4())],
        "datasets": [str(uuid.uuid4())],
        "retrieval_config": {"retrieval_strategy": "semantic", "k": 4, "score": 0.5},
    }

    descriptor = LegacyAppWorkerAdapter().app_to_worker_descriptor(app, config)

    assert descriptor.runtime_type == "worker"
    assert descriptor.target_ref_type == "app"
    assert descriptor.target_ref_id == str(app.id)
    assert descriptor.to_agent_payload()["status"] == "published"
    assert descriptor.to_agent_payload()["visibility_scope"] == {"account_id": str(app.account_id)}
    assert descriptor.to_version_payload()["model_config"]["model"] == "gpt-4o-mini"
    assert descriptor.to_version_payload()["prompt_config"]["preset_prompt"] == "Help users"
    assert descriptor.to_version_payload()["worker_config"]["execution_agent_type"] == "react_worker"
    assert [binding["type"] for binding in descriptor.capability_bindings] == [
        "tool",
        "workflow",
        "knowledge_base",
    ]
    assert descriptor.capability_bindings[0]["target_ref_type"] == "builtin_tool"
    assert descriptor.capability_bindings[0]["target_ref_id"] == "time/current_time"


def test_assistant_agent_worker_descriptor_classifies_platform_assistant() -> None:
    assistant_agent_id = uuid.uuid4()
    config = {"model_config": {"provider": "deepseek", "model": "deepseek-chat", "parameters": {}}}

    descriptor = LegacyAppWorkerAdapter().assistant_agent_to_worker_descriptor(assistant_agent_id, config)

    assert descriptor.runtime_type == "worker"
    assert descriptor.product_category == "assistant"
    assert descriptor.target_ref_type == "assistant_agent"
    assert descriptor.target_ref_id == str(assistant_agent_id)
    assert descriptor.status == "published"
    assert descriptor.to_agent_payload()["visibility_scope"] == {"system": True}


def test_app_service_exposes_worker_agent_descriptor_without_persisting_agent() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    app = App(
        id=uuid.uuid4(),
        account_id=account.id,
        name="Draft App",
        icon="",
        description="",
        status="draft",
    )
    config = SimpleNamespace(
        model_config={"provider": "openai", "model": "gpt-4o-mini", "parameters": {}},
        dialog_round=3,
        preset_prompt="",
        tools=[],
        workflows=[],
        datasets=[],
        retrieval_config={},
        long_term_memory={},
        opening_statement="",
        opening_questions=[],
        speech_to_text={},
        text_to_speech={},
        suggested_after_answer={},
        review_config={},
    )

    class FakeAppService(AppService):
        def get_app(self, session, app_id, current_account):  # noqa: ANN001
            assert current_account is account
            assert app_id == app.id
            return app

        def get_or_create_draft_config(self, session, target_app):  # noqa: ANN001
            assert target_app is app
            return config

    descriptor = FakeAppService().app_to_worker_agent_descriptor(None, app.id, account)

    assert descriptor.target_ref_type == "app"
    assert descriptor.target_ref_id == str(app.id)
    assert descriptor.runtime_type == "worker"

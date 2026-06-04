import uuid

from app.core.language_model.entities import BaseLanguageModel
from app.domain.agent_runtime.protocols import RouterPlan, RouterPlanStep
from app.domain.agent_runtime.router_runtime import RouterRuntime
from app.models.account import Account
from app.models.agent import Agent, AgentVersion
from app.services.agent_capability_service import AgentCapabilityService


class FakeSession:
    def __init__(self, *objects) -> None:  # noqa: ANN002
        self.objects = {(type(item), item.id): item for item in objects if getattr(item, "id", None) is not None}
        self.flushed = 0
        self.refreshed = []

    def get(self, model, primary_key):  # noqa: ANN001
        return self.objects.get((model, primary_key))

    def flush(self) -> None:
        self.flushed += 1

    def refresh(self, model_instance) -> None:  # noqa: ANN001
        self.refreshed.append(model_instance)


class FakeLanguageModelService:
    def load_language_model(self, model_config, *, session=None, account=None):  # noqa: ANN001
        assert model_config["model"] == "gpt-4o"
        return BaseLanguageModel(provider="openai", model="gpt-4o", features=["tool_call", "image_input"])


def test_worker_capability_summary_is_generated_from_model_and_bindings() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    version_id = uuid.uuid4()
    worker = Agent(
        id=uuid.uuid4(),
        tenant_id=account.id,
        name="Weather Search Worker",
        description="Query weather and search latest web sources",
        runtime_type="worker",
        product_category="custom",
        status="published",
        target_ref_type="app",
        target_ref_id=str(uuid.uuid4()),
        published_version_id=version_id,
    )
    version = AgentVersion(
        id=version_id,
        tenant_id=account.id,
        agent_id=worker.id,
        version=1,
        config_type="worker",
        model_config={"provider": "openai", "model": "gpt-4o", "parameters": {}},
        worker_config={"execution_agent_type": "react_worker"},
        capability_bindings=[
            {
                "type": "tool",
                "target_ref_type": "builtin_tool",
                "target_ref_id": "google/google_serper",
                "name": "google_serper",
                "enabled": True,
            },
            {
                "type": "tool",
                "target_ref_type": "builtin_tool",
                "target_ref_id": "gaode/gaode_weather",
                "name": "gaode_weather",
                "enabled": True,
            },
        ],
    )
    session = FakeSession(worker, version)

    service = AgentCapabilityService(language_model_service=FakeLanguageModelService())
    summary = service.ensure_worker_capability_summary(
        session,
        worker,
        account=account,
    )

    assert summary["schema_version"] == "worker_capability_v2"
    assert summary["executor_type"] == "react_worker"
    assert "image_input" in summary["model_features"]
    assert "image/png" in summary["input_modalities"]
    assert "search" in summary["semantic_tags"]
    assert "weather" in summary["semantic_tags"]
    assert summary["tool_names"] == ["google_serper", "gaode_weather"]
    assert version.worker_config["capability_summary"]["semantic_tags"] == summary["semantic_tags"]


def test_manual_overrides_are_preserved_when_attaching_refreshed_summary() -> None:
    service = AgentCapabilityService(language_model_service=FakeLanguageModelService())
    payload = service.attach_summary_to_version_payload(
        agent_payload={
            "name": "General Worker",
            "description": "",
            "target_ref_type": "app",
            "target_ref_id": str(uuid.uuid4()),
        },
        version_payload={
            "model_config": {"provider": "openai", "model": "gpt-4o", "parameters": {}},
            "worker_config": {"execution_agent_type": "react_worker"},
            "capability_bindings": [],
        },
        preserve_manual_overrides_from={
            "manual_overrides": {
                "semantic_tags": ["search"],
                "input_modalities": ["text/plain"],
            }
        },
    )

    summary = payload["worker_config"]["capability_summary"]
    assert summary["semantic_tags"] == ["search"]
    assert summary["input_modalities"] == ["text/plain"]
    assert summary["manual_overrides"]["semantic_tags"] == ["search"]


def test_router_preflight_blocks_image_input_without_vision_worker() -> None:
    worker_id = str(uuid.uuid4())
    result = RouterRuntime().preflight_plan(
        RouterPlan(
            router_id=str(uuid.uuid4()),
            user_intent="describe image",
            steps=[RouterPlanStep(step_id="step_1", worker_id=worker_id, task="describe image")],
        ),
        worker_capabilities={
            worker_id: {
                "input_modalities": ["text/plain"],
                "model_features": ["tool_call"],
                "semantic_tags": [],
            }
        },
        user_input={"query": "识别这张图", "input_modalities": ["image/png"]},
    )

    assert result["status"] == "failed"
    assert result["results"][0]["checks"][0]["error_code"] == "capability_missing:image_input"


def test_router_preflight_blocks_latest_query_without_search_worker() -> None:
    worker_id = str(uuid.uuid4())
    search_worker_id = str(uuid.uuid4())
    result = RouterRuntime().preflight_plan(
        RouterPlan(
            router_id=str(uuid.uuid4()),
            user_intent="search latest",
            steps=[RouterPlanStep(step_id="step_1", worker_id=worker_id, task="search latest")],
        ),
        worker_capabilities={
            worker_id: {
                "input_modalities": ["text/plain"],
                "model_features": ["tool_call"],
                "semantic_tags": ["weather"],
            },
            search_worker_id: {
                "input_modalities": ["text/plain"],
                "model_features": ["tool_call"],
                "semantic_tags": ["search"],
            },
        },
        user_input={"query": "搜索最新广州天气预警"},
    )

    assert result["status"] == "failed"
    assert result["results"][0]["checks"][0]["error_code"] == "capability_missing:search"
    assert result["suggested_worker_ids"] == [search_worker_id]

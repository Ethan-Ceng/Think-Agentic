import uuid

from app.models.account import Account
from app.models.api_tool import ApiTool
from app.models.workflow import Workflow
from app.services.app_service import AppService
from app.services.capability_adapter_service import CapabilityDescriptor, ToolCapabilityAdapter


def test_builtin_tool_capability_descriptor_keeps_legacy_tool_config() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    descriptor = ToolCapabilityAdapter().tool_config_to_descriptor(
        None,
        {"type": "builtin_tool", "provider_id": "time", "tool_id": "current_time", "params": {}},
        account,
    )

    assert descriptor is not None
    assert descriptor.to_registry_payload()["type"] == "tool"
    assert descriptor.target_ref_type == "builtin_tool"
    assert descriptor.target_ref_id == "time/current_time"
    assert descriptor.input_schema == {"type": "object", "properties": {}, "required": []}
    assert descriptor.config["tool_config"]["tool_id"] == "current_time"


def test_api_tool_capability_descriptor_uses_tool_id_as_target_ref() -> None:
    provider_id = uuid.uuid4()
    tool_id = uuid.uuid4()
    api_tool = ApiTool(
        id=tool_id,
        account_id=uuid.uuid4(),
        provider_id=provider_id,
        name="lookup_docs",
        description="Lookup docs",
        url="https://example.test/search",
        method="get",
        parameters=[{"name": "query", "type": "string", "description": "Search query", "required": True}],
    )

    descriptor = ToolCapabilityAdapter().api_tool_to_descriptor(api_tool)

    assert descriptor.provider == str(provider_id)
    assert descriptor.target_ref_type == "api_tool"
    assert descriptor.target_ref_id == str(tool_id)
    assert descriptor.input_schema["required"] == ["query"]
    assert descriptor.input_schema["properties"]["query"]["type"] == "string"


def test_workflow_capability_descriptor_uses_start_inputs_as_schema() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    workflow = Workflow(
        id=uuid.uuid4(),
        account_id=account.id,
        name="Research Workflow",
        tool_call_name="research_flow",
        icon="https://example.test/icon.png",
        description="Research a topic",
        status="published",
        is_debug_passed=False,
        graph={
            "nodes": [
                {
                    "id": str(uuid.uuid4()),
                    "node_type": "start",
                    "title": "start",
                    "inputs": [
                        {"name": "topic", "type": "string", "description": "Research topic", "required": True},
                        {"name": "limit", "type": "int", "description": "Result limit", "required": False},
                    ],
                }
            ],
            "edges": [],
        },
    )

    descriptor = ToolCapabilityAdapter().workflow_to_descriptor(workflow, account)

    assert descriptor is not None
    assert descriptor.to_registry_payload()["type"] == "workflow"
    assert descriptor.target_ref_type == "workflow"
    assert descriptor.target_ref_id == str(workflow.id)
    assert descriptor.input_schema["required"] == ["topic"]
    assert descriptor.input_schema["properties"]["limit"]["type"] == "integer"
    assert descriptor.config["workflow_id"] == str(workflow.id)


def test_workflow_capability_descriptor_skips_unpublished_or_foreign_workflow() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    adapter = ToolCapabilityAdapter()
    draft_workflow = Workflow(
        id=uuid.uuid4(),
        account_id=account.id,
        name="Draft",
        tool_call_name="draft",
        icon="https://example.test/icon.png",
        description="",
        status="draft",
        is_debug_passed=False,
        graph={},
    )
    foreign_workflow = Workflow(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        name="Foreign",
        tool_call_name="foreign",
        icon="https://example.test/icon.png",
        description="",
        status="published",
        is_debug_passed=False,
        graph={},
    )

    assert adapter.workflow_to_descriptor(draft_workflow, account) is None
    assert adapter.workflow_to_descriptor(foreign_workflow, account) is None


def test_dataset_collection_descriptor_wraps_configured_datasets_as_knowledge_capability() -> None:
    dataset_id = uuid.uuid4()
    app_config = {
        "datasets": [str(dataset_id), "not-a-uuid"],
        "retrieval_config": {"retrieval_strategy": "hybrid", "k": 3, "score": 0.4},
    }

    descriptor = ToolCapabilityAdapter().dataset_collection_to_descriptor(
        app_config["datasets"],
        app_config["retrieval_config"],
        app_config,
    )

    assert descriptor is not None
    assert descriptor.to_registry_payload()["type"] == "knowledge_base"
    assert descriptor.target_ref_type == "dataset_collection"
    assert descriptor.target_ref_id == str(dataset_id)
    assert descriptor.input_schema["required"] == ["query"]
    assert descriptor.config["app_config"] is app_config
    assert descriptor.config["retrieval_config"]["retrieval_strategy"] == "hybrid"


def test_app_service_runtime_tool_capability_is_built_from_adapter() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    class FakeAdapter:
        def tool_config_to_descriptor(self, session, tool_config, current_account):  # noqa: ANN001
            assert current_account is account
            return CapabilityDescriptor(
                name="lookup docs",
                description="Lookup docs",
                kind="tool",
                provider="api",
                target_ref_type="api_tool",
                target_ref_id="tool-id",
                input_schema={"type": "object", "properties": {}, "required": []},
                config={"tool_config": {"type": "api_tool", "provider_id": "provider-id", "tool_id": "lookup_docs"}},
            )

    capability = AppService(capability_adapter=FakeAdapter())._tool_config_to_capability(  # noqa: SLF001
        None,
        {"type": "api_tool"},
        account,
    )

    assert capability is not None
    assert capability.name == "lookup_docs"
    assert capability.kind == "tool"
    assert capability.config["tool_config"]["tool_id"] == "lookup_docs"


def test_app_service_runtime_workflow_capability_is_built_from_adapter() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    workflow_id = uuid.uuid4()
    workflow = Workflow(
        id=workflow_id,
        account_id=account.id,
        name="Research Workflow",
        tool_call_name="research_flow",
        icon="https://example.test/icon.png",
        description="",
        status="published",
        is_debug_passed=False,
        graph={},
    )

    class FakeSession:
        def get(self, model, primary_key):  # noqa: ANN001
            assert model is Workflow
            assert primary_key == workflow_id
            return workflow

    capabilities = AppService()._build_runtime_capabilities(  # noqa: SLF001
        FakeSession(),
        {"tools": [], "datasets": [], "workflows": [str(workflow_id)]},
        account,
    )

    assert len(capabilities) == 1
    assert capabilities[0].name == "research_flow"
    assert capabilities[0].kind == "workflow"
    assert capabilities[0].config["workflow_id"] == str(workflow_id)


def test_app_service_runtime_dataset_capability_is_built_from_adapter() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    dataset_id = uuid.uuid4()
    config = {
        "tools": [],
        "datasets": [str(dataset_id)],
        "workflows": [],
        "retrieval_config": {"retrieval_strategy": "semantic", "k": 5, "score": 0.5},
    }

    capabilities = AppService()._build_runtime_capabilities(None, config, account)  # noqa: SLF001

    assert len(capabilities) == 1
    assert capabilities[0].name == "dataset_retrieval"
    assert capabilities[0].kind == "knowledge_base"
    assert capabilities[0].parameters["required"] == ["query"]
    assert capabilities[0].config["app_config"] is config

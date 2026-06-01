import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_account, get_db_session, get_workflow_service
from app.app_factory import create_app
from app.core.config import Settings
from app.core.exceptions import ValidateErrorException
from app.models.account import Account
from app.services.workflow_service import WorkflowService


def _node(node_id: uuid.UUID, node_type: str, title: str) -> dict:
    return {
        "id": str(node_id),
        "node_type": node_type,
        "title": title,
        "position": {"x": 1, "y": 2},
    }


def _edge(edge_id: uuid.UUID, source: uuid.UUID, source_type: str, target: uuid.UUID, target_type: str) -> dict:
    return {
        "id": str(edge_id),
        "source": str(source),
        "source_type": source_type,
        "target": str(target),
        "target_type": target_type,
    }


def test_workflow_draft_graph_validation_keeps_legacy_shape() -> None:
    start_id = uuid.uuid4()
    end_id = uuid.uuid4()
    graph = {
        "nodes": [
            _node(start_id, "start", "start"),
            _node(end_id, "end", "end"),
            {"id": "bad", "node_type": "start"},
        ],
        "edges": [
            _edge(uuid.uuid4(), start_id, "start", end_id, "end"),
            {"id": str(uuid.uuid4()), "source": str(start_id), "source_type": "start"},
        ],
    }

    validated = WorkflowService.validate_draft_graph(graph)

    assert len(validated["nodes"]) == 2
    assert len(validated["edges"]) == 1
    assert validated["nodes"][0]["position"] == {"x": 1.0, "y": 2.0}


def test_workflow_publish_graph_requires_connected_dag() -> None:
    start_id = uuid.uuid4()
    end_id = uuid.uuid4()
    isolated_id = uuid.uuid4()
    graph = {
        "nodes": [
            _node(start_id, "start", "start"),
            _node(end_id, "end", "end"),
            _node(isolated_id, "code", "code"),
        ],
        "edges": [_edge(uuid.uuid4(), start_id, "start", end_id, "end")],
    }

    with pytest.raises(ValidateErrorException):
        WorkflowService.validate_publish_graph(graph)


def test_workflow_publish_graph_requires_start_entry_and_end_exit() -> None:
    start_id = uuid.uuid4()
    end_id = uuid.uuid4()
    code_id = uuid.uuid4()
    graph = {
        "nodes": [
            _node(start_id, "start", "start"),
            _node(end_id, "end", "end"),
            _node(code_id, "code", "code"),
        ],
        "edges": [
            _edge(uuid.uuid4(), start_id, "start", end_id, "end"),
            _edge(uuid.uuid4(), end_id, "end", code_id, "code"),
        ],
    }

    with pytest.raises(ValidateErrorException):
        WorkflowService.validate_publish_graph(graph)


def test_workflow_publish_graph_rejects_non_upstream_variable_ref() -> None:
    start_id = uuid.uuid4()
    code_id = uuid.uuid4()
    template_id = uuid.uuid4()
    end_id = uuid.uuid4()
    graph = {
        "nodes": [
            {
                **_node(start_id, "start", "start"),
                "inputs": [{"name": "query", "type": "string", "required": True}],
            },
            {
                **_node(code_id, "code", "code"),
                "inputs": [
                    {
                        "name": "query",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {"ref_node_id": str(start_id), "ref_var_name": "query"},
                        },
                    }
                ],
                "outputs": [{"name": "answer", "type": "string", "value": {"type": "generated"}}],
            },
            {
                **_node(template_id, "template_transform", "template"),
                "inputs": [
                    {
                        "name": "answer",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {"ref_node_id": str(code_id), "ref_var_name": "answer"},
                        },
                    }
                ],
            },
            {
                **_node(end_id, "end", "end"),
                "outputs": [
                    {
                        "name": "final",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {"ref_node_id": str(template_id), "ref_var_name": "output"},
                        },
                    }
                ],
            },
        ],
        "edges": [
            _edge(uuid.uuid4(), start_id, "start", code_id, "code"),
            _edge(uuid.uuid4(), start_id, "start", template_id, "template_transform"),
            _edge(uuid.uuid4(), code_id, "code", end_id, "end"),
            _edge(uuid.uuid4(), template_id, "template_transform", end_id, "end"),
        ],
    }

    with pytest.raises(ValidateErrorException):
        WorkflowService.validate_publish_graph(graph)


def test_workflow_publish_graph_rejects_cycle_after_entry_validation() -> None:
    start_id = uuid.uuid4()
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    end_id = uuid.uuid4()
    graph = {
        "nodes": [
            _node(start_id, "start", "start"),
            _node(first_id, "code", "first"),
            _node(second_id, "code", "second"),
            _node(end_id, "end", "end"),
        ],
        "edges": [
            _edge(uuid.uuid4(), start_id, "start", first_id, "code"),
            _edge(uuid.uuid4(), first_id, "code", second_id, "code"),
            _edge(uuid.uuid4(), second_id, "code", first_id, "code"),
            _edge(uuid.uuid4(), second_id, "code", end_id, "end"),
        ],
    }

    with pytest.raises(ValidateErrorException):
        WorkflowService.validate_publish_graph(graph)


def test_workflow_publish_graph_rejects_missing_variable_ref() -> None:
    start_id = uuid.uuid4()
    code_id = uuid.uuid4()
    end_id = uuid.uuid4()
    graph = {
        "nodes": [
            {
                **_node(start_id, "start", "start"),
                "inputs": [{"name": "query", "type": "string", "required": True}],
            },
            {
                **_node(code_id, "code", "code"),
                "inputs": [
                    {
                        "name": "query",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {"ref_node_id": str(start_id), "ref_var_name": "missing"},
                        },
                    }
                ],
                "outputs": [{"name": "answer", "type": "string", "value": {"type": "generated"}}],
            },
            {
                **_node(end_id, "end", "end"),
                "outputs": [
                    {
                        "name": "final",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {"ref_node_id": str(code_id), "ref_var_name": "answer"},
                        },
                    }
                ],
            },
        ],
        "edges": [
            _edge(uuid.uuid4(), start_id, "start", code_id, "code"),
            _edge(uuid.uuid4(), code_id, "code", end_id, "end"),
        ],
    }

    with pytest.raises(ValidateErrorException):
        WorkflowService.validate_publish_graph(graph)


def test_workflow_execution_batches_wait_for_parallel_predecessors() -> None:
    start_id = uuid.uuid4()
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    end_id = uuid.uuid4()
    graph = WorkflowService.validate_publish_graph(
        {
            "nodes": [
                _node(start_id, "start", "start"),
                _node(first_id, "code", "first"),
                _node(second_id, "code", "second"),
                _node(end_id, "end", "end"),
            ],
            "edges": [
                _edge(uuid.uuid4(), start_id, "start", first_id, "code"),
                _edge(uuid.uuid4(), start_id, "start", second_id, "code"),
                _edge(uuid.uuid4(), first_id, "code", end_id, "end"),
                _edge(uuid.uuid4(), second_id, "code", end_id, "end"),
            ],
        }
    )

    batches = WorkflowService._execution_batches(graph)  # noqa: SLF001

    assert [[node["id"] for node in batch] for batch in batches] == [
        [str(start_id)],
        [str(first_id), str(second_id)],
        [str(end_id)],
    ]


def test_workflow_executor_runs_start_template_code_and_end_nodes() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    service = WorkflowService()
    start_id = uuid.uuid4()
    template_id = uuid.uuid4()
    code_id = uuid.uuid4()
    end_id = uuid.uuid4()
    node_results = []

    start_node = {
        **_node(start_id, "start", "start"),
        "inputs": [{"name": "name", "type": "string", "required": True}],
    }
    template_node = {
        **_node(template_id, "template_transform", "template"),
        "template": "Hello {{ name }}",
        "inputs": [
            {
                "name": "name",
                "type": "string",
                "value": {"type": "ref", "content": {"ref_node_id": str(start_id), "ref_var_name": "name"}},
            }
        ],
        "outputs": [{"name": "output", "value": {"type": "generated"}}],
    }
    code_node = {
        **_node(code_id, "code", "code"),
        "code": "def main(params):\n    return {'final': params['text'] + '!'}\n",
        "inputs": [
            {
                "name": "text",
                "type": "string",
                "value": {
                    "type": "ref",
                    "content": {"ref_node_id": str(template_id), "ref_var_name": "output"},
                },
            }
        ],
        "outputs": [{"name": "final", "type": "string", "value": {"type": "generated"}}],
    }
    end_node = {
        **_node(end_id, "end", "end"),
        "outputs": [
            {
                "name": "answer",
                "type": "string",
                "value": {"type": "ref", "content": {"ref_node_id": str(code_id), "ref_var_name": "final"}},
            }
        ],
    }

    for node in [start_node, template_node, code_node, end_node]:
        result = service._execute_node(None, node, node_results, {"name": "Ada"}, account)  # noqa: SLF001
        node_results.append(result)

    assert [result["status"] for result in node_results] == ["succeeded"] * 4
    assert node_results[-1]["outputs"] == {"answer": "Hello Ada!"}


def test_workflow_debug_stops_on_failed_node_before_downstream_execution() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")
    workflow_id = uuid.uuid4()
    start_id = uuid.uuid4()
    code_id = uuid.uuid4()
    end_id = uuid.uuid4()
    graph = WorkflowService.validate_publish_graph(
        {
            "nodes": [
                {
                    **_node(start_id, "start", "start"),
                    "inputs": [{"name": "name", "type": "string", "required": True}],
                },
                {
                    **_node(code_id, "code", "code"),
                    "code": "def main(params):\n    return {'answer': params['missing']}\n",
                    "inputs": [
                        {
                            "name": "name",
                            "type": "string",
                            "value": {
                                "type": "ref",
                                "content": {"ref_node_id": str(start_id), "ref_var_name": "name"},
                            },
                        }
                    ],
                    "outputs": [{"name": "answer", "type": "string", "value": {"type": "generated"}}],
                },
                {
                    **_node(end_id, "end", "end"),
                    "outputs": [
                        {
                            "name": "final",
                            "type": "string",
                            "value": {
                                "type": "ref",
                                "content": {"ref_node_id": str(code_id), "ref_var_name": "answer"},
                            },
                        }
                    ],
                },
            ],
            "edges": [
                _edge(uuid.uuid4(), start_id, "start", code_id, "code"),
                _edge(uuid.uuid4(), code_id, "code", end_id, "end"),
            ],
        }
    )
    workflow = SimpleNamespace(id=workflow_id, draft_graph=graph, is_debug_passed=False)
    updates = []

    class FakeWorkflowService(WorkflowService):
        def get_workflow(self, session, workflow_id, account):  # noqa: ANN001, ARG002
            return workflow

        def create(self, session, model, **payload):  # noqa: ANN001, ARG002
            return SimpleNamespace(id=uuid.uuid4(), **payload)

        def update(self, session, obj, **payload):  # noqa: ANN001, ARG002
            updates.append(payload)
            for key, value in payload.items():
                setattr(obj, key, value)
            return obj

    events = list(FakeWorkflowService().debug_workflow(None, workflow_id, {"name": "Ada"}, account))
    payloads = [json.loads(event.split("data: ", 1)[1]) for event in events]

    assert [payload["node_data"]["id"] for payload in payloads] == [str(start_id), str(code_id)]
    assert payloads[-1]["status"] == "failed"
    assert any(update.get("status") == "failed" for update in updates)
    assert workflow.is_debug_passed is False


def test_workflow_create_route_keeps_legacy_payload_shape() -> None:
    workflow_id = uuid.uuid4()

    class FakeWorkflowService:
        def create_workflow(self, session, req, current_user):  # noqa: ANN001
            return SimpleNamespace(id=workflow_id)

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_workflow_service] = lambda: FakeWorkflowService()

    with TestClient(app) as client:
        response = client.post(
            "/workflows",
            json={
                "name": "Workflow",
                "tool_call_name": "workflow_1",
                "icon": "https://example.test/icon.png",
                "description": "desc",
            },
        )

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert response.json()["data"]["id"] == str(workflow_id)

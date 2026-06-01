import ast
import json
import re
import time
import uuid
from collections import deque
from collections.abc import Generator
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.exceptions import FailException, ForbiddenException, NotFoundException, ValidateErrorException
from app.core.language_model.chat_runtime import ChatCompletionRuntime
from app.core.tools.api_tools.entities import ToolEntity
from app.core.tools.api_tools.providers import ApiProviderManager
from app.core.tools.builtin_tools.providers import BuiltinProviderManager
from app.core.tools.builtin_tools.runtime import get_tool_params
from app.core.workflow import DEFAULT_WORKFLOW_CONFIG, NodeStatus, NodeType, WorkflowResultStatus, WorkflowStatus
from app.models.account import Account
from app.models.api_tool import ApiTool
from app.models.dataset import Dataset
from app.models.workflow import Workflow, WorkflowResult
from app.schemas.workflow import CreateWorkflowRequest, GetWorkflowsWithPageRequest, UpdateWorkflowRequest
from app.services.base_service import BaseService
from app.services.dataset_service import DatasetService
from app.services.language_model_service import LanguageModelService
from app.shared.paginator import Paginator


@dataclass
class WorkflowService(BaseService):
    builtin_provider_manager: BuiltinProviderManager = field(default_factory=BuiltinProviderManager)

    def create_workflow(self, session: Session, req: CreateWorkflowRequest, account: Account) -> Workflow:
        tool_call_name = req.tool_call_name.strip()
        duplicated = (
            session.query(Workflow)
            .filter(Workflow.tool_call_name == tool_call_name, Workflow.account_id == account.id)
            .one_or_none()
        )
        if duplicated:
            raise ValidateErrorException(f"Workflow already exists in current account: {tool_call_name}")

        payload = req.model_dump()
        payload["tool_call_name"] = tool_call_name
        return self.create(
            session,
            Workflow,
            **payload,
            **deepcopy(DEFAULT_WORKFLOW_CONFIG),
            account_id=account.id,
            is_debug_passed=False,
            status=WorkflowStatus.DRAFT.value,
        )

    def get_workflow(self, session: Session, workflow_id: UUID, account: Account) -> Workflow:
        workflow = self.get(session, Workflow, workflow_id)
        if workflow is None:
            raise NotFoundException("Workflow does not exist")
        if workflow.account_id != account.id:
            raise ForbiddenException("Current account cannot access this workflow")
        return workflow

    def delete_workflow(self, session: Session, workflow_id: UUID, account: Account) -> Workflow:
        workflow = self.get_workflow(session, workflow_id, account)
        self.delete(session, workflow)
        return workflow

    def update_workflow(
        self,
        session: Session,
        workflow_id: UUID,
        req: UpdateWorkflowRequest,
        account: Account,
    ) -> Workflow:
        workflow = self.get_workflow(session, workflow_id, account)
        payload = req.model_dump()
        payload["tool_call_name"] = req.tool_call_name.strip()

        duplicated = (
            session.query(Workflow)
            .filter(
                Workflow.tool_call_name == payload["tool_call_name"],
                Workflow.account_id == account.id,
                Workflow.id != workflow.id,
            )
            .one_or_none()
        )
        if duplicated:
            raise ValidateErrorException(f"Workflow already exists in current account: {payload['tool_call_name']}")

        return self.update(session, workflow, **payload)

    def get_workflows_with_page(
        self,
        session: Session,
        req: GetWorkflowsWithPageRequest,
        account: Account,
    ) -> tuple[list[Workflow], Paginator]:
        paginator = Paginator(db=session, req=req)
        query = session.query(Workflow).filter(Workflow.account_id == account.id)
        if req.search_word:
            query = query.filter(Workflow.name.ilike(f"%{req.search_word}%"))
        if req.status:
            query = query.filter(Workflow.status == req.status)

        workflows = paginator.paginate(query.order_by(desc(Workflow.created_at)))
        return workflows, paginator

    def update_draft_graph(
        self,
        session: Session,
        workflow_id: UUID,
        draft_graph: dict[str, Any],
        account: Account,
    ) -> Workflow:
        workflow = self.get_workflow(session, workflow_id, account)
        validated_graph = self.validate_draft_graph(draft_graph)
        return self.update(
            session,
            workflow,
            draft_graph=validated_graph,
            is_debug_passed=False,
        )

    def get_draft_graph(self, session: Session, workflow_id: UUID, account: Account) -> dict[str, Any]:
        workflow = self.get_workflow(session, workflow_id, account)
        draft_graph = self.validate_draft_graph(workflow.draft_graph or {})
        self._attach_node_meta(session, draft_graph, account)
        return draft_graph

    def debug_workflow(
        self,
        session: Session,
        workflow_id: UUID,
        inputs: dict[str, Any],
        account: Account,
    ) -> Generator[str, None, None]:
        workflow = self.get_workflow(session, workflow_id, account)
        workflow_result = self.create(
            session,
            WorkflowResult,
            app_id=None,
            account_id=account.id,
            workflow_id=workflow.id,
            graph=workflow.draft_graph,
            state=[],
            latency=0,
            status=WorkflowResultStatus.RUNNING.value,
        )
        start_at = time.perf_counter()

        def handle_stream() -> Generator[str, None, None]:
            node_results: list[dict[str, Any]] = []
            try:
                validated_graph = self.validate_publish_graph(workflow.draft_graph or {})
                for node_batch in self._execution_batches(validated_graph):
                    for node in node_batch:
                        node_result = self._execute_node(session, node, node_results, inputs, account)
                        node_results.append(node_result)
                        yield self._format_workflow_event(node_result)
                        if node_result["status"] == NodeStatus.FAILED.value:
                            self.update(
                                session,
                                workflow_result,
                                status=WorkflowResultStatus.FAILED.value,
                                state=node_results,
                                latency=time.perf_counter() - start_at,
                            )
                            return

                self.update(
                    session,
                    workflow_result,
                    status=WorkflowResultStatus.SUCCEEDED.value,
                    state=node_results,
                    latency=time.perf_counter() - start_at,
                )
                self.update(session, workflow, is_debug_passed=True)
            except Exception as exc:
                node_result = {
                    "node_data": {},
                    "status": NodeStatus.FAILED.value,
                    "inputs": inputs,
                    "outputs": {},
                    "latency": time.perf_counter() - start_at,
                    "error": str(exc),
                }
                node_results.append(node_result)
                self.update(
                    session,
                    workflow_result,
                    status=WorkflowResultStatus.FAILED.value,
                    state=node_results,
                    latency=time.perf_counter() - start_at,
                )
                yield self._format_workflow_event(node_result)

        return handle_stream()

    def publish_workflow(self, session: Session, workflow_id: UUID, account: Account) -> Workflow:
        workflow = self.get_workflow(session, workflow_id, account)
        if workflow.is_debug_passed is False:
            raise FailException("Workflow has not passed debug")

        try:
            validated_graph = self.validate_publish_graph(workflow.draft_graph or {})
        except Exception as exc:
            self.update(session, workflow, is_debug_passed=False)
            raise ValidateErrorException("Workflow config validation failed") from exc

        return self.update(
            session,
            workflow,
            graph=validated_graph,
            status=WorkflowStatus.PUBLISHED.value,
            is_debug_passed=False,
            published_at=datetime.now(),
        )

    def cancel_publish_workflow(self, session: Session, workflow_id: UUID, account: Account) -> Workflow:
        workflow = self.get_workflow(session, workflow_id, account)
        if workflow.status != WorkflowStatus.PUBLISHED.value:
            raise FailException("Workflow is not published")

        return self.update(
            session,
            workflow,
            graph={},
            status=WorkflowStatus.DRAFT.value,
            is_debug_passed=False,
            published_at=None,
        )

    def _execute_node(
        self,
        session: Session,
        node: dict[str, Any],
        node_results: list[dict[str, Any]],
        workflow_inputs: dict[str, Any],
        account: Account,
    ) -> dict[str, Any]:
        start_at = time.perf_counter()
        node_type = node.get("node_type")
        state = {"inputs": workflow_inputs, "node_results": node_results}
        try:
            if node_type == NodeType.START.value:
                inputs_dict = workflow_inputs
                outputs = self._start_outputs(node, workflow_inputs)
            elif node_type == NodeType.TEMPLATE_TRANSFORM.value:
                inputs_dict = self._extract_variables(node.get("inputs", []), state)
                outputs = {"output": self._render_template(str(node.get("template") or ""), inputs_dict)}
            elif node_type == NodeType.CODE.value:
                inputs_dict = self._extract_variables(node.get("inputs", []), state)
                outputs = self._run_code_node(node, inputs_dict)
            elif node_type == NodeType.HTTP_REQUEST.value:
                inputs_dict, outputs = self._run_http_node(node, state)
            elif node_type == NodeType.TOOL.value:
                inputs_dict, outputs = self._run_tool_node(session, node, state, account)
            elif node_type == NodeType.DATASET_RETRIEVAL.value:
                inputs_dict, outputs = self._run_dataset_retrieval_node(session, node, state, account)
            elif node_type == NodeType.LLM.value:
                inputs_dict, outputs = self._run_llm_node(node, state)
            elif node_type == NodeType.END.value:
                inputs_dict = {}
                outputs = self._extract_variables(node.get("outputs", []), state)
            else:
                raise FailException(f"Unsupported workflow node type: {node_type}")

            return {
                "node_data": node,
                "status": NodeStatus.SUCCEEDED.value,
                "inputs": inputs_dict,
                "outputs": outputs,
                "latency": time.perf_counter() - start_at,
                "error": "",
            }
        except Exception as exc:
            return {
                "node_data": node,
                "status": NodeStatus.FAILED.value,
                "inputs": {},
                "outputs": {},
                "latency": time.perf_counter() - start_at,
                "error": str(exc),
            }

    def _start_outputs(self, node: dict[str, Any], workflow_inputs: dict[str, Any]) -> dict[str, Any]:
        inputs = self._ensure_list(node.get("inputs"))
        if not inputs:
            return {}

        outputs = {}
        for variable in inputs:
            name = str(variable.get("name") or "")
            if not name:
                continue
            value = workflow_inputs.get(name)
            if value is None and variable.get("required", True):
                raise FailException(f"Workflow input is required: {name}")
            outputs[name] = self._coerce_variable_value(value, variable.get("type"))
        return outputs

    def _run_llm_node(self, node: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        inputs_dict = self._extract_variables(node.get("inputs", []), state)
        prompt = self._render_template(str(node.get("prompt") or ""), inputs_dict)
        llm = LanguageModelService().load_language_model(node.get("model_config") or {})
        answer = ChatCompletionRuntime().complete(
            model=llm,
            query=prompt,
            image_urls=[],
            history=[],
            system_prompt="",
        )
        return inputs_dict, {self._first_output_name(node, "output"): answer}

    def _run_dataset_retrieval_node(
        self,
        session: Session,
        node: dict[str, Any],
        state: dict[str, Any],
        account: Account,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        inputs_dict = self._extract_variables(node.get("inputs", []), state)
        query = str(inputs_dict.get("query") or next(iter(inputs_dict.values()), ""))
        retrieval_config = node.get("retrieval_config") or {}
        dataset_service = DatasetService()
        hits = []
        for raw_dataset_id in self._ensure_list(node.get("dataset_ids")):
            dataset_id = self._parse_uuid(raw_dataset_id)
            if dataset_id is None:
                continue
            hits.extend(
                dataset_service.hit(
                    session=session,
                    dataset_id=dataset_id,
                    query=query,
                    retrieval_strategy=str(retrieval_config.get("retrieval_strategy", "semantic")),
                    k=max(1, int(retrieval_config.get("k", 4) or 4)),
                    score=float(retrieval_config.get("score", 0) or 0),
                    account=account,
                )
            )
        combine_documents = "\n\n".join(hit["content"] for hit in hits) or "No matching dataset content"
        return inputs_dict, {self._first_output_name(node, "combine_documents"): combine_documents}

    def _run_tool_node(
        self,
        session: Session,
        node: dict[str, Any],
        state: dict[str, Any],
        account: Account,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        inputs_dict = self._extract_variables(node.get("inputs", []), state)
        tool_type = node.get("tool_type") or node.get("type")
        if tool_type == "builtin_tool":
            tool = self.builtin_provider_manager.get_tool(
                str(node.get("provider_id") or ""),
                str(node.get("tool_id") or ""),
            )
            if tool is None:
                raise NotFoundException("Builtin tool does not exist")
            result = tool.invoke({**(node.get("params") or {}), **inputs_dict})
        elif tool_type == "api_tool":
            provider_id = self._parse_uuid(node.get("provider_id"))
            if provider_id is None:
                raise NotFoundException("API tool provider does not exist")
            api_tool = (
                session.query(ApiTool)
                .filter(
                    ApiTool.provider_id == provider_id,
                    ApiTool.name == str(node.get("tool_id") or ""),
                    ApiTool.account_id == account.id,
                )
                .one_or_none()
            )
            if api_tool is None:
                raise NotFoundException("API tool does not exist")
            result = ApiProviderManager().get_tool(
                ToolEntity(
                    id=str(api_tool.id),
                    name=api_tool.name,
                    url=api_tool.url,
                    method=api_tool.method,
                    description=api_tool.description,
                    headers=api_tool.provider.headers,
                    parameters=api_tool.parameters,
                )
            ).invoke(inputs_dict)
        else:
            raise FailException("Workflow tool node type is invalid")

        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False, default=str)
        return inputs_dict, {self._first_output_name(node, "text"): result}

    def _run_http_node(self, node: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        import httpx

        flat_inputs = self._extract_variables(node.get("inputs", []), state)
        grouped_inputs = {"params": {}, "headers": {}, "body": {}}
        for variable in self._ensure_list(node.get("inputs")):
            name = str(variable.get("name") or "")
            input_type = str((variable.get("meta") or {}).get("type") or "params")
            if name and input_type in grouped_inputs:
                grouped_inputs[input_type][name] = flat_inputs.get(name)

        response = httpx.request(
            method=str(node.get("method") or "get").upper(),
            url=str(node.get("url") or ""),
            params=grouped_inputs["params"],
            headers=grouped_inputs["headers"],
            json=grouped_inputs["body"] or None,
            timeout=30.0,
        )
        return grouped_inputs, {"status_code": response.status_code, "text": response.text}

    def _run_code_node(self, node: dict[str, Any], inputs_dict: dict[str, Any]) -> dict[str, Any]:
        result = self._execute_python_main(str(node.get("code") or ""), params=inputs_dict)
        if not isinstance(result, dict):
            raise FailException("Workflow code node main(params) must return a dict")
        output_variables = self._ensure_list(node.get("outputs"))
        if not output_variables:
            return result
        return {
            str(variable.get("name")): result.get(
                str(variable.get("name")),
                self._default_value_for_type(variable.get("type")),
            )
            for variable in output_variables
            if variable.get("name")
        }

    @classmethod
    def _execute_python_main(cls, code: str, **kwargs: Any) -> Any:
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            raise FailException("Workflow code node syntax is invalid") from exc

        main_func = None
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                raise FailException("Workflow code node can only define main(params)")
            if node.name != "main":
                raise FailException("Workflow code node can only define main(params)")
            if main_func is not None:
                raise FailException("Workflow code node can only define one main(params)")
            if len(node.args.args) != 1 or node.args.args[0].arg != "params":
                raise FailException("Workflow code node main function must accept params")
            main_func = node

        if main_func is None:
            raise FailException("Workflow code node must define main(params)")

        local_vars: dict[str, Any] = {}
        exec(code, {"__builtins__": {"len": len, "str": str, "int": int, "float": float, "bool": bool}}, local_vars)
        return local_vars["main"](**kwargs)

    def _extract_variables(self, variables: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
        values = {}
        for variable in self._ensure_list(variables):
            name = str(variable.get("name") or "")
            if not name:
                continue
            values[name] = self._resolve_variable_value(variable, state)
        return values

    def _resolve_variable_value(self, variable: dict[str, Any], state: dict[str, Any]) -> Any:
        value = variable.get("value") if isinstance(variable.get("value"), dict) else {}
        value_type = str(value.get("type") or "literal")
        content = value.get("content")

        if value_type == "literal":
            return self._coerce_variable_value(content, variable.get("type"))
        if value_type == "generated":
            return self._default_value_for_type(variable.get("type"))
        if value_type == "ref":
            ref_node_id = str((content or {}).get("ref_node_id") or "")
            ref_var_name = str((content or {}).get("ref_var_name") or "")
            for node_result in state["node_results"]:
                if str(node_result.get("node_data", {}).get("id")) == ref_node_id:
                    return self._coerce_variable_value(
                        node_result.get("outputs", {}).get(ref_var_name),
                        variable.get("type"),
                    )
            return self._default_value_for_type(variable.get("type"))
        return self._coerce_variable_value(content, variable.get("type"))

    @staticmethod
    def _render_template(template: str, values: dict[str, Any]) -> str:
        def replace(match: re.Match[str]) -> str:
            return str(values.get(match.group(1), ""))

        rendered = re.sub(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}", replace, template)
        try:
            return rendered.format(**values)
        except (KeyError, IndexError, ValueError):
            return rendered

    @classmethod
    def _coerce_variable_value(cls, value: Any, variable_type: Any) -> Any:
        if value is None:
            return cls._default_value_for_type(variable_type)
        match str(variable_type or "string"):
            case "int":
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 0
            case "float":
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
            case "boolean":
                if isinstance(value, bool):
                    return value
                return str(value).strip().lower() in {"true", "1", "yes", "on"}
            case _:
                return str(value)

    @staticmethod
    def _default_value_for_type(variable_type: Any) -> Any:
        match str(variable_type or "string"):
            case "int":
                return 0
            case "float":
                return 0.0
            case "boolean":
                return False
            case _:
                return ""

    @staticmethod
    def _first_output_name(node: dict[str, Any], default: str) -> str:
        outputs = node.get("outputs") if isinstance(node.get("outputs"), list) else []
        if outputs and isinstance(outputs[0], dict) and outputs[0].get("name"):
            return str(outputs[0]["name"])
        return default

    @classmethod
    def _ordered_nodes(cls, graph: dict[str, Any]) -> list[dict[str, Any]]:
        return [node for batch in cls._execution_batches(graph) for node in batch]

    @classmethod
    def _execution_batches(cls, graph: dict[str, Any]) -> list[list[dict[str, Any]]]:
        nodes = graph["nodes"]
        node_map = {node["id"]: node for node in nodes}
        order_index = {node["id"]: index for index, node in enumerate(nodes)}
        in_degree = {node_id: 0 for node_id in node_map}
        adj_list = {node_id: [] for node_id in node_map}
        for edge in graph["edges"]:
            source = edge["source"]
            target = edge["target"]
            adj_list[source].append(target)
            in_degree[target] += 1

        queue = deque(sorted([node_id for node_id, degree in in_degree.items() if degree == 0], key=order_index.get))
        batches: list[list[dict[str, Any]]] = []
        visited_count = 0
        while queue:
            current_batch_ids = list(queue)
            queue.clear()
            batches.append([node_map[node_id] for node_id in current_batch_ids])
            visited_count += len(current_batch_ids)
            next_batch_ids = []
            for node_id in current_batch_ids:
                for target in sorted(adj_list[node_id], key=order_index.get):
                    in_degree[target] -= 1
                    if in_degree[target] == 0:
                        next_batch_ids.append(target)
            queue.extend(sorted(next_batch_ids, key=order_index.get))

        if visited_count != len(node_map):
            raise ValidateErrorException("Workflow graph contains a cycle")
        return batches

    @classmethod
    def validate_draft_graph(cls, graph: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(graph, dict):
            return {"nodes": [], "edges": []}

        node_data_dict: dict[str, dict[str, Any]] = {}
        titles: set[str] = set()
        node_type_count = {NodeType.START.value: 0, NodeType.END.value: 0}

        for raw_node in graph.get("nodes", []):
            node = cls._normalize_node(raw_node)
            if node is None:
                continue

            node_id = node["id"]
            title = node.get("title", "").strip()
            node_type = node["node_type"]
            if node_id in node_data_dict or title in titles:
                continue
            if node_type in node_type_count:
                node_type_count[node_type] += 1
                if node_type_count[node_type] > 1:
                    continue

            node_data_dict[node_id] = node
            titles.add(title)

        edge_data_dict: dict[str, dict[str, Any]] = {}
        source_target_pairs: set[tuple[str, str]] = set()
        for raw_edge in graph.get("edges", []):
            edge = cls._normalize_edge(raw_edge, node_data_dict)
            if edge is None:
                continue

            edge_id = edge["id"]
            source_target = (edge["source"], edge["target"])
            if edge_id in edge_data_dict or source_target in source_target_pairs:
                continue

            edge_data_dict[edge_id] = edge
            source_target_pairs.add(source_target)

        return {
            "nodes": list(node_data_dict.values()),
            "edges": list(edge_data_dict.values()),
        }

    @classmethod
    def validate_publish_graph(cls, graph: dict[str, Any] | None) -> dict[str, Any]:
        validated_graph = cls.validate_draft_graph(graph)
        nodes = validated_graph["nodes"]
        edges = validated_graph["edges"]
        node_ids = {node["id"] for node in nodes}

        if not nodes:
            raise ValidateErrorException("Workflow graph must contain nodes")

        start_nodes = [node for node in nodes if node["node_type"] == NodeType.START.value]
        end_nodes = [node for node in nodes if node["node_type"] == NodeType.END.value]
        if len(start_nodes) != 1 or len(end_nodes) != 1:
            raise ValidateErrorException("Workflow graph must contain one start node and one end node")

        if len(nodes) > 1 and not edges:
            raise ValidateErrorException("Workflow graph must contain edges")

        node_map = {node["id"]: node for node in nodes}
        adj_list: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        reverse_adj_list: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        in_degree: dict[str, int] = {node_id: 0 for node_id in node_ids}
        out_degree: dict[str, int] = {node_id: 0 for node_id in node_ids}
        for edge in edges:
            adj_list[edge["source"]].append(edge["target"])
            reverse_adj_list[edge["target"]].append(edge["source"])
            in_degree[edge["target"]] += 1
            out_degree[edge["source"]] += 1

        graph_start_nodes = [node for node in nodes if in_degree[node["id"]] == 0]
        graph_end_nodes = [node for node in nodes if out_degree[node["id"]] == 0]
        if (
            len(graph_start_nodes) != 1
            or graph_start_nodes[0]["node_type"] != NodeType.START.value
            or len(graph_end_nodes) != 1
            or graph_end_nodes[0]["node_type"] != NodeType.END.value
        ):
            raise ValidateErrorException("Workflow graph must have one start entry and one end exit")

        if not cls._is_connected(adj_list, start_nodes[0]["id"], node_ids):
            raise ValidateErrorException("Workflow graph contains unreachable nodes")
        if cls._has_cycle(adj_list, in_degree):
            raise ValidateErrorException("Workflow graph contains a cycle")
        cls._validate_variable_refs(node_map, reverse_adj_list)

        return validated_graph

    def _attach_node_meta(self, session: Session, graph: dict[str, Any], account: Account) -> None:
        for node in graph["nodes"]:
            if node.get("node_type") == NodeType.TOOL.value:
                self._attach_tool_node_meta(session, node, account)
            elif node.get("node_type") == NodeType.DATASET_RETRIEVAL.value:
                dataset_ids = [
                    parsed_id
                    for raw_id in self._ensure_list(node.get("dataset_ids"))
                    if (parsed_id := self._parse_uuid(raw_id)) is not None
                ]
                datasets = (
                    session.query(Dataset)
                    .filter(Dataset.id.in_(dataset_ids), Dataset.account_id == account.id)
                    .all()
                    if dataset_ids
                    else []
                )
                node["meta"] = {
                    "datasets": [
                        {
                            "id": str(dataset.id),
                            "name": dataset.name,
                            "icon": dataset.icon,
                            "description": dataset.description,
                        }
                        for dataset in datasets
                    ]
                }

    def _attach_tool_node_meta(self, session: Session, node: dict[str, Any], account: Account) -> None:
        tool_type = node.get("tool_type") or node.get("type") or ""
        if tool_type == "builtin_tool":
            provider = self.builtin_provider_manager.get_provider(str(node.get("provider_id") or ""))
            if provider is None:
                return

            tool_entity = provider.get_tool_entity(str(node.get("tool_id") or ""))
            if tool_entity is None:
                return

            params = node.get("params") if isinstance(node.get("params"), dict) else {}
            param_keys = {param.name for param in get_tool_params(tool_entity)}
            if set(params.keys()) - param_keys:
                params = {
                    param.name: param.default
                    for param in get_tool_params(tool_entity)
                    if param.default is not None
                }
                node["params"] = params

            provider_entity = provider.provider_entity
            node["meta"] = {
                "type": "builtin_tool",
                "provider": {
                    "id": provider_entity.name,
                    "name": provider_entity.name,
                    "label": provider_entity.label,
                    "icon": f"/builtin-tools/{provider_entity.name}/icon",
                    "description": provider_entity.description,
                },
                "tool": {
                    "id": tool_entity.name,
                    "name": tool_entity.name,
                    "label": tool_entity.label,
                    "description": tool_entity.description,
                    "params": params,
                },
            }
        elif tool_type == "api_tool":
            provider_id = self._parse_uuid(node.get("provider_id"))
            if provider_id is None:
                return
            tool_record = (
                session.query(ApiTool)
                .filter(
                    ApiTool.provider_id == provider_id,
                    ApiTool.name == str(node.get("tool_id") or ""),
                    ApiTool.account_id == account.id,
                )
                .one_or_none()
            )
            if tool_record is None:
                return

            provider = tool_record.provider
            node["meta"] = {
                "type": "api_tool",
                "provider": {
                    "id": str(provider.id),
                    "name": provider.name,
                    "label": provider.name,
                    "icon": provider.icon,
                    "description": provider.description,
                },
                "tool": {
                    "id": str(tool_record.id),
                    "name": tool_record.name,
                    "label": tool_record.name,
                    "description": tool_record.description,
                    "params": {},
                },
            }
        else:
            node["meta"] = {
                "type": "api_tool",
                "provider": {"id": "", "name": "", "label": "", "icon": "", "description": ""},
                "tool": {"id": "", "name": "", "label": "", "description": "", "params": {}},
            }

    @classmethod
    def _normalize_node(cls, raw_node: Any) -> dict[str, Any] | None:
        if not isinstance(raw_node, dict):
            return None

        node_id = cls._parse_uuid(raw_node.get("id"))
        node_type = str(raw_node.get("node_type") or "")
        if node_id is None or node_type not in {item.value for item in NodeType}:
            return None

        node = cls._to_jsonable(dict(raw_node))
        node["id"] = str(node_id)
        node["node_type"] = node_type
        node["title"] = str(node.get("title") or "")
        node["description"] = str(node.get("description") or "")
        node["position"] = cls._normalize_position(node.get("position"))

        if "type" in node and "tool_type" not in node:
            node["tool_type"] = node["type"]

        if node_type == NodeType.LLM.value:
            node.setdefault("prompt", "")
            node.setdefault("model_config", {})
            node["inputs"] = cls._ensure_list(node.get("inputs"))
            node["outputs"] = cls._generated_output("output")
        elif node_type == NodeType.TEMPLATE_TRANSFORM.value:
            node.setdefault("template", "")
            node["inputs"] = cls._ensure_list(node.get("inputs"))
            node["outputs"] = cls._generated_output("output")
        elif node_type == NodeType.TOOL.value:
            node.setdefault("tool_type", "")
            node.setdefault("provider_id", "")
            node.setdefault("tool_id", "")
            node["params"] = node.get("params") if isinstance(node.get("params"), dict) else {}
            node["inputs"] = cls._ensure_list(node.get("inputs"))
            node["outputs"] = cls._generated_output("text")
        elif node_type == NodeType.DATASET_RETRIEVAL.value:
            dataset_ids = cls._ensure_list(node.get("dataset_ids"))
            node["dataset_ids"] = [
                str(parsed_id)
                for raw_id in dataset_ids[:5]
                if (parsed_id := cls._parse_uuid(raw_id)) is not None
            ]
            node.setdefault("retrieval_config", {"retrieval_strategy": "semantic", "k": 4, "score": 0})
            node["inputs"] = cls._ensure_list(node.get("inputs"))
            node["outputs"] = cls._generated_output("combine_documents")
        elif node_type == NodeType.HTTP_REQUEST.value:
            url = node.get("url")
            node["url"] = str(url) if url else None
            method = str(node.get("method") or "get").lower()
            node["method"] = method if method in {"get", "post", "put", "patch", "delete", "head", "options"} else "get"
            node["inputs"] = cls._ensure_list(node.get("inputs"))
            node["outputs"] = [
                {"name": "status_code", "type": "int", "value": {"type": "generated", "content": 0}},
                {"name": "text", "value": {"type": "generated"}},
            ]
        elif node_type == NodeType.CODE.value:
            node.setdefault("code", "def main(params):\n    return params\n")
            node["inputs"] = cls._ensure_list(node.get("inputs"))
            node["outputs"] = cls._ensure_list(node.get("outputs"))
        elif node_type == NodeType.START.value:
            node["inputs"] = cls._ensure_list(node.get("inputs"))
        elif node_type == NodeType.END.value:
            node["outputs"] = cls._ensure_list(node.get("outputs"))

        return node

    @classmethod
    def _normalize_edge(cls, raw_edge: Any, node_data_dict: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        if not isinstance(raw_edge, dict):
            return None

        edge_id = cls._parse_uuid(raw_edge.get("id"))
        source = cls._parse_uuid(raw_edge.get("source"))
        target = cls._parse_uuid(raw_edge.get("target"))
        source_type = str(raw_edge.get("source_type") or "")
        target_type = str(raw_edge.get("target_type") or "")
        if edge_id is None or source is None or target is None:
            return None

        source_id = str(source)
        target_id = str(target)
        source_node = node_data_dict.get(source_id)
        target_node = node_data_dict.get(target_id)
        if source_node is None or target_node is None:
            return None
        if source_type != source_node["node_type"] or target_type != target_node["node_type"]:
            return None

        edge = cls._to_jsonable(dict(raw_edge))
        edge["id"] = str(edge_id)
        edge["source"] = source_id
        edge["target"] = target_id
        edge["source_type"] = source_type
        edge["target_type"] = target_type
        return edge

    @staticmethod
    def _is_connected(adj_list: dict[str, list[str]], start_node_id: str, node_ids: set[str]) -> bool:
        visited = {start_node_id}
        queue: deque[str] = deque([start_node_id])
        while queue:
            node_id = queue.popleft()
            for neighbor in adj_list[node_id]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited == node_ids

    @staticmethod
    def _has_cycle(adj_list: dict[str, list[str]], in_degree: dict[str, int]) -> bool:
        zero_in_degree_nodes: deque[str] = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
        visited_count = 0
        in_degree = dict(in_degree)

        while zero_in_degree_nodes:
            node_id = zero_in_degree_nodes.popleft()
            visited_count += 1
            for neighbor in adj_list[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    zero_in_degree_nodes.append(neighbor)

        return visited_count != len(in_degree)

    @classmethod
    def _validate_variable_refs(
        cls,
        node_map: dict[str, dict[str, Any]],
        reverse_adj_list: dict[str, list[str]],
    ) -> None:
        for node in node_map.values():
            if node["node_type"] == NodeType.START.value:
                continue

            predecessor_ids = cls._predecessor_ids(reverse_adj_list, node["id"])
            for variable in cls._node_reference_variables(node):
                ref = cls._variable_ref_content(variable)
                if ref is None:
                    continue

                ref_node_id = ref["ref_node_id"]
                ref_var_name = ref["ref_var_name"]
                if ref_node_id not in predecessor_ids:
                    raise ValidateErrorException(f"Workflow node [{node['title']}] references a non-upstream node")

                ref_node = node_map.get(ref_node_id)
                if ref_node is None:
                    raise ValidateErrorException(f"Workflow node [{node['title']}] references a missing node")

                ref_output_names = {str(output.get("name")) for output in cls._node_output_variables(ref_node)}
                if ref_var_name not in ref_output_names:
                    raise ValidateErrorException(f"Workflow node [{node['title']}] references a missing variable")

    @staticmethod
    def _node_reference_variables(node: dict[str, Any]) -> list[dict[str, Any]]:
        if node["node_type"] == NodeType.END.value:
            return [item for item in node.get("outputs", []) if isinstance(item, dict)]
        return [item for item in node.get("inputs", []) if isinstance(item, dict)]

    @staticmethod
    def _node_output_variables(node: dict[str, Any]) -> list[dict[str, Any]]:
        if node["node_type"] == NodeType.START.value:
            return [item for item in node.get("inputs", []) if isinstance(item, dict)]
        return [item for item in node.get("outputs", []) if isinstance(item, dict)]

    @staticmethod
    def _variable_ref_content(variable: dict[str, Any]) -> dict[str, str] | None:
        value = variable.get("value") if isinstance(variable.get("value"), dict) else {}
        if value.get("type") != "ref" or not isinstance(value.get("content"), dict):
            return None

        ref_node_id = str(value["content"].get("ref_node_id") or "")
        ref_var_name = str(value["content"].get("ref_var_name") or "")
        if not ref_node_id or not ref_var_name:
            return None
        return {"ref_node_id": ref_node_id, "ref_var_name": ref_var_name}

    @classmethod
    def _predecessor_ids(cls, reverse_adj_list: dict[str, list[str]], node_id: str) -> set[str]:
        visited: set[str] = set()

        def visit(current_node_id: str) -> None:
            for predecessor_id in reverse_adj_list.get(current_node_id, []):
                if predecessor_id in visited:
                    continue
                visited.add(predecessor_id)
                visit(predecessor_id)

        visit(node_id)
        return visited

    @staticmethod
    def _format_workflow_event(node_result: dict[str, Any]) -> str:
        data = {
            "id": str(uuid.uuid4()),
            **node_result,
        }
        return f"event: workflow\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @classmethod
    def _normalize_position(cls, value: Any) -> dict[str, float]:
        if not isinstance(value, dict):
            return {"x": 0, "y": 0}
        return {"x": cls._to_float(value.get("x")), "y": cls._to_float(value.get("y"))}

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _ensure_list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _generated_output(name: str) -> list[dict[str, Any]]:
        return [{"name": name, "value": {"type": "generated"}}]

    @classmethod
    def _to_jsonable(cls, value: Any) -> Any:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, list):
            return [cls._to_jsonable(item) for item in value]
        if isinstance(value, dict):
            return {key: cls._to_jsonable(item) for key, item in value.items()}
        return value

    @staticmethod
    def _parse_uuid(value: Any) -> UUID | None:
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

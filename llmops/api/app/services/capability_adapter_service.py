from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.tools.builtin_tools.entities import ToolParamType
from app.core.tools.builtin_tools.providers import BuiltinProviderManager
from app.core.tools.builtin_tools.runtime import get_tool_params
from app.core.workflow import WorkflowStatus
from app.models.account import Account
from app.models.api_tool import ApiTool
from app.models.workflow import Workflow


@dataclass(frozen=True)
class CapabilityDescriptor:
    name: str
    description: str
    kind: str
    provider: str
    target_ref_type: str
    target_ref_id: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def to_registry_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.kind,
            "provider": self.provider,
            "target_ref_type": self.target_ref_type,
            "target_ref_id": self.target_ref_id,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


@dataclass
class ToolCapabilityAdapter:
    builtin_provider_manager: BuiltinProviderManager = field(default_factory=BuiltinProviderManager)

    def tool_config_to_descriptor(
        self,
        session: Session,
        tool_config: dict[str, Any],
        account: Account,
    ) -> CapabilityDescriptor | None:
        if not isinstance(tool_config, dict):
            return None

        normalized = self._normalize_tool_config(tool_config)
        tool_type = normalized["type"]
        provider_id = normalized["provider_id"]
        tool_id = normalized["tool_id"]

        if tool_type == "builtin_tool":
            provider = self.builtin_provider_manager.get_provider(provider_id)
            if provider is None:
                return None
            tool_entity = provider.get_tool_entity(tool_id)
            if tool_entity is None:
                return None
            return CapabilityDescriptor(
                name=tool_entity.name,
                description=tool_entity.description,
                kind="tool",
                provider=provider.provider_entity.name,
                target_ref_type="builtin_tool",
                target_ref_id=f"{provider.provider_entity.name}/{tool_entity.name}",
                input_schema=self._builtin_tool_schema(tool_entity),
                output_schema={"type": "string"},
                config={"tool_config": normalized},
            )

        if tool_type == "api_tool":
            api_tool = self._get_api_tool(session, provider_id, tool_id, account)
            if api_tool is None:
                return None
            return self.api_tool_to_descriptor(api_tool, normalized)

        return None

    def api_tool_to_descriptor(
        self,
        api_tool: ApiTool,
        normalized_tool_config: dict[str, Any] | None = None,
    ) -> CapabilityDescriptor:
        provider_id = str(api_tool.provider_id)
        tool_config = normalized_tool_config or {
            "type": "api_tool",
            "provider_id": provider_id,
            "tool_id": api_tool.name,
            "params": {},
        }
        return CapabilityDescriptor(
            name=api_tool.name,
            description=api_tool.description,
            kind="tool",
            provider=provider_id,
            target_ref_type="api_tool",
            target_ref_id=str(api_tool.id),
            input_schema=self._api_tool_schema(api_tool.parameters),
            output_schema={"type": "string"},
            config={"tool_config": tool_config},
        )

    def workflow_to_descriptor(self, workflow: Workflow, account: Account) -> CapabilityDescriptor | None:
        if workflow.account_id != account.id or workflow.status != WorkflowStatus.PUBLISHED.value:
            return None
        return CapabilityDescriptor(
            name=workflow.tool_call_name,
            description=workflow.description or workflow.name,
            kind="workflow",
            provider="workflow",
            target_ref_type="workflow",
            target_ref_id=str(workflow.id),
            input_schema=self.workflow_input_schema(workflow.graph or {}),
            output_schema={"type": "object"},
            config={"workflow_id": str(workflow.id)},
        )

    def dataset_collection_to_descriptor(
        self,
        dataset_ids: list[Any],
        retrieval_config: dict[str, Any] | None,
        app_config: dict[str, Any],
    ) -> CapabilityDescriptor | None:
        valid_dataset_ids = [str(parsed_id) for value in dataset_ids or [] if (parsed_id := self._parse_uuid(value))]
        if not valid_dataset_ids:
            return None
        return CapabilityDescriptor(
            name="dataset_retrieval",
            description="Retrieve relevant text segments from configured datasets.",
            kind="knowledge_base",
            provider="dataset",
            target_ref_type="dataset_collection",
            target_ref_id=",".join(valid_dataset_ids),
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
            output_schema={
                "type": "array",
                "items": {"type": "object"},
            },
            config={
                "app_config": app_config,
                "dataset_ids": valid_dataset_ids,
                "retrieval_config": retrieval_config or {},
            },
        )

    def _get_api_tool(
        self,
        session: Session,
        provider_id: str,
        tool_id: str,
        account: Account,
    ) -> ApiTool | None:
        provider_uuid = self._parse_uuid(provider_id)
        if provider_uuid is None:
            return None
        return (
            session.query(ApiTool)
            .filter(
                ApiTool.provider_id == provider_uuid,
                ApiTool.name == tool_id,
                ApiTool.account_id == account.id,
            )
            .one_or_none()
        )

    @classmethod
    def _normalize_tool_config(cls, tool_config: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": str(tool_config.get("type") or ""),
            "provider_id": str(tool_config.get("provider_id") or tool_config.get("provider", {}).get("id") or ""),
            "tool_id": cls._tool_config_name(tool_config),
            "params": tool_config.get("params") if isinstance(tool_config.get("params"), dict) else {},
        }

    @staticmethod
    def _tool_config_name(tool_config: dict[str, Any]) -> str:
        return str(
            tool_config.get("tool_id")
            or tool_config.get("tool_name")
            or tool_config.get("name")
            or tool_config.get("tool", {}).get("id")
            or tool_config.get("tool", {}).get("name")
            or ""
        )

    @classmethod
    def _builtin_tool_schema(cls, tool_entity) -> dict[str, Any]:
        properties = {}
        required = []
        for param in get_tool_params(tool_entity):
            properties[param.name] = {
                "type": cls._json_schema_type(param.type),
                "description": param.label,
            }
            if param.default is not None:
                properties[param.name]["default"] = param.default
            if param.required:
                required.append(param.name)
        return {"type": "object", "properties": properties, "required": required}

    @classmethod
    def _api_tool_schema(cls, parameters: list[dict[str, Any]]) -> dict[str, Any]:
        properties = {}
        required = []
        for parameter in parameters or []:
            name = str(parameter.get("name") or "")
            if not name:
                continue
            properties[name] = {
                "type": cls._json_schema_type(parameter.get("type")),
                "description": str(parameter.get("description") or ""),
            }
            if parameter.get("required", True):
                required.append(name)
        return {"type": "object", "properties": properties, "required": required}

    @classmethod
    def workflow_input_schema(cls, graph: dict[str, Any]) -> dict[str, Any]:
        start_node = next((node for node in graph.get("nodes", []) if node.get("node_type") == "start"), {})
        properties = {}
        required = []
        for variable in start_node.get("inputs") if isinstance(start_node.get("inputs"), list) else []:
            name = str(variable.get("name") or "")
            if not name:
                continue
            properties[name] = {
                "type": cls._json_schema_type(variable.get("type")),
                "description": str(variable.get("label") or variable.get("description") or name),
            }
            if variable.get("required", True):
                required.append(name)
        return {"type": "object", "properties": properties, "required": required}

    @staticmethod
    def _json_schema_type(value: Any) -> str:
        type_name = str(value.value if isinstance(value, ToolParamType) else value or "string").lower()
        if type_name in {"int", "integer"}:
            return "integer"
        if type_name in {"float", "number"}:
            return "number"
        if type_name in {"bool", "boolean"}:
            return "boolean"
        if type_name == "array":
            return "array"
        if type_name == "object":
            return "object"
        return "string"

    @staticmethod
    def _parse_uuid(value: Any):
        from uuid import UUID

        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

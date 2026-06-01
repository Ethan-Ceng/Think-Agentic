from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.core.app import DEFAULT_APP_CONFIG
from app.models.app import App


@dataclass(frozen=True)
class WorkerAgentDescriptor:
    name: str
    description: str
    icon: str
    status: str
    target_ref_type: str
    target_ref_id: str
    model_config: dict[str, Any]
    prompt_config: dict[str, Any]
    worker_config: dict[str, Any]
    capability_bindings: list[dict[str, Any]] = field(default_factory=list)
    runtime_type: str = "worker"
    product_category: str = "custom"
    visibility_scope: dict[str, Any] = field(default_factory=dict)

    def to_agent_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "runtime_type": self.runtime_type,
            "product_category": self.product_category,
            "status": self.status,
            "visibility_scope": self.visibility_scope,
            "target_ref_type": self.target_ref_type,
            "target_ref_id": self.target_ref_id,
        }

    def to_version_payload(self) -> dict[str, Any]:
        return {
            "model_config": self.model_config,
            "prompt_config": self.prompt_config,
            "router_config": {},
            "worker_config": self.worker_config,
            "capability_bindings": self.capability_bindings,
            "policies": {},
            "output_schema": {"type": "object"},
        }


@dataclass
class LegacyAppWorkerAdapter:
    def app_to_worker_descriptor(self, app: App, config: Any) -> WorkerAgentDescriptor:
        config_dict = self._config_to_dict(config)
        return WorkerAgentDescriptor(
            name=app.name,
            description=app.description or "",
            icon=app.icon or "",
            status=str(app.status or "draft"),
            target_ref_type="app",
            target_ref_id=str(app.id),
            model_config=config_dict["model_config"],
            prompt_config=self._prompt_config(config_dict),
            worker_config=self._worker_config(config_dict),
            capability_bindings=self._capability_bindings(config_dict),
            visibility_scope={"account_id": str(app.account_id)},
        )

    def assistant_agent_to_worker_descriptor(
        self,
        assistant_agent_id: UUID,
        config: dict[str, Any],
    ) -> WorkerAgentDescriptor:
        config_dict = self._config_to_dict(config)
        return WorkerAgentDescriptor(
            name="Assistant Agent",
            description="Platform assistant agent",
            icon="",
            status="published",
            target_ref_type="assistant_agent",
            target_ref_id=str(assistant_agent_id),
            model_config=config_dict["model_config"],
            prompt_config=self._prompt_config(config_dict),
            worker_config=self._worker_config(config_dict),
            capability_bindings=self._capability_bindings(config_dict),
            product_category="assistant",
            visibility_scope={"system": True},
        )

    @classmethod
    def _config_to_dict(cls, config: Any) -> dict[str, Any]:
        if isinstance(config, dict):
            raw = config
        else:
            raw = {
                "model_config": getattr(config, "model_config", None),
                "dialog_round": getattr(config, "dialog_round", None),
                "preset_prompt": getattr(config, "preset_prompt", None),
                "tools": getattr(config, "tools", None),
                "workflows": getattr(config, "workflows", None),
                "datasets": getattr(config, "datasets", None),
                "retrieval_config": getattr(config, "retrieval_config", None),
                "long_term_memory": getattr(config, "long_term_memory", None),
                "opening_statement": getattr(config, "opening_statement", None),
                "opening_questions": getattr(config, "opening_questions", None),
                "speech_to_text": getattr(config, "speech_to_text", None),
                "text_to_speech": getattr(config, "text_to_speech", None),
                "suggested_after_answer": getattr(config, "suggested_after_answer", None),
                "review_config": getattr(config, "review_config", None),
            }

        normalized = deepcopy(DEFAULT_APP_CONFIG)
        normalized.update({key: value for key, value in raw.items() if value is not None})
        normalized["tools"] = normalized["tools"] if isinstance(normalized["tools"], list) else []
        normalized["workflows"] = [str(item) for item in normalized["workflows"] or []]
        normalized["datasets"] = [str(item) for item in normalized["datasets"] or []]
        return normalized

    @staticmethod
    def _prompt_config(config: dict[str, Any]) -> dict[str, Any]:
        return {
            "preset_prompt": config.get("preset_prompt") or "",
            "opening_statement": config.get("opening_statement") or "",
            "opening_questions": config.get("opening_questions") or [],
            "review_config": config.get("review_config") or {},
        }

    @staticmethod
    def _worker_config(config: dict[str, Any]) -> dict[str, Any]:
        return {
            "dialog_round": config.get("dialog_round", 3),
            "retrieval_config": config.get("retrieval_config") or {},
            "long_term_memory": config.get("long_term_memory") or {},
            "speech_to_text": config.get("speech_to_text") or {},
            "text_to_speech": config.get("text_to_speech") or {},
            "suggested_after_answer": config.get("suggested_after_answer") or {},
        }

    @classmethod
    def _capability_bindings(cls, config: dict[str, Any]) -> list[dict[str, Any]]:
        bindings = []
        for tool_config in config.get("tools", []) or []:
            if not isinstance(tool_config, dict):
                continue
            normalized = cls._normalize_tool_config(tool_config)
            target_ref_type = normalized["type"]
            target_ref_id = (
                f"{normalized['provider_id']}/{normalized['tool_id']}"
                if target_ref_type == "builtin_tool"
                else normalized["tool_id"]
            )
            bindings.append(
                {
                    "type": "tool",
                    "target_ref_type": target_ref_type,
                    "target_ref_id": target_ref_id,
                    "name": normalized["tool_id"],
                    "params": normalized["params"],
                    "enabled": True,
                }
            )

        for workflow_id in config.get("workflows", []) or []:
            bindings.append(
                {
                    "type": "workflow",
                    "target_ref_type": "workflow",
                    "target_ref_id": str(workflow_id),
                    "name": str(workflow_id),
                    "params": {},
                    "enabled": True,
                }
            )

        retrieval_config = config.get("retrieval_config") or {}
        for dataset_id in config.get("datasets", []) or []:
            bindings.append(
                {
                    "type": "knowledge_base",
                    "target_ref_type": "dataset",
                    "target_ref_id": str(dataset_id),
                    "name": str(dataset_id),
                    "params": {"retrieval_config": retrieval_config},
                    "enabled": True,
                }
            )
        return bindings

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

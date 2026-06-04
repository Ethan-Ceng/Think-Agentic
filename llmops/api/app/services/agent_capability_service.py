import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import FailException, NotFoundException
from app.domain.agent_runtime.capability import (
    WORKER_CAPABILITY_SCHEMA_VERSION,
    normalize_routing_policy,
    validate_routing_policy,
)
from app.models.account import Account
from app.models.agent import Agent, AgentVersion
from app.services.language_model_service import LanguageModelService


@dataclass
class AgentCapabilityService:
    language_model_service: LanguageModelService = field(default_factory=LanguageModelService)

    def get_agent_capability_summary(
        self,
        session: Session,
        agent_id: uuid.UUID,
        account: Account,
    ) -> dict[str, Any]:
        agent = self._get_worker_agent(session, agent_id, account)
        summary = self.ensure_worker_capability_summary(session, agent, account=account)
        version = self._active_version(session, agent)
        return self._summary_response(agent, version, summary)

    def refresh_agent_capability_summary(
        self,
        session: Session,
        agent_id: uuid.UUID,
        account: Account,
        *,
        preserve_manual_overrides: bool = True,
    ) -> dict[str, Any]:
        agent = self._get_worker_agent(session, agent_id, account)
        version = self._active_version(session, agent)
        if version is None:
            raise FailException("Worker agent has no active version")
        existing = self._stored_summary(version)
        manual_overrides = existing.get("manual_overrides", {}) if preserve_manual_overrides else {}
        summary = self.build_summary_from_agent_version(
            agent=agent,
            version=version,
            session=session,
            account=account,
            manual_overrides=manual_overrides,
        )
        self._save_summary(session, version, summary)
        return self._summary_response(agent, version, summary, refreshed=True)

    def patch_agent_capability_summary(
        self,
        session: Session,
        agent_id: uuid.UUID,
        account: Account,
        *,
        manual_overrides: dict[str, Any],
    ) -> dict[str, Any]:
        agent = self._get_worker_agent(session, agent_id, account)
        version = self._active_version(session, agent)
        if version is None:
            raise FailException("Worker agent has no active version")
        existing = self._stored_summary(version)
        base_summary = existing or self.build_summary_from_agent_version(
            agent=agent,
            version=version,
            session=session,
            account=account,
        )
        summary = self._apply_manual_overrides(base_summary, manual_overrides)
        self._save_summary(session, version, summary)
        return self._summary_response(agent, version, summary)

    def ensure_worker_capability_summary(
        self,
        session: Session,
        agent: Agent,
        *,
        account: Account | None = None,
    ) -> dict[str, Any]:
        version = self._active_version(session, agent)
        if version is None:
            return self.build_summary_from_payload(agent_payload=self._agent_payload(agent), version_payload={})

        existing = self._stored_summary(version)
        if existing:
            return existing

        summary = self.build_summary_from_agent_version(
            agent=agent,
            version=version,
            session=session,
            account=account,
        )
        self._save_summary(session, version, summary)
        return summary

    def attach_summary_to_version_payload(
        self,
        *,
        agent_payload: dict[str, Any],
        version_payload: dict[str, Any],
        session: Session | None = None,
        account: Account | None = None,
        preserve_manual_overrides_from: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = deepcopy(version_payload)
        existing = preserve_manual_overrides_from if isinstance(preserve_manual_overrides_from, dict) else {}
        manual_overrides = (
            existing.get("manual_overrides", {}) if isinstance(existing.get("manual_overrides"), dict) else {}
        )
        summary = self.build_summary_from_payload(
            agent_payload=agent_payload,
            version_payload=payload,
            session=session,
            account=account,
            manual_overrides=manual_overrides,
        )
        worker_config = dict(payload.get("worker_config") or {})
        worker_config["capability_summary"] = summary
        payload["worker_config"] = worker_config
        return payload

    def build_summary_from_agent_version(
        self,
        *,
        agent: Agent,
        version: AgentVersion,
        session: Session | None = None,
        account: Account | None = None,
        manual_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.build_summary_from_payload(
            agent_payload=self._agent_payload(agent),
            version_payload={
                "model_config": version.model_config or {},
                "worker_config": version.worker_config or {},
                "capability_bindings": version.capability_bindings or [],
            },
            session=session,
            account=account,
            manual_overrides=manual_overrides,
        )

    def build_summary_from_payload(
        self,
        *,
        agent_payload: dict[str, Any],
        version_payload: dict[str, Any],
        session: Session | None = None,
        account: Account | None = None,
        manual_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw_model_config = version_payload.get("model_config")
        raw_worker_config = version_payload.get("worker_config")
        raw_bindings = version_payload.get("capability_bindings")
        model_config = raw_model_config if isinstance(raw_model_config, dict) else {}
        worker_config = raw_worker_config if isinstance(raw_worker_config, dict) else {}
        bindings = raw_bindings if isinstance(raw_bindings, list) else []
        executor_type = str(
            worker_config.get("executor_type")
            or worker_config.get("execution_agent_type")
            or self._executor_type_from_target(agent_payload.get("target_ref_type"))
        )
        model_features = self._model_features(model_config, session=session, account=account)
        tool_names = self._tool_names(bindings)
        skills = self._skills(bindings)
        semantic_tags = self._semantic_tags(
            agent_payload=agent_payload,
            bindings=bindings,
            model_features=model_features,
            tool_names=tool_names,
        )
        input_modalities = ["text/plain"]
        if "image_input" in model_features:
            input_modalities.extend(["image/png", "image/jpeg", "image/webp"])

        summary = {
            "schema_version": WORKER_CAPABILITY_SCHEMA_VERSION,
            "executor_type": executor_type,
            "input_modalities": self._unique(input_modalities),
            "output_modalities": ["text/plain"],
            "semantic_tags": semantic_tags,
            "skills": skills,
            "tool_names": tool_names,
            "model_features": model_features,
            "constraints": {
                "requires_credentials": any(
                    str(binding.get("target_ref_type") or "") in {"builtin_tool", "api_tool"}
                    for binding in bindings
                    if isinstance(binding, dict)
                ),
                "requires_approval": False,
                "max_timeout_seconds": 120,
            },
            "manual_overrides": {},
            "generated_at": int(time.time()),
        }
        if manual_overrides:
            summary = self._apply_manual_overrides(summary, manual_overrides)
        return summary

    def validate_routing_policy(self, routing_policy: dict[str, Any] | None) -> dict[str, Any]:
        normalized = normalize_routing_policy(routing_policy)
        valid, errors, warnings = validate_routing_policy(normalized)
        return {"valid": valid, "routing_policy": normalized, "errors": errors, "warnings": warnings}

    def _model_features(
        self,
        model_config: dict[str, Any],
        *,
        session: Session | None,
        account: Account | None,
    ) -> list[str]:
        explicit = model_config.get("features")
        if isinstance(explicit, list):
            return self._unique([self._feature_value(item) for item in explicit])
        try:
            model = self.language_model_service.load_language_model(model_config, session=session, account=account)
        except Exception:  # noqa: BLE001
            return []
        return self._unique([self._feature_value(item) for item in model.features])

    def _stored_summary(self, version: AgentVersion) -> dict[str, Any]:
        worker_config = version.worker_config if isinstance(version.worker_config, dict) else {}
        summary = worker_config.get("capability_summary")
        if not isinstance(summary, dict):
            return {}
        if summary.get("schema_version") != WORKER_CAPABILITY_SCHEMA_VERSION:
            return {}
        return deepcopy(summary)

    def _save_summary(self, session: Session, version: AgentVersion, summary: dict[str, Any]) -> None:
        worker_config = dict(version.worker_config or {})
        worker_config["capability_summary"] = summary
        version.worker_config = worker_config
        session.flush()
        session.refresh(version)

    def _active_version(self, session: Session, agent: Agent) -> AgentVersion | None:
        version_id = agent.published_version_id or agent.draft_version_id
        if version_id is None:
            return None
        return session.get(AgentVersion, version_id)

    def _get_worker_agent(self, session: Session, agent_id: uuid.UUID, account: Account) -> Agent:
        agent = session.get(Agent, agent_id)
        if agent is None or agent.tenant_id != account.id or agent.runtime_type != "worker":
            raise NotFoundException("Worker agent not found")
        return agent

    @staticmethod
    def _summary_response(
        agent: Agent,
        version: AgentVersion | None,
        summary: dict[str, Any],
        *,
        refreshed: bool = False,
    ) -> dict[str, Any]:
        return {
            "agent_id": str(agent.id),
            "version_id": str(version.id) if version is not None else "",
            "refreshed": refreshed,
            "capability_summary": summary,
            "warnings": [],
        }

    @staticmethod
    def _agent_payload(agent: Agent) -> dict[str, Any]:
        return {
            "id": str(agent.id),
            "name": agent.name,
            "description": agent.description or "",
            "runtime_type": agent.runtime_type,
            "product_category": agent.product_category,
            "target_ref_type": agent.target_ref_type,
            "target_ref_id": agent.target_ref_id,
        }

    @staticmethod
    def _executor_type_from_target(target_ref_type: Any) -> str:
        if str(target_ref_type or "") == "a2a_agent":
            return "a2a"
        return "app"

    @classmethod
    def _apply_manual_overrides(cls, summary: dict[str, Any], manual_overrides: dict[str, Any]) -> dict[str, Any]:
        updated = deepcopy(summary)
        clean_overrides = manual_overrides if isinstance(manual_overrides, dict) else {}
        list_fields = {
            "input_modalities",
            "output_modalities",
            "semantic_tags",
            "tool_names",
            "model_features",
        }
        for field_name in list_fields:
            value = clean_overrides.get(field_name)
            if isinstance(value, list):
                updated[field_name] = cls._unique([str(item) for item in value if str(item).strip()])
        if isinstance(clean_overrides.get("skills"), list):
            updated["skills"] = [item for item in clean_overrides["skills"] if isinstance(item, dict)]
        if isinstance(clean_overrides.get("constraints"), dict):
            updated["constraints"] = {**dict(updated.get("constraints") or {}), **clean_overrides["constraints"]}
        updated["manual_overrides"] = deepcopy(clean_overrides)
        return updated

    @classmethod
    def _semantic_tags(
        cls,
        *,
        agent_payload: dict[str, Any],
        bindings: list[dict[str, Any]],
        model_features: list[str],
        tool_names: list[str],
    ) -> list[str]:
        tags: list[str] = []
        text_parts = [
            str(agent_payload.get("name") or ""),
            str(agent_payload.get("description") or ""),
            str(agent_payload.get("target_ref_type") or ""),
            *tool_names,
        ]
        if "image_input" in model_features:
            tags.append("vision")

        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            binding_type = str(binding.get("type") or "")
            target_ref_type = str(binding.get("target_ref_type") or "")
            target_ref_id = str(binding.get("target_ref_id") or "")
            text_parts.extend([binding_type, target_ref_type, target_ref_id, str(binding.get("name") or "")])
            if binding_type == "workflow":
                tags.append("workflow")
            if binding_type == "knowledge_base":
                tags.append("document_qa")
            if target_ref_type == "api_tool":
                tags.append("api")
            if binding_type == "tool":
                tags.append("tool")

        text = " ".join(text_parts).lower()
        keyword_tags = {
            "search": [
                "search",
                "serper",
                "duckduckgo",
                "wikipedia",
                "google_serper",
                "web",
                "news",
                "搜索",
                "网页",
                "来源",
                "最新",
            ],
            "weather": ["weather", "gaode", "forecast", "alert", "天气", "预警"],
            "time": ["time", "current_time", "日期", "时间"],
            "image_generation": ["dalle", "image_generation", "图片生成"],
            "document_qa": ["dataset", "knowledge", "retrieval", "document", "知识库", "文档"],
        }
        for tag, keywords in keyword_tags.items():
            if any(keyword in text for keyword in keywords):
                tags.append(tag)
        return cls._unique(tags)

    @classmethod
    def _skills(cls, bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        for binding in bindings:
            if not isinstance(binding, dict) or binding.get("enabled") is False:
                continue
            name = str(binding.get("name") or binding.get("target_ref_id") or "").strip()
            if not name:
                continue
            binding_type = str(binding.get("type") or "capability")
            skills.append(
                {
                    "id": str(binding.get("target_ref_id") or name),
                    "name": name,
                    "description": str(binding.get("description") or ""),
                    "tags": cls._unique([binding_type, str(binding.get("target_ref_type") or "")]),
                    "input_modes": ["text/plain"],
                    "output_modes": ["text/plain"],
                }
            )
        return skills

    @classmethod
    def _tool_names(cls, bindings: list[dict[str, Any]]) -> list[str]:
        names: list[str] = []
        for binding in bindings:
            if not isinstance(binding, dict) or binding.get("enabled") is False:
                continue
            if str(binding.get("type") or "") != "tool":
                continue
            raw_name = str(binding.get("name") or binding.get("target_ref_id") or "")
            if "/" in raw_name:
                raw_name = raw_name.rsplit("/", 1)[-1]
            if raw_name:
                names.append(raw_name)
        return cls._unique(names)

    @staticmethod
    def _feature_value(value: Any) -> str:
        return str(getattr(value, "value", value) or "")

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

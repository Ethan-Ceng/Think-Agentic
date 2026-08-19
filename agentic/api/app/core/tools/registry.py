#!/usr/bin/env python
# -*- coding: utf-8 -*-
import copy
import inspect
from typing import Any, Dict, Iterable, List, Optional

from app.core.entities.tool_config import ToolBinding, ToolConfig
from app.core.tools.api import api_risk_for_method, build_api_tool_definitions
from app.core.tools.base import BaseTool
from app.core.tools.builtin import (
    BUILTIN_TOOL_GROUPS,
    BuiltinToolGroup,
    generality_for_builtin_function,
    label_for_builtin_function,
    risk_for_builtin_function,
)
from app.schemas.tool_config import (
    ProviderDescriptor,
    ToolDescriptor,
    ToolRegistration,
)


class ToolRegistry:
    """Collect built-in and registered tool metadata."""

    def __init__(
        self,
        groups: Iterable[BuiltinToolGroup] | None = None,
        tool_config: ToolConfig | None = None,
    ) -> None:
        self._groups: List[BuiltinToolGroup] = list(groups or BUILTIN_TOOL_GROUPS)
        self._tool_config = tool_config
        self._builtin_descriptors: Optional[List[ToolDescriptor]] = None
        self._runtime_descriptors: List[ToolDescriptor] = []
        self._provider_descriptors: Dict[str, ProviderDescriptor] = {}

    def register_provider_descriptors(
        self,
        descriptors: Iterable[ProviderDescriptor],
    ) -> None:
        """Register safe offline Provider metadata for this Agent runtime."""
        for descriptor in descriptors:
            self._provider_descriptors[descriptor.provider_id] = descriptor.model_copy(
                deep=True
            )

    def list_provider_descriptors(
        self,
        tool_config: ToolConfig | None = None,
    ) -> List[ProviderDescriptor]:
        """List configured and inferred providers without runtime configuration."""
        effective_config = tool_config or self._tool_config or ToolConfig()
        providers: Dict[str, ProviderDescriptor] = {
            key: value.model_copy(deep=True)
            for key, value in self._provider_descriptors.items()
        }
        for descriptor in self.list_descriptors(effective_config):
            providers.setdefault(
                descriptor.provider_id,
                ProviderDescriptor(
                    provider_id=descriptor.provider_id,
                    provider_type=descriptor.source_type,
                    label=descriptor.provider_label,
                    description=descriptor.description,
                    capability_groups=[descriptor.group],
                    semantic_tags=[descriptor.source_type, descriptor.group],
                    metadata_trust=(
                        "platform_static"
                        if descriptor.provider_id.startswith("builtin.")
                        else "untrusted_configuration"
                    ),
                    enabled=descriptor.enabled_by_default,
                    credential_state=(
                        "configured"
                        if descriptor.requires_credentials
                        else "not_required"
                    ),
                    snapshot_state=(
                        "missing" if descriptor.source_type == "mcp" else "fresh"
                    ),
                ),
            )
        return sorted(providers.values(), key=lambda item: item.provider_id)

    def register_runtime_tool(
        self,
        runtime_tool: BaseTool,
        *,
        provider_id: str | None = None,
        provider_label: str = "Skill draft",
        group: str | None = None,
        executor_type: str = "builtin",
        source_type: str | None = None,
        execution_backend: str | None = None,
        execution_class: str | None = None,
        generality: str = "specialized",
        cost_class: str | None = None,
        category: str = "Skills",
        requires_sandbox: bool = False,
        requires_browser: bool = False,
        requires_credentials: bool = False,
    ) -> None:
        """Register descriptors only in this Run's registry."""
        provider_id = provider_id or f"builtin.{runtime_tool.name}"
        group = group or runtime_tool.name
        source_type = source_type or (
            executor_type if executor_type in {"api", "mcp", "a2a"} else "builtin"
        )
        execution_backend = execution_backend or (
            "sandbox_browser"
            if requires_browser
            else "sandbox"
            if requires_sandbox
            else "delegation"
            if source_type == "a2a"
            else "external_provider"
            if source_type == "mcp"
            else "remote_http"
            if source_type == "api"
            else "in_process"
        )
        execution_class = execution_class or (
            "sandbox_local"
            if execution_backend in {"sandbox", "sandbox_browser"}
            else "delegation"
            if execution_backend == "delegation"
            else "external_read"
        )
        cost_class = cost_class or (
            "high"
            if execution_backend == "sandbox_browser"
            else "medium"
            if execution_backend != "in_process"
            else "low"
        )
        self.register_runtime_schemas(
            runtime_tool.get_tools(),
            provider_id=provider_id,
            provider_label=provider_label,
            group=group,
            executor_type=executor_type,
            source_type=source_type,
            execution_backend=execution_backend,
            execution_class=execution_class,
            generality=generality,
            cost_class=cost_class,
            category=category,
            requires_sandbox=requires_sandbox,
            requires_browser=requires_browser,
            requires_credentials=requires_credentials,
        )

    def register_runtime_schemas(
        self,
        schemas: Iterable[Dict[str, Any]],
        *,
        provider_id: str,
        provider_label: str,
        group: str,
        executor_type: str,
        source_type: str,
        execution_backend: str,
        execution_class: str,
        generality: str = "specialized",
        cost_class: str = "medium",
        category: str,
        requires_sandbox: bool = False,
        requires_browser: bool = False,
        requires_credentials: bool = False,
    ) -> None:
        """Register already-normalized runtime schemas under their real Provider."""
        existing = {item.function_name for item in self._runtime_descriptors}
        for schema in schemas:
            function_name = schema["function"]["name"]
            if function_name in existing:
                continue
            existing.add(function_name)
            self._runtime_descriptors.append(
                ToolDescriptor(
                    tool_id=f"{provider_id}.{function_name}",
                    function_name=function_name,
                    provider_id=provider_id,
                    provider_label=provider_label,
                    group=group,
                    executor_type=executor_type,
                    source_type=source_type,
                    execution_backend=execution_backend,
                    resource_requirements=self._resource_requirements(
                        execution_backend=execution_backend,
                        requires_sandbox=requires_sandbox,
                        requires_browser=requires_browser,
                        requires_credentials=requires_credentials,
                    ),
                    execution_class=execution_class,
                    generality=generality,
                    cost_class=cost_class,
                    label=function_name,
                    description=schema["function"].get("description", ""),
                    schema=schema,
                    category=category,
                    risk_level="high" if function_name == "skill_draft_write" else "low",
                    requires_sandbox=requires_sandbox,
                    requires_browser=requires_browser,
                    requires_credentials=requires_credentials,
                    enabled_by_default=True,
                )
            )

    def replace_runtime_schemas(
        self,
        schemas: Iterable[Dict[str, Any]],
        *,
        provider_id: str,
        provider_label: str,
        group: str,
        executor_type: str,
        source_type: str,
        execution_backend: str,
        execution_class: str,
        generality: str = "specialized",
        cost_class: str = "medium",
        category: str,
        requires_sandbox: bool = False,
        requires_browser: bool = False,
        requires_credentials: bool = False,
    ) -> None:
        """Replace one Provider's active runtime Schema view atomically."""
        self._runtime_descriptors = [
            descriptor
            for descriptor in self._runtime_descriptors
            if not (
                descriptor.provider_id == provider_id
                and descriptor.group == group
            )
        ]
        self.register_runtime_schemas(
            schemas,
            provider_id=provider_id,
            provider_label=provider_label,
            group=group,
            executor_type=executor_type,
            source_type=source_type,
            execution_backend=execution_backend,
            execution_class=execution_class,
            generality=generality,
            cost_class=cost_class,
            category=category,
            requires_sandbox=requires_sandbox,
            requires_browser=requires_browser,
            requires_credentials=requires_credentials,
        )

    def register_group(self, group: BuiltinToolGroup) -> None:
        self._groups.append(group)
        self._builtin_descriptors = None

    def list_descriptors(self, tool_config: ToolConfig | None = None) -> List[ToolDescriptor]:
        descriptors = [descriptor.model_copy(deep=True) for descriptor in self._list_builtin_descriptors()]
        descriptors.extend(
            descriptor.model_copy(deep=True) for descriptor in self._runtime_descriptors
        )
        descriptors.extend(self._build_api_descriptors(tool_config or self._tool_config))
        return descriptors

    def get_by_function_name(
        self,
        function_name: str,
        tool_config: ToolConfig | None = None,
    ) -> Optional[ToolDescriptor]:
        for descriptor in self.list_descriptors(tool_config):
            if descriptor.function_name == function_name:
                return descriptor
        return None

    def get_by_tool_id(
        self,
        tool_id: str,
        tool_config: ToolConfig | None = None,
    ) -> Optional[ToolDescriptor]:
        for descriptor in self.list_descriptors(tool_config):
            if descriptor.tool_id == tool_id:
                return descriptor
        return None

    def list_registrations(self, tool_config: ToolConfig | None = None) -> List[ToolRegistration]:
        builtin_ids = {group.provider_id for group in self._groups}
        registrations = [
            ToolRegistration(
                registration_id=group.provider_id,
                provider_id=group.provider_id,
                provider_label=group.provider_label,
                source_type="builtin",
                executor_type=group.executor_type,
                group=group.group,
                category=group.category,
                description=group.description,
                enabled=True,
                builtin=True,
                editable=False,
                requires_sandbox=group.requires_sandbox,
                requires_browser=group.requires_browser,
                requires_credentials=group.requires_credentials,
            )
            for group in self._groups
        ]

        if tool_config:
            registrations.extend(
                ToolRegistration.model_validate(registration.model_dump(mode="json"))
                for registration in tool_config.registrations.values()
                if registration.registration_id not in builtin_ids
            )

        return sorted(registrations, key=lambda item: (item.source_type, item.provider_id))

    def list_capability_catalog(
        self,
        tool_config: ToolConfig | None = None,
    ) -> List[Dict[str, Any]]:
        """Return compact enabled capability metadata without parameter schemas."""
        effective_config = tool_config or self._tool_config or ToolConfig()
        registrations = {
            registration.group: registration
            for registration in self.list_registrations(effective_config)
            if registration.enabled
        }
        catalog: Dict[str, Dict[str, Any]] = {}
        for provider in self.list_provider_descriptors(effective_config):
            if not provider.enabled:
                continue
            provider_summary = {
                "provider_id": provider.provider_id,
                "provider_type": provider.provider_type,
                "label": provider.label,
                "description": provider.description,
                "semantic_tags": list(provider.semantic_tags),
                "metadata_trust": provider.metadata_trust,
                "credential_state": provider.credential_state,
                "snapshot_state": provider.snapshot_state,
                "health_state": provider.health_state,
            }
            for group in provider.capability_groups:
                entry = catalog.setdefault(
                    group,
                    {
                        "group": group,
                        "description": provider.description,
                        "requires_sandbox": False,
                        "requires_browser": False,
                        "providers": [],
                        "tools": [],
                    },
                )
                entry["providers"].append(provider_summary)
        for descriptor in self.apply_config(effective_config, effective=True):
            if not descriptor.enabled:
                continue
            registration = registrations.get(descriptor.group)
            entry = catalog.setdefault(
                descriptor.group,
                {
                    "group": descriptor.group,
                    "description": (
                        registration.description
                        if registration and registration.description
                        else descriptor.description
                    ),
                    "requires_sandbox": False,
                    "requires_browser": False,
                    "providers": [],
                    "tools": [],
                },
            )
            entry["requires_sandbox"] = bool(
                entry["requires_sandbox"] or descriptor.requires_sandbox
            )
            entry["requires_browser"] = bool(
                entry["requires_browser"] or descriptor.requires_browser
            )
            entry["tools"].append(
                {
                    "tool_id": descriptor.tool_id,
                    "function_name": descriptor.function_name,
                    "provider_id": descriptor.provider_id,
                    "source_type": descriptor.source_type,
                    "execution_backend": descriptor.execution_backend,
                    "generality": descriptor.generality,
                    "cost_class": descriptor.cost_class,
                    "description": descriptor.description,
                }
            )
        for entry in catalog.values():
            entry["providers"].sort(key=lambda item: item["provider_id"])
            entry["tools"].sort(key=lambda item: item["tool_id"])
        return [catalog[group] for group in sorted(catalog)]

    def provider_ids(self, tool_config: ToolConfig | None = None) -> set[str]:
        effective_config = tool_config or self._tool_config or ToolConfig()
        descriptor_ids = {
            descriptor.provider_id
            for descriptor in self.apply_config(effective_config, effective=True)
            if descriptor.enabled
        }
        descriptor_ids.update(
            provider.provider_id
            for provider in self.list_provider_descriptors(effective_config)
            if provider.enabled
        )
        return descriptor_ids

    def tool_ids(self, tool_config: ToolConfig | None = None) -> set[str]:
        effective_config = tool_config or self._tool_config or ToolConfig()
        return {
            descriptor.tool_id
            for descriptor in self.apply_config(effective_config, effective=True)
            if descriptor.enabled
        }

    def capability_groups_for_provider_ids(
        self,
        provider_ids: Iterable[str],
        tool_config: ToolConfig | None = None,
    ) -> set[str]:
        """Return capability groups represented by the selected Providers."""
        selected = set(provider_ids)
        if not selected:
            return set()
        effective_config = tool_config or self._tool_config or ToolConfig()
        groups = {
            group
            for provider in self.list_provider_descriptors(effective_config)
            if provider.provider_id in selected and provider.enabled
            for group in provider.capability_groups
        }
        groups.update(
            descriptor.group
            for descriptor in self.apply_config(effective_config, effective=True)
            if descriptor.enabled and descriptor.provider_id in selected
        )
        return groups

    def capability_groups_for_tool_ids(
        self,
        tool_ids: Iterable[str],
        tool_config: ToolConfig | None = None,
    ) -> set[str]:
        """Return capability groups represented by the selected Tool IDs."""
        selected = set(tool_ids)
        if not selected:
            return set()
        effective_config = tool_config or self._tool_config or ToolConfig()
        return {
            descriptor.group
            for descriptor in self.apply_config(effective_config, effective=True)
            if descriptor.enabled and descriptor.tool_id in selected
        }

    def capability_groups(self, tool_config: ToolConfig | None = None) -> set[str]:
        return {
            item["group"]
            for item in self.list_capability_catalog(tool_config)
        }

    def validate_capability_groups(
        self,
        capabilities: Iterable[str],
        tool_config: ToolConfig | None = None,
    ) -> None:
        known = self.capability_groups(tool_config)
        unknown = sorted(
            {
                str(capability).strip()
                for capability in capabilities
                if str(capability).strip() not in known
            }
        )
        if unknown:
            raise ValueError(f"未知 capability group: {', '.join(unknown)}")

    def resolve_scope_selection(
        self,
        capabilities: Iterable[str] | None,
        provider_ids: Iterable[str] | None = None,
        tool_ids: Iterable[str] | None = None,
        tool_config: ToolConfig | None = None,
    ) -> tuple[List[str], List[str], List[str]]:
        """Return a deterministic selection that can only narrow Catalog access."""
        effective_config = tool_config or self._tool_config or ToolConfig()
        descriptors = [
            descriptor
            for descriptor in self.apply_config(effective_config, effective=True)
            if descriptor.enabled
        ]
        known_capabilities = {descriptor.group for descriptor in descriptors}
        known_capabilities.update(
            group
            for provider in self.list_provider_descriptors(effective_config)
            if provider.enabled
            for group in provider.capability_groups
        )
        normalized_capabilities = self._normalized_values(capabilities)
        resolved_capabilities = [
            value
            for value in normalized_capabilities
            if value in known_capabilities
        ]
        selected_groups = set(resolved_capabilities)

        normalized_providers = self._normalized_values(provider_ids)
        allowed_providers = {
            descriptor.provider_id
            for descriptor in descriptors
            if descriptor.group in selected_groups
        }
        allowed_providers.update(
            provider.provider_id
            for provider in self.list_provider_descriptors(effective_config)
            if provider.enabled
            and selected_groups.intersection(provider.capability_groups)
        )
        if not normalized_providers:
            configured_mcp_candidates = [
                provider.provider_id
                for provider in self._provider_descriptors.values()
                if provider.enabled
                and provider.provider_type == "mcp"
                and selected_groups.intersection(provider.capability_groups)
            ]
            if len(configured_mcp_candidates) == 1:
                normalized_providers = configured_mcp_candidates
        resolved_providers = [
            value
            for value in normalized_providers
            if value in allowed_providers
        ]
        if len(resolved_providers) != len(normalized_providers):
            return [], [], []
        selected_providers = set(resolved_providers)
        provider_constrained_groups = (
            self.capability_groups_for_provider_ids(
                resolved_providers,
                effective_config,
            ).intersection(selected_groups)
        )

        normalized_tools = self._normalized_values(tool_ids)
        descriptors_by_id = {
            descriptor.tool_id: descriptor for descriptor in descriptors
        }
        resolved_tools: List[str] = []
        for tool_id in normalized_tools:
            descriptor = descriptors_by_id.get(tool_id)
            if descriptor is None or descriptor.group not in selected_groups:
                continue
            if (
                descriptor.group in provider_constrained_groups
                and descriptor.provider_id not in selected_providers
            ):
                continue
            resolved_tools.append(tool_id)
        if len(resolved_tools) != len(normalized_tools):
            return [], [], []
        return resolved_capabilities, resolved_providers, resolved_tools

    def tool_id_for_function(self, tool_name: str, function_name: str) -> str:
        descriptor = self.get_by_function_name(function_name)
        if descriptor:
            return descriptor.tool_id
        if tool_name == "api" or function_name.startswith("api_"):
            return f"api.dynamic.{function_name}"
        if tool_name == "mcp" or function_name.startswith("mcp_"):
            return f"mcp.dynamic.{function_name}"
        if tool_name == "a2a":
            return f"a2a.remote.{function_name}"
        return f"builtin.{tool_name}.{function_name}"

    def executor_type_for_function(self, tool_name: str, function_name: str) -> str:
        descriptor = self.get_by_function_name(function_name)
        if descriptor:
            return descriptor.executor_type
        if tool_name == "api" or function_name.startswith("api_"):
            return "api"
        if tool_name == "mcp" or function_name.startswith("mcp_"):
            return "mcp"
        if tool_name == "a2a":
            return "a2a"
        return "builtin"

    def default_bindings(self, tool_config: ToolConfig | None = None) -> Dict[str, ToolBinding]:
        return {
            descriptor.tool_id: ToolBinding(
                enabled=descriptor.enabled_by_default,
                risk_level=descriptor.risk_level,
            )
            for descriptor in self.list_descriptors(tool_config)
            if not self._is_system_builtin(descriptor)
        }

    def resolve_binding(
        self,
        tool_config: ToolConfig,
        tool_name: str,
        function_name: str,
    ) -> tuple[str, ToolBinding, str, bool]:
        descriptor = self.get_by_function_name(function_name, tool_config)
        tool_id = descriptor.tool_id if descriptor else self.tool_id_for_function(tool_name, function_name)
        default_risk = descriptor.risk_level if descriptor else self._risk_for(function_name)
        source_enabled = descriptor.enabled_by_default if descriptor else True
        binding = tool_config.bindings.get(
            tool_id,
            ToolBinding(enabled=source_enabled, risk_level=default_risk),
        )
        if descriptor and self._is_system_builtin(descriptor):
            binding = binding.model_copy(update={"enabled": True})
            source_enabled = True
        executor_type = descriptor.executor_type if descriptor else self.executor_type_for_function(tool_name, function_name)
        return tool_id, binding, executor_type, source_enabled

    def is_function_enabled(
        self,
        tool_config: ToolConfig,
        tool_name: str,
        function_name: str,
    ) -> bool:
        descriptor = self.get_by_function_name(function_name, tool_config)
        if descriptor and self._is_system_builtin(descriptor):
            return True
        _, binding, executor_type, source_enabled = self.resolve_binding(
            tool_config,
            tool_name,
            function_name,
        )
        if executor_type not in tool_config.runtime_policy.allowed_executor_types:
            return False
        return source_enabled and binding.enabled

    def apply_config(self, tool_config: ToolConfig, effective: bool = False) -> List[ToolDescriptor]:
        descriptors = self.list_descriptors(tool_config)
        for descriptor in descriptors:
            binding = tool_config.bindings.get(descriptor.tool_id)
            descriptor.enabled = descriptor.enabled_by_default
            if binding and not self._is_system_builtin(descriptor):
                descriptor.enabled = descriptor.enabled and binding.enabled
                descriptor.risk_level = binding.risk_level or descriptor.risk_level
            if self._is_system_builtin(descriptor):
                descriptor.enabled = True
            provider = self._provider_descriptors.get(descriptor.provider_id)
            if provider is not None and not provider.enabled:
                descriptor.enabled = False
            if effective:
                descriptor.enabled = self._is_system_builtin(descriptor) or (
                    descriptor.enabled
                    and descriptor.executor_type in tool_config.runtime_policy.allowed_executor_types
                )
        return descriptors

    def _list_builtin_descriptors(self) -> List[ToolDescriptor]:
        if self._builtin_descriptors is None:
            self._builtin_descriptors = list(self._build_builtin_descriptors())
        return self._builtin_descriptors

    def _build_builtin_descriptors(self) -> Iterable[ToolDescriptor]:
        for group in self._groups:
            for schema in self._schemas_from_class(group.tool_cls):
                function_name = schema["function"]["name"]
                yield ToolDescriptor(
                    tool_id=f"{group.provider_id}.{function_name}",
                    function_name=function_name,
                    provider_id=group.provider_id,
                    provider_label=group.provider_label,
                    group=group.group,
                    executor_type=group.executor_type,
                    source_type=group.source_type,
                    execution_backend=group.execution_backend,
                    resource_requirements=self._resource_requirements(
                        execution_backend=group.execution_backend,
                        requires_sandbox=group.requires_sandbox,
                        requires_browser=group.requires_browser,
                        requires_credentials=group.requires_credentials,
                    ),
                    execution_class=group.execution_class,
                    generality=generality_for_builtin_function(function_name),
                    cost_class=group.cost_class,
                    label=label_for_builtin_function(function_name),
                    description=schema["function"].get("description", ""),
                    schema=schema,
                    category=group.category,
                    risk_level=risk_for_builtin_function(function_name),
                    requires_sandbox=group.requires_sandbox,
                    requires_browser=group.requires_browser,
                    requires_credentials=group.requires_credentials,
                    enabled_by_default=True,
                )

    def _build_api_descriptors(self, tool_config: ToolConfig | None) -> List[ToolDescriptor]:
        descriptors: List[ToolDescriptor] = []
        for definition in build_api_tool_definitions(tool_config):
            descriptors.append(
                ToolDescriptor(
                    tool_id=f"{definition.provider_id}.{definition.function_name}",
                    function_name=definition.function_name,
                    provider_id=definition.provider_id,
                    provider_label=definition.provider_label,
                    group=definition.group,
                    executor_type="api",
                    source_type="api",
                    execution_backend="remote_http",
                    resource_requirements=self._resource_requirements(
                        execution_backend="remote_http",
                        requires_sandbox=definition.requires_sandbox,
                        requires_browser=definition.requires_browser,
                        requires_credentials=definition.requires_credentials,
                    ),
                    execution_class=(
                        "external_read"
                        if definition.method in {"get", "head", "options"}
                        else "external_write"
                    ),
                    generality="specialized",
                    cost_class="medium",
                    label=definition.label,
                    description=definition.description,
                    schema=definition.tool_schema,
                    category=definition.category,
                    risk_level=api_risk_for_method(definition.method),
                    requires_sandbox=definition.requires_sandbox,
                    requires_browser=definition.requires_browser,
                    requires_credentials=definition.requires_credentials,
                    enabled_by_default=definition.source_enabled,
                )
            )
        return descriptors

    @classmethod
    def _schemas_from_class(cls, tool_cls: type[BaseTool]) -> Iterable[Dict[str, Any]]:
        for _, method in inspect.getmembers(tool_cls, inspect.isfunction):
            if hasattr(method, "_tool_schema"):
                yield copy.deepcopy(getattr(method, "_tool_schema"))

    @classmethod
    def _risk_for(cls, function_name: str) -> str:
        return risk_for_builtin_function(function_name)

    @staticmethod
    def _normalized_values(values: Iterable[str] | None) -> List[str]:
        normalized: List[str] = []
        for value in values or ():
            item = str(value).strip()
            if item and item not in normalized:
                normalized.append(item)
        return normalized

    @staticmethod
    def _resource_requirements(
        *,
        execution_backend: str,
        requires_sandbox: bool,
        requires_browser: bool,
        requires_credentials: bool,
    ) -> List[str]:
        requirements: List[str] = []
        if requires_sandbox or requires_browser:
            requirements.append("sandbox")
        if requires_browser:
            requirements.append("browser")
        if execution_backend in {
            "remote_http",
            "external_provider",
            "delegation",
        }:
            requirements.append("network")
        if requires_credentials:
            requirements.append("credentials")
        return requirements

    @staticmethod
    def _is_system_builtin(descriptor: ToolDescriptor) -> bool:
        return descriptor.provider_id.startswith("builtin.")

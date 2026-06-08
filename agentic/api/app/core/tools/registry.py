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
    label_for_builtin_function,
    risk_for_builtin_function,
)
from app.schemas.tool_config import ToolDescriptor, ToolRegistration


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

    def register_group(self, group: BuiltinToolGroup) -> None:
        self._groups.append(group)
        self._builtin_descriptors = None

    def list_descriptors(self, tool_config: ToolConfig | None = None) -> List[ToolDescriptor]:
        descriptors = [descriptor.model_copy(deep=True) for descriptor in self._list_builtin_descriptors()]
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
        executor_type = descriptor.executor_type if descriptor else self.executor_type_for_function(tool_name, function_name)
        return tool_id, binding, executor_type, source_enabled

    def is_function_enabled(
        self,
        tool_config: ToolConfig,
        tool_name: str,
        function_name: str,
    ) -> bool:
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
            if binding:
                descriptor.enabled = descriptor.enabled and binding.enabled
                descriptor.risk_level = binding.risk_level or descriptor.risk_level
            if effective:
                descriptor.enabled = (
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

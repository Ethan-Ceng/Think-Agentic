#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import Optional

from app.core.tools.api import APITool, validate_api_tool_registration
from app.core.tools.registry import ToolRegistry
from app.schemas.tool_config import (
    RuntimeToolPolicy,
    ToolBinding,
    ToolBindingsUpdate,
    ToolCapabilitySummary,
    ToolConfig,
    ToolListResponse,
    ToolPreflightResponse,
    ToolRegistration,
    ToolRegistrationCreate,
    ToolRegistrationListResponse,
    ToolRegistrationTestRequest,
    ToolRegistrationTestResponse,
    ToolRegistrationUpdate,
)
from app.schemas.exceptions import BadRequestError, NotFoundError
from app.services.app_config_service import AppConfigService, get_app_config_service
from app.services.tool_capability_service import ToolCapabilityService
from app.services.tool_preflight_service import ToolPreflightService


class ToolConfigService:
    """工具管理服务。"""

    def __init__(
        self,
        app_config_service: AppConfigService,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.app_config_service = app_config_service
        self.registry = registry or ToolRegistry()
        self.capability_service = ToolCapabilityService(self.registry)
        self.preflight_service = ToolPreflightService(self.capability_service)

    async def list_tools(self) -> ToolListResponse:
        tool_config = await self.get_tool_config()
        return ToolListResponse(
            tools=self.registry.apply_config(tool_config),
            registrations=self.registry.list_registrations(tool_config),
            runtime_policy=tool_config.runtime_policy,
        )

    async def get_tool_config(self) -> ToolConfig:
        config = await self.app_config_service.get_tool_config()
        return ToolConfig.model_validate(config.model_dump(mode="json"))

    async def update_bindings(self, update: ToolBindingsUpdate) -> ToolListResponse:
        current = await self.get_tool_config()
        merged_bindings = dict(current.bindings)
        merged_bindings.update(update.bindings)
        updated = ToolConfig(
            schema_version=current.schema_version,
            mode=current.mode,
            bindings=merged_bindings,
            registrations=current.registrations,
            runtime_policy=update.runtime_policy,
        )
        await self.app_config_service.update_tool_config(updated)
        return await self.list_tools()

    async def reset_defaults(self) -> ToolListResponse:
        current = await self.get_tool_config()
        bindings = {
            tool_id: ToolBinding.model_validate(binding.model_dump(mode="json"))
            for tool_id, binding in self.registry.default_bindings(current).items()
        }
        await self.app_config_service.update_tool_config(
            ToolConfig(
                bindings=bindings,
                registrations=current.registrations,
                runtime_policy=RuntimeToolPolicy(),
            )
        )
        return await self.list_tools()

    async def list_registrations(self) -> ToolRegistrationListResponse:
        tool_config = await self.get_tool_config()
        return ToolRegistrationListResponse(
            registrations=self.registry.list_registrations(tool_config)
        )

    async def create_registration(
        self,
        request: ToolRegistrationCreate,
    ) -> ToolRegistrationListResponse:
        current = await self.get_tool_config()
        registration_id = request.provider_id
        if self._is_builtin_registration(registration_id):
            raise BadRequestError("内置工具源不能被覆盖")
        if registration_id in current.registrations:
            raise BadRequestError("工具源已存在")

        registration = ToolRegistration(
            registration_id=registration_id,
            provider_id=request.provider_id,
            provider_label=request.provider_label,
            source_type=request.source_type,
            executor_type=request.executor_type,
            group=request.group,
            category=request.category,
            description=request.description,
            enabled=request.enabled,
            builtin=False,
            editable=True,
            requires_sandbox=request.requires_sandbox,
            requires_browser=request.requires_browser,
            requires_credentials=request.requires_credentials,
            config=request.config,
        )
        self._validate_registration(registration)
        runtime_policy = self._with_executor_type(
            current.runtime_policy,
            registration.executor_type,
        )
        updated = current.model_copy(
            update={
                "registrations": {**current.registrations, registration_id: registration},
                "runtime_policy": runtime_policy,
            }
        )
        await self.app_config_service.update_tool_config(updated)
        return await self.list_registrations()

    async def update_registration(
        self,
        registration_id: str,
        request: ToolRegistrationUpdate,
    ) -> ToolRegistrationListResponse:
        current = await self.get_tool_config()
        if self._is_builtin_registration(registration_id):
            raise BadRequestError("内置工具源不能编辑")
        registration = current.registrations.get(registration_id)
        if not registration:
            raise NotFoundError("工具源不存在")

        patch = request.model_dump(exclude_unset=True)
        updated_registration = registration.model_copy(update=patch)
        self._validate_registration(updated_registration)
        updated_registrations = dict(current.registrations)
        updated_registrations[registration_id] = updated_registration
        runtime_policy = (
            self._with_executor_type(current.runtime_policy, updated_registration.executor_type)
            if updated_registration.enabled
            else current.runtime_policy
        )
        await self.app_config_service.update_tool_config(
            current.model_copy(
                update={
                    "registrations": updated_registrations,
                    "runtime_policy": runtime_policy,
                }
            )
        )
        return await self.list_registrations()

    async def delete_registration(self, registration_id: str) -> ToolRegistrationListResponse:
        current = await self.get_tool_config()
        if self._is_builtin_registration(registration_id):
            raise BadRequestError("内置工具源不能删除")
        if registration_id not in current.registrations:
            raise NotFoundError("工具源不存在")

        updated_registrations = dict(current.registrations)
        updated_registrations.pop(registration_id, None)
        await self.app_config_service.update_tool_config(
            current.model_copy(update={"registrations": updated_registrations})
        )
        return await self.list_registrations()

    async def test_registration(
        self,
        registration_id: str,
        request: ToolRegistrationTestRequest,
    ) -> ToolRegistrationTestResponse:
        current = await self.get_tool_config()
        registration = current.registrations.get(registration_id)
        if not registration:
            raise NotFoundError("Tool registration not found")
        if registration.source_type != "api" or registration.executor_type != "api":
            raise BadRequestError("Only API tool registrations can be tested")

        test_registration = registration.model_copy(update={"enabled": True})
        self._validate_registration(test_registration)
        test_config = ToolConfig(
            schema_version=current.schema_version,
            mode=current.mode,
            bindings=current.bindings,
            registrations={registration_id: test_registration},
            runtime_policy=self._with_executor_type(current.runtime_policy, "api"),
        )
        tools = [
            descriptor
            for descriptor in self.registry.apply_config(test_config, effective=True)
            if descriptor.provider_id == test_registration.provider_id
        ]
        selected_tool = None
        result = None

        if request.function_name:
            selected_tool = next(
                (tool for tool in tools if tool.function_name == request.function_name),
                None,
            )
            if not selected_tool:
                raise NotFoundError("Tool function not found")
            tool_result = await APITool(test_config).invoke(
                request.function_name,
                **request.arguments,
            )
            result = tool_result.model_dump(mode="json")

        return ToolRegistrationTestResponse(
            registration=test_registration,
            tools=tools,
            selected_tool=selected_tool,
            result=result,
        )

    def _is_builtin_registration(self, registration_id: str) -> bool:
        return any(
            registration.registration_id == registration_id and registration.builtin
            for registration in self.registry.list_registrations()
        )

    def _validate_registration(self, registration: ToolRegistration) -> None:
        try:
            validate_api_tool_registration(registration)
        except ValueError as exc:
            raise BadRequestError(str(exc)) from exc

    @classmethod
    def _with_executor_type(
        cls,
        runtime_policy: RuntimeToolPolicy,
        executor_type: str,
    ) -> RuntimeToolPolicy:
        if executor_type in runtime_policy.allowed_executor_types:
            return runtime_policy
        return runtime_policy.model_copy(
            update={
                "allowed_executor_types": [
                    *runtime_policy.allowed_executor_types,
                    executor_type,
                ]
            }
        )

    async def capability_summary(self) -> ToolCapabilitySummary:
        tool_config = await self.get_tool_config()
        return self.capability_service.build_summary(tool_config)

    async def preflight(self, message: str) -> ToolPreflightResponse:
        tool_config = await self.get_tool_config()
        return self.preflight_service.check(message=message, tool_config=tool_config)


_tool_config_service: Optional[ToolConfigService] = None


def get_tool_config_service() -> ToolConfigService:
    global _tool_config_service
    if _tool_config_service is None:
        _tool_config_service = ToolConfigService(get_app_config_service())
    return _tool_config_service

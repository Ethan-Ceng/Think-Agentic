#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio

import httpx

from app.core.tools.api import APITool
from app.core.tools.file import FileTool
from app.core.tools.filter import FilteredTool
from app.core.tools.message import MessageTool
from app.core.tools.base import BaseTool, tool
from app.core.tools.registry import ToolRegistry
from app.schemas.tool_config import (
    ToolBinding,
    ToolBindingsUpdate,
    ToolConfig,
    ToolRegistration,
    ToolRegistrationTestRequest,
    RuntimeToolPolicy,
)
from app.schemas.tool_config import ToolRegistrationCreate, ToolRegistrationUpdate
from app.services.tool_config_service import ToolConfigService
from app.services.tool_capability_service import ToolCapabilityService
from app.services.tool_preflight_service import ToolPreflightService


WEATHER_OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Weather", "version": "1.0.0"},
    "servers": [{"url": "https://weather.example.com"}],
    "paths": {
        "/weather/{city}": {
            "get": {
                "operationId": "get_weather",
                "summary": "Get weather",
                "parameters": [
                    {
                        "name": "city",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "unit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "enum": ["c", "f"]},
                    },
                ],
            }
        }
    },
}

USER_ID = "user-1"


class RuntimeRiskTool(BaseTool):
    name = "skill_draft"

    @tool(
        name="skill_draft_write",
        description="Write a Skill draft",
        parameters={"content": {"type": "string"}},
        required=["content"],
    )
    async def skill_draft_write(self, content: str):
        raise AssertionError("policy tests must not execute the tool")


def test_tool_registry_lists_builtin_metadata() -> None:
    registry = ToolRegistry()

    shell_execute = next(
        descriptor
        for descriptor in registry.list_descriptors()
        if descriptor.function_name == "shell_execute"
    )

    assert shell_execute.tool_id == "builtin.shell.shell_execute"
    assert shell_execute.group == "shell"
    assert shell_execute.executor_type == "builtin"
    assert shell_execute.risk_level == "high"


def test_sandbox_file_writes_are_auto_allowed_by_default() -> None:
    config = ToolConfig()
    registry = ToolRegistry(tool_config=config)
    filtered = FilteredTool(FileTool(sandbox=object()), config, registry)

    assert filtered.get_risk_level("read_file") == "low"
    assert filtered.get_risk_level("write_file") == "medium"
    assert filtered.get_risk_level("replace_in_file") == "medium"
    assert filtered.get_approval_policy("read_file") == "allow"
    assert filtered.get_approval_policy("write_file") == "allow"
    assert filtered.get_approval_policy("replace_in_file") == "allow"

    ask_config = ToolConfig(
        bindings={
            "builtin.file.write_file": ToolBinding(
                risk_level="medium",
                approval="ask",
            ),
        },
    )
    ask_filtered = FilteredTool(
        FileTool(sandbox=object()),
        ask_config,
        ToolRegistry(tool_config=ask_config),
    )
    assert ask_filtered.get_approval_policy("write_file") == "ask"


def test_tool_list_exposes_only_safe_builtin_approval_settings() -> None:
    class FakeAppConfigService:
        def __init__(self) -> None:
            self.config = ToolConfig(
                bindings={
                    "builtin.shell.shell_execute": ToolBinding(
                        risk_level="high",
                        approval="allow",
                        params={"secret": "must-not-leak"},
                    ),
                    "builtin.browser.browser_console_exec": ToolBinding(
                        risk_level="high",
                        approval="ask",
                    ),
                    "api.weather.api_weather_get_weather": ToolBinding(
                        risk_level="low",
                        approval="ask",
                        params={"unit": "c"},
                    ),
                },
            )

        async def get_tool_config(self, user_id: str) -> ToolConfig:
            assert user_id == USER_ID
            return self.config

        async def update_tool_config(self, user_id: str, new_config: ToolConfig) -> ToolConfig:
            assert user_id == USER_ID
            self.config = new_config
            return self.config

    async def run() -> None:
        app_config = FakeAppConfigService()
        service = ToolConfigService(app_config)

        listed = await service.list_tools(USER_ID)
        settings = {item.tool_id: item for item in listed.approval_tools}

        assert set(settings) == {
            "builtin.shell.shell_execute",
            "builtin.shell.shell_write_input",
            "builtin.shell.shell_kill_process",
            "builtin.browser.browser_console_exec",
        }
        assert settings["builtin.shell.shell_execute"].approval == "allow"
        assert settings["builtin.shell.shell_write_input"].approval == "auto"
        assert "params" not in settings["builtin.shell.shell_execute"].model_dump()

        await service.update_bindings(
            USER_ID,
            ToolBindingsUpdate(
                bindings={
                    "builtin.shell.shell_execute": ToolBinding(
                        risk_level="high",
                        approval="deny",
                    ),
                },
                runtime_policy=app_config.config.runtime_policy,
            ),
        )
        assert app_config.config.bindings["builtin.shell.shell_execute"].approval == "deny"
        assert app_config.config.bindings["builtin.shell.shell_execute"].params == {
            "secret": "must-not-leak",
        }
        assert (
            app_config.config.bindings["builtin.browser.browser_console_exec"].approval
            == "ask"
        )
        assert (
            app_config.config.bindings["api.weather.api_weather_get_weather"].approval
            == "ask"
        )
        assert app_config.config.bindings["api.weather.api_weather_get_weather"].params == {
            "unit": "c",
        }

    asyncio.run(run())


def test_tool_config_defaults_are_backward_compatible_and_ask_for_high_risk() -> None:
    binding = ToolBinding.model_validate({"enabled": True, "risk_level": "high"})
    policy = RuntimeToolPolicy.model_validate({})

    assert binding.approval == "auto"
    assert policy.require_approval_for_high_risk is True


def test_filtered_tool_resolves_effective_approval_policy() -> None:
    runtime_tool = RuntimeRiskTool()
    config = ToolConfig()
    registry = ToolRegistry(tool_config=config)
    registry.register_runtime_tool(runtime_tool)
    filtered = FilteredTool(runtime_tool, config, registry)

    assert filtered.get_risk_level("skill_draft_write") == "high"
    assert filtered.get_approval_policy("skill_draft_write") == "ask"

    allow_config = ToolConfig(
        runtime_policy=RuntimeToolPolicy(require_approval_for_high_risk=False),
    )
    allow_registry = ToolRegistry(tool_config=allow_config)
    allow_registry.register_runtime_tool(runtime_tool)
    allow_filtered = FilteredTool(runtime_tool, allow_config, allow_registry)
    assert allow_filtered.get_approval_policy("skill_draft_write") == "allow"

    for configured, expected in (("allow", "allow"), ("ask", "ask"), ("deny", "deny")):
        override = ToolConfig(
            bindings={
                "builtin.skill_draft.skill_draft_write": ToolBinding(
                    risk_level="high",
                    approval=configured,
                ),
            },
        )
        override_registry = ToolRegistry(tool_config=override)
        override_registry.register_runtime_tool(runtime_tool)
        override_filtered = FilteredTool(runtime_tool, override, override_registry)
        assert override_filtered.get_approval_policy("skill_draft_write") == expected


def test_message_interaction_tools_bypass_generic_approval_policy() -> None:
    config = ToolConfig(
        bindings={
            "builtin.message.message_ask_user": ToolBinding(
                risk_level="high",
                approval="deny",
            ),
        },
    )
    filtered = FilteredTool(MessageTool(), config, ToolRegistry(tool_config=config))

    assert filtered.get_approval_policy("message_ask_user") == "allow"


def test_tool_registry_lists_builtin_registrations() -> None:
    registry = ToolRegistry()

    registrations = registry.list_registrations()
    shell = next(
        registration
        for registration in registrations
        if registration.registration_id == "builtin.shell"
    )

    assert shell.provider_label == "Shell"
    assert shell.source_type == "builtin"
    assert shell.executor_type == "builtin"
    assert shell.builtin is True
    assert shell.editable is False


def test_filtered_tool_hides_and_denies_disabled_function() -> None:
    config = ToolConfig(
        registrations={
            "api.weather": ToolRegistration(
                registration_id="api.weather",
                provider_id="api.weather",
                provider_label="Weather API",
                source_type="api",
                executor_type="api",
                group="weather",
                category="weather",
                config={"openapi_schema": WEATHER_OPENAPI},
            )
        },
        bindings={
            "api.weather.api_weather_get_weather": ToolBinding(
                enabled=False,
                risk_level="low",
            )
        }
    )
    registry = ToolRegistry(tool_config=config)
    filtered = FilteredTool(APITool(config), config, registry)

    tool_names = {schema["function"]["name"] for schema in filtered.get_tools()}
    assert "api_weather_get_weather" not in tool_names
    assert not filtered.has_tool("api_weather_get_weather")

    result = asyncio.run(filtered.invoke("api_weather_get_weather", city="Hong Kong"))
    assert result.success is False
    assert "api.weather.api_weather_get_weather" in result.message


def test_system_builtin_tools_ignore_user_bindings_and_executor_policy() -> None:
    registry = ToolRegistry()
    config = ToolConfig(
        bindings={
            "builtin.file.read_file": ToolBinding(
                enabled=False,
                risk_level="low",
            ),
            "builtin.message.message_notify_user": ToolBinding(
                enabled=False,
                risk_level="low",
            ),
            "builtin.message.message_ask_user": ToolBinding(
                enabled=False,
                risk_level="medium",
            ),
        },
        runtime_policy=RuntimeToolPolicy(allowed_executor_types=["api"]),
    )
    filtered = FilteredTool(MessageTool(), config, registry)

    tool_names = {schema["function"]["name"] for schema in filtered.get_tools()}
    assert tool_names == {"message_notify_user", "message_ask_user"}
    assert filtered.has_tool("message_notify_user")
    assert filtered.has_tool("message_ask_user")

    descriptors = {
        descriptor.function_name: descriptor
        for descriptor in registry.apply_config(config, effective=True)
        if descriptor.provider_id.startswith("builtin.")
    }
    assert descriptors["message_notify_user"].enabled is True
    assert descriptors["message_ask_user"].enabled is True
    assert descriptors["read_file"].enabled is True
    assert all(
        not tool_id.startswith("builtin.")
        for tool_id in registry.default_bindings(config)
    )


def test_preflight_ignores_historical_disabled_builtin_bindings() -> None:
    registry = ToolRegistry()
    bindings = {
        descriptor.tool_id: ToolBinding(
            enabled=False,
            risk_level=descriptor.risk_level,
        )
        for descriptor in registry.list_descriptors()
        if descriptor.group == "shell"
    }
    config = ToolConfig(bindings=bindings)
    service = ToolPreflightService(ToolCapabilityService(registry))

    result = service.check("帮我运行 pytest", config)

    assert result.status == "pass"
    assert "shell" in result.capability_snapshot.semantic_tags
    assert any(
        check.rule_id == "shell_required"
        and check.passed
        for check in result.checks
    )


def test_tool_config_service_manages_custom_registrations() -> None:
    class FakeAppConfigService:
        def __init__(self) -> None:
            self.config = ToolConfig()

        async def get_tool_config(self, user_id: str) -> ToolConfig:
            assert user_id == USER_ID
            return self.config

        async def update_tool_config(self, user_id: str, new_config: ToolConfig) -> ToolConfig:
            assert user_id == USER_ID
            self.config = new_config
            return self.config

    async def run() -> None:
        service = ToolConfigService(FakeAppConfigService())

        created = await service.create_registration(
            USER_ID,
            ToolRegistrationCreate(
                provider_id="api.weather",
                provider_label="Weather API",
                source_type="api",
                executor_type="api",
                group="weather",
                category="天气",
            )
        )
        custom = next(
            registration
            for registration in created.registrations
            if registration.registration_id == "api.weather"
        )
        assert len(created.registrations) == 1
        assert custom.editable is True
        assert custom.enabled is True

        listed = await service.list_tools(USER_ID)
        assert listed.tools == []
        assert all(not registration.builtin for registration in listed.registrations)

        updated = await service.update_registration(
            USER_ID,
            "api.weather",
            ToolRegistrationUpdate(enabled=False),
        )
        custom = next(
            registration
            for registration in updated.registrations
            if registration.registration_id == "api.weather"
        )
        assert custom.enabled is False

        deleted = await service.delete_registration(USER_ID, "api.weather")
        assert all(
            registration.registration_id != "api.weather"
            for registration in deleted.registrations
        )

    asyncio.run(run())


def test_api_registration_generates_tool_descriptor_and_runtime_call() -> None:
    config = ToolConfig(
        registrations={
            "api.weather": ToolRegistration(
                registration_id="api.weather",
                provider_id="api.weather",
                provider_label="Weather API",
                source_type="api",
                executor_type="api",
                group="weather",
                category="weather",
                config={
                    "openapi_schema": WEATHER_OPENAPI,
                    "headers": {"X-Test": "ok"},
                },
            )
        }
    )
    registry = ToolRegistry(tool_config=config)

    descriptor = next(
        item
        for item in registry.apply_config(config)
        if item.function_name == "api_weather_get_weather"
    )

    assert descriptor.tool_id == "api.weather.api_weather_get_weather"
    assert descriptor.executor_type == "api"
    assert descriptor.group == "weather"
    assert descriptor.risk_level == "low"
    assert descriptor.tool_schema["function"]["parameters"]["required"] == ["city"]

    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"city": "Hong Kong", "unit": "c"})

    api_tool = APITool(config, transport=httpx.MockTransport(handler))
    result = asyncio.run(
        api_tool.invoke(
            "api_weather_get_weather",
            city="Hong Kong",
            unit="c",
        )
    )

    assert result.success is True
    assert result.data["body"] == {"city": "Hong Kong", "unit": "c"}
    assert str(captured["request"].url) == "https://weather.example.com/weather/Hong%20Kong?unit=c"
    assert captured["request"].headers["X-Test"] == "ok"


def test_disabled_api_registration_is_hidden_by_filtered_tool() -> None:
    config = ToolConfig(
        registrations={
            "api.weather": ToolRegistration(
                registration_id="api.weather",
                provider_id="api.weather",
                provider_label="Weather API",
                source_type="api",
                executor_type="api",
                group="weather",
                category="weather",
                enabled=False,
                config={"openapi_schema": WEATHER_OPENAPI},
            )
        }
    )
    filtered = FilteredTool(APITool(config), config, ToolRegistry(tool_config=config))

    assert filtered.get_tools() == []
    result = asyncio.run(filtered.invoke("api_weather_get_weather", city="Hong Kong"))

    assert result.success is False
    assert "api.weather.api_weather_get_weather" in result.message


def test_api_tool_blocks_local_network_targets() -> None:
    config = ToolConfig(
        registrations={
            "api.local": ToolRegistration(
                registration_id="api.local",
                provider_id="api.local",
                provider_label="Local API",
                source_type="api",
                executor_type="api",
                group="custom",
                category="test",
                config={
                    "base_url": "http://127.0.0.1:8080",
                    "openapi_schema": {
                        **WEATHER_OPENAPI,
                        "servers": [],
                        "paths": {
                            "/ping": {
                                "get": {
                                    "operationId": "ping",
                                    "summary": "Ping",
                                }
                            }
                        },
                    },
                },
            )
        }
    )
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"ok": True})

    result = asyncio.run(
        APITool(config, transport=httpx.MockTransport(handler)).invoke(
            "api_local_ping",
        )
    )

    assert result.success is False
    assert "private" in result.message or "non-global" in result.message
    assert called is False


def test_tool_config_service_tests_api_registration_schema() -> None:
    class FakeAppConfigService:
        def __init__(self) -> None:
            self.config = ToolConfig(
                registrations={
                    "api.weather": ToolRegistration(
                        registration_id="api.weather",
                        provider_id="api.weather",
                        provider_label="Weather API",
                        source_type="api",
                        executor_type="api",
                        group="weather",
                        category="weather",
                        enabled=False,
                        config={"openapi_schema": WEATHER_OPENAPI},
                    )
                }
            )

        async def get_tool_config(self, user_id: str) -> ToolConfig:
            assert user_id == USER_ID
            return self.config

        async def update_tool_config(self, user_id: str, new_config: ToolConfig) -> ToolConfig:
            assert user_id == USER_ID
            self.config = new_config
            return self.config

    async def run() -> None:
        service = ToolConfigService(FakeAppConfigService())
        response = await service.test_registration(
            USER_ID,
            "api.weather",
            ToolRegistrationTestRequest(),
        )

        assert response.registration.enabled is True
        assert [tool.function_name for tool in response.tools] == ["api_weather_get_weather"]
        assert response.result is None

    asyncio.run(run())

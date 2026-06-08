#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio

import httpx

from app.core.tools.api import APITool
from app.core.tools.filter import FilteredTool
from app.core.tools.message import MessageTool
from app.core.tools.registry import ToolRegistry
from app.schemas.tool_config import (
    ToolBinding,
    ToolConfig,
    ToolRegistration,
    ToolRegistrationTestRequest,
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
    registry = ToolRegistry()
    config = ToolConfig(
        bindings={
            "builtin.message.message_ask_user": ToolBinding(
                enabled=False,
                risk_level="medium",
            )
        }
    )
    filtered = FilteredTool(MessageTool(), config, registry)

    tool_names = {schema["function"]["name"] for schema in filtered.get_tools()}
    assert "message_notify_user" in tool_names
    assert "message_ask_user" not in tool_names
    assert not filtered.has_tool("message_ask_user")

    result = asyncio.run(filtered.invoke("message_ask_user", text="confirm?"))
    assert result.success is False
    assert "builtin.message.message_ask_user" in result.message


def test_preflight_blocks_when_required_shell_tools_are_disabled() -> None:
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

    assert result.status == "blocked"
    assert "shell" not in result.capability_snapshot.semantic_tags
    assert any(
        check.rule_id == "shell_required"
        and check.error_code == "capability_missing:shell"
        for check in result.checks
    )


def test_tool_config_service_manages_custom_registrations() -> None:
    class FakeAppConfigService:
        def __init__(self) -> None:
            self.config = ToolConfig()

        async def get_tool_config(self) -> ToolConfig:
            return self.config

        async def update_tool_config(self, new_config: ToolConfig) -> ToolConfig:
            self.config = new_config
            return self.config

    async def run() -> None:
        service = ToolConfigService(FakeAppConfigService())

        created = await service.create_registration(
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
        assert custom.editable is True
        assert custom.enabled is True

        updated = await service.update_registration(
            "api.weather",
            ToolRegistrationUpdate(enabled=False),
        )
        custom = next(
            registration
            for registration in updated.registrations
            if registration.registration_id == "api.weather"
        )
        assert custom.enabled is False

        deleted = await service.delete_registration("api.weather")
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

        async def get_tool_config(self) -> ToolConfig:
            return self.config

        async def update_tool_config(self, new_config: ToolConfig) -> ToolConfig:
            self.config = new_config
            return self.config

    async def run() -> None:
        service = ToolConfigService(FakeAppConfigService())
        response = await service.test_registration(
            "api.weather",
            ToolRegistrationTestRequest(),
        )

        assert response.registration.enabled is True
        assert [tool.function_name for tool in response.tools] == ["api_weather_get_weather"]
        assert response.result is None

    asyncio.run(run())

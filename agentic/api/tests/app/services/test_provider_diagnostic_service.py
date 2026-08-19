from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.llm.failure import ModelFailureCode, ModelRuntimeError, model_failure
from app.core.tools.a2a_runtime import (
    A2AFailureCode,
    A2ARuntimeError,
    a2a_failure,
)
from app.core.tools.provider_runtime import (
    ProviderFailureCode,
    ProviderRuntimeError,
    provider_failure,
)
from app.core.provider_diagnostics import (
    ProviderDiagnosticFailureCode,
    provider_diagnostic_failure,
)
from app.schemas.provider_diagnostic import (
    ProviderCheckKind,
    ProviderDiagnosticRequest,
    ProviderDiagnosticResult,
    ProviderDiagnosticStatus,
    ProviderType,
)
from app.services.provider_diagnostic_service import ProviderDiagnosticService
from app.services.provider_diagnostic_service import (
    A2AProviderDiagnosticAdapter,
    APIProviderDiagnosticAdapter,
    LLMProviderDiagnosticAdapter,
    MCPProviderDiagnosticAdapter,
)
from app.schemas.app_config import (
    A2AConfig,
    A2AServerConfig,
    LLMConfig,
    MCPConfig,
    MCPServerConfig,
)
from app.schemas.exceptions import NotFoundError, TooManusRequestsError
from app.schemas.tool_config import ToolConfig, ToolRegistration
from app.dependencies.infrastructure import get_diagnostic_llm


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class RecordingAdapter:
    def __init__(self, *, gate: asyncio.Event | None = None) -> None:
        self.gate = gate
        self.calls: list[tuple[str, str | None]] = []

    async def diagnose(
        self,
        *,
        user_id: str,
        target_id: str | None,
    ) -> ProviderDiagnosticResult:
        self.calls.append((user_id, target_id))
        if self.gate is not None:
            await self.gate.wait()
        return ProviderDiagnosticResult(
            provider_type=ProviderType.MCP,
            provider_id=f"mcp.{target_id}",
            check_kind=ProviderCheckKind.DISCOVERY,
            status=ProviderDiagnosticStatus.HEALTHY,
            message="Provider capability discovery succeeded.",
            latency_ms=4,
            capability_count=2,
            snapshot_state="fresh",
        )


def test_request_enforces_provider_specific_target_shape() -> None:
    assert ProviderDiagnosticRequest(provider_type="llm").target_id is None
    assert ProviderDiagnosticRequest(provider_type="mcp", target_id="docs").target_id == "docs"

    with pytest.raises(ValidationError):
        ProviderDiagnosticRequest(provider_type="llm", target_id="unexpected")
    with pytest.raises(ValidationError):
        ProviderDiagnosticRequest(provider_type="a2a")
    with pytest.raises(ValidationError):
        ProviderDiagnosticRequest(
            provider_type="api",
            target_id="registration",
            base_url="https://should-not-be-accepted.example",
        )


def test_diagnostic_failure_is_stable_and_safe() -> None:
    failure = provider_diagnostic_failure(
        ProviderDiagnosticFailureCode.DIAGNOSTIC_FAILED,
        provider_id="mcp.docs",
    )

    assert failure.code == "PROVIDER_DIAGNOSTIC_FAILED"
    assert failure.provider_id == "mcp.docs"
    assert failure.retryable is True
    assert "https://" not in failure.message


async def test_same_user_and_target_share_one_inflight_check() -> None:
    gate = asyncio.Event()
    adapter = RecordingAdapter(gate=gate)
    service = ProviderDiagnosticService(adapters={ProviderType.MCP: adapter})
    request = ProviderDiagnosticRequest(provider_type="mcp", target_id="docs")

    first = asyncio.create_task(service.test(user_id="user-1", request=request))
    second = asyncio.create_task(service.test(user_id="user-1", request=request))
    await asyncio.sleep(0)
    gate.set()

    first_result, second_result = await asyncio.gather(first, second)

    assert first_result == second_result
    assert adapter.calls == [("user-1", "docs")]


async def test_different_users_do_not_share_inflight_check() -> None:
    gate = asyncio.Event()
    adapter = RecordingAdapter(gate=gate)
    service = ProviderDiagnosticService(adapters={ProviderType.MCP: adapter})
    request = ProviderDiagnosticRequest(provider_type="mcp", target_id="docs")

    first = asyncio.create_task(service.test(user_id="user-1", request=request))
    second = asyncio.create_task(service.test(user_id="user-2", request=request))
    await asyncio.sleep(0)
    gate.set()
    await asyncio.gather(first, second)

    assert sorted(adapter.calls) == [("user-1", "docs"), ("user-2", "docs")]


async def test_cancelling_waiter_does_not_cancel_shared_check() -> None:
    gate = asyncio.Event()
    adapter = RecordingAdapter(gate=gate)
    service = ProviderDiagnosticService(adapters={ProviderType.MCP: adapter})
    request = ProviderDiagnosticRequest(provider_type="mcp", target_id="docs")

    cancelled_waiter = asyncio.create_task(
        service.test(user_id="user-1", request=request)
    )
    surviving_waiter = asyncio.create_task(
        service.test(user_id="user-1", request=request)
    )
    await asyncio.sleep(0)
    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter

    gate.set()
    result = await surviving_waiter

    assert result.status is ProviderDiagnosticStatus.HEALTHY
    assert adapter.calls == [("user-1", "docs")]


async def test_inflight_registry_rejects_new_keys_at_capacity() -> None:
    gate = asyncio.Event()
    adapter = RecordingAdapter(gate=gate)
    service = ProviderDiagnosticService(
        adapters={ProviderType.MCP: adapter},
        max_inflight=1,
    )
    first = asyncio.create_task(
        service.test(
            user_id="user-1",
            request=ProviderDiagnosticRequest(
                provider_type="mcp",
                target_id="docs",
            ),
        )
    )
    await asyncio.sleep(0)

    with pytest.raises(TooManusRequestsError):
        await service.test(
            user_id="user-1",
            request=ProviderDiagnosticRequest(
                provider_type="mcp",
                target_id="other",
            ),
        )

    gate.set()
    await first


async def test_unexpected_adapter_error_becomes_safe_business_result() -> None:
    class FailingAdapter:
        async def diagnose(self, **_kwargs):
            raise RuntimeError("secret https://internal.example token=abc")

    service = ProviderDiagnosticService(
        adapters={ProviderType.LLM: FailingAdapter()}
    )
    result = await service.test(
        user_id="user-1",
        request=ProviderDiagnosticRequest(provider_type="llm"),
    )

    assert result.status is ProviderDiagnosticStatus.DEGRADED
    assert result.failure is not None
    assert result.failure.code == "PROVIDER_DIAGNOSTIC_FAILED"
    serialized = result.model_dump_json()
    assert "internal.example" not in serialized
    assert "token=abc" not in serialized


async def test_missing_adapter_returns_safe_business_result() -> None:
    service = ProviderDiagnosticService(adapters={})

    result = await service.test(
        user_id="user-1",
        request=ProviderDiagnosticRequest(provider_type="llm"),
    )

    assert result.provider_id == "llm.default"
    assert result.status is ProviderDiagnosticStatus.DEGRADED
    assert result.failure is not None
    assert result.failure.code == "PROVIDER_DIAGNOSTIC_FAILED"


class FakeUserConfigService:
    def __init__(
        self,
        *,
        llm: LLMConfig | None = None,
        mcp: MCPConfig | None = None,
        a2a: A2AConfig | None = None,
        tool: ToolConfig | None = None,
    ) -> None:
        self.llm = llm or LLMConfig()
        self.mcp = mcp or MCPConfig()
        self.a2a = a2a or A2AConfig()
        self.tool = tool or ToolConfig()

    async def get_llm_config(self, user_id: str) -> LLMConfig:
        return self.llm

    async def get_mcp_config(self, user_id: str) -> MCPConfig:
        return self.mcp

    async def get_a2a_config(self, user_id: str) -> A2AConfig:
        return self.a2a

    async def get_tool_config(self, user_id: str) -> ToolConfig:
        return self.tool


async def test_llm_adapter_uses_one_tiny_request_and_closes_client() -> None:
    created_configs: list[LLMConfig] = []

    class FakeLLM:
        def __init__(self) -> None:
            self.calls = []
            self.closed = False

        async def invoke(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            return {"role": "assistant", "content": "OK"}

        async def aclose(self) -> None:
            self.closed = True

    fake_llm = FakeLLM()

    def factory(config: LLMConfig):
        created_configs.append(config)
        return fake_llm

    adapter = LLMProviderDiagnosticAdapter(
        user_config_service=FakeUserConfigService(
            llm=LLMConfig(
                base_url="https://llm.example.test",
                api_key="secret",
                model_name="model",
                max_tokens=8192,
            )
        ),
        llm_factory=factory,
    )

    result = await adapter.diagnose(user_id="user-1", target_id=None)

    assert result.status is ProviderDiagnosticStatus.HEALTHY
    assert result.provider_id == "llm.default"
    assert created_configs[0].max_tokens == 1
    assert created_configs[0].temperature == 0
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0][1]["log_response"] is False
    assert fake_llm.closed is True


async def test_production_diagnostic_llm_disables_sdk_retries() -> None:
    llm = get_diagnostic_llm(
        LLMConfig(
            base_url="https://llm.example.test",
            api_key="secret",
            model_name="model",
        )
    )
    try:
        assert llm._client.max_retries == 0
    finally:
        await llm.aclose()


async def test_llm_adapter_preserves_model_failure_and_closes_client() -> None:
    failure = model_failure(ModelFailureCode.AUTHENTICATION_FAILED).model_copy(
        update={"provider_id": "llm.default"}
    )

    class FakeLLM:
        closed = False

        async def invoke(self, *_args, **_kwargs):
            raise ModelRuntimeError(failure)

        async def aclose(self) -> None:
            self.closed = True

    fake_llm = FakeLLM()
    adapter = LLMProviderDiagnosticAdapter(
        user_config_service=FakeUserConfigService(
            llm=LLMConfig(api_key="secret", model_name="model")
        ),
        llm_factory=lambda _config: fake_llm,
    )

    result = await adapter.diagnose(user_id="user-1", target_id=None)

    assert result.status is ProviderDiagnosticStatus.UNHEALTHY
    assert result.failure == failure
    assert fake_llm.closed is True


async def test_llm_adapter_enforces_outer_timeout() -> None:
    class SlowLLM:
        closed = False

        async def invoke(self, *_args, **_kwargs):
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            self.closed = True

    fake_llm = SlowLLM()
    adapter = LLMProviderDiagnosticAdapter(
        user_config_service=FakeUserConfigService(
            llm=LLMConfig(api_key="secret", model_name="model")
        ),
        llm_factory=lambda _config: fake_llm,
        timeout_seconds=0.001,
    )

    result = await adapter.diagnose(user_id="user-1", target_id=None)

    assert result.status is ProviderDiagnosticStatus.DEGRADED
    assert result.failure is not None
    assert result.failure.code == "MODEL_TIMEOUT"
    assert fake_llm.closed is True


async def test_mcp_adapter_force_refreshes_only_saved_target() -> None:
    saved_config = MCPServerConfig(
        url="https://mcp.example.test",
        enabled=False,
    )

    class FakePool:
        kwargs = None

        async def discover(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(schemas=[{"name": "one"}, {"name": "two"}])

    pool = FakePool()
    adapter = MCPProviderDiagnosticAdapter(
        user_config_service=FakeUserConfigService(
            mcp=MCPConfig(mcpServers={"docs": saved_config})
        ),
        provider_pool=pool,
    )

    result = await adapter.diagnose(user_id="user-1", target_id="docs")

    assert result.status is ProviderDiagnosticStatus.HEALTHY
    assert result.capability_count == 2
    assert result.snapshot_state == "fresh"
    assert pool.kwargs["force_refresh"] is True
    assert pool.kwargs["server_name"] == "docs"
    assert pool.kwargs["server_config"].enabled is True


async def test_mcp_adapter_returns_typed_runtime_failure() -> None:
    failure = provider_failure(
        ProviderFailureCode.TIMEOUT,
        provider_id="mcp.docs",
    )

    class FakePool:
        async def discover(self, **_kwargs):
            raise ProviderRuntimeError(failure)

    adapter = MCPProviderDiagnosticAdapter(
        user_config_service=FakeUserConfigService(
            mcp=MCPConfig(
                mcpServers={"docs": MCPServerConfig(url="https://mcp.example.test")}
            )
        ),
        provider_pool=FakePool(),
    )

    result = await adapter.diagnose(user_id="user-1", target_id="docs")

    assert result.status is ProviderDiagnosticStatus.DEGRADED
    assert result.failure == failure


async def test_mcp_adapter_enforces_outer_timeout() -> None:
    class SlowPool:
        async def discover(self, **_kwargs):
            await asyncio.Event().wait()

    adapter = MCPProviderDiagnosticAdapter(
        user_config_service=FakeUserConfigService(
            mcp=MCPConfig(
                mcpServers={"docs": MCPServerConfig(url="https://mcp.example.test")}
            )
        ),
        provider_pool=SlowPool(),
        timeout_seconds=0.001,
    )

    result = await adapter.diagnose(user_id="user-1", target_id="docs")

    assert result.status is ProviderDiagnosticStatus.DEGRADED
    assert result.failure is not None
    assert result.failure.code == "PROVIDER_TIMEOUT"


async def test_a2a_adapter_forces_fresh_card_without_stale_fallback() -> None:
    target = A2AServerConfig(
        id="researcher",
        base_url="https://agent.example.test",
        enabled=False,
    )

    class FakeRuntime:
        kwargs = None

        async def discover(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                card={"skills": [{"name": "research"}]},
            )

    runtime = FakeRuntime()
    adapter = A2AProviderDiagnosticAdapter(
        user_config_service=FakeUserConfigService(a2a=A2AConfig(a2a_servers=[target])),
        provider_runtime=runtime,
    )

    result = await adapter.diagnose(user_id="user-1", target_id="researcher")

    assert result.status is ProviderDiagnosticStatus.HEALTHY
    assert result.capability_count == 1
    assert runtime.kwargs["force_refresh"] is True
    assert runtime.kwargs["allow_stale"] is False
    assert runtime.kwargs["target_config"].enabled is True


async def test_a2a_adapter_returns_typed_runtime_failure() -> None:
    failure = a2a_failure(
        A2AFailureCode.CARD_DISCOVERY_FAILED,
        target_id="researcher",
    )

    class FakeRuntime:
        async def discover(self, **_kwargs):
            raise A2ARuntimeError(failure)

    adapter = A2AProviderDiagnosticAdapter(
        user_config_service=FakeUserConfigService(
            a2a=A2AConfig(
                a2a_servers=[
                    A2AServerConfig(
                        id="researcher",
                        base_url="https://agent.example.test",
                    )
                ]
            )
        ),
        provider_runtime=FakeRuntime(),
    )

    result = await adapter.diagnose(user_id="user-1", target_id="researcher")

    assert result.status is ProviderDiagnosticStatus.DEGRADED
    assert result.failure == failure


async def test_a2a_adapter_enforces_outer_timeout() -> None:
    class SlowRuntime:
        async def discover(self, **_kwargs):
            await asyncio.Event().wait()

    adapter = A2AProviderDiagnosticAdapter(
        user_config_service=FakeUserConfigService(
            a2a=A2AConfig(
                a2a_servers=[
                    A2AServerConfig(
                        id="researcher",
                        base_url="https://agent.example.test",
                    )
                ]
            )
        ),
        provider_runtime=SlowRuntime(),
        timeout_seconds=0.001,
    )

    result = await adapter.diagnose(user_id="user-1", target_id="researcher")

    assert result.status is ProviderDiagnosticStatus.DEGRADED
    assert result.failure is not None
    assert result.failure.code == "A2A_TIMEOUT"


async def test_api_adapter_only_validates_schema_without_operation_arguments() -> None:
    registration = ToolRegistration(
        registration_id="weather",
        provider_id="api.weather",
        provider_label="Weather",
        config={
            "openapi_schema": {
                "openapi": "3.0.0",
                "paths": {
                    "/one": {"get": {}},
                    "/two": {"get": {}, "post": {}},
                },
            }
        },
    )

    class FakeToolConfigService:
        async def get_tool_config(self, user_id: str):
            return ToolConfig(registrations={"weather": registration})

        async def test_registration(self, *_args, **_kwargs):
            raise AssertionError("diagnostics must not use the Operation test path")

    tool_service = FakeToolConfigService()
    adapter = APIProviderDiagnosticAdapter(tool_config_service=tool_service)

    result = await adapter.diagnose(user_id="user-1", target_id="weather")

    assert result.status is ProviderDiagnosticStatus.HEALTHY
    assert result.check_kind is ProviderCheckKind.CONFIGURATION
    assert result.capability_count == 3


async def test_api_adapter_rejects_missing_schema_without_operation_call() -> None:
    registration = ToolRegistration(
        registration_id="unsafe-id",
        provider_id="https://secret.example/token",
        provider_label="Unsafe",
        config={},
    )

    class FakeToolConfigService:
        async def get_tool_config(self, user_id: str):
            return ToolConfig(registrations={"unsafe-id": registration})

        async def test_registration(self, *_args, **_kwargs):
            raise AssertionError("diagnostics must not use the Operation test path")

    adapter = APIProviderDiagnosticAdapter(
        tool_config_service=FakeToolConfigService()
    )

    result = await adapter.diagnose(user_id="user-1", target_id="unsafe-id")

    assert result.status is ProviderDiagnosticStatus.UNHEALTHY
    assert result.failure is not None
    assert result.failure.code == "PROVIDER_CONFIGURATION_INVALID"
    assert result.provider_id.startswith("api.provider-")
    assert "secret.example" not in result.model_dump_json()


@pytest.mark.parametrize("provider_type", ["mcp", "a2a", "api"])
async def test_missing_saved_target_is_http_not_found(provider_type: str) -> None:
    adapters = {
        ProviderType.MCP: MCPProviderDiagnosticAdapter(
            user_config_service=FakeUserConfigService(),
            provider_pool=SimpleNamespace(),
        ),
        ProviderType.A2A: A2AProviderDiagnosticAdapter(
            user_config_service=FakeUserConfigService(),
            provider_runtime=SimpleNamespace(),
        ),
        ProviderType.API: APIProviderDiagnosticAdapter(
            tool_config_service=SimpleNamespace(
                get_tool_config=FakeUserConfigService().get_tool_config
            )
        ),
    }
    service = ProviderDiagnosticService(adapters=adapters)

    with pytest.raises(NotFoundError):
        await service.test(
            user_id="user-1",
            request=ProviderDiagnosticRequest(
                provider_type=provider_type,
                target_id="missing",
            ),
        )

"""Tenant-isolated coordinator for on-demand Provider diagnostics."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Mapping
from typing import Any, Callable, Protocol

from app.core.llm.failure import ModelFailureCode, ModelRuntimeError, model_failure
from app.core.entities.failure import FailureInfo
from app.core.provider_diagnostics import (
    ProviderDiagnosticFailureCode,
    provider_diagnostic_failure,
)
from app.core.tools.a2a_runtime import (
    A2AFailureCode,
    A2AProviderRuntime,
    A2ARuntimeError,
    a2a_failure,
)
from app.core.tools.api import inspect_api_tool_registration
from app.core.tools.provider_catalog import mcp_provider_id
from app.core.tools.provider_runtime import (
    MCPProviderPool,
    ProviderFailureCode,
    ProviderRuntimeError,
    provider_failure,
)
from app.schemas.exceptions import (
    AppException,
    BadRequestError,
    NotFoundError,
    TooManusRequestsError,
)
from app.schemas.provider_diagnostic import (
    ProviderCheckKind,
    ProviderDiagnosticRequest,
    ProviderDiagnosticResult,
    ProviderDiagnosticStatus,
    ProviderType,
)
from app.services.tool_config_service import ToolConfigService
from app.services.user_config_service import UserConfigService


logger = logging.getLogger(__name__)


class ProviderDiagnosticAdapter(Protocol):
    async def diagnose(
        self,
        *,
        user_id: str,
        target_id: str | None,
    ) -> ProviderDiagnosticResult: ...


DiagnosticKey = tuple[str, ProviderType, str | None]


class LLMProtocol(Protocol):
    async def invoke(self, messages: list[dict[str, Any]], **kwargs) -> dict: ...

    async def aclose(self) -> None: ...


class LLMProviderDiagnosticAdapter:
    def __init__(
        self,
        *,
        user_config_service: UserConfigService,
        llm_factory: Callable[[Any], LLMProtocol],
        timeout_seconds: float = 15.0,
    ) -> None:
        self._user_config_service = user_config_service
        self._llm_factory = llm_factory
        self._timeout_seconds = timeout_seconds

    async def diagnose(
        self,
        *,
        user_id: str,
        target_id: str | None,
    ) -> ProviderDiagnosticResult:
        started = time.monotonic()
        config = await self._user_config_service.get_llm_config(user_id)
        if not str(config.base_url).strip() or not config.model_name.strip():
            return _configuration_failure(
                ProviderType.LLM,
                "llm.default",
                started,
            )
        diagnostic_config = config.model_copy(
            update={"temperature": 0, "max_tokens": 1}
        )
        llm: LLMProtocol | None = None
        try:
            llm = self._llm_factory(diagnostic_config)
            async with asyncio.timeout(self._timeout_seconds):
                await llm.invoke(
                    messages=[
                        {
                            "role": "user",
                            "content": "Reply with OK.",
                        }
                    ],
                    log_response=False,
                )
        except ModelRuntimeError as exc:
            failure = exc.failure.model_copy(
                update={"provider_id": "llm.default"}
            )
            return _failure_result(
                ProviderType.LLM,
                "llm.default",
                failure,
                started,
            )
        except TimeoutError:
            failure = model_failure(ModelFailureCode.TIMEOUT).model_copy(
                update={"provider_id": "llm.default"}
            )
            return _failure_result(
                ProviderType.LLM,
                "llm.default",
                failure,
                started,
            )
        finally:
            if llm is not None:
                try:
                    async with asyncio.timeout(5.0):
                        await llm.aclose()
                except Exception as exc:
                    logger.error(
                        "LLM diagnostic client close failed error_type=%s",
                        type(exc).__name__,
                    )
        return _success_result(
            ProviderType.LLM,
            "llm.default",
            started,
            message="模型服务连接成功。",
        )


class MCPProviderDiagnosticAdapter:
    def __init__(
        self,
        *,
        user_config_service: UserConfigService,
        provider_pool: MCPProviderPool,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._user_config_service = user_config_service
        self._provider_pool = provider_pool
        self._timeout_seconds = timeout_seconds

    async def diagnose(
        self,
        *,
        user_id: str,
        target_id: str | None,
    ) -> ProviderDiagnosticResult:
        assert target_id is not None
        config = await self._user_config_service.get_mcp_config(user_id)
        saved = config.mcpServers.get(target_id)
        if saved is None:
            raise NotFoundError("MCP Provider 不存在。")
        provider_id = mcp_provider_id(target_id)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                snapshot = await self._provider_pool.discover(
                    user_id=user_id,
                    provider_id=provider_id,
                    server_name=target_id,
                    server_config=saved.model_copy(update={"enabled": True}),
                    force_refresh=True,
                )
        except ProviderRuntimeError as exc:
            return _failure_result(
                ProviderType.MCP,
                provider_id,
                exc.failure,
                started,
            )
        except TimeoutError:
            failure = provider_failure(
                ProviderFailureCode.TIMEOUT,
                provider_id=provider_id,
            )
            return _failure_result(
                ProviderType.MCP,
                provider_id,
                failure,
                started,
            )
        return _success_result(
            ProviderType.MCP,
            provider_id,
            started,
            message="MCP Tool Schema 获取成功。",
            capability_count=len(snapshot.schemas),
            snapshot_state="fresh",
        )


class A2AProviderDiagnosticAdapter:
    def __init__(
        self,
        *,
        user_config_service: UserConfigService,
        provider_runtime: A2AProviderRuntime,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._user_config_service = user_config_service
        self._provider_runtime = provider_runtime
        self._timeout_seconds = timeout_seconds

    async def diagnose(
        self,
        *,
        user_id: str,
        target_id: str | None,
    ) -> ProviderDiagnosticResult:
        assert target_id is not None
        config = await self._user_config_service.get_a2a_config(user_id)
        saved = next(
            (item for item in config.a2a_servers if item.id == target_id),
            None,
        )
        if saved is None:
            raise NotFoundError("A2A Provider 不存在。")
        provider_id = f"a2a.remote:{target_id}"
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                snapshot = await self._provider_runtime.discover(
                    user_id=user_id,
                    target_config=saved.model_copy(update={"enabled": True}),
                    force_refresh=True,
                    allow_stale=False,
                )
        except A2ARuntimeError as exc:
            return _failure_result(
                ProviderType.A2A,
                provider_id,
                exc.failure,
                started,
            )
        except TimeoutError:
            failure = a2a_failure(
                A2AFailureCode.TIMEOUT,
                target_id=target_id,
            )
            return _failure_result(
                ProviderType.A2A,
                provider_id,
                failure,
                started,
            )
        raw_skills = snapshot.card.get("skills")
        capability_count = (
            sum(isinstance(item, dict) for item in raw_skills)
            if isinstance(raw_skills, list)
            else 0
        )
        return _success_result(
            ProviderType.A2A,
            provider_id,
            started,
            message="A2A Agent Card 获取成功。",
            capability_count=capability_count,
            snapshot_state="fresh",
        )


class APIProviderDiagnosticAdapter:
    def __init__(
        self,
        *,
        tool_config_service: ToolConfigService,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._tool_config_service = tool_config_service
        self._timeout_seconds = timeout_seconds

    async def diagnose(
        self,
        *,
        user_id: str,
        target_id: str | None,
    ) -> ProviderDiagnosticResult:
        assert target_id is not None
        config = await self._tool_config_service.get_tool_config(user_id)
        registration = config.registrations.get(target_id)
        if (
            registration is None
            or registration.source_type != "api"
            or registration.executor_type != "api"
        ):
            raise NotFoundError("API Provider 不存在。")
        provider_id = _api_provider_id(registration.provider_id)
        started = time.monotonic()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                definitions = await asyncio.to_thread(
                    inspect_api_tool_registration,
                    registration.model_copy(update={"enabled": True}),
                )
        except (BadRequestError, ValueError):
            return _configuration_failure(
                ProviderType.API,
                provider_id,
                started,
            )
        except TimeoutError:
            failure = provider_diagnostic_failure(
                ProviderDiagnosticFailureCode.DIAGNOSTIC_FAILED,
                provider_id=provider_id,
            )
            return _failure_result(
                ProviderType.API,
                provider_id,
                failure,
                started,
            )
        return _success_result(
            ProviderType.API,
            provider_id,
            started,
            message="API Tool 配置与 OpenAPI Schema 有效；未调用远程 Operation。",
            capability_count=len(definitions),
        )


class ProviderDiagnosticService:
    """Coordinate adapters without persisting or changing runtime state."""

    def __init__(
        self,
        *,
        adapters: Mapping[ProviderType, ProviderDiagnosticAdapter],
        max_inflight: int = 128,
    ) -> None:
        if max_inflight <= 0:
            raise ValueError("Provider diagnostic max_inflight must be positive")
        self._adapters = dict(adapters)
        self._max_inflight = max_inflight
        self._inflight: dict[
            DiagnosticKey,
            asyncio.Task[ProviderDiagnosticResult],
        ] = {}
        self._lock = asyncio.Lock()

    async def test(
        self,
        *,
        user_id: str,
        request: ProviderDiagnosticRequest,
    ) -> ProviderDiagnosticResult:
        key = (user_id, request.provider_type, request.target_id)
        async with self._lock:
            task = self._inflight.get(key)
            if task is None:
                if len(self._inflight) >= self._max_inflight:
                    raise TooManusRequestsError(
                        "Provider 诊断请求较多，请稍后重试。"
                    )
                task = asyncio.create_task(
                    self._run_and_cleanup(key, request),
                    name=(
                        "provider-diagnostic:"
                        f"{request.provider_type.value}:"
                        f"{_provider_id(request)}"
                    ),
                )
                self._inflight[key] = task
        return await asyncio.shield(task)

    async def _run_and_cleanup(
        self,
        key: DiagnosticKey,
        request: ProviderDiagnosticRequest,
    ) -> ProviderDiagnosticResult:
        started = time.monotonic()
        try:
            adapter = self._adapters.get(request.provider_type)
            if adapter is None:
                result = self._unexpected_failure(request, started)
                _log_result(result)
                return result
            try:
                result = await adapter.diagnose(
                    user_id=key[0],
                    target_id=request.target_id,
                )
                _log_result(result)
                return result
            except asyncio.CancelledError:
                raise
            except AppException:
                raise
            except Exception as exc:
                logger.error(
                    "Provider diagnostic adapter failed type=%s provider_id=%s error_type=%s",
                    request.provider_type.value,
                    _provider_id(request),
                    type(exc).__name__,
                )
                result = self._unexpected_failure(request, started)
                _log_result(result)
                return result
        finally:
            current = asyncio.current_task()
            async with self._lock:
                if self._inflight.get(key) is current:
                    self._inflight.pop(key, None)

    @staticmethod
    def _unexpected_failure(
        request: ProviderDiagnosticRequest,
        started: float,
    ) -> ProviderDiagnosticResult:
        provider_id = _provider_id(request)
        failure = provider_diagnostic_failure(
            ProviderDiagnosticFailureCode.DIAGNOSTIC_FAILED,
            provider_id=provider_id,
        )
        return ProviderDiagnosticResult(
            provider_type=request.provider_type,
            provider_id=provider_id,
            check_kind=_check_kind(request.provider_type),
            status=ProviderDiagnosticStatus.DEGRADED,
            message=failure.message,
            latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            failure=failure,
        )


def _provider_id(request: ProviderDiagnosticRequest) -> str:
    if request.provider_type is ProviderType.LLM:
        return "llm.default"
    if request.provider_type is ProviderType.MCP:
        return mcp_provider_id(request.target_id or "provider")
    if request.provider_type is ProviderType.A2A:
        return f"a2a.remote:{request.target_id}"
    return _api_provider_id(request.target_id or "api.unknown")


def _check_kind(provider_type: ProviderType) -> ProviderCheckKind:
    if provider_type is ProviderType.LLM:
        return ProviderCheckKind.INFERENCE
    if provider_type is ProviderType.API:
        return ProviderCheckKind.CONFIGURATION
    return ProviderCheckKind.DISCOVERY


def _api_provider_id(provider_id: str) -> str:
    value = str(provider_id).strip()
    if len(value) <= 160 and re.fullmatch(r"api\.[A-Za-z0-9._-]+", value):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"api.provider-{digest}"


def _success_result(
    provider_type: ProviderType,
    provider_id: str,
    started: float,
    *,
    message: str,
    capability_count: int | None = None,
    snapshot_state: str | None = None,
) -> ProviderDiagnosticResult:
    return ProviderDiagnosticResult(
        provider_type=provider_type,
        provider_id=provider_id,
        check_kind=_check_kind(provider_type),
        status=ProviderDiagnosticStatus.HEALTHY,
        message=message,
        latency_ms=_latency_ms(started),
        capability_count=capability_count,
        snapshot_state=snapshot_state,
    )


def _failure_result(
    provider_type: ProviderType,
    provider_id: str,
    failure: FailureInfo,
    started: float,
) -> ProviderDiagnosticResult:
    return ProviderDiagnosticResult(
        provider_type=provider_type,
        provider_id=provider_id,
        check_kind=_check_kind(provider_type),
        status=(
            ProviderDiagnosticStatus.DEGRADED
            if failure.retryable
            else ProviderDiagnosticStatus.UNHEALTHY
        ),
        message=failure.message,
        latency_ms=_latency_ms(started),
        failure=failure,
    )


def _configuration_failure(
    provider_type: ProviderType,
    provider_id: str,
    started: float,
) -> ProviderDiagnosticResult:
    failure = provider_diagnostic_failure(
        ProviderDiagnosticFailureCode.CONFIGURATION_INVALID,
        provider_id=provider_id,
    )
    return _failure_result(provider_type, provider_id, failure, started)


def _latency_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _log_result(result: ProviderDiagnosticResult) -> None:
    logger.info(
        "Provider diagnostic completed type=%s provider_id=%s status=%s code=%s debug_id=%s latency_ms=%d",
        result.provider_type.value,
        result.provider_id,
        result.status.value,
        result.failure.code if result.failure is not None else "none",
        result.failure.debug_id if result.failure is not None else "none",
        result.latency_ms,
    )

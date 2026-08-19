#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Provider runtime primitives shared by external tool adapters."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol

from app.core.entities.app_config import MCPConfig, MCPServerConfig
from app.core.entities.failure import (
    FailureCategory,
    FailureInfo,
    FailureScope,
    RecoveryAction,
)
from app.core.entities.tool_result import ToolResult


logger = logging.getLogger(__name__)


class ProviderFailureCode(str, Enum):
    CONNECT_FAILED = "PROVIDER_CONNECT_FAILED"
    AUTH_FAILED = "PROVIDER_AUTH_FAILED"
    TIMEOUT = "PROVIDER_TIMEOUT"
    PROTOCOL_ERROR = "PROVIDER_PROTOCOL_ERROR"
    SCHEMA_DISCOVERY_FAILED = "MCP_SCHEMA_DISCOVERY_FAILED"


_PROVIDER_FAILURE_DEFAULTS: dict[
    ProviderFailureCode,
    tuple[str, FailureScope, bool, list[RecoveryAction]],
] = {
    ProviderFailureCode.CONNECT_FAILED: (
        "外部工具服务暂时无法连接。",
        FailureScope.OPERATION,
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHOOSE_PROVIDER],
    ),
    ProviderFailureCode.AUTH_FAILED: (
        "外部工具服务需要重新授权或检查配置。",
        FailureScope.OPERATION,
        False,
        [RecoveryAction.REAUTHORIZE, RecoveryAction.CHECK_CONFIG],
    ),
    ProviderFailureCode.TIMEOUT: (
        "外部工具服务响应超时，请稍后重试。",
        FailureScope.OPERATION,
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHOOSE_PROVIDER],
    ),
    ProviderFailureCode.PROTOCOL_ERROR: (
        "外部工具服务通信异常。",
        FailureScope.OPERATION,
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHOOSE_PROVIDER],
    ),
    ProviderFailureCode.SCHEMA_DISCOVERY_FAILED: (
        "外部工具清单暂时无法获取。",
        FailureScope.STEP,
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHOOSE_PROVIDER],
    ),
}


def provider_failure(
    code: ProviderFailureCode,
    *,
    provider_id: str,
    tool_call_id: str | None = None,
    source: str = "mcp",
) -> FailureInfo:
    message, scope, retryable, actions = _PROVIDER_FAILURE_DEFAULTS[code]
    return FailureInfo(
        code=code.value,
        category=FailureCategory.PROVIDER,
        scope=scope,
        source=source,
        message=message,
        retryable=retryable,
        recovery_actions=actions,
        provider_id=provider_id,
        tool_call_id=tool_call_id,
    )


class ProviderRuntimeError(RuntimeError):
    """Internal exception carrying only a safe public FailureInfo projection."""

    def __init__(
        self,
        failure: FailureInfo,
        *,
        cause: BaseException | None = None,
    ) -> None:
        self.failure = failure
        super().__init__(failure.message)
        if cause is not None:
            self.__cause__ = cause


MCP_PROTOCOL_VERSION = "mcp-v1"


def mcp_config_fingerprint(config: MCPServerConfig) -> str:
    """Hash the full config without exposing connection details in runtime keys."""
    payload = json.dumps(
        config.model_dump(mode="json", exclude_none=False),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderRuntimeKey:
    user_id: str
    provider_id: str
    config_fingerprint: str
    protocol_version: str = MCP_PROTOCOL_VERSION


@dataclass(slots=True)
class MCPSchemaSnapshot:
    key: ProviderRuntimeKey
    schemas: list[dict]
    discovered_at: float
    expires_at: float

    def clone(self) -> "MCPSchemaSnapshot":
        return MCPSchemaSnapshot(
            key=self.key,
            schemas=copy.deepcopy(self.schemas),
            discovered_at=self.discovered_at,
            expires_at=self.expires_at,
        )


class MCPSchemaSnapshotCache:
    """Process-local safe schema cache; values are copied across its boundary."""

    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int = 2048,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("MCP schema snapshot TTL must be positive")
        if max_entries <= 0:
            raise ValueError("MCP schema snapshot max entries must be positive")
        self._ttl_seconds = float(ttl_seconds)
        self._max_entries = int(max_entries)
        self._clock = clock
        self._snapshots: dict[ProviderRuntimeKey, MCPSchemaSnapshot] = {}

    def get(self, key: ProviderRuntimeKey) -> MCPSchemaSnapshot | None:
        snapshot = self._snapshots.get(key)
        if snapshot is None:
            return None
        if snapshot.expires_at <= self._clock():
            self._snapshots.pop(key, None)
            return None
        return snapshot.clone()

    def put(
        self,
        key: ProviderRuntimeKey,
        schemas: list[dict],
    ) -> MCPSchemaSnapshot:
        now = self._clock()
        self._prune_expired(now)
        if key not in self._snapshots and len(self._snapshots) >= self._max_entries:
            oldest_key = min(
                self._snapshots,
                key=lambda item: (
                    self._snapshots[item].expires_at,
                    self._snapshots[item].discovered_at,
                ),
            )
            self._snapshots.pop(oldest_key, None)
        snapshot = MCPSchemaSnapshot(
            key=key,
            schemas=copy.deepcopy(schemas),
            discovered_at=now,
            expires_at=now + self._ttl_seconds,
        )
        self._snapshots[key] = snapshot
        return snapshot.clone()

    def invalidate(
        self,
        *,
        user_id: str,
        provider_id: str,
    ) -> int:
        keys = [
            key
            for key in self._snapshots
            if key.user_id == user_id and key.provider_id == provider_id
        ]
        for key in keys:
            self._snapshots.pop(key, None)
        return len(keys)

    def pop(self, key: ProviderRuntimeKey) -> MCPSchemaSnapshot | None:
        snapshot = self._snapshots.pop(key, None)
        return snapshot.clone() if snapshot is not None else None

    def clear(self) -> None:
        self._snapshots.clear()

    def _prune_expired(self, now: float) -> None:
        for key in [
            key
            for key, snapshot in self._snapshots.items()
            if snapshot.expires_at <= now
        ]:
            self._snapshots.pop(key, None)


class MCPManagerProtocol(Protocol):
    async def initialize(self) -> None: ...

    async def get_all_tools(self) -> list[dict[str, Any]]: ...

    async def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult: ...

    async def cleanup(self) -> None: ...


class ProviderActorState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass(slots=True)
class _ActorRequest:
    operation: str
    future: asyncio.Future
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None


class MCPProviderActor:
    """Own exactly one MCP manager and all of its transport lifecycle."""

    def __init__(
        self,
        *,
        key: ProviderRuntimeKey,
        server_name: str,
        server_config: MCPServerConfig,
        manager_factory: Callable[[MCPConfig], MCPManagerProtocol],
        snapshots: MCPSchemaSnapshotCache,
        idle_ttl_seconds: float,
        operation_timeout_seconds: float,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        clock: Callable[[], float],
        on_done: Callable[["MCPProviderActor"], None] | None = None,
    ) -> None:
        self.key = key
        self._server_name = server_name
        self._server_config = server_config.model_copy(deep=True)
        self._manager_factory = manager_factory
        self._snapshots = snapshots
        self._idle_ttl_seconds = max(0.0, float(idle_ttl_seconds))
        self._operation_timeout_seconds = float(operation_timeout_seconds)
        self._backoff_base_seconds = float(backoff_base_seconds)
        self._backoff_max_seconds = float(backoff_max_seconds)
        self._clock = clock
        self._on_done = on_done
        self._queue: asyncio.Queue[_ActorRequest] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._manager: MCPManagerProtocol | None = None
        self._state = ProviderActorState.DISCONNECTED
        self._failure_count = 0
        self._retry_after = 0.0
        self._last_failure: FailureInfo | None = None

    @property
    def state(self) -> ProviderActorState:
        return self._state

    @property
    def done(self) -> bool:
        return self._task is not None and self._task.done()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self._serve(),
                name=f"mcp-provider:{self.key.provider_id}",
            )

    async def discover(self) -> MCPSchemaSnapshot:
        return await self._request("discover")

    async def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        return await self._request(
            "invoke",
            tool_name=tool_name,
            arguments=arguments,
        )

    async def close(self) -> None:
        task = self._task
        if task is None or task.done():
            return
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self._queue.put(_ActorRequest(operation="close", future=future))
        await asyncio.shield(future)
        await asyncio.shield(task)

    async def _request(
        self,
        operation: str,
        *,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
    ):
        self.start()
        if self.done:
            raise ProviderRuntimeError(
                provider_failure(
                    ProviderFailureCode.CONNECT_FAILED,
                    provider_id=self.key.provider_id,
                )
            )
        future = asyncio.get_running_loop().create_future()
        await self._queue.put(
            _ActorRequest(
                operation=operation,
                future=future,
                tool_name=tool_name,
                arguments=arguments,
            )
        )
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # A queued request whose caller has gone away must not later invoke
            # an external Provider. An already-running operation remains under
            # the Actor's own timeout/lifecycle boundary.
            future.cancel()
            raise

    async def _serve(self) -> None:
        terminal_failure: ProviderRuntimeError | None = None
        try:
            while True:
                try:
                    if self._idle_ttl_seconds > 0:
                        request = await asyncio.wait_for(
                            self._queue.get(),
                            timeout=self._idle_ttl_seconds,
                        )
                    else:
                        request = await self._queue.get()
                except TimeoutError:
                    break

                if request.operation == "close":
                    if not request.future.done():
                        request.future.set_result(None)
                    break

                if request.future.cancelled():
                    continue

                try:
                    if request.operation == "discover":
                        result = await self._discover()
                    elif request.operation == "invoke":
                        result = await self._invoke(
                            request.tool_name or "",
                            request.arguments or {},
                        )
                    else:
                        raise RuntimeError("unsupported provider actor request")
                except ProviderRuntimeError as exc:
                    if not request.future.done():
                        request.future.set_exception(exc)
                except BaseException as exc:
                    failure = self._failure_for(
                        ProviderFailureCode.PROTOCOL_ERROR,
                        exc,
                    )
                    runtime_error = ProviderRuntimeError(failure, cause=exc)
                    if not request.future.done():
                        request.future.set_exception(runtime_error)
                else:
                    if not request.future.done():
                        request.future.set_result(result)

                if self._idle_ttl_seconds == 0:
                    break
        except BaseException as exc:
            terminal_failure = ProviderRuntimeError(
                self._failure_for(ProviderFailureCode.PROTOCOL_ERROR, exc),
                cause=exc,
            )
        finally:
            self._state = ProviderActorState.CLOSING
            await self._cleanup_manager()
            self._state = ProviderActorState.CLOSED
            self._fail_pending_requests(
                terminal_failure
                or ProviderRuntimeError(
                    provider_failure(
                        ProviderFailureCode.CONNECT_FAILED,
                        provider_id=self.key.provider_id,
                    )
                )
            )
            if self._on_done is not None:
                self._on_done(self)

    async def _discover(self) -> MCPSchemaSnapshot:
        cached = self._snapshots.get(self.key)
        if cached is not None:
            return cached
        manager = await self._ensure_manager()
        try:
            async with asyncio.timeout(self._operation_timeout_seconds):
                schemas = await manager.get_all_tools()
        except BaseException as exc:
            await self._degrade(
                self._failure_for(
                    ProviderFailureCode.SCHEMA_DISCOVERY_FAILED,
                    exc,
                )
            )
            raise ProviderRuntimeError(self._last_failure, cause=exc) from exc
        snapshot = self._snapshots.put(self.key, schemas)
        self._mark_success()
        return snapshot

    async def _invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        manager = await self._ensure_manager()
        try:
            async with asyncio.timeout(self._operation_timeout_seconds):
                result = await manager.invoke(tool_name, arguments)
        except BaseException as exc:
            await self._degrade(
                self._failure_for(ProviderFailureCode.PROTOCOL_ERROR, exc)
            )
            raise ProviderRuntimeError(self._last_failure, cause=exc) from exc
        self._mark_success()
        return result

    async def _ensure_manager(self) -> MCPManagerProtocol:
        if self._manager is not None:
            return self._manager
        if self._last_failure is not None and self._clock() < self._retry_after:
            raise ProviderRuntimeError(self._last_failure)

        self._state = ProviderActorState.CONNECTING
        manager = self._manager_factory(
            MCPConfig(
                mcpServers={
                    self._server_name: self._server_config.model_copy(deep=True),
                }
            )
        )
        try:
            async with asyncio.timeout(self._operation_timeout_seconds):
                await manager.initialize()
        except BaseException as exc:
            self._manager = manager
            await self._degrade(
                self._failure_for(ProviderFailureCode.CONNECT_FAILED, exc)
            )
            raise ProviderRuntimeError(self._last_failure, cause=exc) from exc

        self._manager = manager
        self._state = ProviderActorState.READY
        return manager

    def _mark_success(self) -> None:
        self._state = ProviderActorState.READY
        self._failure_count = 0
        self._retry_after = 0.0
        self._last_failure = None

    async def _degrade(self, failure: FailureInfo) -> None:
        self._failure_count += 1
        delay = min(
            self._backoff_base_seconds * (2 ** (self._failure_count - 1)),
            self._backoff_max_seconds,
        )
        self._retry_after = self._clock() + delay
        self._last_failure = failure
        self._state = ProviderActorState.DEGRADED
        await self._cleanup_manager()

    async def _cleanup_manager(self) -> None:
        manager = self._manager
        self._manager = None
        if manager is None:
            return
        try:
            async with asyncio.timeout(self._operation_timeout_seconds):
                await manager.cleanup()
        except BaseException:
            logger.exception(
                "MCP Provider [%s] cleanup failed",
                self.key.provider_id,
            )

    def _failure_for(
        self,
        code: ProviderFailureCode,
        exc: BaseException,
    ) -> FailureInfo:
        if isinstance(exc, TimeoutError):
            code = ProviderFailureCode.TIMEOUT
        return provider_failure(code, provider_id=self.key.provider_id)

    def _fail_pending_requests(self, error: ProviderRuntimeError) -> None:
        while True:
            try:
                request = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if not request.future.done():
                request.future.set_exception(error)


class MCPProviderPool:
    """Application-scoped, tenant-isolated MCP Provider Actor registry."""

    def __init__(
        self,
        *,
        manager_factory: Callable[[MCPConfig], MCPManagerProtocol],
        snapshot_ttl_seconds: float,
        snapshot_max_entries: int = 2048,
        idle_ttl_seconds: float,
        operation_timeout_seconds: float = 60.0,
        backoff_base_seconds: float = 1.0,
        backoff_max_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if backoff_base_seconds <= 0:
            raise ValueError("MCP Provider backoff base must be positive")
        if operation_timeout_seconds <= 0:
            raise ValueError("MCP Provider operation timeout must be positive")
        if backoff_max_seconds < backoff_base_seconds:
            raise ValueError("MCP Provider backoff max must be >= base")
        self._manager_factory = manager_factory
        self._snapshots = MCPSchemaSnapshotCache(
            ttl_seconds=snapshot_ttl_seconds,
            max_entries=snapshot_max_entries,
            clock=clock,
        )
        self._idle_ttl_seconds = idle_ttl_seconds
        self._operation_timeout_seconds = operation_timeout_seconds
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds
        self._clock = clock
        self._actors: dict[ProviderRuntimeKey, MCPProviderActor] = {}
        self._current_keys: dict[tuple[str, str], ProviderRuntimeKey] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def actor_count(self) -> int:
        return len(self._actors)

    async def discover(
        self,
        *,
        user_id: str,
        provider_id: str,
        server_name: str,
        server_config: MCPServerConfig,
        force_refresh: bool = False,
    ) -> MCPSchemaSnapshot:
        key = self._key(user_id, provider_id, server_config)
        await self._reconcile_key(key)
        if force_refresh:
            self._snapshots.pop(key)
        else:
            cached = self._snapshots.get(key)
            if cached is not None:
                return cached
        actor = await self._actor_for(key, server_name, server_config)
        return await actor.discover()

    async def invoke(
        self,
        *,
        user_id: str,
        provider_id: str,
        server_name: str,
        server_config: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        key = self._key(user_id, provider_id, server_config)
        await self._reconcile_key(key)
        actor = await self._actor_for(key, server_name, server_config)
        try:
            result = await actor.invoke(tool_name, arguments)
        except ProviderRuntimeError as exc:
            return ToolResult(failure=exc.failure)
        if not result.success and result.failure is None:
            return ToolResult(
                failure=provider_failure(
                    ProviderFailureCode.PROTOCOL_ERROR,
                    provider_id=provider_id,
                )
            )
        return result

    async def invalidate(
        self,
        *,
        user_id: str,
        provider_id: str,
    ) -> None:
        self._snapshots.invalidate(user_id=user_id, provider_id=provider_id)
        async with self._lock:
            self._current_keys.pop((user_id, provider_id), None)
            actors = [
                self._actors.pop(key)
                for key in list(self._actors)
                if key.user_id == user_id and key.provider_id == provider_id
            ]
        await asyncio.gather(
            *(actor.close() for actor in actors),
            return_exceptions=True,
        )

    async def close(self) -> None:
        async with self._lock:
            if self._closed and not self._actors:
                return
            self._closed = True
            actors = list(self._actors.values())
            self._actors.clear()
            self._current_keys.clear()
        await asyncio.gather(
            *(actor.close() for actor in actors),
            return_exceptions=True,
        )
        self._snapshots.clear()

    async def _actor_for(
        self,
        key: ProviderRuntimeKey,
        server_name: str,
        server_config: MCPServerConfig,
    ) -> MCPProviderActor:
        stale: list[MCPProviderActor] = []
        async with self._lock:
            if self._closed:
                raise ProviderRuntimeError(
                    provider_failure(
                        ProviderFailureCode.CONNECT_FAILED,
                        provider_id=key.provider_id,
                    )
                )
            if self._current_keys.get((key.user_id, key.provider_id)) != key:
                raise ProviderRuntimeError(
                    provider_failure(
                        ProviderFailureCode.CONNECT_FAILED,
                        provider_id=key.provider_id,
                    )
                )
            actor = self._actors.get(key)
            if actor is not None and not actor.done:
                return actor
            if actor is not None:
                self._actors.pop(key, None)

            for existing_key in list(self._actors):
                if (
                    existing_key.user_id == key.user_id
                    and existing_key.provider_id == key.provider_id
                    and existing_key != key
                ):
                    stale.append(self._actors.pop(existing_key))

            actor = MCPProviderActor(
                key=key,
                server_name=server_name,
                server_config=server_config,
                manager_factory=self._manager_factory,
                snapshots=self._snapshots,
                idle_ttl_seconds=self._idle_ttl_seconds,
                operation_timeout_seconds=self._operation_timeout_seconds,
                backoff_base_seconds=self._backoff_base_seconds,
                backoff_max_seconds=self._backoff_max_seconds,
                clock=self._clock,
                on_done=self._remove_actor,
            )
            self._actors[key] = actor
            actor.start()

        if stale:
            await asyncio.gather(
                *(item.close() for item in stale),
                return_exceptions=True,
            )
        return actor

    async def _reconcile_key(self, key: ProviderRuntimeKey) -> None:
        """Atomically select one config generation per tenant/provider."""
        stale: list[MCPProviderActor] = []
        identity = (key.user_id, key.provider_id)
        async with self._lock:
            if self._closed:
                raise ProviderRuntimeError(
                    provider_failure(
                        ProviderFailureCode.CONNECT_FAILED,
                        provider_id=key.provider_id,
                    )
                )
            self._prune_current_keys()
            current = self._current_keys.get(identity)
            if current == key:
                return
            self._current_keys[identity] = key
            self._snapshots.invalidate(
                user_id=key.user_id,
                provider_id=key.provider_id,
            )
            for existing_key in list(self._actors):
                if (
                    existing_key.user_id == key.user_id
                    and existing_key.provider_id == key.provider_id
                ):
                    stale.append(self._actors.pop(existing_key))

        if stale:
            await asyncio.gather(
                *(actor.close() for actor in stale),
                return_exceptions=True,
            )

    def _prune_current_keys(self) -> None:
        for identity, current_key in list(self._current_keys.items()):
            if current_key in self._actors:
                continue
            if self._snapshots.get(current_key) is not None:
                continue
            self._current_keys.pop(identity, None)

    def _remove_actor(self, actor: MCPProviderActor) -> None:
        if self._actors.get(actor.key) is actor:
            self._actors.pop(actor.key, None)

    @staticmethod
    def _key(
        user_id: str,
        provider_id: str,
        server_config: MCPServerConfig,
    ) -> ProviderRuntimeKey:
        return ProviderRuntimeKey(
            user_id=user_id,
            provider_id=provider_id,
            config_fingerprint=mcp_config_fingerprint(server_config),
        )

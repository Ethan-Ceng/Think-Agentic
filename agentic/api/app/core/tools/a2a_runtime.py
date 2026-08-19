#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Application-scoped A2A discovery and invocation runtime contracts."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.entities.app_config import A2AServerConfig
from app.core.entities.failure import (
    FailureCategory,
    FailureInfo,
    FailureScope,
    RecoveryAction,
)
from app.core.entities.tool_result import ToolResult


logger = logging.getLogger(__name__)


A2A_NEGOTIATION_POLICY_VERSION = "a2a-bindings-v1"


class A2AFailureCode(str, Enum):
    TARGET_NOT_FOUND = "A2A_TARGET_NOT_FOUND"
    CARD_DISCOVERY_FAILED = "A2A_CARD_DISCOVERY_FAILED"
    CARD_INVALID = "A2A_CARD_INVALID"
    UNSUPPORTED_BINDING = "A2A_UNSUPPORTED_BINDING"
    TIMEOUT = "A2A_TIMEOUT"
    INVOCATION_FAILED = "A2A_INVOCATION_FAILED"
    PROTOCOL_ERROR = "A2A_PROTOCOL_ERROR"
    RESPONSE_TOO_LARGE = "A2A_RESPONSE_TOO_LARGE"


_A2A_FAILURE_DEFAULTS: dict[
    A2AFailureCode,
    tuple[str, bool, list[RecoveryAction]],
] = {
    A2AFailureCode.TARGET_NOT_FOUND: (
        "指定的远程 Agent 不存在或未启用。",
        False,
        [RecoveryAction.CHOOSE_PROVIDER, RecoveryAction.CHECK_CONFIG],
    ),
    A2AFailureCode.CARD_DISCOVERY_FAILED: (
        "远程 Agent 的能力信息暂时无法获取。",
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHOOSE_PROVIDER],
    ),
    A2AFailureCode.CARD_INVALID: (
        "远程 Agent 返回了无效的能力信息。",
        False,
        [RecoveryAction.CHECK_CONFIG, RecoveryAction.CHOOSE_PROVIDER],
    ),
    A2AFailureCode.UNSUPPORTED_BINDING: (
        "远程 Agent 未提供当前支持的通信协议。",
        False,
        [RecoveryAction.CHECK_CONFIG, RecoveryAction.CHOOSE_PROVIDER],
    ),
    A2AFailureCode.TIMEOUT: (
        "远程 Agent 响应超时。",
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHOOSE_PROVIDER],
    ),
    A2AFailureCode.INVOCATION_FAILED: (
        "远程 Agent 暂时无法完成调用。",
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHOOSE_PROVIDER],
    ),
    A2AFailureCode.PROTOCOL_ERROR: (
        "远程 Agent 返回了无法处理的响应。",
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHOOSE_PROVIDER],
    ),
    A2AFailureCode.RESPONSE_TOO_LARGE: (
        "远程 Agent 返回的数据超过平台限制。",
        False,
        [RecoveryAction.CHOOSE_PROVIDER],
    ),
}


def a2a_failure(
    code: A2AFailureCode,
    *,
    target_id: str,
    tool_call_id: str | None = None,
) -> FailureInfo:
    message, retryable, actions = _A2A_FAILURE_DEFAULTS[code]
    return FailureInfo(
        code=code.value,
        category=FailureCategory.PROVIDER,
        scope=FailureScope.STEP,
        source="a2a",
        message=message,
        retryable=retryable,
        recovery_actions=actions,
        provider_id=f"a2a.remote:{target_id}",
        tool_call_id=tool_call_id,
    )


class A2ARuntimeError(RuntimeError):
    """Internal exception carrying only a safe public failure projection."""

    def __init__(
        self,
        failure: FailureInfo,
        *,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(failure.message)
        self.failure = failure
        self.__cause__ = cause


@dataclass(frozen=True, slots=True)
class A2ARuntimeKey:
    user_id: str
    target_id: str
    config_fingerprint: str
    policy_version: str = A2A_NEGOTIATION_POLICY_VERSION


def a2a_config_fingerprint(config: A2AServerConfig) -> str:
    canonical = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SelectedA2AInterface:
    url: str
    protocol_binding: str
    protocol_version: str
    tenant: str | None = None
    legacy: bool = False


@dataclass(slots=True)
class A2ACardSnapshot:
    key: A2ARuntimeKey
    card: dict
    interface: SelectedA2AInterface
    discovered_at: float
    expires_at: float
    stale_until: float
    etag: str | None = None
    last_modified: str | None = None
    cacheable: bool = True
    served_stale: bool = False
    cache_ttl_seconds: float | None = None

    def snapshot_state(self, now: float) -> Literal["fresh", "stale"]:
        del now
        return "stale" if self.served_stale else "fresh"

    def as_stale(self) -> "A2ACardSnapshot":
        snapshot = self.clone()
        snapshot.served_stale = True
        return snapshot

    def clone(self) -> "A2ACardSnapshot":
        return copy.deepcopy(self)


class DelegationSkillDescriptor(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=16)

    model_config = ConfigDict(extra="forbid")


class DelegationTargetDescriptor(BaseModel):
    target_id: str = Field(min_length=1, max_length=120)
    provider_id: str = "a2a.remote"
    target_type: Literal["remote_a2a", "local_subagent"] = "remote_a2a"
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    skills: list[DelegationSkillDescriptor] = Field(
        default_factory=list,
        max_length=32,
    )
    protocol_binding: str = Field(min_length=1, max_length=64)
    protocol_version: str = Field(min_length=1, max_length=32)
    snapshot_state: Literal["fresh", "stale"]
    metadata_trust: Literal["untrusted_external"] = "untrusted_external"

    model_config = ConfigDict(extra="forbid")


class A2ACardSnapshotCache:
    """Bounded tenant/config-isolated snapshot cache with deep-copy edges."""

    def __init__(
        self,
        *,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("A2A Card snapshot max entries must be positive")
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[A2ARuntimeKey, A2ACardSnapshot] = (
            OrderedDict()
        )

    def __len__(self) -> int:
        return len(self._entries)

    def put(self, snapshot: A2ACardSnapshot) -> None:
        self._entries[snapshot.key] = snapshot.clone()
        self._entries.move_to_end(snapshot.key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def get_fresh(self, key: A2ARuntimeKey) -> A2ACardSnapshot | None:
        snapshot = self._get_usable(key)
        if snapshot is None or self._clock() >= snapshot.expires_at:
            return None
        return snapshot

    def get_stale(self, key: A2ARuntimeKey) -> A2ACardSnapshot | None:
        return self._get_usable(key)

    def pop(self, key: A2ARuntimeKey) -> A2ACardSnapshot | None:
        snapshot = self._entries.pop(key, None)
        return snapshot.clone() if snapshot is not None else None

    def invalidate(self, *, user_id: str, target_id: str) -> None:
        for key in list(self._entries):
            if key.user_id == user_id and key.target_id == target_id:
                self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def _get_usable(self, key: A2ARuntimeKey) -> A2ACardSnapshot | None:
        snapshot = self._entries.get(key)
        if snapshot is None:
            return None
        if self._clock() >= snapshot.stale_until:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return snapshot.clone()


class A2AProviderRuntime:
    """Shared HTTP runtime with per-target conditional Card discovery."""

    def __init__(
        self,
        *,
        snapshot_ttl_seconds: float,
        snapshot_stale_seconds: float,
        snapshot_max_entries: int,
        discovery_timeout_seconds: float,
        invoke_timeout_seconds: float,
        response_max_bytes: int,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if snapshot_ttl_seconds <= 0:
            raise ValueError("A2A Card snapshot TTL must be positive")
        if snapshot_stale_seconds < 0:
            raise ValueError("A2A Card stale duration cannot be negative")
        if discovery_timeout_seconds <= 0 or invoke_timeout_seconds <= 0:
            raise ValueError("A2A operation timeouts must be positive")
        if response_max_bytes <= 0:
            raise ValueError("A2A response limit must be positive")
        self._snapshot_ttl_seconds = snapshot_ttl_seconds
        self._snapshot_stale_seconds = snapshot_stale_seconds
        self._snapshot_max_entries = snapshot_max_entries
        self._discovery_timeout_seconds = discovery_timeout_seconds
        self._invoke_timeout_seconds = invoke_timeout_seconds
        self._response_max_bytes = response_max_bytes
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
            )
        )
        self._clock = clock
        self._snapshots = A2ACardSnapshotCache(
            max_entries=snapshot_max_entries,
            clock=clock,
        )
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._refresh_locks: dict[A2ARuntimeKey, asyncio.Lock] = {}
        self._current_keys: OrderedDict[
            tuple[str, str], A2ARuntimeKey
        ] = OrderedDict()
        self._closed = False

    @property
    def client_created(self) -> bool:
        return self._client is not None

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    @property
    def generation_count(self) -> int:
        return len(self._current_keys)

    @property
    def refresh_lock_count(self) -> int:
        return len(self._refresh_locks)

    async def discover(
        self,
        *,
        user_id: str,
        target_config: A2AServerConfig,
        force_refresh: bool = False,
        allow_stale: bool = True,
    ) -> A2ACardSnapshot:
        key = await self._reconcile_key(user_id, target_config)
        if not force_refresh:
            cached = self._snapshots.get_fresh(key)
            if cached is not None:
                return cached

        refresh_lock = await self._refresh_lock_for(key)
        async with refresh_lock:
            if not force_refresh:
                cached = self._snapshots.get_fresh(key)
                if cached is not None:
                    return cached
            previous = self._snapshots.get_stale(key)
            try:
                snapshot = await self._refresh_card(
                    key=key,
                    target_config=target_config,
                    previous=previous,
                )
            except A2ARuntimeError:
                stale = self._snapshots.get_stale(key)
                if (
                    allow_stale
                    and stale is not None
                    and self._clock() >= stale.expires_at
                ):
                    return stale.as_stale()
                raise

            async with self._state_lock:
                if self._current_keys.get((user_id, target_config.id)) != key:
                    raise A2ARuntimeError(
                        a2a_failure(
                            A2AFailureCode.CARD_DISCOVERY_FAILED,
                            target_id=target_config.id,
                        )
                    )
                if snapshot.cacheable:
                    self._snapshots.put(snapshot)
                else:
                    self._snapshots.pop(key)
            return snapshot.clone()

    async def describe(
        self,
        *,
        user_id: str,
        target_config: A2AServerConfig,
    ) -> DelegationTargetDescriptor:
        snapshot = await self.discover(
            user_id=user_id,
            target_config=target_config,
        )
        card = snapshot.card
        skills = []
        raw_skills = card.get("skills")
        if isinstance(raw_skills, list):
            for raw_skill in raw_skills[:32]:
                if not isinstance(raw_skill, dict):
                    continue
                name = self._bounded_text(raw_skill.get("name"), 160)
                if not name:
                    continue
                raw_tags = raw_skill.get("tags")
                tags = []
                if isinstance(raw_tags, list):
                    tags = [
                        value
                        for item in raw_tags[:16]
                        if (value := self._bounded_text(item, 64))
                    ]
                skills.append(
                    DelegationSkillDescriptor(
                        name=name,
                        description=self._bounded_text(
                            raw_skill.get("description"),
                            500,
                        ),
                        tags=tags,
                    )
                )
        return DelegationTargetDescriptor(
            target_id=target_config.id,
            name=(
                self._bounded_text(card.get("name"), 200)
                or target_config.id
            ),
            description=self._bounded_text(card.get("description"), 1000),
            skills=skills,
            protocol_binding=snapshot.interface.protocol_binding,
            protocol_version=snapshot.interface.protocol_version,
            snapshot_state=snapshot.snapshot_state(self._clock()),
        )

    async def invoke(
        self,
        *,
        user_id: str,
        target_config: A2AServerConfig,
        query: str,
    ) -> ToolResult:
        try:
            snapshot = await self.discover(
                user_id=user_id,
                target_config=target_config,
            )
            result = await self._invoke_snapshot(
                snapshot=snapshot,
                target_config=target_config,
                query=query,
            )
        except A2ARuntimeError as exc:
            logger.warning(
                "A2A target [%s] failed with %s (debug_id=%s)",
                target_config.id,
                exc.failure.code,
                exc.failure.debug_id,
            )
            return ToolResult(failure=exc.failure)
        return ToolResult(
            success=True,
            message="远程 Agent 调用成功",
            data=result,
        )

    async def close(self) -> None:
        async with self._client_lock:
            client = self._client
            self._client = None
            self._closed = True
        if client is not None:
            await client.aclose()
        async with self._state_lock:
            self._snapshots.clear()
            self._current_keys.clear()
            self._refresh_locks.clear()

    async def _reconcile_key(
        self,
        user_id: str,
        target_config: A2AServerConfig,
    ) -> A2ARuntimeKey:
        key = A2ARuntimeKey(
            user_id=user_id,
            target_id=target_config.id,
            config_fingerprint=a2a_config_fingerprint(target_config),
        )
        identity = (user_id, target_config.id)
        async with self._state_lock:
            if self._closed:
                raise A2ARuntimeError(
                    a2a_failure(
                        A2AFailureCode.CARD_DISCOVERY_FAILED,
                        target_id=target_config.id,
                    )
                )
            current = self._current_keys.get(identity)
            if current != key:
                self._snapshots.invalidate(
                    user_id=user_id,
                    target_id=target_config.id,
                )
                if current is not None:
                    self._refresh_locks.pop(current, None)
                self._current_keys[identity] = key
            self._current_keys.move_to_end(identity)
            while len(self._current_keys) > self._snapshot_max_entries:
                old_identity, old_key = self._current_keys.popitem(last=False)
                self._snapshots.invalidate(
                    user_id=old_identity[0],
                    target_id=old_identity[1],
                )
                self._refresh_locks.pop(old_key, None)
        return key

    async def _refresh_lock_for(self, key: A2ARuntimeKey) -> asyncio.Lock:
        async with self._state_lock:
            return self._refresh_locks.setdefault(key, asyncio.Lock())

    async def _get_client(self, target_id: str) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._closed:
                raise A2ARuntimeError(
                    a2a_failure(
                        A2AFailureCode.CARD_DISCOVERY_FAILED,
                        target_id=target_id,
                    )
                )
            if self._client is None:
                self._client = self._client_factory()
            return self._client

    async def _refresh_card(
        self,
        *,
        key: A2ARuntimeKey,
        target_config: A2AServerConfig,
        previous: A2ACardSnapshot | None,
    ) -> A2ACardSnapshot:
        headers: dict[str, str] = {"Accept": "application/json"}
        if previous is not None:
            if previous.etag:
                headers["If-None-Match"] = previous.etag
            elif previous.last_modified:
                headers["If-Modified-Since"] = previous.last_modified
        discovery_url = (
            f"{target_config.base_url}/.well-known/agent-card.json"
        )
        try:
            response, body = await self._request_bytes(
                method="GET",
                url=discovery_url,
                target_id=target_config.id,
                timeout_seconds=self._discovery_timeout_seconds,
                headers=headers,
                allow_not_modified=True,
            )
            now = self._clock()
            if response.status_code == 304 and previous is None:
                raise A2ARuntimeError(
                    a2a_failure(
                        A2AFailureCode.PROTOCOL_ERROR,
                        target_id=target_config.id,
                    )
                )
            if (
                response.status_code == 304
                and "Cache-Control" not in response.headers
            ):
                ttl = previous.cache_ttl_seconds
                if ttl is None:
                    ttl = max(
                        0.0,
                        previous.expires_at - previous.discovered_at,
                    )
                cacheable = previous.cacheable
            else:
                ttl, cacheable = self._cache_policy(response.headers)
            expires_at = now + ttl
            stale_until = (
                expires_at + self._snapshot_stale_seconds
                if cacheable
                else now
            )
            if response.status_code == 304:
                return A2ACardSnapshot(
                    key=key,
                    card=previous.card,
                    interface=previous.interface,
                    discovered_at=now,
                    expires_at=expires_at,
                    stale_until=stale_until,
                    etag=response.headers.get("ETag") or previous.etag,
                    last_modified=(
                        response.headers.get("Last-Modified")
                        or previous.last_modified
                    ),
                    cacheable=cacheable,
                    cache_ttl_seconds=ttl,
                )
            try:
                card = json.loads(body)
            except (TypeError, ValueError) as exc:
                raise A2ARuntimeError(
                    a2a_failure(
                        A2AFailureCode.CARD_INVALID,
                        target_id=target_config.id,
                    ),
                    cause=exc,
                ) from exc
            if not isinstance(card, dict):
                raise A2ARuntimeError(
                    a2a_failure(
                        A2AFailureCode.CARD_INVALID,
                        target_id=target_config.id,
                    )
                )
            selected_interface = self._select_interface(
                card=card,
                target_config=target_config,
            )
            return A2ACardSnapshot(
                key=key,
                card=copy.deepcopy(card),
                interface=selected_interface,
                discovered_at=now,
                expires_at=expires_at,
                stale_until=stale_until,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
                cacheable=cacheable,
                cache_ttl_seconds=ttl,
            )
        except A2ARuntimeError:
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise A2ARuntimeError(
                a2a_failure(
                    A2AFailureCode.TIMEOUT,
                    target_id=target_config.id,
                ),
                cause=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise A2ARuntimeError(
                a2a_failure(
                    A2AFailureCode.CARD_DISCOVERY_FAILED,
                    target_id=target_config.id,
                ),
                cause=exc,
            ) from exc
        except Exception as exc:
            raise A2ARuntimeError(
                a2a_failure(
                    A2AFailureCode.CARD_DISCOVERY_FAILED,
                    target_id=target_config.id,
                ),
                cause=exc,
            ) from exc

    async def _invoke_snapshot(
        self,
        *,
        snapshot: A2ACardSnapshot,
        target_config: A2AServerConfig,
        query: str,
    ) -> object:
        interface = snapshot.interface
        if interface.legacy:
            url = interface.url
            payload = {
                "id": str(uuid.uuid4()),
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"kind": "text", "text": query}],
                    }
                },
            }
            headers = {"Content-Type": "application/json"}
            json_rpc = True
        else:
            message = {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_USER",
                "parts": [{"text": query}],
            }
            if interface.tenant:
                message["tenant"] = interface.tenant
            headers = {"A2A-Version": interface.protocol_version}
            if interface.protocol_binding == "JSONRPC":
                url = interface.url
                payload = {
                    "id": str(uuid.uuid4()),
                    "jsonrpc": "2.0",
                    "method": "SendMessage",
                    "params": {"message": message},
                }
                headers["Content-Type"] = "application/json"
                json_rpc = True
            else:
                url = interface.url
                if not url.rstrip("/").endswith("/message:send"):
                    url = f"{url.rstrip('/')}/message:send"
                payload = {"message": message}
                headers["Content-Type"] = "application/a2a+json"
                json_rpc = False
        try:
            _, body = await self._request_bytes(
                method="POST",
                url=url,
                target_id=target_config.id,
                timeout_seconds=self._invoke_timeout_seconds,
                headers=headers,
                json_body=payload,
            )
            try:
                result = json.loads(body)
            except (TypeError, ValueError) as exc:
                raise A2ARuntimeError(
                    a2a_failure(
                        A2AFailureCode.PROTOCOL_ERROR,
                        target_id=target_config.id,
                    ),
                    cause=exc,
                ) from exc
            if not isinstance(result, dict):
                raise A2ARuntimeError(
                    a2a_failure(
                        A2AFailureCode.PROTOCOL_ERROR,
                        target_id=target_config.id,
                    )
                )
            if json_rpc:
                if "error" in result or "result" not in result:
                    raise A2ARuntimeError(
                        a2a_failure(
                            A2AFailureCode.PROTOCOL_ERROR,
                            target_id=target_config.id,
                        )
                    )
                return result["result"]
            return result
        except A2ARuntimeError:
            raise
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise A2ARuntimeError(
                a2a_failure(
                    A2AFailureCode.TIMEOUT,
                    target_id=target_config.id,
                ),
                cause=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise A2ARuntimeError(
                a2a_failure(
                    A2AFailureCode.INVOCATION_FAILED,
                    target_id=target_config.id,
                ),
                cause=exc,
            ) from exc
        except Exception as exc:
            raise A2ARuntimeError(
                a2a_failure(
                    A2AFailureCode.INVOCATION_FAILED,
                    target_id=target_config.id,
                ),
                cause=exc,
            ) from exc

    async def _request_bytes(
        self,
        *,
        method: str,
        url: str,
        target_id: str,
        timeout_seconds: float,
        headers: dict[str, str],
        json_body: dict | None = None,
        allow_not_modified: bool = False,
    ) -> tuple[httpx.Response, bytes]:
        client = await self._get_client(target_id)
        async with asyncio.timeout(timeout_seconds):
            async with client.stream(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=timeout_seconds,
            ) as response:
                if allow_not_modified and response.status_code == 304:
                    return response, b""
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        declared_length = int(content_length)
                    except ValueError:
                        declared_length = 0
                    if declared_length > self._response_max_bytes:
                        raise A2ARuntimeError(
                            a2a_failure(
                                A2AFailureCode.RESPONSE_TOO_LARGE,
                                target_id=target_id,
                            )
                        )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self._response_max_bytes:
                        raise A2ARuntimeError(
                            a2a_failure(
                                A2AFailureCode.RESPONSE_TOO_LARGE,
                                target_id=target_id,
                            )
                        )
                return response, bytes(body)

    def _select_interface(
        self,
        *,
        card: dict,
        target_config: A2AServerConfig,
    ) -> SelectedA2AInterface:
        raw_interfaces = card.get("supportedInterfaces")
        if raw_interfaces is None:
            raw_interfaces = card.get("supported_interfaces")
        if isinstance(raw_interfaces, list):
            for item in raw_interfaces:
                if not isinstance(item, dict):
                    continue
                binding = str(
                    item.get("protocolBinding")
                    or item.get("protocol_binding")
                    or ""
                ).upper()
                if binding not in {"JSONRPC", "HTTP+JSON"}:
                    continue
                url = item.get("url")
                version = (
                    item.get("protocolVersion")
                    or item.get("protocol_version")
                )
                if not isinstance(url, str) or not isinstance(version, str):
                    raise A2ARuntimeError(
                        a2a_failure(
                            A2AFailureCode.CARD_INVALID,
                            target_id=target_config.id,
                        )
                    )
                self._validate_interface_url(
                    base_url=target_config.base_url,
                    interface_url=url,
                    target_id=target_config.id,
                )
                tenant = item.get("tenant")
                return SelectedA2AInterface(
                    url=url,
                    protocol_binding=binding,
                    protocol_version=version,
                    tenant=tenant if isinstance(tenant, str) and tenant else None,
                )
            raise A2ARuntimeError(
                a2a_failure(
                    A2AFailureCode.UNSUPPORTED_BINDING,
                    target_id=target_config.id,
                )
            )
        legacy_url = card.get("url")
        if isinstance(legacy_url, str) and legacy_url:
            self._validate_interface_url(
                base_url=target_config.base_url,
                interface_url=legacy_url,
                target_id=target_config.id,
            )
            return SelectedA2AInterface(
                url=legacy_url,
                protocol_binding="JSONRPC",
                protocol_version="0.3",
                legacy=True,
            )
        raise A2ARuntimeError(
            a2a_failure(
                A2AFailureCode.CARD_INVALID,
                target_id=target_config.id,
            )
        )

    @staticmethod
    def _validate_interface_url(
        *,
        base_url: str,
        interface_url: str,
        target_id: str,
    ) -> None:
        try:
            base = urlsplit(base_url)
            interface = urlsplit(interface_url)
            valid = (
                interface.scheme in {"http", "https"}
                and interface.hostname is not None
                and interface.username is None
                and interface.password is None
                and A2AProviderRuntime._origin(base)
                == A2AProviderRuntime._origin(interface)
            )
        except ValueError:
            valid = False
        if not valid:
            raise A2ARuntimeError(
                a2a_failure(
                    A2AFailureCode.CARD_INVALID,
                    target_id=target_id,
                )
            )

    @staticmethod
    def _origin(parsed) -> tuple[str, str | None, int | None]:
        default_port = 443 if parsed.scheme == "https" else 80
        return parsed.scheme, parsed.hostname, parsed.port or default_port

    def _cache_policy(self, headers: httpx.Headers) -> tuple[float, bool]:
        cache_control = headers.get("Cache-Control", "")
        directives = {
            item.strip().lower().split("=", 1)[0]
            for item in cache_control.split(",")
            if item.strip()
        }
        if "no-store" in directives:
            return 0.0, False
        if "no-cache" in directives:
            return 0.0, True
        match = re.search(r"(?:^|,)\s*max-age\s*=\s*(\d+)", cache_control, re.I)
        if match is None:
            return self._snapshot_ttl_seconds, True
        return min(float(match.group(1)), self._snapshot_ttl_seconds), True

    @staticmethod
    def _bounded_text(value: object, max_chars: int) -> str:
        if not isinstance(value, str):
            return ""
        normalized = " ".join(value.split())
        return normalized[:max_chars]

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.entities.app_config import A2AConfig, A2AServerConfig
from app.core.tools.a2a_runtime import (
    A2ACardSnapshot,
    A2ACardSnapshotCache,
    A2AFailureCode,
    A2ARuntimeError,
    A2ARuntimeKey,
    SelectedA2AInterface,
    a2a_config_fingerprint,
    a2a_failure,
)
from app.schemas.app_config import (
    A2AConfig as A2ARequestConfig,
    A2AServerConfig as A2ARequestServerConfig,
)


def _key(
    *,
    user_id: str = "user-a",
    target_id: str = "researcher",
    fingerprint: str = "fingerprint-a",
) -> A2ARuntimeKey:
    return A2ARuntimeKey(
        user_id=user_id,
        target_id=target_id,
        config_fingerprint=fingerprint,
    )


def _snapshot(
    key: A2ARuntimeKey,
    *,
    expires_at: float = 20.0,
    stale_until: float = 40.0,
) -> A2ACardSnapshot:
    return A2ACardSnapshot(
        key=key,
        card={"name": "Researcher", "skills": [{"name": "Search"}]},
        interface=SelectedA2AInterface(
            url="https://agents.example.test/rpc",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        ),
        discovered_at=10.0,
        expires_at=expires_at,
        stale_until=stale_until,
        etag='"card-v1"',
    )


def test_a2a_config_fingerprint_changes_without_exposing_raw_config() -> None:
    first = A2AServerConfig(
        id="researcher",
        base_url="https://agents.example.test",
    )
    second = first.model_copy(
        update={"base_url": "https://agents-v2.example.test"}
    )

    first_fingerprint = a2a_config_fingerprint(first)
    second_fingerprint = a2a_config_fingerprint(second)

    assert first_fingerprint != second_fingerprint
    assert len(first_fingerprint) == 64
    assert "agents.example.test" not in first_fingerprint


def test_snapshot_cache_is_tenant_and_config_isolated_and_deep_copied() -> None:
    now = [12.0]
    cache = A2ACardSnapshotCache(max_entries=4, clock=lambda: now[0])
    first_key = _key()
    cache.put(_snapshot(first_key))

    first = cache.get_fresh(first_key)
    assert first is not None
    first.card["name"] = "mutated"

    again = cache.get_fresh(first_key)
    assert again is not None
    assert again.card["name"] == "Researcher"
    assert cache.get_fresh(replace(first_key, user_id="user-b")) is None
    assert cache.get_fresh(
        replace(first_key, config_fingerprint="fingerprint-b")
    ) is None


def test_snapshot_cache_distinguishes_fresh_stale_and_expired_entries() -> None:
    now = [12.0]
    cache = A2ACardSnapshotCache(max_entries=4, clock=lambda: now[0])
    key = _key()
    cache.put(_snapshot(key))

    assert cache.get_fresh(key) is not None

    now[0] = 25.0
    assert cache.get_fresh(key) is None
    stale = cache.get_stale(key)
    assert stale is not None
    assert stale.as_stale().snapshot_state(now[0]) == "stale"

    now[0] = 45.0
    assert cache.get_stale(key) is None
    assert len(cache) == 0


def test_snapshot_cache_is_lru_bounded_and_can_invalidate_one_target() -> None:
    cache = A2ACardSnapshotCache(max_entries=2, clock=lambda: 12.0)
    first = _key(target_id="first")
    second = _key(target_id="second")
    third = _key(target_id="third")
    cache.put(_snapshot(first))
    cache.put(_snapshot(second))
    assert cache.get_fresh(first) is not None
    cache.put(_snapshot(third))

    assert cache.get_fresh(first) is not None
    assert cache.get_fresh(second) is None
    assert cache.get_fresh(third) is not None

    cache.invalidate(user_id="user-a", target_id="first")
    assert cache.get_fresh(first) is None
    assert cache.get_fresh(third) is not None


def test_a2a_failure_contract_is_safe_and_typed() -> None:
    failure = a2a_failure(
        A2AFailureCode.CARD_DISCOVERY_FAILED,
        target_id="researcher",
    )
    error = A2ARuntimeError(
        failure,
        cause=RuntimeError(
            "token=secret https://private.example.test/card"
        ),
    )

    assert failure.code == "A2A_CARD_DISCOVERY_FAILED"
    assert failure.source == "a2a"
    assert failure.provider_id == "a2a.remote:researcher"
    assert failure.retryable is True
    assert "secret" not in failure.message
    assert "private.example.test" not in failure.message
    assert error.failure == failure


def test_a2a_config_rejects_invalid_urls_and_duplicate_target_ids() -> None:
    with pytest.raises(ValidationError):
        A2AServerConfig(id="bad", base_url="file:///tmp/agent")

    with pytest.raises(ValidationError):
        A2AServerConfig(
            id="bad",
            base_url="https://user:password@agents.example.test",
        )

    with pytest.raises(ValidationError):
        A2AServerConfig(
            id="bad",
            base_url="https://agents.example.test:not-a-port",
        )

    target = A2AServerConfig(
        id="duplicate",
        base_url="https://agents.example.test",
    )
    with pytest.raises(ValidationError):
        A2AConfig(a2a_servers=[target, target.model_copy()])

    request_target = A2ARequestServerConfig(
        id="duplicate",
        base_url="https://agents.example.test",
    )
    with pytest.raises(ValidationError):
        A2ARequestConfig(
            a2a_servers=[request_target, request_target.model_copy()]
        )


def test_a2a_runtime_settings_have_safe_defaults_and_validate_bounds() -> None:
    settings = Settings(_env_file=None)

    assert settings.a2a_card_snapshot_ttl_seconds > 0
    assert settings.a2a_card_snapshot_stale_seconds >= 0
    assert settings.a2a_card_snapshot_max_entries > 0
    assert settings.a2a_card_discovery_timeout_seconds > 0
    assert settings.a2a_invoke_timeout_seconds > 0
    assert settings.a2a_response_max_bytes > 0

    with pytest.raises(ValidationError):
        Settings(_env_file=None, a2a_card_snapshot_max_entries=0)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, a2a_invoke_timeout_seconds=0)

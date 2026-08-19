from __future__ import annotations

from app.core.config import Settings
from app.core.entities.app_config import MCPServerConfig
from app.core.tools.provider_runtime import (
    MCPSchemaSnapshotCache,
    ProviderRuntimeKey,
    mcp_config_fingerprint,
)


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def _config(*, token: str = "secret-a") -> MCPServerConfig:
    return MCPServerConfig(
        url="https://mcp.example.test/api",
        headers={"Authorization": f"Bearer {token}"},
    )


def _key(*, user_id: str = "user-1", token: str = "secret-a") -> ProviderRuntimeKey:
    config = _config(token=token)
    return ProviderRuntimeKey(
        user_id=user_id,
        provider_id="mcp.github",
        config_fingerprint=mcp_config_fingerprint(config),
    )


def test_runtime_key_isolated_by_user_and_full_config_fingerprint() -> None:
    first = _key()

    assert first != _key(user_id="user-2")
    assert first != _key(token="secret-b")
    assert "secret-a" not in repr(first)
    assert "mcp.example.test" not in repr(first)


def test_snapshot_cache_returns_deep_copies_and_never_connection_config() -> None:
    clock = Clock()
    cache = MCPSchemaSnapshotCache(ttl_seconds=60, clock=clock)
    key = _key()
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "mcp_github_search",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    cache.put(key, schemas)
    first = cache.get(key)
    assert first is not None
    first.schemas[0]["function"]["name"] = "mutated"

    second = cache.get(key)
    assert second is not None
    assert second.schemas[0]["function"]["name"] == "mcp_github_search"
    assert "Authorization" not in repr(second)
    assert "secret-a" not in repr(second)


def test_snapshot_expires_and_can_be_invalidated_by_user_provider() -> None:
    clock = Clock()
    cache = MCPSchemaSnapshotCache(ttl_seconds=10, clock=clock)
    first_key = _key()
    other_user_key = _key(user_id="user-2")
    cache.put(first_key, [])
    cache.put(other_user_key, [])

    clock.value = 109.9
    assert cache.get(first_key) is not None
    clock.value = 110.0
    assert cache.get(first_key) is None
    assert cache.get(other_user_key) is None

    clock.value = 200.0
    cache.put(first_key, [])
    cache.put(other_user_key, [])
    assert cache.invalidate(user_id="user-1", provider_id="mcp.github") == 1
    assert cache.get(first_key) is None
    assert cache.get(other_user_key) is not None


def test_snapshot_cache_prunes_expired_values_and_enforces_capacity() -> None:
    clock = Clock()
    cache = MCPSchemaSnapshotCache(
        ttl_seconds=10,
        max_entries=2,
        clock=clock,
    )
    first = _key(user_id="user-1")
    second = _key(user_id="user-2")
    third = _key(user_id="user-3")

    cache.put(first, [])
    clock.value = 101.0
    cache.put(second, [])
    clock.value = 102.0
    cache.put(third, [])

    assert cache.get(first) is None
    assert cache.get(second) is not None
    assert cache.get(third) is not None

    clock.value = 112.0
    cache.put(first, [])
    assert cache.get(second) is None
    assert cache.get(third) is None
    assert cache.get(first) is not None


def test_provider_runtime_settings_have_safe_positive_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.mcp_schema_snapshot_ttl_seconds > 0
    assert settings.mcp_schema_snapshot_max_entries > 0
    assert settings.mcp_provider_operation_timeout_seconds > 0
    assert settings.mcp_provider_idle_ttl_seconds >= 0
    assert settings.mcp_provider_backoff_base_seconds > 0
    assert (
        settings.mcp_provider_backoff_max_seconds
        >= settings.mcp_provider_backoff_base_seconds
    )

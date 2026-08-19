from __future__ import annotations

import json

from app.core.entities.event import ErrorEvent
from app.core.entities.failure import (
    FailureCategory,
    FailureInfo,
    FailureScope,
    RecoveryAction,
)
from app.core.entities.tool_result import ToolResult
from app.core.tools.provider_runtime import (
    ProviderFailureCode,
    ProviderRuntimeError,
    provider_failure,
)


def test_legacy_error_event_and_tool_result_remain_compatible() -> None:
    event = ErrorEvent.model_validate({"type": "error", "error": "legacy error"})
    result = ToolResult.model_validate(
        {"success": False, "message": "legacy tool failure", "data": None}
    )

    assert event.error == "legacy error"
    assert event.failure is None
    assert result.message == "legacy tool failure"
    assert result.failure is None


def test_failure_info_drives_compatible_user_message_fields() -> None:
    failure = FailureInfo(
        code="PROVIDER_TIMEOUT",
        category=FailureCategory.PROVIDER,
        scope=FailureScope.OPERATION,
        source="mcp",
        message="外部工具服务响应超时，请稍后重试。",
        retryable=True,
        recovery_actions=[RecoveryAction.RETRY, RecoveryAction.CHOOSE_PROVIDER],
        provider_id="mcp.github",
    )

    event = ErrorEvent(error="unsafe stale message", failure=failure)
    result = ToolResult(success=True, message="unsafe stale message", failure=failure)

    assert event.error == failure.message
    assert result.success is False
    assert result.message == failure.message
    assert event.model_dump(mode="json")["failure"]["code"] == "PROVIDER_TIMEOUT"
    assert result.model_dump(mode="json")["failure"]["provider_id"] == "mcp.github"


def test_provider_runtime_error_exposes_only_safe_failure_projection() -> None:
    raw = RuntimeError(
        "Authorization: Bearer secret-token at https://private.example.test/mcp"
    )
    failure = provider_failure(
        ProviderFailureCode.CONNECT_FAILED,
        provider_id="mcp.github",
    )
    error = ProviderRuntimeError(failure, cause=raw)

    projected = json.dumps(error.failure.model_dump(mode="json"), ensure_ascii=False)

    assert error.__cause__ is raw
    assert str(error) == "外部工具服务暂时无法连接。"
    assert "secret-token" not in projected
    assert "private.example.test" not in projected
    assert error.failure.retryable is True
    assert error.failure.scope == FailureScope.OPERATION
    assert error.failure.recovery_actions == [
        RecoveryAction.RETRY,
        RecoveryAction.CHOOSE_PROVIDER,
    ]


def test_failure_debug_ids_are_present_and_unique() -> None:
    first = provider_failure(
        ProviderFailureCode.PROTOCOL_ERROR,
        provider_id="mcp.github",
    )
    second = provider_failure(
        ProviderFailureCode.PROTOCOL_ERROR,
        provider_id="mcp.github",
    )

    assert first.debug_id
    assert second.debug_id
    assert first.debug_id != second.debug_id

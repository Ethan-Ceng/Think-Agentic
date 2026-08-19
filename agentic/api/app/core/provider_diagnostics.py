"""Stable, user-safe failure contracts for manual Provider diagnostics."""
from __future__ import annotations

from enum import Enum

from app.core.entities.failure import (
    FailureCategory,
    FailureInfo,
    FailureScope,
    RecoveryAction,
)


class ProviderDiagnosticFailureCode(str, Enum):
    CONFIGURATION_INVALID = "PROVIDER_CONFIGURATION_INVALID"
    DIAGNOSTIC_FAILED = "PROVIDER_DIAGNOSTIC_FAILED"


_FAILURE_DEFAULTS: dict[
    ProviderDiagnosticFailureCode,
    tuple[str, bool, list[RecoveryAction]],
] = {
    ProviderDiagnosticFailureCode.CONFIGURATION_INVALID: (
        "Provider 配置无效，请检查并重新保存配置。",
        False,
        [RecoveryAction.CHECK_CONFIG],
    ),
    ProviderDiagnosticFailureCode.DIAGNOSTIC_FAILED: (
        "Provider 诊断暂未完成，请稍后重试或检查配置。",
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHECK_CONFIG],
    ),
}


def provider_diagnostic_failure(
    code: ProviderDiagnosticFailureCode,
    *,
    provider_id: str,
) -> FailureInfo:
    message, retryable, actions = _FAILURE_DEFAULTS[code]
    return FailureInfo(
        code=code.value,
        category=FailureCategory.PROVIDER,
        scope=FailureScope.OPERATION,
        source="provider.diagnostic",
        message=message,
        retryable=retryable,
        recovery_actions=actions,
        provider_id=provider_id,
    )

"""Stable, user-safe model failure contracts."""
from __future__ import annotations

from enum import Enum

from app.core.entities.failure import (
    FailureCategory,
    FailureInfo,
    FailureScope,
    RecoveryAction,
)


class ModelFailureCode(str, Enum):
    AUTHENTICATION_FAILED = "MODEL_AUTHENTICATION_FAILED"
    PERMISSION_DENIED = "MODEL_PERMISSION_DENIED"
    RATE_LIMITED = "MODEL_RATE_LIMITED"
    TIMEOUT = "MODEL_TIMEOUT"
    CONNECTION_FAILED = "MODEL_CONNECTION_FAILED"
    REQUEST_INVALID = "MODEL_REQUEST_INVALID"
    SERVICE_UNAVAILABLE = "MODEL_SERVICE_UNAVAILABLE"
    INVALID_RESPONSE = "MODEL_INVALID_RESPONSE"
    EMPTY_RESPONSE = "MODEL_EMPTY_RESPONSE"
    UNKNOWN_ERROR = "MODEL_UNKNOWN_ERROR"


_MODEL_FAILURE_DEFAULTS: dict[
    ModelFailureCode,
    tuple[str, bool, list[RecoveryAction]],
] = {
    ModelFailureCode.AUTHENTICATION_FAILED: (
        "模型服务鉴权失败，请检查 API Key 或模型配置。",
        False,
        [RecoveryAction.CHECK_CONFIG, RecoveryAction.START_NEW_RUN],
    ),
    ModelFailureCode.PERMISSION_DENIED: (
        "当前模型服务拒绝访问，请检查账户权限或模型配置。",
        False,
        [RecoveryAction.CHECK_CONFIG, RecoveryAction.START_NEW_RUN],
    ),
    ModelFailureCode.RATE_LIMITED: (
        "模型服务请求过多或额度受限，请稍后重试或检查账户配置。",
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHECK_CONFIG],
    ),
    ModelFailureCode.TIMEOUT: (
        "模型服务响应超时，请稍后重试。",
        True,
        [RecoveryAction.RETRY],
    ),
    ModelFailureCode.CONNECTION_FAILED: (
        "无法连接模型服务，请稍后重试或检查模型配置。",
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHECK_CONFIG],
    ),
    ModelFailureCode.REQUEST_INVALID: (
        "模型请求配置无效，请检查模型名称、地址和生成参数。",
        False,
        [RecoveryAction.CHECK_CONFIG, RecoveryAction.START_NEW_RUN],
    ),
    ModelFailureCode.SERVICE_UNAVAILABLE: (
        "模型服务暂时不可用，请稍后重试。",
        True,
        [RecoveryAction.RETRY],
    ),
    ModelFailureCode.INVALID_RESPONSE: (
        "模型服务返回了无效响应，请稍后重试。",
        True,
        [RecoveryAction.RETRY],
    ),
    ModelFailureCode.EMPTY_RESPONSE: (
        "模型未返回有效内容，请重试。",
        True,
        [RecoveryAction.RETRY],
    ),
    ModelFailureCode.UNKNOWN_ERROR: (
        "模型调用未完成，请稍后重试或检查模型配置。",
        True,
        [RecoveryAction.RETRY, RecoveryAction.CHECK_CONFIG],
    ),
}


def model_failure(code: ModelFailureCode) -> FailureInfo:
    message, retryable, actions = _MODEL_FAILURE_DEFAULTS[code]
    return FailureInfo(
        code=code.value,
        category=FailureCategory.MODEL,
        scope=FailureScope.RUN,
        source="llm.openai_compatible",
        message=message,
        retryable=retryable,
        recovery_actions=actions,
    )


class ModelRuntimeError(RuntimeError):
    """Internal model exception carrying only a safe public projection."""

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

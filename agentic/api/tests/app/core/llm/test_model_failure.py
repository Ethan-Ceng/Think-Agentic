from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from app.core.entities.failure import FailureCategory, FailureScope, RecoveryAction
from app.core.llm.failure import ModelFailureCode, ModelRuntimeError, model_failure
from app.core.llm.openai_llm import model_failure_from_openai_error


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://model.invalid/v1/chat/completions")


def _status_error(
    error_type: type[Exception],
    status_code: int,
) -> Exception:
    response = httpx.Response(status_code, request=_request())
    return error_type(
        "sensitive upstream body: sk-secret",
        response=response,
        body={"api_key": "sk-secret"},
    )


@pytest.mark.parametrize(
    ("make_error", "expected_code"),
    [
        (
            lambda: _status_error(AuthenticationError, 401),
            ModelFailureCode.AUTHENTICATION_FAILED,
        ),
        (
            lambda: _status_error(PermissionDeniedError, 403),
            ModelFailureCode.PERMISSION_DENIED,
        ),
        (
            lambda: _status_error(RateLimitError, 429),
            ModelFailureCode.RATE_LIMITED,
        ),
        (
            lambda: APITimeoutError(_request()),
            ModelFailureCode.TIMEOUT,
        ),
        (
            lambda: APIConnectionError(
                message="sensitive host failed: sk-secret",
                request=_request(),
            ),
            ModelFailureCode.CONNECTION_FAILED,
        ),
        (
            lambda: _status_error(BadRequestError, 400),
            ModelFailureCode.REQUEST_INVALID,
        ),
        (
            lambda: _status_error(NotFoundError, 404),
            ModelFailureCode.REQUEST_INVALID,
        ),
        (
            lambda: _status_error(UnprocessableEntityError, 422),
            ModelFailureCode.REQUEST_INVALID,
        ),
        (
            lambda: _status_error(ConflictError, 409),
            ModelFailureCode.REQUEST_INVALID,
        ),
        (
            lambda: _status_error(InternalServerError, 503),
            ModelFailureCode.SERVICE_UNAVAILABLE,
        ),
        (
            lambda: RuntimeError("sensitive unknown: sk-secret"),
            ModelFailureCode.UNKNOWN_ERROR,
        ),
    ],
)
def test_openai_errors_map_to_safe_stable_failures(
    make_error: Callable[[], Exception],
    expected_code: ModelFailureCode,
) -> None:
    error = make_error()

    failure = model_failure_from_openai_error(error)

    assert failure.code == expected_code.value
    assert failure.category == FailureCategory.MODEL
    assert failure.scope == FailureScope.RUN
    assert failure.source == "llm.openai_compatible"
    assert "sk-secret" not in failure.message
    assert "model.invalid" not in failure.message


def test_model_failure_defaults_distinguish_retry_and_configuration_actions() -> None:
    auth = model_failure(ModelFailureCode.AUTHENTICATION_FAILED)
    timeout = model_failure(ModelFailureCode.TIMEOUT)
    rate_limit = model_failure(ModelFailureCode.RATE_LIMITED)

    assert auth.retryable is False
    assert auth.recovery_actions == [
        RecoveryAction.CHECK_CONFIG,
        RecoveryAction.START_NEW_RUN,
    ]
    assert timeout.retryable is True
    assert timeout.recovery_actions == [RecoveryAction.RETRY]
    assert rate_limit.retryable is True
    assert rate_limit.recovery_actions == [
        RecoveryAction.RETRY,
        RecoveryAction.CHECK_CONFIG,
    ]


def test_model_runtime_error_exposes_only_failure_message() -> None:
    failure = model_failure(ModelFailureCode.CONNECTION_FAILED)
    cause = RuntimeError("Authorization: Bearer sk-secret")

    error = ModelRuntimeError(failure, cause=cause)

    assert str(error) == failure.message
    assert error.failure == failure
    assert error.__cause__ is cause
    assert "sk-secret" not in str(error)

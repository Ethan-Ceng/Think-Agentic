from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.controllers.provider_diagnostics import diagnose_provider
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


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_endpoint_wraps_business_failure_in_success_response() -> None:
    failure = provider_diagnostic_failure(
        ProviderDiagnosticFailureCode.DIAGNOSTIC_FAILED,
        provider_id="llm.default",
    )
    result = ProviderDiagnosticResult(
        provider_type=ProviderType.LLM,
        provider_id="llm.default",
        check_kind=ProviderCheckKind.INFERENCE,
        status=ProviderDiagnosticStatus.DEGRADED,
        message=failure.message,
        latency_ms=12,
        failure=failure,
    )

    class FakeService:
        async def test(self, *, user_id, request):
            assert user_id == "user-1"
            assert request.provider_type is ProviderType.LLM
            return result

    response = await diagnose_provider(
        request=ProviderDiagnosticRequest(provider_type="llm"),
        current_user=SimpleNamespace(id="user-1"),
        service=FakeService(),
    )

    assert response.code == 200
    assert response.data == result
    assert response.data.failure == failure

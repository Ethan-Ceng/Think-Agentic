"""Authenticated endpoint for manual Provider diagnostics."""
from fastapi import APIRouter, Depends

from app.core.entities.user import User
from app.dependencies import get_current_user, get_provider_diagnostic_service
from app.schemas import Response
from app.schemas.provider_diagnostic import (
    ProviderDiagnosticRequest,
    ProviderDiagnosticResult,
)
from app.services.provider_diagnostic_service import ProviderDiagnosticService


router = APIRouter(prefix="/provider-diagnostics", tags=["Provider 诊断"])


@router.post("/test", summary="测试已保存的 Provider 配置")
async def diagnose_provider(
    request: ProviderDiagnosticRequest,
    current_user: User = Depends(get_current_user),
    service: ProviderDiagnosticService = Depends(get_provider_diagnostic_service),
) -> Response[ProviderDiagnosticResult]:
    result = await service.test(user_id=current_user.id, request=request)
    return Response.success(data=result)

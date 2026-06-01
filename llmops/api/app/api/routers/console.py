from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_tenant, get_db_session
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.schemas.identity import (
    AccountResponse,
    BootstrapTenantRequest,
    BootstrapTenantResponse,
    CurrentWorkspaceResponse,
    TenantMemberResponse,
    TenantResponse,
)
from app.services.identity_service import IdentityService

router = APIRouter(prefix="/console/api", tags=["console"])


@router.get("/status")
async def console_status() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/setup/default-tenant", response_model=BootstrapTenantResponse)
def bootstrap_default_tenant(
    req: BootstrapTenantRequest,
    session: Session = Depends(get_db_session),
) -> BootstrapTenantResponse:
    result = IdentityService().bootstrap_tenant(session, req)
    return BootstrapTenantResponse(
        tenant=TenantResponse(id=result.tenant.id, name=result.tenant.name, status=result.tenant.status),
        account=AccountResponse(
            id=result.account.id,
            name=result.account.name,
            email=result.account.email,
            status=result.account.status,
        ),
        member=TenantMemberResponse(
            id=result.member.id,
            tenant_id=result.member.tenant_id,
            user_id=result.member.user_id,
            role=result.member.role,
            status=result.member.status,
        ),
    )


@router.get("/workspaces/current", response_model=CurrentWorkspaceResponse)
def get_current_workspace(
    tenant_context: TenantContext = Depends(get_current_tenant),
    session: Session = Depends(get_db_session),
) -> CurrentWorkspaceResponse:
    tenant = session.get(Tenant, tenant_context.tenant_id)
    return CurrentWorkspaceResponse(tenant=TenantResponse(id=tenant.id, name=tenant.name, status=tenant.status))

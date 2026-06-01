from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_approval_service, get_current_account, get_current_tenant, get_db_session
from app.core.tenant import TenantContext
from app.models.account import Account
from app.schemas.approval import ApprovalDecisionRequest, ApprovalResponse
from app.services.approval_service import ApprovalService
from app.shared.response import success_json

router = APIRouter(prefix="/approvals", tags=["approval"])


@router.get("")
def list_pending_approvals(
    session: Session = Depends(get_db_session),
    tenant: TenantContext = Depends(get_current_tenant),
    svc: ApprovalService = Depends(get_approval_service),
):
    approvals = svc.list_pending(session, tenant_id=tenant.tenant_id)
    return success_json({"list": [ApprovalResponse.from_approval(item).model_dump() for item in approvals]})


@router.post("/{approval_id}/approve")
def approve_request(
    approval_id: UUID,
    req: ApprovalDecisionRequest,
    session: Session = Depends(get_db_session),
    tenant: TenantContext = Depends(get_current_tenant),
    current_user: Account = Depends(get_current_account),
    svc: ApprovalService = Depends(get_approval_service),
):
    approval = svc.get_request(session, tenant_id=tenant.tenant_id, approval_id=approval_id)
    approval = svc.approve(session, approval, approved_by=current_user.id, decision_payload=req.decision_payload)
    return success_json(ApprovalResponse.from_approval(approval).model_dump())


@router.post("/{approval_id}/reject")
def reject_request(
    approval_id: UUID,
    req: ApprovalDecisionRequest,
    session: Session = Depends(get_db_session),
    tenant: TenantContext = Depends(get_current_tenant),
    current_user: Account = Depends(get_current_account),
    svc: ApprovalService = Depends(get_approval_service),
):
    approval = svc.get_request(session, tenant_id=tenant.tenant_id, approval_id=approval_id)
    approval = svc.reject(session, approval, rejected_by=current_user.id, decision_payload=req.decision_payload)
    return success_json(ApprovalResponse.from_approval(approval).model_dump())

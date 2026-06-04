from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_agent_capability_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.app import PatchCapabilitySummaryRequest, RefreshCapabilitySummaryRequest
from app.services.agent_capability_service import AgentCapabilityService
from app.shared.response import success_json

router = APIRouter(prefix="/agents", tags=["agent"])


@router.get("/{agent_id}/capability-summary")
def get_agent_capability_summary(
    agent_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AgentCapabilityService = Depends(get_agent_capability_service),
):
    return success_json(svc.get_agent_capability_summary(session, agent_id, current_user))


@router.post("/{agent_id}/capability-summary/refresh")
def refresh_agent_capability_summary(
    agent_id: UUID,
    req: RefreshCapabilitySummaryRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AgentCapabilityService = Depends(get_agent_capability_service),
):
    return success_json(
        svc.refresh_agent_capability_summary(
            session,
            agent_id,
            current_user,
            preserve_manual_overrides=req.preserve_manual_overrides,
        )
    )


@router.patch("/{agent_id}/capability-summary")
def patch_agent_capability_summary(
    agent_id: UUID,
    req: PatchCapabilitySummaryRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AgentCapabilityService = Depends(get_agent_capability_service),
):
    return success_json(
        svc.patch_agent_capability_summary(
            session,
            agent_id,
            current_user,
            manual_overrides=req.manual_overrides,
        )
    )

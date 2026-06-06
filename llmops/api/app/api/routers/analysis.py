from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.analysis import GetAppAgentRuntimeAnalysisRequest
from app.services.analysis_service import AnalysisService
from app.shared.response import success_json

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/app/{app_id}")
def get_app_analysis(
    app_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AnalysisService = Depends(get_analysis_service),
):
    return success_json(svc.get_app_analysis(session, app_id, current_user))


@router.get("/app/{app_id}/agent-runtime")
def get_app_agent_runtime_analysis(
    app_id: UUID,
    req: GetAppAgentRuntimeAnalysisRequest = Depends(),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AnalysisService = Depends(get_analysis_service),
):
    return success_json(
        svc.get_app_agent_runtime_analysis(
            session,
            app_id,
            current_user,
            from_ts=req.from_ts,
            to_ts=req.to_ts,
            status=req.status,
            user_id=req.user_id,
            router_agent_id=req.router_agent_id,
            worker_agent_id=req.worker_agent_id,
            group_by=req.group_by,
        )
    )

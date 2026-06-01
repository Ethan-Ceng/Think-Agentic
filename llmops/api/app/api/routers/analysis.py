from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_service, get_current_account, get_db_session
from app.models.account import Account
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

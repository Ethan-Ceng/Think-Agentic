from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_api_key_account, get_db_session, get_openapi_service
from app.models.account import Account
from app.schemas.openapi import OpenAPIChatRequest
from app.services.openapi_service import OpenAPIService
from app.shared.response import compact_generate_response

router = APIRouter(prefix="/openapi", tags=["openapi"])


@router.post("/chat")
def openapi_chat(
    req: OpenAPIChatRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_api_key_account),
    svc: OpenAPIService = Depends(get_openapi_service),
):
    return compact_generate_response(svc.chat(session, req, current_user))

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_account, get_db_session, get_web_app_service
from app.models.account import Account
from app.schemas.web_app import GetWebAppConversationsRequest, WebAppChatRequest, WebAppConversationResponse
from app.services.web_app_service import WebAppService
from app.shared.response import compact_generate_response, success_json, success_message

router = APIRouter(prefix="/web-apps", tags=["web_app"])


@router.get("/{token}")
def get_web_app(
    token: str,
    session: Session = Depends(get_db_session),
    _: Account = Depends(get_current_account),
    svc: WebAppService = Depends(get_web_app_service),
):
    return success_json(svc.get_web_app_info(session, token))


@router.post("/{token}/chat")
def web_app_chat(
    token: str,
    req: WebAppChatRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WebAppService = Depends(get_web_app_service),
):
    return compact_generate_response(svc.web_app_chat(session, token, req, current_user))


@router.post("/{token}/stop/{task_id}")
def stop_web_app_chat(
    token: str,
    task_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WebAppService = Depends(get_web_app_service),
):
    svc.stop_web_app_chat(session, token, task_id, current_user)
    return success_message("Stop web app chat success")


@router.get("/{token}/conversations")
def get_conversations(
    token: str,
    req: GetWebAppConversationsRequest = Depends(),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: WebAppService = Depends(get_web_app_service),
):
    conversations = svc.get_conversations(session, token, req.is_pinned, current_user)
    return success_json([WebAppConversationResponse.from_conversation(item).model_dump() for item in conversations])

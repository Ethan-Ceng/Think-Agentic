from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_web_app_service
from app.schemas.ai import GenerateSuggestedQuestionsRequest
from app.schemas.conversation import MessageResponse, UpdateConversationIsPinnedRequest, UpdateConversationNameRequest
from app.schemas.web_app import GetWebAppConversationsRequest, WebAppChatRequest, WebAppConversationResponse
from app.services.web_app_service import WebAppService
from app.shared.response import compact_generate_response, success_json, success_message

router = APIRouter(prefix="/web-apps", tags=["web_app"])
WEB_APP_END_USER_COOKIE_PREFIX = "llmops_web_app_end_user_"
WEB_APP_END_USER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


@router.get("/{token}")
def get_web_app(
    token: str,
    request: Request,
    session: Session = Depends(get_db_session),
    svc: WebAppService = Depends(get_web_app_service),
):
    end_user, data = svc.get_web_app_info(session, token, _get_end_user_id(request, token))
    response = success_json(data)
    _set_end_user_cookie(response, token, end_user.id)
    return response


@router.post("/{token}/suggested-questions")
def generate_suggested_questions(
    token: str,
    req: GenerateSuggestedQuestionsRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    svc: WebAppService = Depends(get_web_app_service),
):
    end_user, questions = svc.generate_suggested_questions(session, token, req.message_id, _get_end_user_id(request, token))
    response = success_json(questions)
    _set_end_user_cookie(response, token, end_user.id)
    return response


@router.get("/{token}/conversations/{conversation_id}/messages")
def get_conversation_messages(
    token: str,
    conversation_id: UUID,
    request: Request,
    created_at: int = Query(default=0, ge=0),
    current_page: int = Query(default=1, ge=1, le=9999),
    page_size: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_db_session),
    svc: WebAppService = Depends(get_web_app_service),
):
    end_user, messages, total_record, total_page = svc.get_conversation_messages_with_page(
        session,
        token,
        conversation_id,
        _get_end_user_id(request, token),
        created_at,
        current_page,
        page_size,
    )
    response = success_json(
        {
            "list": [MessageResponse.from_message(message).model_dump() for message in messages],
            "paginator": {
                "total_page": total_page,
                "total_record": total_record,
                "current_page": current_page,
                "page_size": page_size,
            },
            "total_page": total_page,
            "total_record": total_record,
            "current_page": current_page,
            "page_size": page_size,
        }
    )
    _set_end_user_cookie(response, token, end_user.id)
    return response


@router.delete("/{token}/conversations/{conversation_id}")
def delete_conversation(
    token: str,
    conversation_id: UUID,
    request: Request,
    session: Session = Depends(get_db_session),
    svc: WebAppService = Depends(get_web_app_service),
):
    svc.delete_conversation(session, token, conversation_id, _get_end_user_id(request, token))
    return success_message("Delete conversation success")


@router.put("/{token}/conversations/{conversation_id}/is-pinned")
def update_conversation_is_pinned(
    token: str,
    conversation_id: UUID,
    req: UpdateConversationIsPinnedRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    svc: WebAppService = Depends(get_web_app_service),
):
    svc.update_conversation_is_pinned(
        session,
        token,
        conversation_id,
        _get_end_user_id(request, token),
        req.is_pinned,
    )
    return success_message("Update conversation pinned state success")


@router.put("/{token}/conversations/{conversation_id}/name")
def update_conversation_name(
    token: str,
    conversation_id: UUID,
    req: UpdateConversationNameRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    svc: WebAppService = Depends(get_web_app_service),
):
    svc.update_conversation_name(
        session,
        token,
        conversation_id,
        _get_end_user_id(request, token),
        req.name,
    )
    return success_message("Update conversation name success")


@router.post("/{token}/chat")
def web_app_chat(
    token: str,
    req: WebAppChatRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    svc: WebAppService = Depends(get_web_app_service),
):
    end_user, stream = svc.web_app_chat(session, token, req, _get_end_user_id(request, token))
    response = compact_generate_response(stream)
    _set_end_user_cookie(response, token, end_user.id)
    return response


@router.post("/{token}/stop/{task_id}")
def stop_web_app_chat(
    token: str,
    task_id: UUID,
    request: Request,
    session: Session = Depends(get_db_session),
    svc: WebAppService = Depends(get_web_app_service),
):
    svc.stop_web_app_chat(session, token, task_id, _get_end_user_id(request, token))
    return success_message("Stop web app chat success")


@router.get("/{token}/conversations")
def get_conversations(
    token: str,
    request: Request,
    req: GetWebAppConversationsRequest = Depends(),
    session: Session = Depends(get_db_session),
    svc: WebAppService = Depends(get_web_app_service),
):
    end_user, conversations = svc.get_conversations(session, token, req.is_pinned, _get_end_user_id(request, token))
    response = success_json([WebAppConversationResponse.from_conversation(item).model_dump() for item in conversations])
    _set_end_user_cookie(response, token, end_user.id)
    return response


def _cookie_name(token: str) -> str:
    return f"{WEB_APP_END_USER_COOKIE_PREFIX}{token}"


def _get_end_user_id(request: Request, token: str) -> UUID | None:
    value = request.cookies.get(_cookie_name(token))
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _set_end_user_cookie(response, token: str, end_user_id: UUID) -> None:
    response.set_cookie(
        key=_cookie_name(token),
        value=str(end_user_id),
        max_age=WEB_APP_END_USER_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )

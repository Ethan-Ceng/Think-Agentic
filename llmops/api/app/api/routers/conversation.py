from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_conversation_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.conversation import MessageResponse, UpdateConversationIsPinnedRequest, UpdateConversationNameRequest
from app.services.conversation_service import ConversationService
from app.shared.response import success_json, success_message

router = APIRouter(prefix="/conversations", tags=["conversation"])


@router.get("/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: UUID,
    created_at: int = Query(default=0, ge=0),
    current_page: int = Query(default=1, ge=1, le=9999),
    page_size: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ConversationService = Depends(get_conversation_service),
):
    messages, total_record, total_page = svc.get_conversation_messages_with_page(
        session,
        conversation_id,
        current_user,
        created_at,
        current_page,
        page_size,
    )
    return success_json(
        {
            "list": [MessageResponse.from_message(message).model_dump() for message in messages],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": current_page,
            "page_size": page_size,
        }
    )


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ConversationService = Depends(get_conversation_service),
):
    svc.delete_conversation(session, conversation_id, current_user)
    return success_message("Delete conversation success")


@router.delete("/{conversation_id}/messages/{message_id}")
def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ConversationService = Depends(get_conversation_service),
):
    svc.delete_message(session, conversation_id, message_id, current_user)
    return success_message("Delete conversation message success")


@router.get("/{conversation_id}/name")
def get_conversation_name(
    conversation_id: UUID,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ConversationService = Depends(get_conversation_service),
):
    conversation = svc.get_conversation(session, conversation_id, current_user)
    return success_json({"name": conversation.name})


@router.put("/{conversation_id}/name")
def update_conversation_name(
    conversation_id: UUID,
    req: UpdateConversationNameRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ConversationService = Depends(get_conversation_service),
):
    svc.update_conversation(session, conversation_id, current_user, name=req.name)
    return success_message("Update conversation name success")


@router.put("/{conversation_id}/is-pinned")
def update_conversation_is_pinned(
    conversation_id: UUID,
    req: UpdateConversationIsPinnedRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: ConversationService = Depends(get_conversation_service),
):
    svc.update_conversation(session, conversation_id, current_user, is_pinned=req.is_pinned)
    return success_message("Update conversation pinned state success")


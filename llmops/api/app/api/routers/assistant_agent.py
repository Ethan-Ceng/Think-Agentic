from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_assistant_agent_service, get_current_account, get_db_session
from app.models.account import Account
from app.schemas.assistant_agent import (
    AssistantAgentChatRequest,
    AssistantAgentMessageResponse,
    GetAssistantAgentMessagesWithPageRequest,
)
from app.services.assistant_agent_service import AssistantAgentService
from app.shared.response import compact_generate_response, success_json, success_message

router = APIRouter(prefix="/assistant-agent", tags=["assistant_agent"])


@router.post("/chat")
def assistant_agent_chat(
    req: AssistantAgentChatRequest,
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AssistantAgentService = Depends(get_assistant_agent_service),
):
    return compact_generate_response(svc.chat(session, req, current_user))


@router.post("/stop/{task_id}")
def stop_assistant_agent_chat(
    task_id: UUID,
    current_user: Account = Depends(get_current_account),
    svc: AssistantAgentService = Depends(get_assistant_agent_service),
):
    svc.stop_chat(task_id, current_user)
    return success_message("Stop assistant agent chat success")


@router.get("/messages")
def get_assistant_agent_messages(
    req: GetAssistantAgentMessagesWithPageRequest = Depends(),
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AssistantAgentService = Depends(get_assistant_agent_service),
):
    messages, total_record, total_page = svc.get_conversation_messages_with_page(session, req, current_user)
    return success_json(
        {
            "list": [AssistantAgentMessageResponse.from_message(message).model_dump() for message in messages],
            "total_page": total_page,
            "total_record": total_record,
            "current_page": req.page,
            "page_size": req.page_size,
        }
    )


@router.delete("/conversation")
def delete_assistant_agent_conversation(
    session: Session = Depends(get_db_session),
    current_user: Account = Depends(get_current_account),
    svc: AssistantAgentService = Depends(get_assistant_agent_service),
):
    svc.delete_conversation(session, current_user)
    return success_message("Delete assistant agent conversation success")

import math
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session, selectinload

from app.core.conversation import MessageStatus
from app.core.exceptions import NotFoundException
from app.models.account import Account
from app.models.conversation import Conversation, Message
from app.services.base_service import BaseService


@dataclass
class ConversationService(BaseService):
    def get_conversation(self, session: Session, conversation_id: UUID, account: Account) -> Conversation:
        conversation = self.get(session, Conversation, conversation_id)
        if conversation is None or conversation.created_by != account.id or conversation.is_deleted:
            raise NotFoundException("Conversation does not exist")
        return conversation

    def get_message(self, session: Session, message_id: UUID, account: Account) -> Message:
        message = self.get(session, Message, message_id)
        if message is None or message.created_by != account.id or message.is_deleted:
            raise NotFoundException("Message does not exist")
        return message

    def get_conversation_messages_with_page(
        self,
        session: Session,
        conversation_id: UUID,
        account: Account,
        created_at: int = 0,
        current_page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Message], int, int]:
        conversation = self.get_conversation(session, conversation_id, account)
        query = (
            session.query(Message)
            .options(selectinload(Message.agent_thoughts))
            .filter(
                Message.conversation_id == conversation.id,
                Message.status.in_([MessageStatus.STOP.value, MessageStatus.NORMAL.value]),
                Message.answer != "",
                Message.is_deleted.is_(False),
            )
        )
        if created_at:
            query = query.filter(Message.created_at <= datetime.fromtimestamp(created_at))

        total_record = query.count()
        total_page = math.ceil(total_record / page_size) if total_record else 0
        messages = (
            query.order_by(desc(Message.created_at))
            .offset((current_page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return list(messages), total_record, total_page

    def delete_conversation(self, session: Session, conversation_id: UUID, account: Account) -> Conversation:
        conversation = self.get_conversation(session, conversation_id, account)
        return self.update(session, conversation, is_deleted=True)

    def delete_message(self, session: Session, conversation_id: UUID, message_id: UUID, account: Account) -> Message:
        conversation = self.get_conversation(session, conversation_id, account)
        message = self.get_message(session, message_id, account)
        if conversation.id != message.conversation_id:
            raise NotFoundException("Message does not exist in this conversation")
        return self.update(session, message, is_deleted=True)

    def update_conversation(
        self,
        session: Session,
        conversation_id: UUID,
        account: Account,
        **kwargs,
    ) -> Conversation:
        conversation = self.get_conversation(session, conversation_id, account)
        return self.update(session, conversation, **kwargs)


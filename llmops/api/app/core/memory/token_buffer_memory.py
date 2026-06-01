from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.conversation import MessageStatus
from app.models.conversation import Message


@dataclass
class TokenBufferMemory:
    session: Session
    conversation_id: UUID

    def get_history_messages(self, message_limit: int = 10) -> list[dict[str, str]]:
        if message_limit <= 0:
            return []

        messages = (
            self.session.query(Message)
            .filter(
                Message.conversation_id == self.conversation_id,
                Message.answer != "",
                Message.is_deleted.is_(False),
                Message.status.in_(
                    [
                        MessageStatus.NORMAL.value,
                        MessageStatus.STOP.value,
                        MessageStatus.TIMEOUT.value,
                    ]
                ),
            )
            .order_by(desc(Message.created_at))
            .limit(message_limit)
            .all()
        )

        history: list[dict[str, str]] = []
        for message in reversed(messages):
            history.append({"role": "user", "content": message.query})
            history.append({"role": "assistant", "content": message.answer})
        return history

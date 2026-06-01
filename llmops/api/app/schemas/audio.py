from uuid import UUID

from pydantic import BaseModel


class MessageToAudioRequest(BaseModel):
    message_id: UUID

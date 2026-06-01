from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.upload_file import UploadFile


def datetime_to_timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    return int(value.timestamp())


class UploadFileResponse(BaseModel):
    id: UUID
    account_id: UUID
    name: str
    key: str
    size: int
    extension: str
    mime_type: str
    created_at: int = 0

    @classmethod
    def from_upload_file(cls, upload_file: UploadFile) -> "UploadFileResponse":
        return cls(
            id=upload_file.id,
            account_id=upload_file.account_id,
            name=upload_file.name,
            key=upload_file.key,
            size=upload_file.size,
            extension=upload_file.extension,
            mime_type=upload_file.mime_type,
            created_at=datetime_to_timestamp(upload_file.created_at),
        )


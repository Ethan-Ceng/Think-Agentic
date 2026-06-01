from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.dataset import ProcessType
from app.models.dataset import Document


def datetime_to_timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    return int(value.timestamp())


class CreateDocumentsRequest(BaseModel):
    upload_file_ids: list[UUID]
    process_type: str = Field(default=ProcessType.AUTOMATIC.value)
    rule: dict[str, Any] | None = None


class UpdateDocumentNameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class UpdateDocumentEnabledRequest(BaseModel):
    enabled: bool


class DocumentResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    name: str = ""
    position: int = 0
    character_count: int = 0
    token_count: int = 0
    hit_count: int = 0
    enabled: bool = True
    disabled_at: int | None = None
    status: str = ""
    error: str | None = None
    updated_at: int = 0
    created_at: int = 0

    @classmethod
    def from_document(cls, document: Document, hit_count: int = 0) -> "DocumentResponse":
        return cls(
            id=document.id,
            dataset_id=document.dataset_id,
            name=document.name or "",
            position=document.position or 0,
            character_count=document.character_count or 0,
            token_count=document.token_count or 0,
            hit_count=hit_count,
            enabled=document.enabled if document.enabled is not None else True,
            disabled_at=datetime_to_timestamp(document.disabled_at),
            status=document.status or "",
            error=document.error,
            updated_at=datetime_to_timestamp(document.updated_at),
            created_at=datetime_to_timestamp(document.created_at),
        )


class CreateDocumentsResponse(BaseModel):
    documents: list[DocumentResponse]
    batch: str = ""


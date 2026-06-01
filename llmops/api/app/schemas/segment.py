from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.dataset import Segment


def datetime_to_timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    return int(value.timestamp())


class CreateSegmentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    keywords: list[str] = Field(default_factory=list)


class UpdateSegmentRequest(CreateSegmentRequest):
    pass


class UpdateSegmentEnabledRequest(BaseModel):
    enabled: bool


class SegmentResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    document_id: UUID
    position: int = 0
    content: str = ""
    character_count: int = 0
    token_count: int = 0
    keywords: list[str] = Field(default_factory=list)
    hash: str = ""
    hit_count: int = 0
    enabled: bool = True
    disabled_at: int | None = None
    status: str = ""
    error: str | None = None
    updated_at: int = 0
    created_at: int = 0

    @classmethod
    def from_segment(cls, segment: Segment) -> "SegmentResponse":
        return cls(
            id=segment.id,
            dataset_id=segment.dataset_id,
            document_id=segment.document_id,
            position=segment.position or 0,
            content=segment.content or "",
            character_count=segment.character_count or 0,
            token_count=segment.token_count or 0,
            keywords=segment.keywords or [],
            hash=segment.hash or "",
            hit_count=segment.hit_count or 0,
            enabled=segment.enabled if segment.enabled is not None else True,
            disabled_at=datetime_to_timestamp(segment.disabled_at),
            status=segment.status or "",
            error=segment.error,
            updated_at=datetime_to_timestamp(segment.updated_at),
            created_at=datetime_to_timestamp(segment.created_at),
        )


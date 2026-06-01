from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.core.dataset import RetrievalStrategy
from app.models.dataset import Dataset, DatasetQuery


def datetime_to_timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    return int(value.timestamp())


@dataclass
class DatasetStats:
    document_count: int = 0
    hit_count: int = 0
    related_app_count: int = 0
    character_count: int = 0


class CreateDatasetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    icon: HttpUrl
    description: str = Field(default="", max_length=2000)


class UpdateDatasetRequest(CreateDatasetRequest):
    pass


class HitRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    retrieval_strategy: RetrievalStrategy
    k: int = Field(..., ge=1, le=10)
    score: float = Field(default=0.0, ge=0.0, le=0.99)


class DatasetResponse(BaseModel):
    id: UUID
    name: str = ""
    icon: str = ""
    description: str = ""
    document_count: int = 0
    hit_count: int = 0
    related_app_count: int = 0
    character_count: int = 0
    updated_at: int = 0
    created_at: int = 0

    @classmethod
    def from_dataset(cls, dataset: Dataset, stats: DatasetStats | None = None) -> "DatasetResponse":
        stats = stats or DatasetStats()
        return cls(
            id=dataset.id,
            name=dataset.name or "",
            icon=dataset.icon or "",
            description=dataset.description or "",
            document_count=stats.document_count,
            hit_count=stats.hit_count,
            related_app_count=stats.related_app_count,
            character_count=stats.character_count,
            updated_at=datetime_to_timestamp(dataset.updated_at),
            created_at=datetime_to_timestamp(dataset.created_at),
        )


class DatasetQueryResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    query: str = ""
    source: str = ""
    created_at: int = 0

    @classmethod
    def from_query(cls, query: DatasetQuery) -> "DatasetQueryResponse":
        return cls(
            id=query.id,
            dataset_id=query.dataset_id,
            query=query.query or "",
            source=query.source or "",
            created_at=datetime_to_timestamp(query.created_at),
        )


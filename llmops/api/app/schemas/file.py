from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FileCreateFolderRequest(BaseModel):
    name: str
    parent_id: UUID | None = None


class FileUpdateRequest(BaseModel):
    name: str | None = None
    parent_id: UUID | None = None


class FileResponse(BaseModel):
    id: UUID
    account_id: UUID
    parent_id: UUID | None = None
    type: str
    name: str
    extension: str = ""
    mime_type: str = ""
    size: int = 0
    storage_provider: str = "local"
    file_path: str = ""
    hash: str = ""
    source: str = "upload"
    status: str = "available"
    metadata: dict[str, Any] = Field(default_factory=dict)
    url: str = ""
    download_url: str = ""
    preview_url: str = ""
    created_at: int = 0
    updated_at: int = 0

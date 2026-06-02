from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SettingUpsertRequest(BaseModel):
    value: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SettingResponse(BaseModel):
    id: UUID
    account_id: UUID
    category: str
    key: str
    value: dict[str, Any]
    enabled: bool
    created_at: int = 0
    updated_at: int = 0


class SettingsResponse(BaseModel):
    data: list[SettingResponse]


class StorageTestRequest(BaseModel):
    provider: str
    value: dict[str, Any] = Field(default_factory=dict)

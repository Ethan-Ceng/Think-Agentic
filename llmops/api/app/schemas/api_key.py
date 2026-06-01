from uuid import UUID

from pydantic import BaseModel, Field

from app.models.api_key import ApiKey


class CreateApiKeyRequest(BaseModel):
    is_active: bool = True
    remark: str = Field(default="", max_length=100)


class UpdateApiKeyRequest(BaseModel):
    is_active: bool = True
    remark: str = Field(default="", max_length=100)


class UpdateApiKeyIsActiveRequest(BaseModel):
    is_active: bool


class ApiKeyResponse(BaseModel):
    id: UUID
    api_key: str
    is_active: bool
    remark: str = ""
    updated_at: int = 0
    created_at: int = 0

    @classmethod
    def from_api_key(cls, api_key: ApiKey) -> "ApiKeyResponse":
        return cls(
            id=api_key.id,
            api_key=api_key.api_key,
            is_active=api_key.is_active,
            remark=api_key.remark or "",
            updated_at=int(api_key.updated_at.timestamp()) if api_key.updated_at else 0,
            created_at=int(api_key.created_at.timestamp()) if api_key.created_at else 0,
        )


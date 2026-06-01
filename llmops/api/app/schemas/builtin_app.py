from uuid import UUID

from pydantic import BaseModel, Field


class CategoryResponse(BaseModel):
    category: str
    name: str


class BuiltinAppModelConfig(BaseModel):
    provider: str
    model: str


class BuiltinAppResponse(BaseModel):
    id: str
    category: str
    name: str
    icon: str
    description: str
    app_model_config: BuiltinAppModelConfig = Field(..., alias="model_config")
    created_at: int = 0


class AddBuiltinAppRequest(BaseModel):
    builtin_app_id: UUID = Field(...)

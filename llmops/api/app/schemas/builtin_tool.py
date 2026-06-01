from pydantic import BaseModel, Field


class BuiltinToolDetail(BaseModel):
    name: str
    label: str
    description: str
    params: list[dict] = Field(default_factory=list)
    inputs: list[dict] = Field(default_factory=list)


class BuiltinToolProvider(BaseModel):
    name: str
    label: str
    description: str
    icon: str
    background: str
    category: str
    created_at: int = 0
    tools: list[BuiltinToolDetail] = Field(default_factory=list)


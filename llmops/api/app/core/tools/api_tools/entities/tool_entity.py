from pydantic import BaseModel, Field


class ToolEntity(BaseModel):
    id: str = Field(default="")
    name: str = Field(default="")
    url: str = Field(default="")
    method: str = Field(default="get")
    description: str = Field(default="")
    headers: list[dict] = Field(default_factory=list)
    parameters: list[dict] = Field(default_factory=list)


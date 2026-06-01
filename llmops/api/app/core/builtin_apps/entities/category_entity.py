from pydantic import BaseModel, Field


class CategoryEntity(BaseModel):
    category: str = Field(default="")
    name: str = Field(default="")

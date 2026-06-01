from pydantic import BaseModel, field_validator

from app.core.exceptions import FailException


class CategoryEntity(BaseModel):
    category: str
    name: str
    icon: str

    @field_validator("icon")
    @classmethod
    def check_icon_extension(cls, value: str) -> str:
        if not value.endswith(".svg"):
            raise FailException("Category icon must be an SVG file")
        return value


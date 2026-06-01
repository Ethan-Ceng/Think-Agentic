import re

from pydantic import BaseModel, Field, field_validator

from app.shared.password import password_pattern


class PasswordLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=16)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.match(password_pattern, value):
            raise ValueError("Password must contain at least one letter and one number, length 8-16")
        return value


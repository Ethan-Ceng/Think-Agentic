import re
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.account import Account
from app.shared.password import password_pattern


class GetCurrentUserResponse(BaseModel):
    id: UUID
    name: str = ""
    email: str = ""
    avatar: str = ""
    last_login_at: int = 0
    last_login_ip: str = ""
    created_at: int = 0

    @classmethod
    def from_account(cls, account: Account) -> "GetCurrentUserResponse":
        return cls(
            id=account.id,
            name=account.name or "",
            email=account.email or "",
            avatar=account.avatar or "",
            last_login_at=int(account.last_login_at.timestamp()) if account.last_login_at else 0,
            last_login_ip=account.last_login_ip or "",
            created_at=int(account.created_at.timestamp()) if account.created_at else 0,
        )


class UpdatePasswordRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=16)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.match(password_pattern, value):
            raise ValueError("Password must contain at least one letter and one number, length 8-16")
        return value


class UpdateNameRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=30)


class UpdateAvatarRequest(BaseModel):
    avatar: HttpUrl


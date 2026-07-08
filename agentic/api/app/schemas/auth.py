#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Auth request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.entities.user import User
from app.core.security import normalize_email, validate_password


class UserResponse(BaseModel):
    id: str
    email: str
    name: str = ""
    avatar: str = ""
    status: str = "active"
    last_login_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            avatar=user.avatar,
            status=user.status,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
        )


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=8, max_length=16)
    name: str | None = Field(default=None, max_length=255)
    avatar: str | None = Field(default="", max_length=512)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized:
            raise ValueError("Invalid email")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password_value(cls, value: str) -> str:
        if not validate_password(value):
            raise ValueError("Password must contain at least one letter and one number, length 8-16")
        return value


class PasswordLoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized:
            raise ValueError("Invalid email")
        return normalized


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Authentication service."""
from datetime import datetime

from app.core.config import get_settings
from app.core.entities.user import User
from app.core.security import (
    PASSWORD_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    normalize_email,
    verify_password,
)
from app.repositories.uow import IUnitOfWork
from app.schemas.auth import AuthResponse, UserResponse
from app.schemas.exceptions import BadRequestError, ForbiddenError, UnauthorizedError


class AuthService:
    """User registration and token authentication."""

    def __init__(self, uow_factory) -> None:
        self._uow_factory = uow_factory
        self._settings = get_settings()

    def _token_response(self, user: User) -> AuthResponse:
        token = create_access_token(
            user.id,
            self._settings.auth_secret_key,
            self._settings.auth_access_token_ttl_seconds,
        )
        return AuthResponse(access_token=token, user=UserResponse.from_user(user))

    async def register(self, email: str, password: str, name: str | None = None, avatar: str | None = "") -> AuthResponse:
        if not self._settings.auth_registration_enabled:
            raise ForbiddenError("注册已关闭")

        normalized_email = normalize_email(email)
        password_hash, password_salt = hash_password(password)
        display_name = (name or normalized_email.split("@", 1)[0]).strip()

        uow: IUnitOfWork = self._uow_factory()
        async with uow:
            existing = await uow.user.get_by_email(normalized_email)
            if existing:
                raise BadRequestError("该邮箱已注册")

            user = User(
                email=normalized_email,
                name=display_name,
                avatar=(avatar or "").strip(),
                password_hash=password_hash,
                password_salt=password_salt,
                password_algorithm=PASSWORD_ALGORITHM,
                status="active",
                last_login_at=datetime.now(),
            )
            await uow.user.save(user)

        return self._token_response(user)

    async def password_login(self, email: str, password: str) -> AuthResponse:
        normalized_email = normalize_email(email)

        uow: IUnitOfWork = self._uow_factory()
        async with uow:
            user = await uow.user.get_by_email(normalized_email)
            if not user or not verify_password(password, user.password_hash, user.password_salt):
                raise UnauthorizedError("邮箱或密码错误")
            if user.status != "active":
                raise ForbiddenError("用户已被禁用")

            user.last_login_at = datetime.now()
            await uow.user.save(user)

        return self._token_response(user)

    async def get_user_from_token(self, token: str) -> User:
        payload = decode_access_token(token, self._settings.auth_secret_key)
        if not payload or not payload.get("sub"):
            raise UnauthorizedError("登录已过期，请重新登录")

        uow: IUnitOfWork = self._uow_factory()
        async with uow:
            user = await uow.user.get_by_id(str(payload["sub"]))
        if not user:
            raise UnauthorizedError("登录用户不存在")
        if user.status != "active":
            raise ForbiddenError("用户已被禁用")
        return user

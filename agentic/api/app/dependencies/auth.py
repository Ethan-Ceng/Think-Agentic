#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Authentication dependencies."""
from fastapi import Depends, Header

from app.core.entities.user import User
from app.dependencies.services import get_auth_service
from app.schemas.exceptions import UnauthorizedError
from app.services.auth_service import AuthService


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise UnauthorizedError("请先登录")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("无效的认证信息")
    return token.strip()


async def get_current_user(
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    token = extract_bearer_token(authorization)
    return await auth_service.get_user_from_token(token)


async def get_user_from_token(token: str, auth_service: AuthService | None = None) -> User:
    service = auth_service or get_auth_service()
    return await service.get_user_from_token(token)

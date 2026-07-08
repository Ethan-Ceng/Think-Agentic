#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Authentication routes."""
from fastapi import APIRouter, Depends

from app.core.entities.user import User
from app.dependencies import get_current_user
from app.dependencies.services import get_auth_service
from app.schemas import Response
from app.schemas.auth import AuthResponse, PasswordLoginRequest, RegisterRequest, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", summary="注册用户")
async def register(
    request: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> Response[AuthResponse]:
    return Response.success(
        msg="注册成功",
        data=await auth_service.register(
            email=request.email,
            password=request.password,
            name=request.name,
            avatar=request.avatar,
        ),
    )


@router.post("/password-login", summary="密码登录")
async def password_login(
    request: PasswordLoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> Response[AuthResponse]:
    return Response.success(
        msg="登录成功",
        data=await auth_service.password_login(request.email, request.password),
    )


@router.post("/logout", summary="退出登录")
async def logout(_: User = Depends(get_current_user)) -> Response[dict]:
    return Response.success(msg="退出成功")


@router.get("/me", summary="当前用户")
async def me(current_user: User = Depends(get_current_user)) -> Response[UserResponse]:
    return Response.success(data=UserResponse.from_user(current_user))

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Controllers package - API routes
"""
from fastapi import APIRouter

from .session import router as session_router
from .auth import router as auth_router
from .health import router as health_router
from .app_config import router as app_config_router
from .file import router as file_router
from .tools import router as tools_router
from .runs import router as runs_router

# 主路由
router = APIRouter()

# 注册子路由
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(session_router)
router.include_router(app_config_router)
router.include_router(file_router)
router.include_router(tools_router)
router.include_router(runs_router)

__all__ = ["router"]

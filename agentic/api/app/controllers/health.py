#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Health check controller
"""
from fastapi import APIRouter

router = APIRouter(prefix="/status", tags=["健康检查"])


@router.get("", summary="健康检查")
async def health_check():
    """
    健康检查接口

    Returns:
        dict: 服务状态
    """
    return {
        "status": "ok",
        "service": "MoocManus",
        "version": "2.0.0",
    }

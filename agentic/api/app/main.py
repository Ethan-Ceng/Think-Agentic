#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主应用入口 - 重构后的简化版本
"""
import logging
import asyncio
from contextlib import suppress
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.extensions import get_db, get_redis
from app.dependencies.infrastructure import get_file_storage
from app.controllers import router
from app.schemas.exceptions import AppException
from app.core.config import get_settings

# 加载配置
settings = get_settings()

# 配置日志
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _purge_deleted_files() -> None:
    while True:
        await asyncio.sleep(settings.file_purge_interval_seconds)
        try:
            purged = await get_file_storage().purge_expired()
            if purged:
                logger.info("Purged %s expired files", purged)
        except Exception:
            logger.exception("Deleted file purge failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("MoocManus 正在启动...")

    # 运行数据库迁移
    if settings.run_migrations_on_startup:
        try:
            alembic_cfg = Config("alembic.ini")
            command.upgrade(alembic_cfg, "head")
            logger.info("数据库迁移完成")
        except Exception as e:
            logger.error(f"数据库迁移失败: {e}")

    # 初始化扩展
    await get_db().init()
    await get_redis().init()
    purge_task = asyncio.create_task(_purge_deleted_files())

    logger.info("MoocManus 启动完成")

    try:
        yield
    finally:
        logger.info("MoocManus 正在关闭...")
        purge_task.cancel()
        with suppress(asyncio.CancelledError):
            await purge_task
        await get_db().shutdown()
        await get_redis().shutdown()
        logger.info("MoocManus 关闭完成")


# 创建FastAPI应用
app = FastAPI(
    title="MoocManus",
    description="通用AI Agent系统 - 重构版（服务层架构）",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router, prefix="/api")


# 全局异常处理器
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """处理自定义应用异常"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "msg": exc.msg,
            "data": exc.data,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

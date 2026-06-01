#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database extension - SQLAlchemy async session management
"""
import logging
from functools import lru_cache
from typing import Optional, AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Database:
    """数据库管理类 - 简化版Postgres"""

    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._settings = get_settings()

    async def init(self) -> None:
        """初始化数据库连接"""
        if self._engine is not None:
            logger.warning("数据库引擎已初始化，无需重复操作")
            return

        try:
            logger.info("正在初始化数据库连接...")
            self._engine = create_async_engine(
                self._settings.sqlalchemy_database_uri,
                echo=self._settings.env == "development",
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
            )

            self._session_factory = async_sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # 安装PostgreSQL扩展
            async with self._engine.begin() as conn:
                await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
                logger.info("成功连接数据库并安装uuid-ossp扩展")

        except Exception as e:
            logger.error(f"连接数据库失败: {str(e)}")
            raise

    async def shutdown(self) -> None:
        """关闭数据库连接"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("成功关闭数据库连接")

        # 清除缓存
        get_db.cache_clear()

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """获取会话工厂"""
        if self._session_factory is None:
            raise RuntimeError("数据库未初始化，请先调用init()")
        return self._session_factory


@lru_cache()
def get_db() -> Database:
    """获取数据库实例（单例）"""
    return Database()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI依赖项：获取数据库会话

    用法：
        @router.get("/sessions")
        async def get_sessions(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    db = get_db()
    session_factory = db.session_factory

    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

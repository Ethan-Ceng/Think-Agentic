#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Redis extension - Redis async client management
"""
import logging
from functools import lru_cache
from typing import Optional

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis客户端管理类"""

    def __init__(self):
        self._client: Optional[Redis] = None
        self._settings = get_settings()

    async def init(self) -> None:
        """初始化Redis客户端"""
        if self._client:
            logger.warning("Redis客户端已初始化，无需重复操作")
            return

        try:
            logger.info("正在初始化Redis客户端...")
            self._client = Redis(
                host=self._settings.redis_host,
                port=self._settings.redis_port,
                db=self._settings.redis_db,
                password=self._settings.redis_password,
                decode_responses=True,
            )

            # 测试连接
            await self._client.ping()
            logger.info("Redis客户端初始化成功")
        except Exception as e:
            logger.error(f"初始化Redis客户端失败: {str(e)}")
            raise

    async def shutdown(self) -> None:
        """关闭Redis客户端"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("Redis客户端成功关闭")

        # 清除缓存
        get_redis.cache_clear()

    @property
    def client(self) -> Redis:
        """获取Redis客户端"""
        if self._client is None:
            raise RuntimeError("Redis客户端未初始化，请先调用init()")
        return self._client


@lru_cache()
def get_redis() -> RedisClient:
    """获取Redis实例（单例）"""
    return RedisClient()

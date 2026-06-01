#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/5/20 1:30
@Author  : thezehui@gmail.com
@File    : redis_health_checker.py
"""
import logging

from app.core.health_checker.base import HealthChecker
from app.core.entities.health_status import HealthStatus
from app.extensions.redis import RedisClient

logger = logging.getLogger(__name__)


class RedisHealthChecker(HealthChecker):
    """Redis health checker."""

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis_client = redis_client

    async def check(self) -> HealthStatus:
        try:
            if await self._redis_client.client.ping():
                return HealthStatus(service="redis", status="ok")
            else:
                return HealthStatus(service="redis", status="error", details="Redis ping failed")
        except Exception as e:
            logger.error(f"Redis health check failed: {str(e)}")
            return HealthStatus(
                service="redis",
                status="error",
                details=str(e),
            )

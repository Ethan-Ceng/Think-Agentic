#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/5/20 1:25
@Author  : thezehui@gmail.com
@File    : postgres_health_checker.py
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.health_checker.base import HealthChecker
from app.core.entities.health_status import HealthStatus

logger = logging.getLogger(__name__)


class PostgresHealthChecker(HealthChecker):
    """Postgres health checker."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._db_session = db_session

    async def check(self) -> HealthStatus:
        """Run a simple query to check database availability."""
        try:
            await self._db_session.execute(text("SELECT 1"))
            return HealthStatus(service="postgres", status="ok")
        except Exception as e:
            logger.error(f"Postgres health check failed: {str(e)}")
            return HealthStatus(
                service="postgres",
                status="error",
                details=str(e),
            )

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database-backed Unit of Work.
"""
import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.uow import IUnitOfWork
from .db_file_repository import DBFileRepository
from .db_session_repository import DBSessionRepository
from .db_user_repository import DBUserRepository
from .db_config_repository import DBConfigRepository

logger = logging.getLogger(__name__)


class DBUnitOfWork(IUnitOfWork):
    """PostgreSQL Unit of Work implementation."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self.db_session: Optional[AsyncSession] = None

    async def commit(self):
        await self.db_session.commit()

    async def rollback(self):
        await self.db_session.rollback()

    async def __aenter__(self) -> "DBUnitOfWork":
        self.db_session = self.session_factory()
        self.file = DBFileRepository(db_session=self.db_session)
        self.session = DBSessionRepository(db_session=self.db_session)
        self.user = DBUserRepository(db_session=self.db_session)
        self.config = DBConfigRepository(db_session=self.db_session)
        return self

    @staticmethod
    def _log_finalize_error(task: asyncio.Task) -> None:
        if task.cancelled():
            logger.warning("UoW finalize task was cancelled; database connection may not be returned")
            return

        try:
            task.result()
        except Exception as e:
            logger.warning(f"UoW finalize task failed: {e}")

    async def _finalize(self, exc_type) -> None:
        if self.db_session is None:
            return

        try:
            if exc_type:
                await self.rollback()
            else:
                await self.commit()
        except Exception as e:
            logger.warning(f"UoW commit/rollback failed: {e}")
        finally:
            try:
                await self.db_session.close()
            finally:
                self.db_session = None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        finalize_task = asyncio.create_task(self._finalize(exc_type))
        try:
            await asyncio.shield(finalize_task)
        except asyncio.CancelledError:
            finalize_task.add_done_callback(self._log_finalize_error)
            logger.warning("UoW finalize was cancelled by caller; closing database session in background")
